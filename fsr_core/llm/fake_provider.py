"""FakeProvider — scripted event stream for tests.

Construct with a list-of-list-of-events; each inner list is one LLM
round-trip's worth of events. The provider emits each in order. Useful
for asserting that the route handler / telemetry pipeline reacts the
right way without burning Anthropic credits.

Example::

    from fsr_core.llm.fake_provider import FakeProvider, scripted
    fake = FakeProvider(scripted([
        [TextEvent(text="hello"),
         UsageEvent(session_id="s", turn=1, model="fake-1",
                    input_tokens=10, output_tokens=5,
                    cache_read=0, cache_write=0,
                    history_chars=20, stop_reason="end_turn")],
    ]))
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Iterable

from .provider import DoneEvent, Event, Message, UsageEvent


def scripted(turns: list[list[Event]]) -> list[list[Event]]:
    """Identity helper for readable test fixtures."""
    return turns


class FakeProvider:
    name = "fake"

    def __init__(self, turns: Iterable[Iterable[Event]] | None = None,
                 model: str = "fake-1"):
        self.model = model
        self._turns = [list(t) for t in (turns or [])]
        # Recorded for assertions
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None
        self.last_tools: list[dict[str, Any]] | None = None
        self.last_tags: dict[str, Any] | None = None
        self.call_count: int = 0

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tags: dict[str, Any] | None = None,
    ) -> AsyncIterator[Event]:
        self.last_system = system
        self.last_messages = list(messages)
        self.last_tools = list(tools)
        self.last_tags = dict(tags) if tags else None
        self.call_count += 1

        for events in self._turns:
            for ev in events:
                # Stamp tags on UsageEvents that didn't come pre-tagged,
                # mirroring AnthropicProvider behavior.
                if isinstance(ev, UsageEvent) and not ev.tags and tags:
                    ev = UsageEvent(
                        **{**ev.__dict__, "tags": dict(tags)}
                    )
                yield ev
        # If the script didn't end with a Done, terminate cleanly so
        # the consumer's `async for` finishes.
        yield DoneEvent(stop_reason="end_turn")
