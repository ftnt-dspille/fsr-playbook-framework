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

from anthropic import AsyncAnthropic

from .provider import (
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
from ._loop_helpers import (
    MAX_SELF_REPAIR_TURNS,
    MAX_TOOL_TURNS,
    compile_errors as _compile_errors,
    extract_yaml_block as _extract_yaml_block,
)
from .tools import anthropic_tools, dispatch


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
    ):
        self.model = model or DEFAULT_MODEL
        # max_retries=5 (SDK default is 2). Failed retries cost nothing —
        # Anthropic only bills successful generations — so a higher
        # ceiling makes us robust to transient 529 overloads at zero
        # cost. The SDK already exponentially backs off between retries.
        if client is not None:
            self._client = client
        elif api_key:
            self._client = AsyncAnthropic(api_key=api_key, max_retries=5)
        else:
            # Falls back to ANTHROPIC_API_KEY env var via SDK default.
            self._client = AsyncAnthropic(max_retries=5)

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
            tool_result_blocks: list[dict[str, Any]] = []
            for call_id, name, args in tool_calls:
                yield ToolUseEvent(name=name, arguments=args, call_id=call_id)
                result = dispatch(name, args)
                yield ToolResultEvent(call_id=call_id, result=result)
                content_str = _stringify(result)
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": content_str,
                })
                try:
                    args_chars = len(json.dumps(args, default=str))
                except Exception:
                    args_chars = 0
                tool_call_usage.append(ToolCallUsage(
                    name=name, args_chars=args_chars,
                    result_chars=len(content_str),
                ))
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

        yield DoneEvent(stop_reason="max_tool_turns")


def _stringify(result: Any) -> str:
    import json

    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


