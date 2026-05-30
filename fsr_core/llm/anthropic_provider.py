"""Anthropic provider — streaming with tool use.

We do the agentic loop here so the route handler stays a dumb pipe:
- send messages + tools
- stream text deltas as TextEvent
- on stop_reason=tool_use, emit ToolUseEvent for each tool_use block,
  then call dispatch(), append a tool_result message, and loop again
- emit DoneEvent on stop_reason=end_turn (or any non-tool_use stop)
"""
from __future__ import annotations

import json
import os
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
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    compile_errors as _compile_errors,
    extract_yaml_block as _extract_yaml_block,
    shrink_history as _shrink_history,
)
from .tools import anthropic_tools, dispatch, _resolve_tier as _tier_for


DEFAULT_MODEL = os.environ.get("STUDIO_ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")


def _to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m.content, str):
            out.append({"role": m.role, "content": m.content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        client: AsyncAnthropic | None = None,
        approval_gateway: Any = None,
    ):
        self.model = model or DEFAULT_MODEL
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
            self._client = AsyncAnthropic(api_key=api_key, max_retries=5)
        else:
            # Falls back to ANTHROPIC_API_KEY env var via SDK default.
            self._client = AsyncAnthropic(max_retries=5)
        # ApprovalGateway impl (fsr_core.protocols.ApprovalGateway). When
        # None, falls back to the module-level singleton in
        # `fsr_core.llm.approvals` — that's what the web backend uses.
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
        if decision == "approve":
            # Bypass the gate this one time — see tools.dispatch.
            resolved = dispatch(
                suspended.tool,
                {**suspended.args, "_approved": True},
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
        for pid, _pn, _pa in suspended.remaining_tool_calls:
            resumed_blocks.append({
                "type": "tool_result",
                "tool_use_id": pid,
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

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
    ) -> AsyncIterator[Event]:
        import uuid as _uuid

        history = list(messages)
        self_repair_turns = 0
        session_id = _uuid.uuid4().hex[:8]
        turn_idx = 0
        tags = tags or {}
        # Allow callers to pass tools=None or tools=[] and have the
        # provider supply its own. Keeps the route handler ignorant of
        # which schema shape applies.
        if not tools:
            tools = anthropic_tools()

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
            try:
                async with self._client.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=cached_system,
                    messages=_to_anthropic_messages(history),
                    tools=cached_tools,
                ) as stream:
                    async for event in stream:
                        # Text deltas
                        if event.type == "content_block_delta" and getattr(
                            event.delta, "type", None
                        ) == "text_delta":
                            yield TextEvent(text=event.delta.text)

                    final = await stream.get_final_message()
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
            for i, (call_id, name, args) in enumerate(tool_calls):
                yield ToolUseEvent(
                    name=name, arguments=args, call_id=call_id,
                    tier=_tier_for(name, args),
                )
                result = dispatch(name, args)
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
                        remaining_tool_calls=list(pending_remaining),
                        system=system,
                        tags=dict(tags),
                        summary=result.get("summary"),
                    )
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

                yield ToolResultEvent(call_id=call_id, result=result)
                content_str = _stringify(result)
                # Flag failures so the model's self-repair loop branches on a
                # real error signal instead of guessing from prose. Recognizes
                # both the `{ok: false}` envelope (canonical, from `_err`) and
                # a bare `{error: ...}` dict.
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": content_str,
                    "is_error": _is_error_result(result),
                })
                try:
                    args_chars = len(json.dumps(args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=name, args_chars=args_chars,
                    result_chars=len(content_str),
                ))

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
        history.append(Message(
            role="user",
            content=(
                f"You've used the full tool-turn budget "
                f"({MAX_TOOL_TURNS} rounds) without finishing. Stop "
                f"calling tools. In 2-4 sentences, tell the user: "
                f"(1) what state the YAML is in (valid? warnings? "
                f"errors?), (2) what specifically is left to do, and "
                f"(3) one concrete next step they can take. Do not "
                f"re-emit the YAML."
            ),
        ))
        turn_idx += 1
        try:
            history_chars = len(json.dumps(
                _to_anthropic_messages(history), default=str
            ))
        except Exception:
            history_chars = 0
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=512,
                system=cached_system,
                messages=_to_anthropic_messages(history),
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
                stop_reason="max_tool_turns_summary",
                self_repair_turn=self_repair_turns,
                tool_calls=[], tags=tags,
            )
        except Exception:
            # If the wrap-up call fails, fall through to DoneEvent —
            # the user still gets *something* (the prior assistant
            # text from turn N-1).
            import logging
            logging.exception("max-tool-turns summary call failed")
        yield DoneEvent(stop_reason="max_tool_turns")


def _is_error_result(result: Any) -> bool:
    """True if a tool result represents a failure, for the wire
    `is_error` flag. Recognizes the canonical `{ok: false}` envelope
    (from `_err`) and a bare `{error: ...}` dict."""
    return isinstance(result, dict) and (
        result.get("ok") is False or "error" in result)


def _stringify(result: Any) -> str:
    import json

    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


