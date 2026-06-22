"""§2.7 — seq_in_turn alignment in run_agent_turn.
§2.2 — stream timeout at the run_turn level (consumer-side safety net).

Verifies that history rows get consecutive seq values with no gaps when
coalesce_text=True, and that a timed-out stream surfaces an ErrorEvent.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

from fsr_playbooks.llm.provider import (
    DoneEvent,
    ErrorEvent,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from fsr_playbooks.llm.run_turn import run_agent_turn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _Row:
    session_id: str
    turn: int
    seq: int
    kind: str
    content: str = ""
    name: str = ""


class _FakeSink:
    def __init__(self):
        self.rows: list[_Row] = []

    def record_chat_message(self, session_id, turn, seq, *, kind, content="", name=""):
        self.rows.append(_Row(session_id, turn, seq, kind, content=content, name=name))


class _FakeProvider:
    """Emits a scripted sequence of events as a stream."""

    def __init__(self, events):
        self._events = events

    async def stream(self, *, system, messages, tools, tags=None) -> AsyncIterator:
        for ev in self._events:
            yield ev

    async def resume(self, *a, **kw):
        raise NotImplementedError


def _usage(session_id="s1", turn=1, stop_reason="tool_use"):
    return UsageEvent(
        session_id=session_id,
        turn=turn,
        model="fake",
        input_tokens=10,
        output_tokens=5,
        cache_read=0,
        cache_write=0,
        history_chars=0,
        stop_reason=stop_reason,
    )


# ---------------------------------------------------------------------------
# §2.7 seq alignment tests
# ---------------------------------------------------------------------------

def test_seq_consecutive_text_then_tool():
    """text block → tool_use → tool_result → done: seq must be consecutive (no gaps)."""
    events = [
        _usage(),
        TextEvent(text="Hello "),
        TextEvent(text="world"),
        ToolUseEvent(call_id="c1", name="validate_yaml", arguments={}),
        ToolResultEvent(call_id="c1", result={"ok": True}),
        _usage(stop_reason="end_turn"),
        DoneEvent(stop_reason="end_turn"),
    ]
    sink = _FakeSink()
    provider = _FakeProvider(events)
    result = asyncio.run(run_agent_turn(
        provider=provider,
        system="sys",
        messages=[Message(role="user", content="hi")],
        tools=[],
        history_sink=sink,
        coalesce_text=True,
    ))
    assert result.stop_reason == "end_turn"
    # Filter out user-message rows (negative seq base)
    assistant_rows = [r for r in sink.rows if r.seq >= 0 and r.session_id == "s1"]
    seqs = [r.seq for r in assistant_rows]
    assert seqs, "expected at least some history rows"
    assert seqs == sorted(seqs), "seq values must be non-decreasing"
    assert len(set(seqs)) == len(seqs), "seq values must be unique (no duplicates)"
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), "seq values must be consecutive"


def test_seq_no_text_only_tool():
    """No text, just tool calls — seq must still be consecutive."""
    events = [
        _usage(),
        ToolUseEvent(call_id="c1", name="find_connector", arguments={}),
        ToolResultEvent(call_id="c1", result="result"),
        _usage(stop_reason="end_turn"),
        DoneEvent(stop_reason="end_turn"),
    ]
    sink = _FakeSink()
    provider = _FakeProvider(events)
    asyncio.run(run_agent_turn(
        provider=provider,
        system="sys",
        messages=[],
        tools=[],
        history_sink=sink,
        coalesce_text=True,
    ))
    assistant_rows = [r for r in sink.rows if r.seq >= 0]
    seqs = [r.seq for r in assistant_rows]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_seq_coalesce_false_each_text_gets_own_seq():
    """With coalesce_text=False every TextEvent gets its own seq."""
    events = [
        _usage(),
        TextEvent(text="A"),
        TextEvent(text="B"),
        DoneEvent(stop_reason="end_turn"),
    ]
    sink = _FakeSink()
    provider = _FakeProvider(events)
    asyncio.run(run_agent_turn(
        provider=provider,
        system="sys",
        messages=[],
        tools=[],
        history_sink=sink,
        session_id="s1",
        coalesce_text=False,
    ))
    text_rows = [r for r in sink.rows if r.kind == "assistant_text"]
    assert len(text_rows) == 2
    assert text_rows[0].seq != text_rows[1].seq


# ---------------------------------------------------------------------------
# §2.2 stream timeout (run_turn consumer-side)
# ---------------------------------------------------------------------------

def test_run_turn_timeout_surfaces_error_event():
    """A stream that hangs past timeout_secs emits ErrorEvent + stream_error."""

    class _HangProvider:
        async def stream(self, *, system, messages, tools, tags=None):
            await asyncio.sleep(9999)
            return
            yield  # make it an async generator

        async def resume(self, *a, **kw):
            raise NotImplementedError

    events_seen = []
    result = asyncio.run(asyncio.wait_for(
        run_agent_turn(
            provider=_HangProvider(),
            system="sys",
            messages=[],
            tools=[],
            on_event=lambda ev: events_seen.append(ev),
            timeout_secs=0.05,  # tiny for the test
        ),
        timeout=3.0,  # outer guard so a bug doesn't hang CI
    ))
    assert result.stop_reason == "stream_error"
    assert result.error is not None and "timed out" in result.error.lower()
    assert any(isinstance(ev, ErrorEvent) for ev in events_seen)
