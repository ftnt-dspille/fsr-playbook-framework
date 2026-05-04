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
from .tools import dispatch


DEFAULT_MODEL = os.environ.get("STUDIO_ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
MAX_TOOL_TURNS = 8
# Cap on extra "fix the YAML" turns we'll auto-issue when the assistant's
# final message contains a yaml block that fails to compile. Each repair
# turn is ~$0.02–0.03; 2 keeps the cost ceiling at ~$0.05/conversation.
MAX_SELF_REPAIR_TURNS = 2

_SELF_REPAIR_SENTINEL = "__fsr_studio_self_repair__"


def _extract_yaml_block(text: str) -> str | None:
    """Last fenced ```yaml block. Mirrors frontend's extractYamlBlock."""
    import re

    matches = list(re.finditer(r"```ya?ml\n([\s\S]*?)```", text, flags=re.IGNORECASE))
    return matches[-1].group(1) if matches else None


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

    def __init__(self, *, model: str = DEFAULT_MODEL, client: AsyncAnthropic | None = None):
        self.model = model
        self._client = client or AsyncAnthropic()

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
                yield ErrorEvent(message=f"{type(e).__name__}: {e}")
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


def _compile_errors(yaml_text: str) -> str | None:
    """Run the same compiler the editor uses; return a human/LLM-readable
    bullet list of error messages, or None if the YAML compiles clean."""
    from pathlib import Path

    try:
        from compiler import compile_yaml as _cy  # type: ignore
    except Exception as e:
        return f"compiler import failed: {e}"

    db = Path(__file__).resolve().parents[3] / "store" / "fsr_reference.db"
    res = _cy(yaml_text, db)
    if res.ok:
        return None
    blocking = [e for e in res.errors if e.severity != "warning"]
    if not blocking:
        return None
    lines: list[str] = []
    for e in blocking:
        line = f"- [{e.code.value}] {e.message}"
        if e.path:
            line += f"  (path: {e.path})"
        if e.suggestion:
            line += f"  → {e.suggestion}"
        lines.append(line)
    return "\n".join(lines)
