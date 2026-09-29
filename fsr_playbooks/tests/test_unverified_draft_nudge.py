"""A build turn that drafts, checks, and stops -- never verified, never offered.

The gap between the two build guards: BuildProgressGuard counts
`validate_yaml` / `compile_yaml` as progress, and CreateDeliveryGuard has no
bytes to offer until a `verify_playbook` passes. So a turn that stops after
compile ended with YAML in prose and no Create button. Seen replaying the live
build row ("Build a simple playbook that blocks a malicious IP ...") on
gpt-5.4-mini: 1 of 3 runs.

The fix nudges the NEXT step (verify, then offer) and lets the loop continue --
it never forces an offer of unverified YAML. These drive the real provider loops.
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

from test_anthropic_enhance_delivery_forced import _FakeStream as _AnthropicStream
from test_anthropic_enhance_delivery_forced import _text_block, _tool_use_block, _usage
from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm._loop_helpers import (
    UNVERIFIED_DRAFT_DIRECTIVE,
    BuildProgressGuard,
)
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolUseEvent

YAML = "playbooks:\n  - name: Block IP\n"
_NAMES = ("get_step_type", "compile_yaml", "validate_yaml", "verify_playbook",
          "emit_card", "run_playbook")
_OPENAI_TOOLS = [{"type": "function", "function": {
    "name": n, "description": n,
    "parameters": {"type": "object", "properties": {}}}} for n in _NAMES]
_ANTHROPIC_TOOLS = [{"name": n, "description": n,
                     "input_schema": {"type": "object", "properties": {}}}
                    for n in _NAMES]


def _dispatch(name, args):
    if name == "verify_playbook":
        return {"ready_to_push": True, "summary": "blocks the IP"}
    if name == "emit_card":
        return {"ok": True, "card": {"type": "playbook_offer"}}
    return {"ok": True}


async def _drain(gen):
    return [ev async for ev in gen]


def _call_round(cid, name, args):
    return [_delta_chunk(tool_calls=[_tc(index=0, id=cid, name=name,
                                         args=json.dumps(args))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _text_round(text):
    return [_delta_chunk(content=text), _delta_chunk(finish="stop"), _usage_chunk()]


_RESEARCH = _call_round("c1", "get_step_type", {"name": "connector"})
_COMPILE = _call_round("c2", "compile_yaml", {"yaml": YAML})
_STOP_WITH_PROSE = _text_round("Here is the playbook: it blocks the IP on FortiGate.")
_VERIFY = _call_round("c3", "verify_playbook", {"yaml_text": YAML})
_OFFER = _call_round("c4", "emit_card", {"card_type": "playbook_offer",
                                          "payload": {"id": "o1", "summary": "s",
                                                      "yaml": YAML}})
_CLOSE = _text_round("Saved as a draft.")


def _run_openai(rounds):
    sent: list = []
    queue = [_FakeStream(r) for r in rounds]

    def _create(*_a, **kw):
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=_OPENAI_TOOLS, tags={})))
    return events, sent


def _names(events):
    return [e.name for e in events if isinstance(e, ToolUseEvent)]


def _nudges(sent):
    return sum(1 for m in sent[-1] if m.get("content") == UNVERIFIED_DRAFT_DIRECTIVE)


def test_draft_then_stop_is_nudged_into_verify_and_offer():
    events, sent = _run_openai(
        [_RESEARCH, _COMPILE, _STOP_WITH_PROSE, _VERIFY, _OFFER, _CLOSE])
    names = _names(events)
    assert "verify_playbook" in names, "the turn ended at the prose -- no nudge"
    assert "emit_card" in names, "verified but never offered"
    assert _nudges(sent) == 1
    assert isinstance(events[-1], DoneEvent)


def test_nudge_fires_at_most_once():
    # The model ignores the nudge and stops again: the turn must end, not loop.
    events, sent = _run_openai(
        [_RESEARCH, _COMPILE, _STOP_WITH_PROSE, _STOP_WITH_PROSE])
    assert len(sent) == 4, "the guard fired twice or never"
    assert _nudges(sent) == 1
    assert isinstance(events[-1], DoneEvent)


def test_no_nudge_once_verify_ran():
    # A verify that ran closes the draft loop; delivery is CreateDeliveryGuard's.
    _, sent = _run_openai([_COMPILE, _VERIFY, _OFFER, _CLOSE])
    assert all(m.get("content") != UNVERIFIED_DRAFT_DIRECTIVE
               for req in sent for m in req)


def test_no_nudge_without_a_draft():
    guard = BuildProgressGuard()
    guard.note_result("get_step_type", {}, {"ok": True})
    assert not guard.unverified_draft(set(_NAMES))


def test_no_nudge_on_a_run_request():
    guard = BuildProgressGuard()
    guard.note_result("compile_yaml", {}, {"ok": True})
    guard.note_result("run_playbook", {}, {"ok": True})
    assert not guard.unverified_draft(set(_NAMES))


def test_no_nudge_after_an_enhance_offer():
    guard = BuildProgressGuard()
    guard.note_result("compile_yaml", {}, {"ok": True})
    guard.note_result("emit_card", {"card_type": "enhancement_offer"}, {"ok": True})
    assert not guard.unverified_draft(set(_NAMES))


def test_no_nudge_when_the_slice_cannot_verify():
    guard = BuildProgressGuard()
    guard.note_result("compile_yaml", {}, {"ok": True})
    assert not guard.unverified_draft({"compile_yaml", "emit_card"})


def test_anthropic_draft_then_stop_is_nudged():
    def turn(blocks, stop):
        return _AnthropicStream([], MagicMock(content=blocks, stop_reason=stop,
                                              usage=_usage()))
    streams = [
        turn([_tool_use_block("c2", "compile_yaml", {"yaml": YAML})], "tool_use"),
        turn([_text_block("Here is the playbook.")], "end_turn"),
        turn([_tool_use_block("c3", "verify_playbook", {"yaml_text": YAML})],
             "tool_use"),
        turn([_tool_use_block("c4", "emit_card",
                              {"card_type": "playbook_offer",
                               "payload": {"id": "o1", "summary": "s",
                                           "yaml": YAML}})], "tool_use"),
        turn([_text_block("Saved.")], "end_turn"),
    ]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=streams)
    client.messages.create = AsyncMock()
    p = AnthropicProvider(model="claude-haiku-4-5-20251001", base_url="http://x",
                          api_key="x", client=client)
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.anthropic_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=_ANTHROPIC_TOOLS, tags={})))
    names = _names(events)
    assert "verify_playbook" in names and "emit_card" in names
    assert isinstance(events[-1], DoneEvent)


# The research-only nudge must tell a triage turn from a build turn by what it
# looked up: live, both advertise the same full surface.
_FULL = set(_NAMES) | {"get_record", "siem_search", "get_op_schema", "find"}


def test_a_triage_turn_is_not_nudged_to_write_a_playbook():
    guard = BuildProgressGuard()
    guard.note_result("get_record", {"record": "a"}, {"ok": True})
    guard.note_result("siem_search", {"q": "10.0.0.5"}, {"ok": True})
    guard.note_result("find", {"kind": "action", "target_type": "ip"}, {"ok": True})
    assert not guard.outstanding(_FULL)


def test_a_build_turn_that_only_researched_is_still_nudged():
    for name, args in (("get_step_type", {"name": "connector"}),
                       ("get_op_schema", {"connector": "c", "op": "o"}),
                       ("find", {"kind": "recipe", "query": "block ip"})):
        guard = BuildProgressGuard()
        guard.note_result(name, args, {"ok": True})
        assert guard.outstanding(_FULL), name
