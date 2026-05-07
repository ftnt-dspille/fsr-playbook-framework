"""LLM provider protocol.

Anthropic v1; OpenAI lands in Phase 5. The protocol normalizes the
event stream so the SSE route doesn't care which backend it's talking to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class LadderRung:
    """One step on the L1→L5 success ladder for the current YAML.

    `id` is one of `compile`, `prechecks`, `reachability`, `dry_run`,
    `outcome`. `state` is `passed`, `failed`, `skipped`, or `pending`.
    `summary` is a short human string the UI renders verbatim.
    """
    id: str
    label: str
    state: Literal["passed", "failed", "skipped", "pending"]
    summary: str = ""


@dataclass
class LadderEvent:
    """Emitted at the end of each chat turn when there's a meaningful
    YAML to score. Powers the in-chat ladder strip.

    `error_count` is the count of blocking compile errors (used by the
    UI to show the error trend ↘ → ↗ across turns).
    """
    rungs: list[LadderRung]
    error_count: int
    warning_count: int
    achieved: int
    """Highest rung index passed (1-based; 0 means even L1 failed)."""
    kind: Literal["ladder"] = "ladder"


Event = (
    TextEvent | ToolUseEvent | ToolResultEvent
    | DoneEvent | ErrorEvent | UsageEvent | LadderEvent
)


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
