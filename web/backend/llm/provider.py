"""LLM provider protocol.

Anthropic v1; OpenAI lands in Phase 5. The protocol normalizes the
event stream so the SSE route doesn't care which backend it's talking to.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol


Role = Literal["user", "assistant"]


@dataclass
class TextEvent:
    kind: Literal["text"] = "text"
    text: str = ""


@dataclass
class ToolUseEvent:
    name: str
    arguments: dict[str, Any]
    call_id: str
    kind: Literal["tool_use"] = "tool_use"


@dataclass
class ToolResultEvent:
    call_id: str
    result: Any
    kind: Literal["tool_result"] = "tool_result"


@dataclass
class DoneEvent:
    stop_reason: str
    kind: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    message: str
    kind: Literal["error"] = "error"


Event = TextEvent | ToolUseEvent | ToolResultEvent | DoneEvent | ErrorEvent


@dataclass
class Message:
    role: Role
    content: str | list[dict[str, Any]]
    """Content is either a plain string (user msg) or Anthropic-style block list
    (assistant turn with text + tool_use blocks, or user turn with tool_result blocks)."""


class LLMProvider(Protocol):
    name: str

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[Event]: ...
