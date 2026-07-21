"""Anthropic provider — streaming with tool use.

We do the agentic loop here so the route handler stays a dumb pipe:
- send messages + tools
- stream text deltas as TextEvent
- on stop_reason=tool_use, emit ToolUseEvent for each tool_use block,
  then call dispatch(), append a tool_result message, and loop again
- emit DoneEvent on stop_reason=end_turn (or any non-tool_use stop)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, AsyncIterator

try:
    from anthropic import AsyncAnthropic
except ImportError:
    # The SDK isn't installed in every environment (e.g. the test/dev box
    # that only exercises the pure helpers, or the FSR connector runtime).
    # Defer the hard failure to AnthropicProvider.__init__ so the module —
    # and its module-level helpers — import cleanly without it.
    AsyncAnthropic = None  # type: ignore[assignment,misc]

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
from . import approvals as _approvals
from ._loop_helpers import (
    MAX_PARALLEL_TOOLS,
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    STREAM_TIMEOUT_SECS,
    TriageDiscipline,
    compile_errors as _compile_errors,
    drain_with_idle_timeout,
    extract_yaml_block as _extract_yaml_block,
    shrink_history as _shrink_history,
)
from .tools import anthropic_tools, dispatch, _resolve_tier as _tier_for


DEFAULT_MODEL = os.environ.get("STUDIO_ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")


# P1 — forced written assessment. When a turn runs tools but the final
# assistant block carries no text (only tool_use / emitted cards), the chat
# looks like it "didn't answer." We append this directive and do ONE more
# no-tools round so the analyst always gets a narrative close.
_ASSESSMENT_DIRECTIVE = (
    "You ran tools but did not write anything back to the analyst. Stop "
    "calling tools. In a short written assessment, tell the analyst: "
    "(1) what you found, (2) your severity / disposition verdict, and "
    "(3) the single recommended next action. Be concise and do not call tools."
)


def _to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m.content, str):
            out.append({"role": m.role, "content": m.content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def _with_history_breakpoint(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a rolling cache breakpoint on the last block of the last message.

    Without this we cache only the (tools + system) prefix — 2 of the 4
    breakpoints Anthropic allows — and re-send the whole conversation uncached
    on every iteration. That is the expensive half of an agentic turn: `history`
    grows by an assistant block plus a tool_result block per tool call, so a
    10-tool turn pays full input price on a transcript that is mostly identical
    to the previous request's.

    Anthropic's cache is prefix-based, so a breakpoint at the END of history
    makes each request read everything up to the previous request's breakpoint
    and write only the new increment. Reads bill at 0.1x input; writes at 1.25x
    for the default 5-minute TTL, which refreshes free on every hit — so a write
    repays itself after roughly three reads.

    Placement follows the documented rule: mark the last block that is identical
    across requests. The final block of the current history is exactly that — on
    the next request it is unchanged and everything after it is new.
    """
    if not msgs:
        return msgs
    out = list(msgs)
    last = dict(out[-1])
    content = last.get("content")
    # cache_control lives on a content BLOCK, so a bare string must be widened
    # to a one-element text block first.
    if isinstance(content, str):
        if not content:
            return msgs
        blocks: list[Any] = [{"type": "text", "text": content}]
    elif isinstance(content, list) and content:
        blocks = list(content)
    else:
        return msgs
    tail = blocks[-1]
    if not isinstance(tail, dict):
        return msgs
    blocks[-1] = {**tail, "cache_control": {"type": "ephemeral"}}
    last["content"] = blocks
    out[-1] = last
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        client: AsyncAnthropic | None = None,
        approval_gateway: Any = None,
    ):
        self.model = model or DEFAULT_MODEL
        # base_url override: point at an Anthropic-compatible gateway/proxy
        # (corporate egress proxy, Bedrock/Vertex-compat shim, a local mock).
        # None → the SDK's default (https://api.anthropic.com). Only forwarded
        # when set so we don't override a caller-injected client's own base.
        _client_kwargs: dict[str, Any] = {"max_retries": 5}
        if base_url:
            _client_kwargs["base_url"] = base_url
        # max_retries=5 (SDK default is 2). Failed retries cost nothing —
        # Anthropic only bills successful generations — so a higher
        # ceiling makes us robust to transient 529 overloads at zero
        # cost. The SDK already exponentially backs off between retries.
        if client is not None:
            self._client = client
        elif AsyncAnthropic is None:
            raise RuntimeError(
                "the 'anthropic' SDK is not installed; AnthropicProvider "
                "needs it unless you inject a `client=`")
        elif api_key:
            self._client = AsyncAnthropic(api_key=api_key, **_client_kwargs)
        else:
            # Falls back to ANTHROPIC_API_KEY env var via SDK default.
            self._client = AsyncAnthropic(**_client_kwargs)
        # ApprovalGateway impl (fsr_playbooks.protocols.ApprovalGateway). When
        # None, falls back to the module-level singleton in
        # `fsr_playbooks.llm.approvals` — that's what the web backend uses.
        # The FortiSOAR connector passes a PersistedApprovalGateway so
        # paused HITL turns survive worker restarts.
        self._approval_gateway = approval_gateway

    async def resume(
        self,
        *,
        suspended: "_approvals.SuspendedSession",
        decision: str,  # "approve" | "deny"
    ) -> AsyncIterator[Event]:
        """Resume a turn that was suspended on a pending_approval.

        Rebuilds the user-side tool_result message covering every
        tool_use the model emitted in the suspended assistant turn:
        - prior_tool_result_blocks for calls that completed pre-pending
        - one block for the pending call (re-dispatched on approve, or
          synthesized `{ok: false, code: "user_denied"}` on deny)
        - placeholders for remaining_tool_calls (Anthropic requires a
          tool_result for every tool_use; without these the next
          messages call 400s).

        Then re-enters `stream()` with the rebuilt history. The full
        provider loop (text deltas, further tool calls, UsageEvent,
        DoneEvent) flows as usual.
        """
        # Phase 3.1: verify the HMAC binding before trusting the stored args.
        # A mismatch means the session was tampered with (or minted before a
        # secret rotation / restart without a stable FSR_APPROVAL_HMAC_KEY) —
        # fail closed rather than re-dispatch a possibly-substituted call.
        if not _approvals.verify(suspended):
            yield ErrorEvent(
                message="Approval binding check failed — the suspended action "
                        "could not be verified and was not executed. Re-issue "
                        "the request."
            )
            yield DoneEvent(stop_reason="approval_unverified")
            return

        if decision == "approve":
            # Bypass the gate this one time — see tools.dispatch.
            resolved = dispatch(
                suspended.tool,
                {**suspended.args, "_approved": True},
                _internal=True,
            )
            decision_event_result: Any = resolved
        else:
            resolved = {"ok": False, "code": "user_denied",
                        "reason": "User denied the action."}
            decision_event_result = resolved

        # Emit the resolved tool_result so the UI can render it inline
        # with the approval card it was waiting on.
        yield ToolResultEvent(
            call_id=suspended.tool_use_id,
            result=decision_event_result,
        )

        resumed_blocks: list[dict[str, Any]] = list(
            suspended.prior_tool_result_blocks
        )
        resumed_blocks.append({
            "type": "tool_result",
            "tool_use_id": suspended.tool_use_id,
            "content": _stringify(resolved),
            "is_error": _is_error_result(resolved),
        })
        for skipped in suspended.remaining_tool_calls:
            resumed_blocks.append({
                "type": "tool_result",
                "tool_use_id": skipped.call_id,
                "content": "{\"ok\": false, \"code\": "
                            "\"superseded_by_approval\"}",
                "is_error": True,
            })

        # Rehydrate Messages from the wire-form snapshot + the rebuilt
        # tool_result user turn. The provider's `stream()` will run
        # _to_anthropic_messages over this again, which is a no-op for
        # already-shaped block lists.
        rehydrated: list[Message] = []
        for m in suspended.history_snapshot:
            rehydrated.append(Message(role=m["role"], content=m["content"]))
        rehydrated.append(Message(role="user", content=resumed_blocks))

        async for ev in self.stream(
            system=suspended.system,
            messages=rehydrated,
            tools=[],
            tags=suspended.tags,
        ):
            yield ev

    async def _wrapup_call(
        self,
        *,
        history: list[Message],
        directive: str,
        cached_system: Any,
        session_id: str,
        turn_idx: int,
        tags: dict[str, Any],
        self_repair_turns: int,
        stop_reason_label: str,
        max_tokens: int = 512,
    ) -> AsyncIterator[Event]:
        """One forced no-tools model round that yields its text + a UsageEvent.

        Shared by the max-tool-turns wrap-up and the P1 forced-assessment
        guarantee. Appends ``directive`` as a user turn, runs the model with
        NO tools (so it can't keep investigating), and streams the resulting
        text. Failures are logged and swallowed — the caller still emits a
        terminal DoneEvent so the turn never hangs.
        """
        history.append(Message(role="user", content=directive))
        try:
            history_chars = len(json.dumps(
                _to_anthropic_messages(history), default=str
            ))
        except Exception:
            history_chars = 0
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=cached_system,
                messages=_with_history_breakpoint(_to_anthropic_messages(history)),
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and getattr(
                        event.delta, "type", None
                    ) == "text_delta":
                        yield TextEvent(text=event.delta.text)
                final = await stream.get_final_message()
            usage = getattr(final, "usage", None)
            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0 if usage else 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0 if usage else 0,
                cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0 if usage else 0,
                cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0 if usage else 0,
                history_chars=history_chars,
                stop_reason=stop_reason_label,
                self_repair_turn=self_repair_turns,
                tool_calls=[], tags=tags,
            )
        except Exception:
            import logging
            logging.exception("%s call failed", stop_reason_label)

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
        case_state: Any = None,  # CaseState | None, kept as Any to avoid import
    ) -> AsyncIterator[Event]:
        import uuid as _uuid

        history = list(messages)
        self_repair_turns = 0
        # P1 — forced-assessment guarantee. `any_tools_run` flips once any
        # tool result has been folded into history; `assessment_forced`
        # caps the guarantee at one extra round so it can't loop.
        any_tools_run = False
        assessment_forced = False
        session_id = _uuid.uuid4().hex[:8]
        turn_idx = 0
        tags = tags or {}
        # Allow callers to pass tools=None or tools=[] and have the
        # provider supply its own. Keeps the route handler ignorant of
        # which schema shape applies.
        if not tools:
            tools = anthropic_tools()

        # Defense-in-depth for the intent tool-slice (see llm/intents.py).
        # The caller advertises an intent-filtered tool list (triage drops
        # the build-only authoring/mutation surface), but `dispatch` will
        # happily execute ANY tool name. If a build-only tool name reaches
        # us in a triage session — model confusion, a stale widget, a
        # replayed transcript — refuse to run it instead of silently
        # authoring/mutating. The model only ever sees `allowed_names`, so
        # in the normal path this never triggers; it's a backstop.
        allowed_names = {t["name"] for t in tools}

        # P4 — repeated-error guard. If a tool call with the identical
        # (name, args) shape already failed once this turn, don't re-run it:
        # return a guard envelope telling the model to stop retrying that exact
        # shape and adapt (e.g. re-resolve a SIEM incidentId from sourcedata)
        # or surface the blocker. Stops the "same 400 twice, no adaptation"
        # budget burn seen in live triage.
        failed_signatures: set[str] = set()
        # Triage discipline (hunt floor + forbidden pivot + call-once) — see
        # _loop_helpers.TriageDiscipline. Fires only on triage tool names.
        # If case_state is provided, pass its investigation to seed counters.
        investigation_state = (
            getattr(case_state, "investigation", None)
            if case_state is not None else None
        )
        # Authoring/build turns are detected by the absence of the triage-only
        # staging tool `emit_action_card` from the advertised slice — build never
        # stages containment, so the hunt-floor gate must not block
        # find_containment_actions DISCOVERY there (it stays fully in force for
        # triage, whose slice includes emit_action_card).
        _authoring = "emit_action_card" not in allowed_names
        _discipline = TriageDiscipline(
            state=investigation_state,
            capabilities=(getattr(case_state, "capabilities", None)
                          if case_state is not None else None),
            authoring=_authoring,
        )

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
                        f"arguments — change the inputs (e.g. resolve the "
                        f"correct id from the record's sourcedata) or stop and "
                        f"report the blocker in your assessment."
                    ),
                }
            guard = _discipline.evaluate(nm, ar)
            if guard is not None:
                # Terminal guards (forbidden pivot / call-once) can never
                # succeed — register the signature so an identical re-call hits
                # the firmer repeated_call_guard and the model stops retrying.
                # The hunt-floor block is intentionally NOT terminal: that exact
                # call should succeed once investigation has caught up.
                if guard.get("forbidden_pivot_guard") or guard.get("call_once_guard"):
                    failed_signatures.add(sig)
                return guard
            result = dispatch(nm, ar)
            _discipline.note_result(nm, ar, result)
            if _is_error_result(result):
                failed_signatures.add(sig)
            return result

        # Prompt caching: mark the last tool with `cache_control` so the
        # entire (system + tools) prefix is cached for 5 min. Cached reads
        # cost 90% less ($0.30/M vs $3/M for Sonnet 4.5). Within a back-to-
        # back chat session every turn after the first is a cache hit.
        cached_system = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        cached_tools: list[dict[str, Any]] = []
        for i, t in enumerate(tools):
            if i == len(tools) - 1:
                cached_tools.append({**t, "cache_control": {"type": "ephemeral"}})
            else:
                cached_tools.append(t)

        for _turn in range(MAX_TOOL_TURNS):
            turn_idx += 1
            # Compact older turns: dedupe idempotent-tool results and
            # cap older validate_yaml/compile_yaml bodies. Only mutates
            # historical blocks — the most recent assistant + tool_result
            # stay byte-identical so prompt cache is preserved.
            try:
                _shrink_history(history)
            except Exception:
                # Never let compaction break a chat turn.
                import logging
                logging.exception("shrink_history failed")
            # Snapshot history size BEFORE the LLM round-trip so we can
            # see what we paid to send. Cached system+tools aren't in
            # this number — Anthropic's `cache_read_input_tokens` is.
            try:
                history_chars = len(json.dumps(
                    _to_anthropic_messages(history), default=str
                ))
            except Exception:
                history_chars = 0
            # §2.2 — stream the round-trip live: text deltas reach the caller
            # (and the connector's chat_poll feed) AS THEY ARRIVE, so the widget
            # shows a live token stream instead of the whole answer landing at
            # once on turn completion. `_pump` keeps `get_final_message()` inside
            # the SDK's streaming context; `drain_with_idle_timeout` supplies the
            # per-delta inactivity timeout + cancellation (shared across
            # providers — see _loop_helpers).
            async def _pump():
                async with self._client.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=cached_system,
                    messages=_with_history_breakpoint(_to_anthropic_messages(history)),
                    tools=cached_tools,
                ) as _stream:
                    async for _ev in _stream:
                        if _ev.type == "content_block_delta" and getattr(
                            _ev.delta, "type", None
                        ) == "text_delta":
                            yield ("text", _ev.delta.text)
                    yield ("final", await _stream.get_final_message())

            final = None
            try:
                async for _kind, _payload in drain_with_idle_timeout(
                    _pump(), timeout=STREAM_TIMEOUT_SECS
                ):
                    if _kind == "text":
                        yield TextEvent(text=_payload)   # live delta
                    else:  # "final"
                        final = _payload
            except asyncio.TimeoutError:
                import logging
                logging.warning(
                    "anthropic stream timed out after %ss", STREAM_TIMEOUT_SECS
                )
                yield ErrorEvent(
                    message=f"The request to Anthropic timed out after "
                            f"{STREAM_TIMEOUT_SECS}s. The API may be slow "
                            f"or unreachable — please try again."
                )
                return
            except Exception as e:
                # Surface a clean, user-readable message; log the raw
                # detail server-side. The SDK already auto-retried up to
                # max_retries on 429/5xx/529 — if we reach this except
                # block, retries were exhausted (or it's a non-retryable
                # error like Auth/BadRequest).
                import logging
                from anthropic import (
                    APIConnectionError, APITimeoutError, AuthenticationError,
                    BadRequestError, PermissionDeniedError, RateLimitError,
                    APIStatusError,
                )
                logging.exception("anthropic stream failed")
                if isinstance(e, AuthenticationError):
                    msg = "Anthropic authentication failed — check ANTHROPIC_API_KEY in the backend env."
                elif isinstance(e, PermissionDeniedError):
                    msg = "Anthropic API key lacks permission for this model."
                elif isinstance(e, RateLimitError):
                    msg = "You've hit Anthropic's rate limit. Wait a moment and try again."
                elif isinstance(e, APITimeoutError):
                    msg = "The request to Anthropic timed out. Try again, or shorten the prompt if it's very long."
                elif isinstance(e, APIConnectionError):
                    msg = "Could not reach Anthropic — check your network connection and try again."
                elif isinstance(e, BadRequestError):
                    msg = f"Anthropic rejected the request: {getattr(e, 'message', str(e))[:200]}"
                elif isinstance(e, APIStatusError):
                    # 529 overloaded_error and any other status that
                    # slipped past auto-retry. Pull the canonical type
                    # from the response body if present.
                    err_type = ""
                    try:
                        body = getattr(e, "body", None) or {}
                        err_type = (body.get("error") or {}).get("type", "")
                    except Exception:
                        pass
                    if err_type == "overloaded_error":
                        msg = ("Anthropic is overloaded right now. We retried a few times "
                               "and still couldn't get through — please try again in a moment.")
                    else:
                        status = getattr(e, "status_code", "?")
                        msg = f"Anthropic returned an error (HTTP {status}). Please try again."
                else:
                    msg = "Something went wrong talking to Anthropic. Please try again."
                yield ErrorEvent(message=msg)
                return

            assistant_blocks: list[dict[str, Any]] = []
            tool_calls: list[tuple[str, str, dict[str, Any]]] = []
            for block in final.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    tool_calls.append((block.id, block.name, dict(block.input)))

            history.append(Message(role="assistant", content=assistant_blocks))

            usage = getattr(final, "usage", None)
            input_tok = getattr(usage, "input_tokens", 0) or 0 if usage else 0
            output_tok = getattr(usage, "output_tokens", 0) or 0 if usage else 0
            cache_hit = getattr(usage, "cache_read_input_tokens", 0) or 0 if usage else 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0 if usage else 0

            # Tool-call sizes are filled in once we execute the tools
            # below; built up locally so we can fold them into the
            # single UsageEvent we emit at the end of the turn.
            tool_call_usage: list[ToolCallUsage] = []

            if final.stop_reason != "tool_use" or not tool_calls:
                # Self-repair: if the assistant emitted a fenced yaml block
                # that doesn't compile, feed the structured errors back as
                # a synthetic user turn and let it try again. Capped at
                # MAX_SELF_REPAIR_TURNS so cost can't spiral.
                if self_repair_turns < MAX_SELF_REPAIR_TURNS:
                    final_text = "".join(
                        b.get("text", "") for b in assistant_blocks if b.get("type") == "text"
                    )
                    yaml_block = _extract_yaml_block(final_text)
                    if yaml_block:
                        errors_text = _compile_errors(yaml_block)
                        if errors_text:
                            self_repair_turns += 1
                            history.append(Message(
                                role="user",
                                content=(
                                    f"The YAML you just produced doesn't compile. "
                                    f"Fix the errors and emit a corrected fenced ```yaml "
                                    f"block.\n\nErrors:\n{errors_text}"
                                ),
                            ))
                            yield UsageEvent(
                                session_id=session_id, turn=turn_idx, model=self.model,
                                input_tokens=input_tok, output_tokens=output_tok,
                                cache_read=cache_hit, cache_write=cache_write,
                                history_chars=history_chars,
                                stop_reason=final.stop_reason or "",
                                self_repair_turn=self_repair_turns - 1,
                                tool_calls=tool_call_usage, tags=tags,
                            )
                            continue
                # P1 — forced-assessment guarantee. The turn ran tools but
                # the final assistant block has no text (only tool_use /
                # emitted cards). Emit the usage for the round we paid for,
                # then force ONE no-tools round so the analyst gets a written
                # close instead of silence. Capped via `assessment_forced`.
                final_text = "".join(
                    b.get("text", "") for b in assistant_blocks
                    if b.get("type") == "text"
                ).strip()
                if not final_text and any_tools_run and not assessment_forced:
                    assessment_forced = True
                    yield UsageEvent(
                        session_id=session_id, turn=turn_idx, model=self.model,
                        input_tokens=input_tok, output_tokens=output_tok,
                        cache_read=cache_hit, cache_write=cache_write,
                        history_chars=history_chars,
                        stop_reason="assessment_forced",
                        self_repair_turn=self_repair_turns,
                        tool_calls=tool_call_usage, tags=tags,
                    )
                    turn_idx += 1
                    async for ev in self._wrapup_call(
                        history=history, directive=_ASSESSMENT_DIRECTIVE,
                        cached_system=cached_system, session_id=session_id,
                        turn_idx=turn_idx, tags=tags,
                        self_repair_turns=self_repair_turns,
                        stop_reason_label="assessment_summary",
                    ):
                        yield ev
                    yield DoneEvent(stop_reason=final.stop_reason or "end_turn")
                    return
                yield UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=cache_hit, cache_write=cache_write,
                    history_chars=history_chars,
                    stop_reason=final.stop_reason or "",
                    self_repair_turn=self_repair_turns,
                    tool_calls=tool_call_usage, tags=tags,
                )
                yield DoneEvent(stop_reason=final.stop_reason or "end_turn")
                return

            # Execute tools, emit events, append tool_result message.
            # If any call returns a pending_approval envelope, we
            # stash the suspension state and bail out for this turn.
            # The chat layer resumes once the user decides.
            tool_result_blocks: list[dict[str, Any]] = []
            pending: ApprovalRequestEvent | None = None
            pending_remaining: list[tuple[str, str, dict[str, Any]]] = []

            def _record_result(name: str, args: dict[str, Any], result: Any,
                               duration_ms: int | None = None) -> dict[str, Any]:
                # Build the tool_result block + fold usage. Returns the block
                # so callers can both append it and (for parallel calls) keep
                # tool_use order intact.
                content_str = _stringify(result)
                block = {
                    "type": "tool_result",
                    "tool_use_id": "",  # filled by caller
                    "content": content_str,
                    "is_error": _is_error_result(result),
                }
                try:
                    args_chars = len(json.dumps(args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=name, args_chars=args_chars,
                    result_chars=len(content_str),
                    duration_ms=duration_ms,
                ))
                return block

            # §2.8 — Parallel read-only dispatch. The first tier-3+ call (if
            # any) is the approval boundary; by construction every call before
            # it is read-only (tier ≤ 2), so those are safe to fan out
            # concurrently. The approval call itself + everything after it
            # route through the sequential suspend path below, unchanged.
            tiers = [_tier_for(name, args) for (_cid, name, args) in tool_calls]
            approval_idx = next(
                (idx for idx, t in enumerate(tiers) if t >= 3), len(tool_calls)
            )
            parallel_batch = tool_calls[:approval_idx]

            # Emit ToolUseEvents up front so the stream preserves tool_use
            # order even though execution is concurrent.
            for (call_id, name, args), tier in zip(parallel_batch, tiers):
                yield ToolUseEvent(
                    name=name, arguments=args, call_id=call_id, tier=tier,
                )
            if parallel_batch:
                _sem = asyncio.Semaphore(MAX_PARALLEL_TOOLS)

                async def _run_one(nm: str, ar: dict[str, Any]) -> Any:
                    async with _sem:
                        _t0 = time.perf_counter()
                        res = await asyncio.to_thread(_guarded_dispatch, nm, ar)
                        return res, int((time.perf_counter() - _t0) * 1000)

                batch_results = await asyncio.gather(
                    *[_run_one(name, args) for (_cid, name, args) in parallel_batch]
                )
                # Emit results + build tool_result blocks in tool_use order.
                for (call_id, name, args), (result, dur_ms) in zip(parallel_batch, batch_results):
                    yield ToolResultEvent(call_id=call_id, result=result, duration_ms=dur_ms)
                    block = _record_result(name, args, result, dur_ms)
                    block["tool_use_id"] = call_id
                    tool_result_blocks.append(block)

            for i in range(approval_idx, len(tool_calls)):
                call_id, name, args = tool_calls[i]
                yield ToolUseEvent(
                    name=name, arguments=args, call_id=call_id,
                    tier=_tier_for(name, args),
                )
                _t0 = time.perf_counter()
                result = _guarded_dispatch(name, args)
                dur_ms = int((time.perf_counter() - _t0) * 1000)
                if isinstance(result, dict) and result.get("pending_approval"):
                    # The assistant turn (with this tool_use) is already
                    # appended to history above. Stash everything resume
                    # needs, including any earlier tool_result_blocks for
                    # calls that resolved in this same turn, plus the
                    # tool_use_ids for calls we DIDN'T get to so resume
                    # can fill them with placeholder denials.
                    pending_remaining = list(tool_calls[i + 1:])
                    approval_id = result["approval_id"]
                    suspended_session = _approvals.SuspendedSession(
                        approval_id=approval_id,
                        session_id=session_id,
                        tool=name,
                        tool_use_id=call_id,
                        args=args,
                        tier=int(result.get("tier", 3)),
                        history_snapshot=_to_anthropic_messages(history),
                        prior_tool_result_blocks=list(tool_result_blocks),
                        remaining_tool_calls=[
                            _approvals.SkippedToolCall(
                                call_id=cid, name=cn, args=ca,
                            )
                            for cid, cn, ca in pending_remaining
                        ],
                        system=system,
                        tags=dict(tags),
                        summary=result.get("summary"),
                    )
                    # Phase 3.1: HMAC-bind the session to its args before
                    # stashing, so store tampering is detected on resume.
                    _approvals.bind(suspended_session)
                    if self._approval_gateway is not None:
                        self._approval_gateway.stash(suspended_session)
                    else:
                        _approvals.stash(suspended_session)
                    pending = ApprovalRequestEvent(
                        approval_id=approval_id,
                        tool_use_id=call_id,
                        tool=name,
                        tier=int(result.get("tier", 3)),
                        preview=result.get("preview") or {},
                        args_hash=result.get("args_hash", ""),
                        summary=result.get("summary"),
                        requires_step_up=bool(result.get("requires_step_up")),
                    )
                    break

                # Flag failures (via `_record_result` → `_is_error_result`)
                # so the model's self-repair loop branches on a real error
                # signal instead of guessing from prose.
                yield ToolResultEvent(call_id=call_id, result=result, duration_ms=dur_ms)
                block = _record_result(name, args, result, dur_ms)
                block["tool_use_id"] = call_id
                tool_result_blocks.append(block)

            if pending is not None:
                # Suspend: emit the approval request + usage for the
                # round-trip we already paid for, then a DoneEvent with
                # a sentinel stop_reason so the chat layer knows this
                # isn't a normal end-of-turn.
                yield pending
                yield UsageEvent(
                    session_id=session_id, turn=turn_idx, model=self.model,
                    input_tokens=input_tok, output_tokens=output_tok,
                    cache_read=cache_hit, cache_write=cache_write,
                    history_chars=history_chars,
                    stop_reason="pending_approval",
                    self_repair_turn=self_repair_turns,
                    tool_calls=tool_call_usage, tags=tags,
                )
                yield DoneEvent(stop_reason="pending_approval")
                return

            history.append(Message(role="user", content=tool_result_blocks))
            any_tools_run = True
            yield UsageEvent(
                session_id=session_id, turn=turn_idx, model=self.model,
                input_tokens=input_tok, output_tokens=output_tok,
                cache_read=cache_hit, cache_write=cache_write,
                history_chars=history_chars,
                stop_reason=final.stop_reason or "tool_use",
                self_repair_turn=self_repair_turns,
                tool_calls=tool_call_usage, tags=tags,
            )

        # Tool-turn budget exhausted. Without a final assistant message
        # the chat just goes silent — the user can't tell whether the
        # agent finished or got cut off. Force one more no-tools round
        # so the model can summarize where it landed and what's left.
        turn_idx += 1
        async for ev in self._wrapup_call(
            history=history,
            directive=(
                f"You've used the full tool-turn budget "
                f"({MAX_TOOL_TURNS} rounds) without finishing. Stop "
                f"calling tools. In 2-4 sentences, tell the user: "
                f"(1) what state the YAML is in (valid? warnings? "
                f"errors?), (2) what specifically is left to do, and "
                f"(3) one concrete next step they can take. Do not "
                f"re-emit the YAML."
            ),
            cached_system=cached_system, session_id=session_id,
            turn_idx=turn_idx, tags=tags,
            self_repair_turns=self_repair_turns,
            stop_reason_label="max_tool_turns_summary",
        ):
            yield ev
        yield DoneEvent(stop_reason="max_tool_turns")


def _is_error_result(result: Any) -> bool:
    """True if a tool result represents a failure, for the wire
    `is_error` flag. Recognizes the canonical `{ok: false}` envelope
    (from `_err`) and a bare `{error: ...}` dict.

    Guard-redirect results (kind=='guard_redirect') are steering, not errors,
    so they don't get flagged."""
    if not isinstance(result, dict):
        return False
    # Guard redirects are steering, not errors
    if result.get("kind") == "guard_redirect":
        return False
    return result.get("ok") is False or "error" in result


def _stringify(result: Any) -> str:
    import json

    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


