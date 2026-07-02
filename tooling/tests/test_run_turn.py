"""Tests for fsr_playbooks.llm.run_turn.

Drives `run_agent_turn` / `resume_agent_turn` against the FakeProvider
fixture and asserts every behavior chat.py used to provide inline,
including the six risks called out in AGENT_LOOP_LIFT_PLAN.md.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


from fsr_playbooks.llm.fake_provider import FakeProvider
from fsr_playbooks.llm.approvals import SuspendedSession, SkippedToolCall
from fsr_playbooks.llm.provider import (
    DoneEvent,
    ErrorEvent,
    Event,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)
from fsr_playbooks.llm.run_turn import (
    KIND_ASSISTANT_TEXT,
    KIND_TOOL_RESULT,
    KIND_TOOL_USE,
    KIND_USER,
    resume_agent_turn,
    run_agent_turn,
)


# ----- helpers --------------------------------------------------------------

@dataclass
class _RecordingSink:
    """In-memory HistorySink for assertions."""
    messages: list[dict] = field(default_factory=list)
    turns: list[dict] = field(default_factory=list)
    active: list[str] = field(default_factory=list)

    def write_active_session(self, session_id):
        self.active.append(session_id)

    def record_chat_turn(self, record):
        self.turns.append(dict(record))

    def record_chat_message(self, session_id, turn, seq, kind, content, name=None):
        self.messages.append({
            "session_id": session_id, "turn": turn, "seq": seq,
            "kind": kind, "content": content, "name": name,
        })


def _usage(session="s1", turn=1, model="fake-1", stop="end_turn"):
    return UsageEvent(
        session_id=session, turn=turn, model=model,
        input_tokens=10, output_tokens=5,
        cache_read=0, cache_write=0,
        history_chars=20, stop_reason=stop,
    )


def _msgs(*user_texts):
    return [Message(role="user", content=t) for t in user_texts]


def _run(coro):
    return asyncio.run(coro)


# ----- 1. basic stream consumption -----------------------------------------

def test_basic_text_turn():
    fake = FakeProvider([[TextEvent(text="hello"), _usage()]])
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
    ))
    assert result.session_id == "s1"
    assert result.stop_reason == "end_turn"
    # transcript = TextEvent + UsageEvent + the FakeProvider's tail DoneEvent
    kinds = [type(e).__name__ for e in result.transcript]
    assert kinds == ["TextEvent", "UsageEvent", "DoneEvent"]


def test_on_event_callback_fires_per_event():
    fake = FakeProvider([[TextEvent(text="hi"), _usage()]])
    seen: list[Event] = []
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hello"),
        on_event=seen.append,
    ))
    assert len(seen) == 3  # text + usage + tail done
    assert isinstance(seen[0], TextEvent)


def test_on_event_callback_async():
    fake = FakeProvider([[TextEvent(text="hi"), _usage()]])
    seen: list[Event] = []

    async def cb(ev):
        await asyncio.sleep(0)  # exercise the awaitable branch
        seen.append(ev)

    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("x"), on_event=cb,
    ))
    assert len(seen) == 3


# ----- 2. session_id captured from first UsageEvent ------------------------

def test_session_id_from_first_usage_event():
    fake = FakeProvider([[TextEvent(text="t1"), _usage(session="sess-A")]])
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
    ))
    assert result.session_id == "sess-A"


# ----- 3. retroactive user-message logging on first UsageEvent -------------

def test_user_messages_logged_retroactively_with_negative_seq():
    sink = _RecordingSink()
    fake = FakeProvider([[TextEvent(text="reply"), _usage(session="s1", turn=2)]])
    _run(run_agent_turn(
        provider=fake, system="sys",
        messages=[Message(role="user", content="first"),
                  Message(role="assistant", content="prior"),
                  Message(role="user", content="second")],
        history_sink=sink,
    ))
    user_rows = [m for m in sink.messages if m["kind"] == KIND_USER]
    # The assistant-role message is skipped; both user-role rows logged.
    assert [r["content"] for r in user_rows] == ["first", "second"]
    # Negative seq base ensures they sort before assistant text in the
    # same turn.
    assert all(r["seq"] < 0 for r in user_rows)
    assert all(r["turn"] == 2 for r in user_rows)


# ----- 4. text coalescing --------------------------------------------------

def test_text_coalesced_into_single_row():
    sink = _RecordingSink()
    fake = FakeProvider([[
        TextEvent(text="hel"), TextEvent(text="lo "), TextEvent(text="world"),
        _usage(),
    ]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink, session_id="s1",
    ))
    txt_rows = [m for m in sink.messages if m["kind"] == KIND_ASSISTANT_TEXT]
    assert len(txt_rows) == 1
    assert txt_rows[0]["content"] == "hello world"


def test_text_not_coalesced_when_disabled():
    sink = _RecordingSink()
    fake = FakeProvider([[
        TextEvent(text="hel"), TextEvent(text="lo"),
        _usage(),
    ]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink, coalesce_text=False, session_id="s1",
    ))
    txt_rows = [m for m in sink.messages if m["kind"] == KIND_ASSISTANT_TEXT]
    assert [r["content"] for r in txt_rows] == ["hel", "lo"]


def test_text_flushed_at_tool_boundary():
    sink = _RecordingSink()
    fake = FakeProvider([[
        TextEvent(text="before tool"),
        ToolUseEvent(name="search", arguments={"q": "x"}, call_id="t1"),
        ToolResultEvent(call_id="t1", result={"hits": []}),
        TextEvent(text="after tool"),
        _usage(),
    ]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink, session_id="s1",
    ))
    kinds = [m["kind"] for m in sink.messages if m["kind"] != KIND_USER]
    # text → flush → tool_use → tool_result → text → flush at end
    assert kinds == [
        KIND_ASSISTANT_TEXT, KIND_TOOL_USE, KIND_TOOL_RESULT,
        KIND_ASSISTANT_TEXT,
    ]


def test_pre_supplied_session_id_persists_first_round():
    """Without a pre-supplied session_id, the function mirrors chat.py
    and drops first-round text from history (only the SSE stream sees
    it). The connector passes session_id from params so first-round
    text IS persisted."""
    sink = _RecordingSink()
    fake = FakeProvider([[TextEvent(text="round-1 reply"), _usage()]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink, session_id="widget-session-42",
    ))
    txt_rows = [m for m in sink.messages if m["kind"] == KIND_ASSISTANT_TEXT]
    assert len(txt_rows) == 1
    assert txt_rows[0]["session_id"] == "widget-session-42"
    assert "round-1 reply" in txt_rows[0]["content"]


def test_chat_py_compat_drops_first_round_text_without_pre_supplied_session():
    """Documents the (pre-existing) chat.py limitation: when session_id
    is None on entry, text events fired before the first UsageEvent
    are NOT persisted. The web app accepts this because the live SSE
    stream still carries them; only history.db loses them."""
    sink = _RecordingSink()
    fake = FakeProvider([[TextEvent(text="dropped"), _usage()]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink,
    ))
    txt_rows = [m for m in sink.messages if m["kind"] == KIND_ASSISTANT_TEXT]
    assert txt_rows == []  # dropped, as documented


# ----- 5. seq does NOT reset between UsageEvents (load-bearing invariant) -

def test_seq_does_not_reset_between_usage_events():
    """Risk #1 from the plan. AnthropicProvider emits one UsageEvent per
    LLM round-trip inside a single user turn. The seq counter must
    persist across them — otherwise round-2 rows collide with round-1
    rows on (session_id, turn, seq) and INSERT OR REPLACE silently
    overwrites the earlier round. See chat.py L379-388 for the
    original incident."""
    sink = _RecordingSink()
    fake = FakeProvider([
        [
            # Round 1: text + tool call + result
            TextEvent(text="round1 reply"),
            ToolUseEvent(name="search", arguments={"q": "x"}, call_id="t1"),
            ToolResultEvent(call_id="t1", result="r1"),
            _usage(session="s1", turn=1, stop="tool_use"),
            # Round 2: more text + final usage
            TextEvent(text="round2 reply"),
            _usage(session="s1", turn=1, stop="end_turn"),
        ],
    ])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink, session_id="s1",
    ))
    non_user = [m for m in sink.messages if m["kind"] != KIND_USER]
    seqs = [m["seq"] for m in non_user]
    # All seq values must be unique within this (session_id, turn).
    assert len(set(seqs)) == len(seqs), \
        f"seq collision risks INSERT OR REPLACE row loss: {seqs}"


# ----- 6. tags mutation through provider reference ------------------------

def test_tags_mutated_on_validate_yaml_tool_use():
    """Risk #2. The provider holds a reference to the tags dict; the
    consumer mutates it when the assistant calls validate_yaml /
    compile_yaml, so subsequent UsageEvents carry the
    playbook_collection tag for transcript attribution."""
    tags: dict[str, Any] = {"intent": "build"}
    yaml_arg = "collection: my-pb\nplaybooks: []\n"
    fake = FakeProvider([[
        ToolUseEvent(name="validate_yaml",
                     arguments={"yaml_text": yaml_arg}, call_id="t1"),
        ToolResultEvent(call_id="t1", result={"ok": True}),
        _usage(),
    ]])
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        tags=tags, session_id="s1",
    ))
    # The same dict was mutated.
    assert tags is result.tags
    assert tags.get("playbook_collection") == "my-pb"
    assert "yaml_sha" in tags
    assert tags["intent"] == "build"  # original key preserved


def test_tags_not_mutated_on_unrelated_tool():
    tags: dict[str, Any] = {"intent": "build"}
    fake = FakeProvider([[
        ToolUseEvent(name="search", arguments={"q": "x"}, call_id="t1"),
        ToolResultEvent(call_id="t1", result="ok"),
        _usage(),
    ]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"), tags=tags,
    ))
    assert "playbook_collection" not in tags


# ----- 7. last_assistant_yaml extraction ----------------------------------

def test_last_assistant_yaml_extracted_from_fenced_block():
    yaml_body = "collection: smoke\nplaybooks: []\n"
    fake = FakeProvider([[
        TextEvent(text=f"here you go:\n```yaml\n{yaml_body}```\nlet me know"),
        _usage(),
    ]])
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        session_id="s1",
    ))
    assert result.last_assistant_yaml is not None
    assert "collection: smoke" in result.last_assistant_yaml


def test_last_assistant_yaml_works_across_split_deltas():
    """The YAML fence may straddle TextEvent deltas in streaming providers.
    Sniffing the running buffer (not per-event) is what makes this work."""
    fake = FakeProvider([[
        TextEvent(text="```ya"), TextEvent(text="ml\ncollection: x\n```"),
        _usage(),
    ]])
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        session_id="s1",
    ))
    assert result.last_assistant_yaml is not None
    assert "collection: x" in result.last_assistant_yaml


# ----- 8. final flush on stream end ---------------------------------------

def test_final_flush_after_text_without_terminal_usage():
    """Risk #4. If the stream ends with assistant text but no terminal
    UsageEvent (or boundary), the coalescer must still flush so the
    text isn't lost from history."""
    sink = _RecordingSink()
    # Note: this script has a usage event first to capture the session
    # id, then trailing text with no further usage / done.
    fake = FakeProvider([[
        _usage(),
        TextEvent(text="trailing"),
    ]])
    _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        history_sink=sink, session_id="s1",
    ))
    txt_rows = [m for m in sink.messages if m["kind"] == KIND_ASSISTANT_TEXT]
    assert len(txt_rows) == 1
    assert txt_rows[0]["content"] == "trailing"


# ----- 9. error handling --------------------------------------------------

class _ExplodingProvider:
    name = "exploding"

    async def stream(self, *, system, messages, tools, tags=None, case_state=None):
        yield _usage()
        raise RuntimeError("simulated outage")


def test_provider_exception_surfaces_synthetic_error_event():
    fake = _ExplodingProvider()
    seen = []
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
        on_event=seen.append,
    ))
    assert result.error is not None
    assert "simulated outage" in result.error
    assert result.stop_reason == "stream_error"
    # The synthetic ErrorEvent reaches both transcript and on_event.
    assert any(isinstance(e, ErrorEvent) for e in result.transcript)
    assert any(isinstance(e, ErrorEvent) for e in seen)


def test_error_event_in_stream_sets_error_field():
    fake = FakeProvider([[ErrorEvent(message="bad auth"), _usage()]])
    result = _run(run_agent_turn(
        provider=fake, system="sys", messages=_msgs("hi"),
    ))
    assert result.error == "bad auth"


# ----- 10. resume — fallback when provider has no resume ------------------

class _NoResumeProvider:
    name = "no-resume"

    async def stream(self, *, system, messages, tools, tags=None, case_state=None):
        yield _usage()


def _suspended():
    return SuspendedSession(
        approval_id="appr-1", session_id="sess-1", tool="run_op",
        tool_use_id="tu-1", args={}, tier=3,
        history_snapshot=[], prior_tool_result_blocks=[],
        remaining_tool_calls=[], system="sys", tags={},
    )


def test_resume_returns_synthetic_error_when_provider_lacks_resume():
    fake = _NoResumeProvider()
    result = _run(resume_agent_turn(
        provider=fake, suspended=_suspended(), decision="approve",
    ))
    assert result.error is not None
    assert "resume" in result.error
    assert result.stop_reason == "config_error"
    assert any(isinstance(e, ErrorEvent) for e in result.transcript)


# ----- 11. resume — happy path --------------------------------------------

class _ScriptedResumeProvider:
    name = "resume-script"

    def __init__(self, events: list[Event]):
        self._events = events

    async def stream(self, *, system, messages, tools, tags=None, case_state=None):
        yield _usage()

    async def resume(self, *, suspended, decision):
        for ev in self._events:
            yield ev


def test_resume_happy_path_collects_transcript():
    sink = _RecordingSink()
    provider = _ScriptedResumeProvider([
        TextEvent(text="resumed reply"),
        _usage(session="sess-1", stop="end_turn"),
        DoneEvent(stop_reason="end_turn"),
    ])
    result = _run(resume_agent_turn(
        provider=provider, suspended=_suspended(), decision="approve",
        history_sink=sink,
    ))
    assert result.session_id == "sess-1"
    assert result.stop_reason == "end_turn"
    txt_rows = [m for m in sink.messages if m["kind"] == KIND_ASSISTANT_TEXT]
    assert len(txt_rows) == 1
    assert "resumed" in txt_rows[0]["content"]


# ----- 12. §2.3 — synthetic skipped-tool events on resume -----------------

def test_resume_emits_synthetic_events_for_skipped_tools():
    """remaining_tool_calls → synthetic ToolUseEvent + ToolResultEvent before
    the provider stream fires; both appear in transcript and history_sink."""
    skipped = [
        SkippedToolCall(call_id="c-skip1", name="get_record", args={"id": "1"}),
        SkippedToolCall(call_id="c-skip2", name="run_op", args={"op": "x"}),
    ]
    suspended = SuspendedSession(
        approval_id="appr-2", session_id="sess-2", tool="dangerous_op",
        tool_use_id="tu-gated", args={}, tier=3,
        history_snapshot=[], prior_tool_result_blocks=[],
        remaining_tool_calls=skipped, system="sys", tags={},
    )
    sink = _RecordingSink()
    events_seen: list[Event] = []
    provider = _ScriptedResumeProvider([
        TextEvent(text="ok"),
        _usage(session="sess-2", stop="end_turn"),
        DoneEvent(stop_reason="end_turn"),
    ])

    result = _run(resume_agent_turn(
        provider=provider, suspended=suspended, decision="deny",
        history_sink=sink, on_event=lambda ev: events_seen.append(ev),
    ))

    # Both skipped tools appear in the event stream as synthetic pairs.
    synth_use = [e for e in events_seen if isinstance(e, ToolUseEvent) and e.synthetic]
    synth_res = [e for e in events_seen if isinstance(e, ToolResultEvent) and e.synthetic]
    assert len(synth_use) == 2, f"expected 2 synthetic ToolUseEvents, got {synth_use}"
    assert len(synth_res) == 2, f"expected 2 synthetic ToolResultEvents, got {synth_res}"
    assert {e.name for e in synth_use} == {"get_record", "run_op"}

    # Both appear in transcript.
    synth_in_transcript = [e for e in result.transcript
                           if isinstance(e, (ToolUseEvent, ToolResultEvent))
                           and e.synthetic]
    assert len(synth_in_transcript) == 4

    # history_sink recorded tool_use + tool_result rows for each skipped call.
    skip_use_rows = [m for m in sink.messages
                     if m["kind"] == KIND_TOOL_USE and m["name"] in {"get_record", "run_op"}]
    skip_res_rows = [m for m in sink.messages
                     if m["kind"] == KIND_TOOL_RESULT
                     and m["name"] in {"c-skip1", "c-skip2"}]
    assert len(skip_use_rows) == 2
    assert len(skip_res_rows) == 2
    # seq values are unique and consecutive starting from 0.
    seqs = sorted(m["seq"] for m in skip_use_rows + skip_res_rows)
    assert seqs == list(range(len(seqs)))

    # The real resume still ran: text reply appeared.
    assert result.stop_reason == "end_turn"
