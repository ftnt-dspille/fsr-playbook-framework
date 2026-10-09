"""Unattended triage: a true_positive with nothing staged is asked, in-turn, for
its containment.

Live on .159 the box model ended 5 of 5 confirmed C2 auto-triage turns on the
verdict card (or on the forced one), so no block was ever proposed and the
autonomy policy had nothing to act on. The ask stays inside the turn because
the policy judges a staged block against this turn's verdict and evidence.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)
from test_verdict_forced_on_full_surface import (
    _TOOLS,
    _forced_verdict_response,
    _hunt_round,
    _prose,
)

from fsr_playbooks.llm._loop_helpers import (
    UNATTENDED_CONTAIN_DIRECTIVE,
    ContainmentFollowThrough,
)
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, UsageEvent

_ALLOWED = {"run_op", "emit_card", "get_record"}


def _verdict(disposition):
    return {"card_type": "verdict", "payload": {"disposition": disposition}}


def _verdict_round(disposition="true_positive"):
    return [_delta_chunk(tool_calls=[_tc(index=0, id="v1", name="emit_card",
                                         args=json.dumps(_verdict(disposition)))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _block_round():
    return [_delta_chunk(tool_calls=[_tc(
                index=0, id="b1", name="run_op",
                args='{"connector": "fortigate", "op": "block_ip_new"}')]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


async def _drain(gen):
    return [ev async for ev in gen]


def _run(rounds, *, unattended=True, forced=None):
    """Drive the OpenAI loop. Returns (events, dispatch mock, the messages each
    streamed round was sent)."""
    streams = [_FakeStream(r) for r in rounds]
    sent: list = []

    async def _create(*_a, **kw):
        if kw.get("stream"):
            sent.append([dict(m) for m in kw["messages"]])
            return streams.pop(0)
        return forced or _forced_verdict_response()

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    tags = {"unattended": True} if unattended else {}
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(return_value={"ok": True})) as disp, \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="triage this")],
            tools=_TOOLS, tags=tags)))
    return events, disp, sent


def _fired(events):
    return sum(1 for e in events if isinstance(e, UsageEvent)
               and e.stop_reason == "containment_follow_through")


def _staged_block(disp):
    return any(c.args[0] == "run_op" for c in disp.call_args_list)


# --- the guard on its own ---------------------------------------------------

def test_a_delivered_true_positive_is_outstanding_once():
    g = ContainmentFollowThrough(enabled=True)
    g.note_result("emit_card", _verdict("true_positive"), {"ok": True})
    assert g.outstanding(_ALLOWED)
    g.mark_fired()
    assert not g.outstanding(_ALLOWED)


def test_it_is_inert_unless_unattended():
    g = ContainmentFollowThrough(enabled=False)
    g.note_result("emit_card", _verdict("true_positive"), {"ok": True})
    assert not g.outstanding(_ALLOWED)


def test_only_a_true_positive_asks():
    for d in ("false_positive", "benign", "suspicious", "needs_more_info"):
        g = ContainmentFollowThrough(enabled=True)
        g.note_result("emit_card", _verdict(d), {"ok": True})
        assert not g.outstanding(_ALLOWED), d


def test_a_refused_verdict_is_not_delivered():
    g = ContainmentFollowThrough(enabled=True)
    g.note_result("emit_card", _verdict("true_positive"),
                  {"ok": False, "code": "invalid_evidence_ids"})
    assert not g.outstanding(_ALLOWED)


def test_the_last_delivered_verdict_wins():
    g = ContainmentFollowThrough(enabled=True)
    g.note_result("emit_card", _verdict("true_positive"), {"ok": True})
    g.note_result("emit_card", _verdict("false_positive"), {"ok": True})
    assert not g.outstanding(_ALLOWED)


def test_no_staging_tool_no_ask():
    g = ContainmentFollowThrough(enabled=True)
    g.note_result("emit_card", _verdict("true_positive"), {"ok": True})
    assert not g.outstanding({"get_record"})


# --- the OpenAI loop --------------------------------------------------------

def test_a_true_positive_that_stops_is_asked_and_stages_the_block():
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _prose(),
                               _block_round(), _prose()])
    assert _fired(events) == 1
    assert sent[3][-1] == {"role": "user", "content": UNATTENDED_CONTAIN_DIRECTIVE}
    assert _staged_block(disp)


def test_it_asks_once_then_the_turn_ends():
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _prose(), _prose()])
    assert _fired(events) == 1
    assert len(sent) == 4
    assert not _staged_block(disp)


def test_an_attended_chat_is_never_asked():
    events, _, sent = _run([_hunt_round(), _verdict_round(), _prose()],
                           unattended=False)
    assert _fired(events) == 0 and len(sent) == 3


def test_a_false_positive_is_never_asked():
    events, _, sent = _run([_hunt_round(), _verdict_round("false_positive"),
                            _prose()])
    assert _fired(events) == 0 and len(sent) == 3


def test_a_forced_true_positive_is_asked_with_the_verdict_in_history():
    """The live shape: the model wrote its verdict as prose, the verdict guard
    forced it, and the turn ended there."""
    events, disp, sent = _run([_hunt_round(), _prose(), _block_round(), _prose()])
    assert _fired(events) == 1
    after = sent[2]
    assert after[-1] == {"role": "user", "content": UNATTENDED_CONTAIN_DIRECTIVE}
    # The forced verdict is answered history, not a dangling directive.
    assert after[-2]["role"] == "tool" and after[-2]["tool_call_id"] == "c_forced"
    assert after[-3]["tool_calls"][0]["function"]["name"] == "emit_card"
    assert _staged_block(disp)


def test_a_forced_false_positive_ends_the_turn():
    events, _, sent = _run([_hunt_round(), _prose()],
                           forced=_forced_verdict_response("false_positive"))
    assert _fired(events) == 0 and len(sent) == 2


# --- the Anthropic loop -----------------------------------------------------

def test_anthropic_forced_true_positive_is_asked_in_turn():
    from test_anthropic_enhance_delivery_forced import _FakeStream as _AStream
    from test_anthropic_enhance_delivery_forced import (
        _text_block,
        _tool_use_block,
        _usage,
    )
    from test_verdict_forced_on_full_surface import _FULL_SURFACE

    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider

    def _prose_stream():
        return _AStream(["Looks like a real C2 beacon."], MagicMock(
            content=[_text_block("Looks like a real C2 beacon.")],
            stop_reason="end_turn", usage=_usage()))

    hunt = _AStream([], MagicMock(content=[
        _tool_use_block("c1", "get_record", {"record": "a"}),
        _tool_use_block("c2", "siem_search", {"q": "10.0.0.5"})],
        stop_reason="tool_use", usage=_usage()))
    forced = MagicMock(content=[_tool_use_block("c_forced", "emit_card", {
        "card_type": "verdict", "payload": {
            "disposition": "true_positive", "severity": "high", "confidence": 0.9,
            "findings": [{"claim": "beacons to C2", "evidence": ["c2"]}],
            "unknowns": []}})])
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(
        side_effect=[hunt, _prose_stream(), _prose_stream()])
    client.messages.create = AsyncMock(return_value=forced)
    p = AnthropicProvider(model="claude-sonnet-5", base_url="http://x", api_key="x",
                          client=client)
    tools = [{"name": n, "description": n,
              "input_schema": {"type": "object", "properties": {}}}
             for n in _FULL_SURFACE]
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(return_value={"ok": True})), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="triage")],
            tools=tools, tags={"unattended": True})))
    assert client.messages.stream.call_count == 3, "no in-turn round after the verdict"
    msgs = client.messages.stream.call_args.kwargs["messages"]
    last = msgs[-1]["content"]
    assert any(isinstance(b, dict) and b.get("type") == "tool_result"
               and b.get("tool_use_id") == "c_forced" for b in last)
    assert any(isinstance(b, dict) and b.get("text") == UNATTENDED_CONTAIN_DIRECTIVE
               for b in last)


def _empty():
    return [_delta_chunk(finish="stop"), _usage_chunk()]


def test_an_empty_reply_after_the_verdict_is_not_replayed():
    """The live shape on .159: the model answered its delivered verdict with
    nothing. Replayed as {"role": "assistant", "content": None} with no calls,
    that message makes the follow-through request a 400 and the turn dies."""
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _empty(),
                               _block_round(), _prose()])
    assert _fired(events) == 1
    for msgs in sent:
        for m in msgs:
            if m.get("role") == "assistant":
                assert m.get("content") or m.get("tool_calls"), m
    assert sent[3][-1] == {"role": "user", "content": UNATTENDED_CONTAIN_DIRECTIVE}
    assert _staged_block(disp)


def test_the_loop_hands_each_run_op_result_to_the_evidence_reader():
    """The autonomy policy grades what a cited lookup SAID; that needs the
    provider to pass the dispatched result through to the evidence registry."""
    from fsr_playbooks.mcp_server import _citation_validator as cv
    seen = []
    cv.set_result_reader(lambda c, o, p, r: seen.append((c, o, r)) or None)
    lookup = [_delta_chunk(tool_calls=[_tc(
                  index=0, id="l1", name="run_op",
                  args='{"connector": "virustotal", "op": "query_ip", '
                       '"params": {"ip": "203.0.113.9"}}')]),
              _delta_chunk(finish="tool_calls"), _usage_chunk()]
    try:
        _run([lookup, _prose()], unattended=False)
    finally:
        cv.set_result_reader(None)
    assert seen == [("virustotal", "query_ip", {"ok": True})]
