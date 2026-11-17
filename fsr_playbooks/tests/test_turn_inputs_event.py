"""The turn-inputs event: what the model was given, recorded in the transcript.

A stored transcript held what the model DID. "The tool was never used" and "the
tool was never offered" read the same, so every diagnosis started by guessing
which. The loop now emits one `TurnInputsEvent` first (names and sizes, never
prompt text) and `harness.frames.turn_inputs` / `offered_tools` read it.
Transcripts stored before the event load as `None` ("unknown"), not as an empty
offer.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from fsr_playbooks.harness import frames
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import Message, TurnInputsEvent, UsageEvent

# `fsr_playbooks/tests` is not a package: load the fake-client fixtures by path.
_SPEC = importlib.util.spec_from_file_location(
    "_guard_fixtures", Path(__file__).with_name("test_guard_sites_are_recorded.py"))
fx = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(fx)


def _events(tags, tools=None, system="the system prompt"):
    provider = AnthropicProvider(model="fake-model", client=fx._Client(
        [fx._Final([fx._say("hello")])]))

    async def go():
        return [e async for e in provider.stream(
            system=system, messages=[Message(role="user", content="hi")],
            tools=fx._SLICE if tools is None else tools, tags=tags)]

    return asyncio.run(go())


def test_the_first_event_is_what_the_model_was_given():
    tags = {"intent": "triage", "prompt_slices": {"base": 100, "rules": 20}}
    evs = _events(tags, system="x" * 123)
    first = evs[0]
    assert isinstance(first, TurnInputsEvent)
    assert first.model == "fake-model"
    assert first.tools == ["emit_card", "get_record", "run_op"]   # sorted names
    assert first.intent == "triage"
    assert first.system_chars == 123
    assert first.slices == [{"name": "base", "chars": 100},
                            {"name": "rules", "chars": 20}]
    assert sum(isinstance(e, TurnInputsEvent) for e in evs) == 1


def test_it_carries_no_prompt_text():
    first = _events({"prompt_slices": {"base": 5}}, system="SECRET PROMPT TEXT")[0]
    assert "SECRET" not in repr(first)


def test_prompt_slices_do_not_ride_every_usage_row():
    tags = {"prompt_slices": {"base": 5}}
    usage = [e for e in _events(tags) if isinstance(e, UsageEvent)]
    assert usage and all("prompt_slices" not in u.tags for u in usage)


def test_a_malformed_slice_value_yields_no_slices_not_a_failed_turn():
    first = _events({"prompt_slices": "oops"})[0]
    assert first.slices == []


def _wire(ev):
    return {"type": "turn_inputs", "model": ev.model, "tools": ev.tools,
            "intent": ev.intent, "system_chars": ev.system_chars,
            "slices": ev.slices}


def test_the_readers_take_an_envelope_or_a_bare_frame_list():
    ev = _events({"intent": "build"})[0]
    frame_list = [_wire(ev), {"type": "text", "text": "hi"}]
    for transcript in ({"transcript": frame_list}, frame_list):
        assert frames.offered_tools(transcript) == ["emit_card", "get_record", "run_op"]
        got = frames.turn_inputs(transcript)
        assert got["model"] == "fake-model" and got["intent"] == "build"


def test_an_old_transcript_without_the_frame_is_unknown_not_empty():
    old = {"transcript": [{"type": "text", "text": "hi"},
                          {"type": "usage", "model": "m"}], "stop_reason": "end_turn"}
    assert frames.turn_inputs(old) is None
    assert frames.offered_tools(old) is None
    # ...and the rest of the readers still work on it.
    assert frames.assistant_text(old) == "hi"
    assert frames.guards_fired(old) == []


def test_a_frame_with_junk_fields_reads_defensively():
    got = frames.turn_inputs([{"type": "turn_inputs", "tools": ["a", 3, None],
                              "slices": ["x", {"name": "n", "chars": 1}]}])
    assert got["tools"] == ["a"] and got["slices"] == [{"name": "n", "chars": 1}]
