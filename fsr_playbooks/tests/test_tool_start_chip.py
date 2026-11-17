"""C4 -- the tool chip is announced when the model starts the tool block.

The provider streams a `content_block_start` for each `tool_use` block well
before the round's final message (where the calls used to be parsed). The loop
must surface that as a `ToolStartEvent` at once, so the chip is on the feed
before the round finishes streaming. The final `ToolUseEvent` still arrives
later with the full arguments, unchanged.

The fake client records whether `get_final_message` has been awaited. The
assertion is that, when the start event reaches the consumer, the round has
not finished yet.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fsr_playbooks.llm import agent_loop
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import (
    Message,
    ToolUseEvent,
    UsageEvent,
)


def _is(ev, cls_name):
    # By name, so the test fails on the missing behaviour, not on an import.
    return type(ev).__name__ == cls_name


class _FinalMessage:
    def __init__(self, content):
        self.content = content
        self.usage = SimpleNamespace(
            input_tokens=10, output_tokens=5,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        )
        self.stop_reason = "tool_use" if any(
            getattr(b, "type", "") == "tool_use" for b in content
        ) else "end_turn"


class _Round:
    """One scripted round: raw stream events, then the final message."""

    def __init__(self, events, final, log, gate):
        self._events = events
        self._final = final
        self._log = log
        self._gate = gate

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def _gen():
            for ev in self._events:
                self._log.append(("event", ev.type))
                yield ev
        return _gen()

    async def get_final_message(self):
        # A real round ends only after the stream does, so the final waits
        # until the consumer has taken the start event. Without the start
        # reaching the consumer first, this times out and the test fails.
        await asyncio.wait_for(self._gate.wait(), timeout=2.0)
        self._log.append(("final", None))
        return self._final


class _Messages:
    def __init__(self, rounds, log, gate):
        self._rounds = list(rounds)
        self._log = log
        self._gate = gate
        self._i = 0

    def stream(self, **kwargs):
        i = min(self._i, len(self._rounds) - 1)
        self._i += 1
        events, final = self._rounds[i]
        return _Round(events, final, self._log, self._gate)


class _FakeClient:
    def __init__(self, rounds, log, gate):
        self.messages = _Messages(rounds, log, gate)


def _tool_use(call_id, name, args):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)


def _block_start(call_id, name):
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(type="tool_use", id=call_id, name=name,
                                      input={}))


def _text(s):
    return SimpleNamespace(type="text", text=s)


_SLICE = [
    {"name": "find_connector", "description": "", "input_schema": {"type": "object"}},
]


async def _drain(provider, messages, log, gate):
    """Collect events, noting in `log` when each one reaches the consumer.
    The start event opens the gate the round's final message waits on."""
    events = []
    async for ev in provider.stream(system="sys", messages=messages, tools=_SLICE):
        events.append(ev)
        log.append(("consumed", type(ev).__name__))
        if _is(ev, "ToolStartEvent"):
            gate.set()
    return events


def test_start_chip_reaches_consumer_before_round_finishes(monkeypatch):
    monkeypatch.setattr(agent_loop, "dispatch",
                        lambda name, args: {"ok": True, "echo": args})
    monkeypatch.setattr(agent_loop, "_tier_for", lambda name, args: 1)

    log: list[tuple[str, str | None]] = []
    gate = asyncio.Event()
    rounds = [
        # Round 1: a block-start for c1 arrives, then the round ends.
        ([_block_start("c1", "find_connector")],
         _FinalMessage([_tool_use("c1", "find_connector", {"q": "8.8.8.8"})])),
        # Round 2: the model answers in text.
        ([], _FinalMessage([_text("done")])),
    ]
    provider = AnthropicProvider(model="fake", client=_FakeClient(rounds, log, gate))

    async def _run():
        return await _drain(provider, [Message(role="user", content="hunt")], log, gate)

    events = asyncio.run(_run())

    starts = [e for e in events if _is(e, "ToolStartEvent")]
    assert [(s.call_id, s.name) for s in starts] == [("c1", "find_connector")], events

    # The start reaches the consumer before this round's final message is read.
    start_at = log.index(("consumed", "ToolStartEvent"))
    final_at = log.index(("final", None))
    assert start_at < final_at, log

    # The full call still arrives later, with its arguments, as before.
    uses = [e for e in events if isinstance(e, ToolUseEvent)]
    assert [(u.call_id, u.arguments) for u in uses] == [("c1", {"q": "8.8.8.8"})]
    assert events.index(starts[0]) < events.index(uses[0])
    # And the chip comes before the round's usage row.
    usage_idx = [i for i, e in enumerate(events) if isinstance(e, UsageEvent)]
    assert usage_idx and events.index(starts[0]) < usage_idx[0]
