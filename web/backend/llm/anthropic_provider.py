"""Anthropic provider — streaming with tool use.

We do the agentic loop here so the route handler stays a dumb pipe:
- send messages + tools
- stream text deltas as TextEvent
- on stop_reason=tool_use, emit ToolUseEvent for each tool_use block,
  then call dispatch(), append a tool_result message, and loop again
- emit DoneEvent on stop_reason=end_turn (or any non-tool_use stop)
"""
from __future__ import annotations

import os
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from .provider import (
    DoneEvent,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from .tools import dispatch


DEFAULT_MODEL = os.environ.get("STUDIO_ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
MAX_TOOL_TURNS = 8


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
    ) -> AsyncIterator[Event]:
        history = list(messages)

        for _turn in range(MAX_TOOL_TURNS):
            try:
                async with self._client.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    messages=_to_anthropic_messages(history),
                    tools=tools,
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

            if final.stop_reason != "tool_use" or not tool_calls:
                yield DoneEvent(stop_reason=final.stop_reason or "end_turn")
                return

            # Execute tools, emit events, append tool_result message.
            tool_result_blocks: list[dict[str, Any]] = []
            for call_id, name, args in tool_calls:
                yield ToolUseEvent(name=name, arguments=args, call_id=call_id)
                result = dispatch(name, args)
                yield ToolResultEvent(call_id=call_id, result=result)
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": _stringify(result),
                })
            history.append(Message(role="user", content=tool_result_blocks))

        yield DoneEvent(stop_reason="max_tool_turns")


def _stringify(result: Any) -> str:
    import json

    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)
