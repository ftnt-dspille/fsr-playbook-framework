"""Unattended triage: a true_positive with nothing staged gets its containment
staged in-turn (the TaskSpec post-condition; this replaced ContainmentFollowThrough).

On a live appliance, the box model ended 5 of 5 confirmed C2 auto-triage turns on the
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

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, UsageEvent
from fsr_playbooks.llm.task_spec import (
    CLOSE,
    CONTAIN,
    POLICY,
    UNATTENDED,
    TaskSpec,
    contain_stage_directive,
    specs_for_turn,
)

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


def _run(rounds, *, unattended=True, forced=None, tools=_TOOLS):
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
            tools=tools, tags=tags)))
    return events, disp, sent


def _fired(events):
    return sum(1 for e in events if isinstance(e, UsageEvent)
               and e.stop_reason == "requested_action_staged")


_ASK = contain_stage_directive(TaskSpec(CONTAIN, frozenset({"true_positive"}),
                                        source=UNATTENDED), "true_positive")


def _staged_block(disp):
    return any(c.args[0] == "run_op" for c in disp.call_args_list)


# --- the OpenAI loop --------------------------------------------------------

def test_a_true_positive_that_stops_is_asked_and_stages_the_block():
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _prose(),
                               _block_round(), _prose()])
    assert _fired(events) == 1
    assert sent[3][-1] == {"role": "user", "content": _ASK}
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
    assert after[-1] == {"role": "user", "content": _ASK}
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
    assert any(isinstance(b, dict) and b.get("text") == _ASK
               for b in last)


def _empty():
    return [_delta_chunk(finish="stop"), _usage_chunk()]


def test_an_empty_reply_after_the_verdict_is_not_replayed():
    """The live shape: the model answered its delivered verdict with
    nothing. Replayed as {"role": "assistant", "content": None} with no calls,
    that message makes the follow-through request a 400 and the turn dies."""
    events, disp, sent = _run([_hunt_round(), _verdict_round(), _empty(),
                               _block_round(), _prose()])
    assert _fired(events) == 1
    for msgs in sent:
        for m in msgs:
            if m.get("role") == "assistant":
                assert m.get("content") or m.get("tool_calls"), m
    assert sent[3][-1] == {"role": "user", "content": _ASK}
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


# --- a false positive under the admin's close rule --------------------------
# On a live appliance, an enforced close rule never closed anything: the box model
# delivered a false_positive verdict at 0.98 and ended the turn, so no close
# was staged for the policy to judge and the alert stayed open.

from contextlib import contextmanager  # noqa: E402

from fsr_playbooks.llm import session_state  # noqa: E402
from fsr_playbooks.llm.autonomy import parse_policy  # noqa: E402

_CLOSE_ALLOWED = _ALLOWED | {"update_record"}


def _close_policy(*, enabled=True, min_confidence=0.9):
    policy, err = parse_policy({
        "version": 1, "enabled": enabled, "mode": "enforce",
        "rules": [{"id": "close-false-positive",
                   "action": {"tool": "update_record", "module": "alerts",
                              "fields": ["status", "closureReason", "closureNotes"],
                              "values": {"status": ["Closed"]}},
                   "when": {"verdict": {"disposition": ["false_positive", "benign"],
                                        "min_confidence": min_confidence},
                            "target": {"kind": "record"},
                            "evidence": {"cites_tool_kind": "read"}}}]})
    assert err is None, err
    return policy


@contextmanager
def _policy(policy):
    # A fresh state for the block: a subject or policy set inside never
    # reaches the next test.
    with session_state.bound(session_state.SessionState(autonomy_policy=policy)):
        yield


def _fp(disposition="false_positive", confidence=0.95):
    return {"card_type": "verdict",
            "payload": {"disposition": disposition, "confidence": confidence}}


def _specs(policy, unattended=True):
    return specs_for_turn("triage this", unattended=unattended, policy=policy)


def test_unattended_requests_containment_and_the_policy_close():
    specs = _specs(_close_policy())
    assert [(s.requested_action, s.source) for s in specs] == [
        (CONTAIN, UNATTENDED), (CLOSE, POLICY)]
    close = specs[1]
    assert set(close.condition) == {"false_positive", "benign"}
    assert close.min_confidence == 0.9
    assert close.fields == ("status", "closureReason", "closureNotes")


def test_the_close_request_holds_only_at_the_rules_bar():
    close = _specs(_close_policy())[1]
    cases = {
        "false_positive at 0.95": ("false_positive", 0.95, True),
        "benign at 0.9": ("benign", 0.9, True),
        "below the bar": ("false_positive", 0.7, False),
        "no confidence": ("false_positive", None, False),
        "not a close verdict": ("suspicious", 0.99, False),
        "a threat": ("true_positive", 0.99, False),
    }
    for why, (d, c, want) in cases.items():
        assert close.wants(d, c) is want, why


def test_no_close_is_requested_without_an_enabled_close_rule():
    for why, policy in {"no policy": None,
                        "switched off": _close_policy(enabled=False)}.items():
        assert [s.requested_action for s in _specs(policy)] == [CONTAIN], why


def test_an_attended_turn_requests_nothing_unasked():
    assert _specs(_close_policy(), unattended=False) == ()


def _fp_round():
    return [_delta_chunk(tool_calls=[_tc(index=0, id="v1", name="emit_card",
                                         args=json.dumps(_fp()))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _close_round():
    return [_delta_chunk(tool_calls=[_tc(
                index=0, id="u1", name="update_record",
                args='{"module": "alerts", "uuid": "a", "fields": {"status": "Closed"}}')]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


_CLOSE_TOOLS = _TOOLS + [{"type": "function", "function": {
    "name": "update_record", "description": "update_record",
    "parameters": {"type": "object", "properties": {}}}}]


def _forced_close(fields):
    fn = MagicMock()
    fn.name = "update_record"
    fn.arguments = json.dumps({"module": "x", "uuid": "y", "fields": fields})
    call = MagicMock(id="c_close", function=fn)
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[call]))])


def test_the_loop_stages_the_policy_close_with_only_the_rules_fields():
    from fsr_playbooks.llm.autonomy import set_turn_subject
    with _policy(_close_policy()):
        set_turn_subject("/api/3/alerts/a1")
        events, disp, sent = _run(
            [_hunt_round(), _fp_round(), _prose(), _prose()], tools=_CLOSE_TOOLS,
            forced=_forced_close({"closureReason": "False Positive",
                                  "closureNotes": "known scanner",
                                  "severity": "Low", "status": "Open"}))
    assert _fired(events) == 1
    closes = [c.args[1] for c in disp.call_args_list if c.args[0] == "update_record"]
    # The record is the turn's, status is the close, severity is dropped.
    assert closes == [{"module": "alerts", "uuid": "a1", "fields": {
        "closureReason": "False Positive", "closureNotes": "known scanner",
        "status": "Closed"}}]
    asks = [m for m in sent[-1] if m.get("role") == "user"
            and "status (to Closed), closureReason, closureNotes" in str(m.get("content"))]
    assert len(asks) == 1


def test_the_loop_stages_no_close_below_the_bar():
    from fsr_playbooks.llm.autonomy import set_turn_subject
    low = [_delta_chunk(tool_calls=[_tc(index=0, id="v1", name="emit_card",
                                        args=json.dumps(_fp(confidence=0.7)))]),
           _delta_chunk(finish="tool_calls"), _usage_chunk()]
    with _policy(_close_policy()):
        set_turn_subject("/api/3/alerts/a1")
        events, disp, sent = _run([_hunt_round(), low, _prose()], tools=_CLOSE_TOOLS)
    assert _fired(events) == 0 and len(sent) == 3
    assert not any(c.args[0] == "update_record" for c in disp.call_args_list)


def test_the_loop_ends_a_false_positive_with_no_close_rule():
    events, _, sent = _run([_hunt_round(), _fp_round(), _prose()], tools=_CLOSE_TOOLS)
    assert len(sent) == 3
