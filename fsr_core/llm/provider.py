"""LLM provider protocol.

Anthropic v1; OpenAI lands in Phase 5. The protocol normalizes the
event stream so the SSE route doesn't care which backend it's talking to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol, Union


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
    # HITL Phase 2: server-resolved tier so the audit pane can colour
    # tier-3+ calls without re-resolving on the client. 0 = tier
    # unknown (e.g. provider didn't stamp it; defaults to "safe" badge).
    tier: int = 0
    kind: Literal["tool_use"] = "tool_use"


@dataclass
class ToolResultEvent:
    call_id: str
    result: Any
    kind: Literal["tool_result"] = "tool_result"


@dataclass
class ApprovalRequestEvent:
    """Emitted when a tier-3+ tool call needs human approval before the
    provider can continue. The loop is suspended on the server until
    `POST /api/approvals/{approval_id}` arrives with the decision.

    `tool_use_id` is the Anthropic tool_use block id that triggered the
    request — frontend matches it back onto the assistant turn so the
    approval card renders inline with the call it gates."""
    approval_id: str
    tool_use_id: str
    tool: str
    tier: int
    preview: dict[str, Any]
    args_hash: str
    summary: str | None = None
    requires_step_up: bool = False
    kind: Literal["approval_request"] = "approval_request"


@dataclass
class DoneEvent:
    stop_reason: str
    kind: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    message: str
    kind: Literal["error"] = "error"


@dataclass
class ToolCallUsage:
    """Per-tool-call accounting emitted with each UsageEvent. Lets the
    consumer attribute context bloat to a specific tool result."""
    name: str
    args_chars: int
    result_chars: int


@dataclass
class UsageEvent:
    """One emitted per LLM round-trip. Providers populate the fields
    they have access to; consumers (telemetry, history.db) are the
    same regardless of provider. This is the contract that lets us
    swap providers without rewiring logging.

    `tags` is a free-form dict the route handler stamps in to attribute
    a turn to e.g. a specific playbook (`{"playbook_collection": "..."}`).
    """
    session_id: str
    turn: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int
    history_chars: int
    stop_reason: str
    self_repair_turn: int = 0
    tool_calls: list[ToolCallUsage] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)
    kind: Literal["usage"] = "usage"


# NOTE: typing.Union, not PEP 604 `X | Y`. This is a runtime assignment
# (a type alias), so the `|` operator would execute at import time and
# raise TypeError on Python 3.9 — the FortiSOAR runtime baseline. The
# `from __future__ import annotations` above only defers *annotations*,
# not this expression. Keep it Union-form for 3.9 compatibility.
Event = Union[
    TextEvent, ToolUseEvent, ToolResultEvent,
    DoneEvent, ErrorEvent, UsageEvent,
    ApprovalRequestEvent,
]


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
        tags: dict[str, Any] | None = None,
    ) -> AsyncIterator[Event]:
        """Stream events for one user turn. Implementations MUST emit
        a `UsageEvent` after each LLM round-trip (before any tool
        execution for that turn) so consumers can attribute cost
        independently of the provider.

        `tags` is opaque to the provider — it just round-trips it on
        the UsageEvent so the route handler can stamp e.g. the active
        playbook collection name."""
        ...
