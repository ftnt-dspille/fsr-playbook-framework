"""FortiAI Proxy provider -- on-box LLM adapter.

Drives the agent loop through the `fortinet-fortiai-proxy` connector
(`agent_chat_completions` operation). Non-streaming: one HTTP call per
round-trip, tool calls round-tripped as flattened text.

**Reasoning depth is selectable.** `feature` picks the backend profile
(`AI_MODEL_MEDIUM` / `AI_MODEL_LARGE`) and `reasoning_effort` sets the depth,
both sent per call via `params.config`; see `_resolve_llm_config` for the one
compatibility rule (effort implies LARGE). The stock appliance ships the same
choice as two connector configurations, "Low Reasoning" and "High Reasoning".

**Tool calls can arrive in batches** -- see `_normalize_tool_calls`.

No customer-supplied API key: the connector holds its own credential. It is
NOT, however, egress-free -- the stock configuration points at FortiAI on
FortiCloud, so an air-gapped deployment requires FortiAI itself to be on-prem.

Phase B of docs/plans/FORTIAI_PROXY_PROVIDER_PLAN.md; corrected by
docs/plans/FORTIAI_PROXY_CAPABILITY_CORRECTION.md.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid as _uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from . import approvals as _approvals
from ._loop_helpers import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    TriageDiscipline,
    is_authoring_slice,
    latest_user_text,
)
from ._loop_helpers import (
    compile_errors as _compile_errors,
)
from ._loop_helpers import (
    extract_yaml_block as _extract_yaml_block,
)
from .provider import (
    ApprovalRequestEvent,
    CapabilityMixin,
    DoneEvent,
    ErrorEvent,
    Event,
    HostEmulation,
    Message,
    ProviderCapabilities,
    TextEvent,
    ToolCallUsage,
    ToolResultEvent,
    ToolUseEvent,
    TurnRequest,
    UsageEvent,
)
from .tools import _resolve_tier as _tier_for
from .tools import anthropic_tools as _anthropic_tools
from .tools import dispatch

#: FortiAI ``feature`` values, i.e. which backend profile serves the call.
#: These are what the appliance's connector *configurations* set as
#: ``config.model`` -- the stock box ships "Low Reasoning" (MEDIUM, default)
#: and "High Reasoning" (LARGE). Live-verified on 8.0.0.
FEATURE_MEDIUM = "AI_MODEL_MEDIUM"
FEATURE_LARGE = "AI_MODEL_LARGE"
FEATURE_SMALL = "AI_MODEL_SMALL"
#: The FSOC default. On an FSR box it answers 404 -30008 "Assistant not found",
#: so it is deliberately not offered.
FEATURE_LOCAL = "AI_MODEL_LOCAL"


def _resolve_llm_config(feature: str | None,
                        reasoning_effort: str | None) -> dict[str, Any]:
    """Build the per-call ``params.config`` overlay -- THE one place the
    effort/model compatibility rule lives.

    The proxy merges ``params["config"]`` over the connector configuration
    (``operations.py``: ``merged_config = {**config, **params.get("config")}``),
    so a caller can pick the backend profile and the reasoning depth per call
    without switching the connector's config UUID. Auth and server address are
    NOT overridable this way -- the client is still constructed from the
    stored config -- which is exactly the seam we want.

    **effort implies LARGE.** ``reasoning_effort`` on ``AI_MODEL_MEDIUM`` is a
    hard ``400 -30000 "The request payload is invalid."`` every time
    (live-verified, 2 reps per cell). Asking for reasoning depth and getting a
    silent empty turn is the worst available outcome, so requesting an effort
    without naming a feature -- or naming a non-LARGE one -- upgrades to LARGE
    here rather than failing at the wire.

    Returns ``{}`` when nothing is set, so the default path sends no ``config``
    key at all and the connector configuration decides, exactly as before.
    """
    overlay: dict[str, Any] = {}
    effort = (reasoning_effort or "").strip() or None
    feat = (feature or "").strip() or None
    if effort:
        if feat != FEATURE_LARGE:
            feat = FEATURE_LARGE
        overlay["reasoning_effort"] = effort
    if feat:
        overlay["model"] = feat
    return overlay


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


def _normalize_tool_calls(tool_name: Any, tool_args: Any,
                          tools_field: Any) -> list[tuple[str, Any]]:
    """Every tool call the proxy elected, as ``[(name, raw_args), ...]``.

    The response carries the FULL batch in ``tools``
    (``[{"name": ..., "args": {...}}, ...]``); ``tool_name``/``tool_args`` are
    only the FIRST of them, kept for back-compat. Reading the singular pair
    alone -- which this provider did until now -- silently discarded every call
    after the first: the model asked for two things, one ran, and nothing
    reported the drop. Live-verified on 8.0.0 that a two-tool prompt returns
    both entries.

    Falls back to the singular pair when ``tools`` is absent or unusable, so an
    older proxy build behaves exactly as before. ``raw_args`` is passed through
    untouched -- the caller parses it and reports its own failures (the proxy
    sometimes hands args back as a JSON *string*).
    """
    calls: list[tuple[str, Any]] = []
    if isinstance(tools_field, list):
        for entry in tools_field:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name:
                calls.append((name, entry.get("args")))
    if calls:
        return calls
    if isinstance(tool_name, str) and tool_name:
        return [(tool_name, tool_args)]
    return []


def _describe_proxy_error(err: Any) -> str:
    """Render the proxy's error envelope as one readable line.

    The dict form carries `error_desc` + `error_code`; anything else (a bare
    string, or a shape we have not seen) is stringified rather than dropped."""
    if isinstance(err, dict):
        desc = err.get("error_desc") or err.get("message") or ""
        code = err.get("error_code") or err.get("status_code") or ""
        if desc and code:
            return f"{desc} (code {code})"
        return str(desc or code or err)
    return str(err)


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


class FortiAIProxyProvider(CapabilityMixin):
    """Non-streaming LLM provider for the FortiAI proxy.

    Calls ``agent_chat_completions`` on the ``fortinet-fortiai-proxy``
    connector via ``POST /api/integration/execute/``. No customer-supplied API
    key (the connector holds its own credential); egress depends on where
    FortiAI itself is deployed. One HTTP round-trip per LLM turn. A turn may
    carry a BATCH of tool calls, which round-trip as flattened-text messages.

    ``feature`` + ``reasoning_effort`` select the backend profile and reasoning
    depth per call -- see :func:`_resolve_llm_config`.
    """

    name = "fortiai-proxy"
    #: Native reasoning depth ONLY: `reasoning_effort` (plus the effort-implies-
    #: LARGE rule) rides in `params.config` on every call -- see
    #: :func:`_resolve_llm_config`. The proxy has no server-side turn budget,
    #: no tool search and no context editing, so the host emulates those.
    capabilities = ProviderCapabilities(reasoning_depth=True)
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        feature: str | None = None,
        reasoning_effort: str | None = None,
        approval_gateway: Any = None,
        max_output_tokens: int | None = None,
        client: Any = None,  # httpx.AsyncClient or compatible, for testing
    ):
        self.base_url = (base_url or "").rstrip("/")
        self._auth = api_key
        # `model` is the COSMETIC params.model -- the proxy echoes it back in
        # data.model and does not route on it. `feature`/`reasoning_effort` are
        # the ones that select a backend profile; see _resolve_llm_config.
        self.model = model or "fortiai-proxy"
        self.feature = feature
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        self._approval_gateway = approval_gateway
        self._client = client or httpx.AsyncClient(timeout=120.0)

    # -- resume ------------------------------------------------------------

    async def resume(
        self,
        *,
        suspended: _approvals.SuspendedSession,
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
            # Off-loop like the main loop's dispatch: live MCP tools call
            # asyncio.run() internally, which raises on the running loop.
            resolved = await asyncio.to_thread(
                dispatch, suspended.tool, {**suspended.args, "_approved": True},
                _internal=True,
            )
        else:
            resolved = {"ok": False, "code": "user_denied",
                        "reason": "User denied the action."}

        # Named synthetic tool_use first -- see anthropic_provider.resume().
        yield ToolUseEvent(
            name=suspended.tool, arguments=dict(suspended.args),
            call_id=suspended.tool_use_id, tier=suspended.tier,
            synthetic=True,
        )
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
                    + _approvals.superseded_result_json()
                ),
            })

        rehydrated = [Message(role="user", content=carried)]

        async for ev in self.stream(
            system=suspended.system,
            messages=rehydrated,
            # Old pickled sessions predate the field -- getattr, not attr.
            tools=list(getattr(suspended, "tools", None) or []),
            tags=suspended.tags,
        ):
            yield ev

    # -- stream -------------------------------------------------------------

    def request(self, req: TurnRequest) -> HostEmulation:
        """Serve reasoning depth NATIVELY, emulate the rest.

        The depth is not a prompt nudge here: it becomes `reasoning_effort` in
        `params.config` on the next call, and `_resolve_llm_config` promotes
        the feature to AI_MODEL_LARGE with it (effort on MEDIUM answers with a
        silent empty turn). An unasked-for depth leaves the configured one
        alone -- `request()` is per turn, not a reconfiguration.
        """
        if req.reasoning:
            self.reasoning_effort = req.reasoning
        return super().request(req)

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
        # Clear per-turn citation validator state for structured verdicts
        from ..mcp_server._citation_validator import clear_tool_registry
        clear_tool_registry()

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
        _authoring = is_authoring_slice(allowed_names)
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
        ) -> tuple[str, list[tuple[str, Any]], dict[str, int]]:
            """Call agent_chat_completions.

            Returns (content, calls, usage). ``content`` is None for tool-call
            turns; ``calls`` is EVERY tool call the proxy elected, normalized to
            ``[(name, raw_args), ...]`` (see _normalize_tool_calls) and empty on
            a text turn. usage is a dict of token counts.
            On error, raises RuntimeError.
            """
            body: dict[str, Any] = {
                "connector": "fortinet-fortiai-proxy",
                "operation": "agent_chat_completions",
                "params": {
                    "messages": history,
                    "tools": tool_defs,
                },
            }
            if self.model:
                body["params"]["model"] = self.model
            overlay = _resolve_llm_config(self.feature, self.reasoning_effort)
            if overlay:
                body["params"]["config"] = overlay

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
            # ANY truthy `error` is an error, whatever its type. This used to
            # test `isinstance(..., str)`, but the live envelope is a DICT --
            # `{"status": "Failure", "status_code": "400", "error_code":
            # "-30000", "error_desc": "The request payload is invalid."}` --
            # so the check never fired and the turn continued with empty
            # content, no usage and no exception. The model then narrated an
            # empty response as a normal answer. A `reasoning_effort` sent
            # against a non-LARGE feature is a live generator of exactly this
            # envelope, so the two fixes belong together.
            err = payload.get("error")
            if err:
                raise RuntimeError(
                    f"FortiAI proxy LLM error: {_describe_proxy_error(err)}")

            content = payload.get("content")
            usage = payload.get("usage") or {}
            calls = _normalize_tool_calls(payload.get("tool_name"),
                                          payload.get("tool_args"),
                                          payload.get("tools"))

            # Pass `tool_args` through UNCHANGED. Coercing a non-dict to `{}`
            # here is what produced the `run_op({})` dispatches seen on
            # contain_block_ip_direct: the proxy hands back tool_args as a
            # JSON *string*, which this turned into an empty call before the
            # caller's parser (which handles strings, and now reports a parse
            # failure instead of emptying) ever saw it.
            return content, calls, usage

        for _turn in range(MAX_TOOL_TURNS):
            turn_idx += 1
            try:
                history_chars = len(json.dumps(history, default=str))
            except Exception:
                history_chars = 0

            # Single proxy call
            try:
                content, calls, usage = await _call_proxy(
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

            if calls:
                # EVERY call in the batch, in order. The proxy can elect
                # more than one (see _normalize_tool_calls); running only
                # the first was a silent drop.
                for _ci, (tool_name, tool_args) in enumerate(calls):
                    # --- Tool call turn ------------------------------------------
                    raw_args = tool_args
                    args_error: str | None = None
                    try:
                        if isinstance(raw_args, str):
                            parsed_args = json.loads(raw_args)
                            if not isinstance(parsed_args, dict):
                                args_error = ("arguments must be a JSON object, got "
                                              f"{type(parsed_args).__name__}")
                                parsed_args = {}
                        elif isinstance(raw_args, dict):
                            parsed_args = raw_args
                        else:
                            args_error = ("arguments must be a JSON object, got "
                                          f"{type(raw_args).__name__}")
                            parsed_args = {}
                    except Exception as exc:  # noqa: BLE001
                        args_error = f"arguments were not valid JSON ({exc})"
                        parsed_args = {}

                    # `_ci` keeps ids unique WITHIN a batch -- two calls in
                    # one turn previously collided on the same id, which the
                    # widget matches results by.
                    call_id = f"call_{session_id}_{turn_idx}_{_ci}"
                    if args_error is not None:
                        # Do NOT dispatch a call whose arguments we could not read.
                        # Emptying them and running anyway is silent arg-dropping:
                        # observed on contain_block_ip_direct (run 20260815T153152Z)
                        # as three consecutive `run_op({})` calls that burned a
                        # third of the turn's budget and staged nothing. It also
                        # weakens the gate -- `_resolve_tier` reads the op out of
                        # the args, so a tier-4 containment with unreadable args
                        # resolves as a plain tier-3 (it escalates from unknown, so
                        # nothing runs ungated, but a step-up requirement is lost).
                        # Hand the parse failure back so the model can re-emit.
                        err = {"ok": False, "code": "bad_tool_arguments",
                               "message": (f"{tool_name}: {args_error}. Re-issue "
                                           f"the call with a single valid JSON "
                                           f"object as the arguments."),
                               "suggestions": []}
                        yield ToolUseEvent(name=tool_name, arguments={},
                                           call_id=call_id,
                                           tier=_tier_for(tool_name, {}))
                        yield ToolResultEvent(call_id=call_id, result=err,
                                              duration_ms=0)
                        history.append({
                            "role": "assistant",
                            "content": f"[called {tool_name} with unreadable arguments]",
                        })
                        history.append({
                            "role": "user",
                            "content": f"Tool result: {tool_name} = {json.dumps(err)}",
                        })
                        # Next call in the batch -- one unreadable call does
                        # not void the others the model elected.
                        continue
                    tier = _tier_for(tool_name, parsed_args)
                    yield ToolUseEvent(
                        name=tool_name, arguments=parsed_args,
                        call_id=call_id, tier=tier,
                    )

                    _t0 = time.perf_counter()
                    result = _guarded_dispatch(tool_name, parsed_args)
                    dur_ms = int((time.perf_counter() - _t0) * 1000)
                    # Register tool result for citation validation
                    from ..mcp_server._citation_validator import register_tool_result
                    register_tool_result(call_id, tool_name, not _is_error_result(result))
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
                        # The rest of THIS batch has not run yet. `remaining_tool_
                        # calls` exists precisely to carry them across the
                        # suspension; leaving it empty (as it was when only one
                        # call per turn was believed possible) would drop every
                        # sibling call the moment one of them needed approval.
                        remaining = [
                            _approvals.SkippedToolCall(
                                call_id=f"{call_id}_skipped_{_si}",
                                name=_sname, args=_sargs
                                if isinstance(_sargs, dict) else {},
                            )
                            for _si, (_sname, _sargs) in enumerate(calls[_ci + 1:])
                        ]
                        # Capture the current turn evidence so citations survive resume.
                        from ..mcp_server._citation_validator import get_turn_evidence
                        evidence = get_turn_evidence()
                        evidence_state = evidence.to_dict() if evidence else {}

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
                            remaining_tool_calls=list(remaining),
                            system=system,
                            tags=dict(tags),
                            summary=result.get("summary"),
                            # the advertised slice -- resume re-enters with it
                            tools=list(tools or []),
                            turn_evidence_state=evidence_state,
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
                    # TurnPlan item 3: state the shrinking budget in the soft
                    # window before the cap (mirrors the other providers).
                    from ._loop_helpers import budget_note
                    _bnote = budget_note(_turn + 1, MAX_TOOL_TURNS) \
                        if self.emulation.task_budget else ""
                    if _bnote:
                        history.append({"role": "user",
                                        "content": f"[turn budget] {_bnote}"})
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
                    wrap_content, _, _ = await _call_proxy(
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
