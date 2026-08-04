"""FortiAI Proxy provider -- on-appliance LLM adapter.

Drives the agent loop through the on-appliance `fortinet-fortiai-proxy`
connector (`agent_chat_completions` operation). Non-streaming, one HTTP
call per round-trip, single sequential tool calls with flattened-text
round-trip. No external key, no egress.

Phase B of docs/plans/FORTIAI_PROXY_PROVIDER_PLAN.md.
"""
from __future__ import annotations

import json
import time
import uuid as _uuid
from typing import Any, AsyncIterator

import httpx

from . import approvals as _approvals
from ._loop_helpers import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    TriageDiscipline,
    latest_user_text,
    compile_errors as _compile_errors,
    extract_yaml_block as _extract_yaml_block,
)
from .provider import (
    ApprovalRequestEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from .tools import _resolve_tier as _tier_for, dispatch, anthropic_tools as _anthropic_tools


def _collapse_union_types(node: Any) -> Any:
    """Rewrite JSON-Schema union types to a single type, recursively.

    The gateway rejects ``{"type": ["integer", "null"]}`` outright -- the whole
    request 400s with ``-30000 "The request payload is invalid"``, naming
    nothing, so ONE nullable property poisons the entire tool payload. Plain
    ``{"type": "integer"}`` is accepted (live-verified on 8.0.0, both
    directions). Optionality is already carried by ``required``, so dropping
    the ``"null"`` member loses nothing the proxy can act on.

    Recurses through ``properties``/``items``/``$defs`` because a union nested
    inside an array's ``items`` fails exactly the same way as a top-level one.
    """
    if isinstance(node, list):
        return [_collapse_union_types(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: _collapse_union_types(v) for k, v in node.items()}
    t = out.get("type")
    if isinstance(t, list):
        # Prefer the first non-"null" member; a type list of only "null" is
        # degenerate, so fall back to "string" rather than emitting a list.
        concrete = [x for x in t if x != "null"]
        out["type"] = concrete[0] if concrete else "string"
    return out


def _normalize_tools_fortiai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate tool schemas into the fortiai-proxy shape: ``{name, description, schema}``.

    The connector advertises an intent tool-slice using the Anthropic shape
    (``{name, description, input_schema}``) regardless of the active provider.
    The proxy rejects both OpenAI's ``{type: function, function: {parameters}}``
    and Anthropic's ``{name, description, input_schema}`` -- it requires the
    plain ``schema`` key.  Already-correct shapes pass through untouched.

    Union types are collapsed here too -- see :func:`_collapse_union_types`.
    """
    out: list[dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        # OpenAI-wrapped tools have name inside function:
        if not name and t.get("type") == "function" and isinstance(t.get("function"), dict):
            name = t["function"].get("name")
        if not name:
            continue
        schema = (t.get("schema") or t.get("input_schema")
                  or t.get("parameters") or {"type": "object", "properties": {}})
        # If this is an OpenAI-wrapped tool, extract the inner schema
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            schema = (t["function"].get("parameters") or schema)
        out.append({
            "name": name,
            "description": t.get("description", ""),
            "schema": _collapse_union_types(schema),
        })
    return out


def _stringify(result: Any) -> str:
    """Convert a tool result to a compact text representation for the
    flattened-text round-trip."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


def _is_error_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    # Guard redirects and deferrals are steering, not errors (parity with
    # the Anthropic provider; tracker #60).
    if result.get("kind") in ("guard_redirect", "guard_defer"):
        return False
    return result.get("ok") is False or "error" in result


class FortiAIProxyProvider:
    """Non-streaming LLM provider for the on-appliance FortiAI proxy.

    Calls ``agent_chat_completions`` on the ``fortinet-fortiai-proxy``
    connector via ``POST /api/integration/execute/``.  No external API key
    or egress.  One HTTP round-trip per LLM turn.  Tool calls are singular
    (one per response) and return as flattened-text messages.
    """

    name = "fortiai-proxy"
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        approval_gateway: Any = None,
        max_output_tokens: int | None = None,
        client: Any = None,  # httpx.AsyncClient or compatible, for testing
    ):
        self.base_url = (base_url or "").rstrip("/")
        self._auth = api_key
        self.model = model or "fortiai-proxy"
        self.max_output_tokens = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        self._approval_gateway = approval_gateway
        self._client = client or httpx.AsyncClient(timeout=120.0)

    # -- resume ------------------------------------------------------------

    async def resume(
        self,
        *,
        suspended: "_approvals.SuspendedSession",
        decision: str,  # "approve" | "deny"
    ) -> AsyncIterator[Event]:
        """Resume a turn suspended on a pending tier-3+ approval.

        Re-dispatches the approved call (or synthesizes a denial), appends
        flattened-text tool result messages, and re-enters stream()."""
        if not _approvals.verify(suspended):
            yield ErrorEvent(
                message="Approval binding check failed -- the suspended action "
                        "could not be verified and was not executed. Re-issue "
                        "the request."
            )
            yield DoneEvent(stop_reason="approval_unverified")
            return

        if decision == "approve":
            resolved = dispatch(
                suspended.tool, {**suspended.args, "_approved": True},
                _internal=True,
            )
        else:
            resolved = {"ok": False, "code": "user_denied",
                        "reason": "User denied the action."}

        yield ToolResultEvent(call_id=suspended.tool_use_id, result=resolved)

        result_str = _stringify(resolved)

        # Build the rehydrated messages from snapshot + tool results.
        # history_snapshot is what stream() used (minus system).  The proxy
        # only accepts flat user/assistant/system messages, so we carry the
        # snapshot as-is and append the tool round-trip as text.
        carried: list[dict[str, Any]] = list(suspended.history_snapshot)
        carried.append(
            {"role": "assistant",
             "content": f"[called {suspended.tool}({json.dumps(suspended.args, default=str)})]"}
        )
        carried.append(
            {"role": "user",
             "content": f"Tool result: {suspended.tool} = {result_str}"}
        )
        # Remaining (superseded) tool calls also get flat-text placeholders
        for skipped in suspended.remaining_tool_calls:
            carried.append({
                "role": "assistant",
                "content": f"[called {skipped.name} -- superseded by approval]",
            })
            carried.append({
                "role": "user",
                "content": (
                    f"Tool result: {skipped.name} = "
                    f'{{"ok": false, "code": "superseded_by_approval"}}'
                ),
            })

        rehydrated = [Message(role="user", content=carried)]

        async for ev in self.stream(
            system=suspended.system,
            messages=rehydrated,
            tools=[],
            tags=suspended.tags,
        ):
            yield ev

    # -- stream -------------------------------------------------------------

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any = None,
        max_tool_turns: int | None = None,
    ) -> AsyncIterator[Event]:
        """Non-streaming agent loop via the on-appliance fortiai-proxy."""
        tags = tags or {}
        session_id = _uuid.uuid4().hex[:8]
        turn_idx = 0
        self_repair_turns = 0
        any_tools_run = False
        assessment_forced = False

        # Own the wire format: fall back to the full tool registry when
        # the caller passes nothing.  Translate to fortiai shape either way.
        tool_defs = _normalize_tools_fortiai(tools) if tools else _normalize_tools_fortiai(_anthropic_tools())

        allowed_names = {t.get("name") for t in tool_defs}

        # Triage discipline
        investigation_state = (
            getattr(case_state, "investigation", None)
            if case_state is not None else None
        )
        _authoring = "emit_action_card" not in allowed_names
        _discipline = TriageDiscipline(
            state=investigation_state,
            capabilities=(getattr(case_state, "capabilities", None)
                          if case_state is not None else None),
            authoring=_authoring,
            # The analyst's own words are the only reliable carrier of an
            # explicit containment order -- see `_detect_analyst_order`.
            user_text=latest_user_text(messages),
        )

        # Build initial history (flat messages the proxy understands).
        history: list[dict[str, Any]] = [
            {"role": "system", "content": system},
        ]
        for m in messages:
            if isinstance(m.content, str):
                history.append({"role": m.role, "content": m.content})
            else:
                # Internal turns carried as block lists (from resume).
                # Flatten: each block carries its own role.
                for block in m.content:
                    if isinstance(block, dict):
                        history.append(block)
                    else:
                        # Non-dict block (str, etc.) → wrap as user message
                        history.append({"role": "user", "content": str(block)})

        # P4 -- repeated-error guard
        failed_signatures: set[str] = set()

        def _call_signature(nm: str, ar: dict[str, Any]) -> str:
            try:
                return nm + "|" + json.dumps(ar, sort_keys=True, default=str)
            except Exception:
                return nm + "|" + repr(ar)

        def _guarded_dispatch(nm: str, ar: dict[str, Any]) -> Any:
            if nm not in allowed_names:
                return {
                    "ok": False,
                    "error": (
                        f"Tool '{nm}' is not available in this session: the "
                        f"current task intent does not permit it. Not executed."
                    ),
                }
            sig = _call_signature(nm, ar)
            if sig in failed_signatures:
                return {
                    "ok": False,
                    "repeated_call_guard": True,
                    "error": (
                        f"This exact call to `{nm}` already failed earlier this "
                        f"turn and was NOT re-run. Do not retry the identical "
                        f"arguments -- change the inputs or stop and report the "
                        f"blocker in your assessment."
                    ),
                }
            guard = _discipline.evaluate(nm, ar)
            if guard is not None:
                if guard.get("forbidden_pivot_guard") or guard.get("call_once_guard"):
                    failed_signatures.add(sig)
                return guard
            result = dispatch(nm, ar)
            _discipline.note_result(nm, ar, result)
            if _is_error_result(result):
                failed_signatures.add(sig)
            return result

        # Loop-scoped usage accumulators read by _emit_usage via closure.
        # Defaults so the helper is callable before the first round-trip.
        input_tok = 0
        output_tok = 0
        history_chars = 0
        tool_call_usage: list[ToolCallUsage] = []

        def _emit_usage(stop_reason: str, *, repair_delta: int = 0):
            return UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=input_tok, output_tokens=output_tok,
                cache_read=0, cache_write=0,
                history_chars=history_chars,
                stop_reason=stop_reason,
                self_repair_turn=self_repair_turns - repair_delta,
                tool_calls=tool_call_usage, tags=tags,
            )

        # Internal helper for a single proxy round-trip.
        async def _call_proxy(
            *, history: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
        ) -> tuple[str, str | None, dict[str, Any] | None, dict[str, int]]:
            """Call agent_chat_completions.

            Returns (content, tool_name, tool_args, usage) as raw values.
            content is None for tool-call turns. tool_name/tool_args are
            populated for tool-call turns. usage is a dict of token counts.
            On error, raises RuntimeError.
            """
            body = {
                "connector": "fortinet-fortiai-proxy",
                "operation": "agent_chat_completions",
                "params": {
                    "messages": history,
                    "tools": tool_defs,
                },
            }
            if self.model:
                body["params"]["model"] = self.model

            headers = {}
            if self._auth:
                headers["Authorization"] = f"Bearer {self._auth}"

            url = f"{self.base_url}/api/integration/execute/"
            resp = await self._client.post(url, json=body, headers=headers)

            if resp.status_code != 200:
                try:
                    err_data = resp.json()
                    err_body = err_data.get("message", str(err_data))[:600]
                except Exception:
                    err_body = resp.text[:600]
                raise RuntimeError(
                    f"FortiAI proxy returned HTTP {resp.status_code}: {err_body}"
                )

            data = resp.json()
            exec_status = data.get("status", "")
            if exec_status not in ("Success", "success", "Completed", "completed", ""):
                msg = data.get("message", str(data)[:600])
                raise RuntimeError(f"FortiAI proxy execution failed: {msg}")

            payload = data.get("data", data)
            if isinstance(payload.get("error"), str):
                raise RuntimeError(f"FortiAI proxy LLM error: {payload['error']}")

            content = payload.get("content")
            tool_name = payload.get("tool_name")
            tool_args = payload.get("tool_args") or {}
            usage = payload.get("usage") or {}

            return (
                content,
                tool_name,
                tool_args if isinstance(tool_args, dict) else {},
                usage,
            )

        for _turn in range(MAX_TOOL_TURNS):
            turn_idx += 1
            try:
                history_chars = len(json.dumps(history, default=str))
            except Exception:
                history_chars = 0

            # Single proxy call
            try:
                content, tool_name, tool_args, usage = await _call_proxy(
                    history=history, tool_defs=tool_defs
                )
            except Exception as exc:
                import logging
                logging.exception("fortiai-proxy call failed")
                yield ErrorEvent(message=f"FortiAI proxy error: {exc}")
                return

            # Usage accounting
            input_tok = usage.get("prompt_tokens", 0) or 0
            output_tok = usage.get("completion_tokens", 0) or 0

            tool_call_usage = []

            if tool_name:
                # --- Tool call turn ------------------------------------------
                raw_args = tool_args
                try:
                    if isinstance(raw_args, str):
                        parsed_args = json.loads(raw_args)
                        if not isinstance(parsed_args, dict):
                            parsed_args = {}
                    else:
                        parsed_args = raw_args
                except Exception:
                    parsed_args = {}

                call_id = f"call_{session_id}_{turn_idx}"
                tier = _tier_for(tool_name, parsed_args)
                yield ToolUseEvent(
                    name=tool_name, arguments=parsed_args,
                    call_id=call_id, tier=tier,
                )

                _t0 = time.perf_counter()
                result = _guarded_dispatch(tool_name, parsed_args)
                dur_ms = int((time.perf_counter() - _t0) * 1000)
                yield ToolResultEvent(
                    call_id=call_id, result=result, duration_ms=dur_ms
                )

                # Record tool-call usage
                content_str = _stringify(result)
                try:
                    args_chars = len(json.dumps(parsed_args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=tool_name, args_chars=args_chars,
                    result_chars=len(content_str), duration_ms=dur_ms,
                ))

                # Check for pending_approval → suspend
                if isinstance(result, dict) and result.get("pending_approval"):
                    approval_id = result["approval_id"]
                    remaining = []
                    suspended_session = _approvals.SuspendedSession(
                        approval_id=approval_id,
                        # The CHAT session id, not `session_id` -- that local
                        # is a per-stream trace id (uuid4().hex[:8]) used for
                        # telemetry correlation. Stashing it here wrote a value
                        # into suspended_sessions.session_id that could never
                        # join to chat_sessions, so the monitor's Pending panel
                        # showed an unresolvable session with a null intent and
                        # user, and list_active_sessions could never derive
                        # `waiting_approval` for any row.
                        session_id=(tags or {}).get("session_id") or session_id,
                        tool=tool_name,
                        tool_use_id=call_id,
                        args=parsed_args,
                        tier=int(result.get("tier", 3)),
                        history_snapshot=list(history),
                        prior_tool_result_blocks=[],
                        remaining_tool_calls=[
                            _approvals.SkippedToolCall(
                                call_id=s.call_id, name=s.name, args=s.args,
                            )
                            for s in remaining
                        ],
                        system=system,
                        tags=dict(tags),
                        summary=result.get("summary"),
                    )
                    _approvals.bind(suspended_session)
                    if self._approval_gateway is not None:
                        self._approval_gateway.stash(suspended_session)
                    else:
                        _approvals.stash(suspended_session)
                    pending = ApprovalRequestEvent(
                        approval_id=approval_id,
                        tool_use_id=call_id,
                        tool=tool_name,
                        tier=int(result.get("tier", 3)),
                        preview=result.get("preview") or {},
                        args_hash=result.get("args_hash", ""),
                        summary=result.get("summary"),
                        requires_step_up=bool(result.get("requires_step_up")),
                    )
                    yield pending
                    yield _emit_usage("pending_approval")
                    yield DoneEvent(stop_reason="pending_approval")
                    return

                # Flatten tool call + result into text messages for the proxy
                args_summary = json.dumps(parsed_args, default=str)
                history.append({
                    "role": "assistant",
                    "content": f"[called {tool_name}({args_summary})]",
                })
                history.append({
                    "role": "user",
                    "content": f"Tool result: {tool_name} = {content_str}",
                })
                any_tools_run = True

                yield _emit_usage("tool_calls")
                continue

            # --- Text turn (terminal or self-repair) -------------------------
            if content is not None:
                yield TextEvent(text=content)

            # Self-repair on broken YAML
            if self_repair_turns < MAX_SELF_REPAIR_TURNS and content:
                yaml_block = _extract_yaml_block(content)
                if yaml_block:
                    errors_text = _compile_errors(yaml_block)
                    if errors_text:
                        self_repair_turns += 1
                        history.append({
                            "role": "user",
                            "content": (
                                "The YAML you just produced doesn't compile. "
                                "Fix the errors and emit a corrected fenced "
                                "```yaml block.\n\nErrors:\n" + errors_text
                            ),
                        })
                        yield _emit_usage("self_repair", repair_delta=1)
                        continue

            # Forced assessment when tools ran but no text followed
            if not content and any_tools_run and not assessment_forced:
                assessment_forced = True
                yield _emit_usage("assessment_forced")
                history.append({
                    "role": "user",
                    "content": (
                        "You ran tools but did not write anything back to the "
                        "analyst. Stop calling tools. In a short written "
                        "assessment, tell the analyst: (1) what you found, "
                        "(2) your severity / disposition verdict, and "
                        "(3) the single recommended next action. Be concise "
                        "and do not call tools."
                    ),
                })
                try:
                    wrap_content, _, _, _ = await _call_proxy(
                        history=history, tool_defs=[]
                    )
                    if wrap_content:
                        yield TextEvent(text=wrap_content)
                except Exception:
                    import logging
                    logging.exception("assessment wrap-up failed")
                yield UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=0, cache_write=0,
                    history_chars=history_chars,
                    stop_reason="assessment_summary",
                    self_repair_turn=self_repair_turns,
                    tool_calls=tool_call_usage, tags=tags,
                )
                yield DoneEvent(stop_reason="end_turn")
                return

            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=input_tok, output_tokens=output_tok,
                cache_read=0, cache_write=0,
                history_chars=history_chars,
                stop_reason="end_turn",
                self_repair_turn=self_repair_turns,
                tool_calls=tool_call_usage, tags=tags,
            )
            yield DoneEvent(stop_reason="end_turn")
            return

        # Tool-turn budget exhausted
        yield UsageEvent(
            session_id=session_id, turn=turn_idx, model=self.model,
            input_tokens=0, output_tokens=0,
            cache_read=0, cache_write=0,
            history_chars=0,
            stop_reason="max_tool_turns",
            self_repair_turn=self_repair_turns,
            tool_calls=[], tags=tags,
        )
        yield DoneEvent(stop_reason="max_tool_turns")

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        if hasattr(self._client, "aclose"):
            await self._client.aclose()

    def __del__(self):
        # Best-effort cleanup; may not run if gc is disabled
        try:
            if hasattr(self._client, "close"):
                self._client.close()
        except Exception:
            pass
