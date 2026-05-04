"""Chat SSE endpoint.

POST /api/chat with {messages: [{role, content}], current_yaml?: str}.
Streams Server-Sent Events with the normalized event shape from
backend.llm.provider.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.llm.anthropic_provider import AnthropicProvider
from backend.llm.provider import (
    DoneEvent,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from backend.llm.tools import anthropic_tools
from backend.system_prompt import SYSTEM_PROMPT


router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    messages: list[ChatMessageIn]
    current_yaml: str | None = None
    provider: str = "anthropic"


def _serialize(event: Event) -> dict[str, Any]:
    if isinstance(event, TextEvent):
        return {"event": "text", "data": json.dumps({"text": event.text})}
    if isinstance(event, ToolUseEvent):
        return {
            "event": "tool_use",
            "data": json.dumps(
                {"name": event.name, "arguments": event.arguments, "call_id": event.call_id}
            ),
        }
    if isinstance(event, ToolResultEvent):
        # Truncate big results so the UI doesn't get flooded.
        result = event.result
        try:
            preview = json.dumps(result, default=str)
        except Exception:
            preview = str(result)
        if len(preview) > 4000:
            preview = preview[:4000] + "…"
        return {
            "event": "tool_result",
            "data": json.dumps({"call_id": event.call_id, "result_preview": preview}),
        }
    if isinstance(event, DoneEvent):
        return {"event": "done", "data": json.dumps({"stop_reason": event.stop_reason})}
    if isinstance(event, ErrorEvent):
        return {"event": "error", "data": json.dumps({"message": event.message})}
    return {"event": "error", "data": json.dumps({"message": "unknown event type"})}


def _build_messages(body: ChatIn) -> list[Message]:
    out: list[Message] = []
    if body.current_yaml:
        out.append(Message(
            role="user",
            content=f"Current editor YAML:\n```yaml\n{body.current_yaml}\n```",
        ))
        out.append(Message(role="assistant", content="Acknowledged."))
    for m in body.messages:
        if m.role not in ("user", "assistant"):
            continue
        out.append(Message(role=m.role, content=m.content))  # type: ignore[arg-type]
    return out


@router.post("/chat")
async def chat(body: ChatIn) -> EventSourceResponse:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        async def gen_err() -> AsyncIterator[dict[str, Any]]:
            yield {
                "event": "error",
                "data": json.dumps({"message": "ANTHROPIC_API_KEY not configured"}),
            }
            yield {"event": "done", "data": json.dumps({"stop_reason": "config_error"})}
        return EventSourceResponse(gen_err())

    provider = AnthropicProvider()
    messages = _build_messages(body)
    tools = anthropic_tools()

    async def gen() -> AsyncIterator[dict[str, Any]]:
        async for ev in provider.stream(system=SYSTEM_PROMPT, messages=messages, tools=tools):
            yield _serialize(ev)

    return EventSourceResponse(gen())
