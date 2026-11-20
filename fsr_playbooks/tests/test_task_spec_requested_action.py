"""TaskSpec, Phase 1: an action the analyst requested is staged by code once the
verdict meets its condition.

The known-answer failure class this removes: "Triage this alert ... If it is a
false positive, close it for my approval." The model delivered the verdict and
ended the turn with nothing staged. The request is now parsed from the
analyst's own words, and when the delivered verdict meets its condition the
loop stages the close itself (record and status from the request, closure
values from a round pinned to update_record). The staged call goes through the
approval tier like any other, so nothing runs without a person or the policy.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)
from test_verdict_forced_on_full_surface import _hunt_round, _prose

from fsr_playbooks.llm import session_state
from fsr_playbooks.llm.autonomy import set_turn_subject
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    Message,
    ToolUseEvent,
)
from fsr_playbooks.llm.task_spec import (
    CLOSE,
    CONTAIN,
    NONE,
    RequestedActionPostcondition,
    TaskSpec,
    parse_task_spec,
    split_subject,
)

FP = {"false_positive", "benign"}
TP = {"true_positive"}
ALERT_UUID = "5c1e2a90-1b7d-4c55-9a3e-7d0c2b1a4e02"
ALERT_IRI = f"/api/3/alerts/{ALERT_UUID}"
CLOSE_ASK = ("Triage this alert and give me your verdict. If it is a false "
             "positive, close it with the right closure reason for my approval.")


# --- the parser: every phrasing, each asserted on action AND condition -----

@pytest.mark.parametrize("text, action, cond", [
    (CLOSE_ASK, CLOSE, FP),
    ("If it's benign, close it.", CLOSE, FP),
    ("triage and if it is a FP resolve the alert", CLOSE, FP),
    ("Close it if this turns out to be harmless", CLOSE, FP),
    ("Investigate; if it's malicious, block the IP.", CONTAIN, TP),
    ("if this is a true positive isolate the host", CONTAIN, TP),
    ("Check this. If confirmed C2, contain it.", CONTAIN, TP),
    ("Close this alert.", CLOSE, FP),          # unconditional: default condition
    ("Block it.", CONTAIN, TP),
    ("What happened here? Then if it's a false positive, close it.", CLOSE, FP),
])
def test_requests_are_parsed(text, action, cond):
    spec = parse_task_spec(text)
    assert spec.requested_action == action, text
    assert set(spec.condition) == cond, text


@pytest.mark.parametrize("text", [
    "",
    None,
    "Triage this alert and give me your verdict.",
    "Should we close it?",
    "Can you block this IP?",
    "Don't close it yet, I want to look first.",
    "Do not block anything.",
    "The IP was already blocked by the firewall.",
    "This was closed yesterday by Tier 1.",
    "Is this close to the earlier incident?",
    "If it's malicious, close it.",      # a close of a threat is never staged
    "If it's a false positive, block it.",  # nor a block of a false positive
])
def test_non_requests_are_none(text):
    assert parse_task_spec(text).requested_action == NONE, text


def test_wants_matches_only_the_condition():
    spec = TaskSpec(CLOSE, frozenset(FP))
    for d in ("false_positive", "benign", " Benign "):
        assert spec.wants(d), d
    for d in ("true_positive", "suspicious", "needs_more_info", "", None):
        assert not spec.wants(d), d
    assert not TaskSpec().wants("false_positive")


def test_split_subject():
    assert split_subject(ALERT_IRI) == ("alerts", ALERT_UUID)
    assert split_subject(None) is None and split_subject("x") is None


# --- the observer --------------------------------------------------------

def _verdict_args(d):
    return {"card_type": "verdict", "payload": {"disposition": d}}


def test_due_once_after_a_delivered_matching_verdict():
    p = RequestedActionPostcondition(parse_task_spec(CLOSE_ASK))
    assert p.due() is None
    p.note_result("emit_card", _verdict_args("false_positive"), {"ok": True})
    assert p.due() == CLOSE
    p.mark_fired()
    assert p.due() is None


@pytest.mark.parametrize("name, args, result", [
    ("emit_card", {"card_type": "action", "payload": {}}, {"ok": True}),
    ("update_record", {"module": "alerts"}, {"ok": True}),
    ("run_op", {}, {"ok": True}),
    ("anything", {}, {"ok": True, "pending_approval": True}),
])
def test_anything_staged_means_not_due(name, args, result):
    p = RequestedActionPostcondition(parse_task_spec(CLOSE_ASK))
    p.note_result("emit_card", _verdict_args("benign"), {"ok": True})
    p.note_result(name, args, result)
    assert p.due() is None, name


def test_a_refused_verdict_or_mismatched_verdict_is_not_due():
    p = RequestedActionPostcondition(parse_task_spec(CLOSE_ASK))
    p.note_result("emit_card", _verdict_args("false_positive"), {"ok": False})
    assert p.due() is None
    p.note_result("emit_card", _verdict_args("true_positive"), {"ok": True})
    assert p.due() is None


# --- the OpenAI loop -----------------------------------------------------

_SURFACE = ("get_record", "find", "emit_card", "update_record", "run_op")
_TOOLS = [{"type": "function", "function": {
    "name": n, "description": n,
    "parameters": {"type": "object", "properties": {}}}} for n in _SURFACE]


def _verdict_round(d="false_positive"):
    return [_delta_chunk(tool_calls=[_tc(index=0, id="v1", name="emit_card",
                                         args=json.dumps(_verdict_args(d)))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _forced_update(fields):
    fn = MagicMock()
    fn.name = "update_record"
    # The model tries to aim the write elsewhere and leave status open: the
    # record and the close are the request's, so both are overridden.
    fn.arguments = json.dumps({"module": "incidents", "uuid": "other",
                               "fields": fields})
    call = MagicMock(id="c_close", function=fn)
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[call]))])


def _run(rounds, *, user=CLOSE_ASK, subject=ALERT_IRI, forced=None, tools=_TOOLS):
    streams = [_FakeStream(r) for r in rounds]
    sent: list = []

    async def _create(*_a, **kw):
        if kw.get("stream"):
            sent.append([dict(m) for m in kw["messages"]])
            return streams.pop(0)
        return forced or _forced_update({"status": "Open",
                                         "closureReason": "False Positive",
                                         "closureNotes": "Authorized scanner."})

    def _dispatch(name, args):
        if name == "update_record":
            return {"ok": False, "pending_approval": True, "approval_id": "ap1",
                    "tier": 3, "summary": "close alert"}
        return {"ok": True}

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    with session_state.bound(session_state.SessionState()):
        set_turn_subject(subject)
        with patch("fsr_playbooks.llm.agent_loop.dispatch",
                   MagicMock(side_effect=_dispatch)) as disp, \
             patch("fsr_playbooks.llm.agent_loop._tier_for",
                   side_effect=lambda n, a: 3 if n == "update_record" else 0), \
             patch("fsr_playbooks.llm.agent_loop._approvals.stash"):
            events = asyncio.run(_drain(p.stream(
                system="s", messages=[Message(role="user", content=user)],
                tools=tools, tags={})))
    return events, disp, sent


async def _drain(gen):
    return [ev async for ev in gen]


def _update_calls(disp):
    return [c.args[1] for c in disp.call_args_list if c.args[0] == "update_record"]


def test_a_matching_verdict_that_stops_gets_the_close_staged_by_code():
    events, disp, _ = _run([_hunt_round(), _verdict_round("false_positive"), _prose()])
    calls = _update_calls(disp)
    assert calls == [{"module": "alerts", "uuid": ALERT_UUID, "fields": {
        "status": "Closed", "closureReason": "False Positive",
        "closureNotes": "Authorized scanner."}}]
    assert any(isinstance(e, ApprovalRequestEvent) for e in events)
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done and done[-1].stop_reason == "pending_approval"
    assert any(isinstance(e, ToolUseEvent) and e.name == "update_record" for e in events)


def test_a_verdict_that_does_not_meet_the_condition_stages_nothing():
    events, disp, _ = _run([_hunt_round(), _verdict_round("true_positive"), _prose()])
    assert _update_calls(disp) == []
    assert not any(isinstance(e, ApprovalRequestEvent) for e in events)


def test_no_request_no_staging():
    _, disp, _ = _run([_hunt_round(), _verdict_round("false_positive"), _prose()],
                      user="Triage this alert and give me your verdict.")
    assert _update_calls(disp) == []


def test_no_page_subject_no_staging():
    _, disp, _ = _run([_hunt_round(), _verdict_round("false_positive"), _prose()],
                      subject=None)
    assert _update_calls(disp) == []


def test_update_record_not_advertised_no_staging():
    tools = [t for t in _TOOLS if t["function"]["name"] != "update_record"]
    _, disp, _ = _run([_hunt_round(), _verdict_round("false_positive"), _prose()],
                      tools=tools)
    assert _update_calls(disp) == []


def test_a_model_that_stages_the_close_itself_is_not_doubled():
    own = [_delta_chunk(tool_calls=[_tc(index=0, id="u1", name="update_record",
                                        args=json.dumps({"module": "alerts",
                                                         "uuid": ALERT_UUID,
                                                         "fields": {"status": "Closed"}}))]),
           _delta_chunk(finish="tool_calls"), _usage_chunk()]
    _, disp, _ = _run([_hunt_round(), _verdict_round("false_positive"), own])
    assert len(_update_calls(disp)) == 1
