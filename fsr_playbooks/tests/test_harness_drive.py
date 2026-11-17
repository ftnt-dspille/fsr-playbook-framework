"""The shared conversation driver (fsr_playbooks.harness.drive).

One test per behaviour in the driver inventory. A halt is answered by policy,
a turn that did not answer is never graded as one, history is what the next
turn sees, and every transport choice (sync or detached, version and config
are the caller's) reaches the box exactly as the caller built it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fsr_playbooks.harness import drive as D
from fsr_playbooks.harness import frames as F


class _Scripted:
    """A transport that replays canned envelopes and records what it was sent."""

    def __init__(self, turns, resumes=()):
        self.session_id = "s-test"
        self._turns, self._resumes = list(turns), list(resumes)
        self.sent: list[tuple[str, dict]] = []

    def turn(self, params):
        self.sent.append(("turn", dict(params)))
        return self._turns.pop(0)

    def resume(self, params):
        self.sent.append(("resume", dict(params)))
        return self._resumes.pop(0)


class _Boom(_Scripted):
    def resume(self, params):
        self.sent.append(("resume", dict(params)))
        raise RuntimeError("down")


_HALT = {"ok": True, "stop_reason": "approval_required", "transcript": [
    {"type": "text", "text": "Running it."},
    {"type": "tool_use", "id": "t1", "name": "run_playbook", "input": {}},
    {"type": "approval_request", "approval_id": "ap1", "tool": "run_playbook"}]}
_DONE = {"ok": True, "stop_reason": "end_turn",
         "transcript": [{"type": "text", "text": "Done."}]}


class _Fsr:
    """An `Executor`: records each execute and answers from a per-op script."""

    def __init__(self, answers):
        self.answers = answers          # op -> list of data dicts (or one dict)
        self.calls: list[tuple[str, dict, object]] = []

    def execute(self, op, params, *, timeout=None):
        self.calls.append((op, params, timeout))
        got = self.answers[op]
        data = got.pop(0) if isinstance(got, list) else got
        if isinstance(data, Exception):
            raise data
        return SimpleNamespace(data=data, ok=data.get("ok", True) if isinstance(data, dict) else True,
                               error=data.get("error") if isinstance(data, dict) else None)


# ------------------------------------------------------------ errors, shape
def test_bad_step_shape_is_drive_error():
    with pytest.raises(D.DriveError, match="expected 'user' or 'resume'"):
        D.drive(_Scripted([]), {"steps": [{"foo": 1}]})


def test_resume_without_a_prior_turn_is_drive_error():
    with pytest.raises(D.DriveError, match="no turn preceded it"):
        D.drive(_Scripted([]), {"steps": [{"resume": {"decision": "approve"}}]})


def test_driver_needs_only_session_id_turn_resume():
    """The transport is duck-typed: a session id and two methods, nothing else."""
    class Minimal:
        session_id = "m"

        def turn(self, params):
            return _DONE

        def resume(self, params):
            return _DONE

    (step,) = D.drive(Minimal(), {"steps": [{"user": "hi"}]})
    assert step.outcome.kind == "answered"


def test_halt_types_are_the_frame_reader_set():
    assert D.HALT_TYPES == F.HALT_FRAME_TYPES


# ---------------------------------------------------------- answer + halts
def test_a_halt_is_answered_by_the_policy_and_both_envelopes_are_kept():
    t = _Scripted([_HALT], [_DONE])

    def approve(halts, env):
        assert [h["type"] for h in halts] == ["approval_request"]
        return t.resume({"decision": "approve", "approval_id": halts[0]["approval_id"]})

    trace = D.drive(t, {"steps": [{"user": "run it"}]}, answer=approve)
    (step,) = trace
    assert step.answered_halts == 1
    assert [e["stop_reason"] for e in step.envelopes] == ["approval_required", "end_turn"]
    assert step.tools == ["run_playbook"]
    assert step.text == "Running it.Done."
    assert step.outcome.kind == "answered"


def test_without_a_policy_a_halt_stops_the_step_and_is_recorded():
    trace = D.drive(_Scripted([_HALT]), {"steps": [{"user": "run it"}]})
    assert trace[0].halt == {"key": "approval_id", "value": "ap1", "kind": "approval"}
    assert trace[0].outcome.kind == "halted"


def test_answer_returning_none_stops_at_halt():
    t = _Scripted([_HALT])
    trace = D.drive(t, {"steps": [{"user": "run it"}]}, answer=lambda halts, env: None)
    (step,) = trace
    assert step.answered_halts == 0
    assert len(step.envelopes) == 1
    assert len(t.sent) == 1


def test_max_halts_bounds_the_answer_loop():
    t = _Scripted([_HALT], [_HALT, _HALT, _HALT, _HALT])

    def always_halt(halts, env):
        return t.resume({"decision": "approve", "approval_id": "ap1"})

    (step,) = D.drive(t, {"steps": [{"user": "run it"}]}, answer=always_halt, max_halts=2)
    assert step.answered_halts == 2
    assert len(step.envelopes) == 3


def test_each_step_carries_its_outcome():
    trace = D.drive(_Scripted([_DONE, _HALT]), {"steps": [{"user": "a"}, {"user": "b"}]})
    assert [s.outcome.kind for s in trace] == ["answered", "halted"]


def test_trace_step_properties_span_every_envelope():
    t = _Scripted([_HALT], [_DONE])

    def approve(halts, env):
        return t.resume({"decision": "approve", "approval_id": "ap1"})

    (step,) = D.drive(t, {"steps": [{"user": "run it"}]}, answer=approve)
    assert step.envelope is step.envelopes[-1]
    assert step.stop == "end_turn"
    assert step.guards == []
    assert step.halt is None
    types = [f["type"] for f in step.transcript]
    assert types == ["text", "tool_use", "approval_request", "text"]


# ------------------------------------------------------------- resume step
def test_a_resume_step_with_nothing_to_resume_is_an_outcome_not_a_crash():
    trace = D.drive(_Scripted([_DONE]), {"steps": [{"user": "hi"}, {"resume": {}}]})
    assert trace[1].error == "no pending halt to resume"


def test_a_resume_step_answers_the_last_halt_with_its_decision():
    t = _Scripted([_HALT], [_DONE])
    D.drive(t, {"steps": [{"user": "run it"}, {"resume": {"decision": "approve"}}]})
    op, params = t.sent[-1]
    assert op == "resume"
    assert params == {"session_id": "s-test", "decision": "approve", "approval_id": "ap1"}


def test_resume_with_explicit_id_uses_key_and_value():
    t = _Scripted([_DONE], [_DONE])
    D.drive(t, {"steps": [{"user": "hi"},
                          {"resume": {"id": "c9", "decision": "choose", "key": "choice_id",
                                      "value": "yes"}}]})
    assert t.sent[-1][1] == {"session_id": "s-test", "decision": "choose",
                             "choice_id": "c9", "value": "yes"}


def test_resume_with_id_defaults_to_card_id():
    t = _Scripted([_DONE], [_DONE])
    D.drive(t, {"steps": [{"user": "hi"}, {"resume": {"id": "c9"}}]})
    assert t.sent[-1][1] == {"session_id": "s-test", "decision": "approve", "card_id": "c9"}


def test_resume_params_hook_rewrites_request():
    t = _Scripted([_HALT], [_DONE])
    D.drive(t, {"steps": [{"user": "run it"}, {"resume": {"decision": "approve"}}]},
            resume_params=lambda raw, halt: {"session_id": "x", "custom": halt["value"]})
    assert t.sent[-1][1] == {"session_id": "x", "custom": "ap1"}


def test_resume_exception_is_recorded_and_drive_continues():
    t = _Boom([_HALT, _DONE])
    trace = D.drive(t, {"steps": [{"user": "run it"}, {"resume": {"decision": "approve"}},
                                  {"user": "next"}]})
    assert trace[1].error == "RuntimeError: down"
    assert trace[1].envelopes == []
    assert len(trace) == 3
    assert trace[2].outcome.kind == "answered"


def test_resume_without_halt_is_sent_when_asked():
    t = _Scripted([_DONE], [_DONE])
    trace = D.drive(t, {"steps": [{"user": "hi"}, {"resume": {"decision": "approve"}}]},
                    resume_without_halt=True)
    assert trace[1].error is None
    assert t.sent[-1] == ("resume", {"session_id": "s-test", "decision": "approve"})


def test_resume_without_halt_is_recorded_unless_asked():
    t = _Scripted([_DONE])
    trace = D.drive(t, {"steps": [{"user": "hi"}, {"resume": {"decision": "approve"}}]})
    assert trace[1].error == "no pending halt to resume"
    assert all(op == "turn" for op, _ in t.sent)


# ----------------------------------------------------------- steps and turns
def test_steps_default_to_spec_and_next_step_chooses_more():
    t = _Scripted([_DONE, _DONE, _DONE])
    chosen = iter([{"user": "third"}])

    def nxt(trace):
        return next(chosen, None)

    trace = D.drive(t, {"steps": [{"user": "first"}, {"user": "second"}]}, next_step=nxt)
    assert [s.sent for s in trace] == ["first", "second", "third"]


def test_steps_kwarg_overrides_the_spec():
    t = _Scripted([_DONE])
    trace = D.drive(t, {"steps": [{"user": "from spec"}]}, steps=[{"user": "from kwarg"}])
    assert [s.sent for s in trace] == ["from kwarg"]


def test_max_steps_bounds_next_step():
    t = _Scripted([_DONE] * 5)
    trace = D.drive(t, {"steps": []}, next_step=lambda tr: {"user": "more"}, max_steps=2)
    assert len(trace) == 2


def test_per_step_intent_overrides_default_intent():
    t = _Scripted([_DONE, _DONE])
    D.drive(t, {"steps": [{"user": "a", "intent": "build"}, {"user": "b"}]}, intent="triage")
    assert [p["intent"] for _, p in t.sent] == ["build", "triage"]


def test_entity_is_sent_only_when_given():
    t = _Scripted([_DONE, _DONE])
    D.drive(t, {"steps": [{"user": "a"}]}, entity={"module": "alerts"})
    D.drive(t, {"steps": [{"user": "b"}]})
    assert t.sent[0][1]["entity"] == {"module": "alerts"}
    assert "entity" not in t.sent[1][1]


def test_turn_params_hook_adds_to_each_turn():
    t = _Scripted([_DONE, _DONE])
    D.drive(t, {"steps": [{"user": "a"}, {"user": "b"}]},
            turn_params=lambda raw: {"record": {"echo": raw["user"]}})
    assert [p["record"] for _, p in t.sent] == [{"echo": "a"}, {"echo": "b"}]


def test_history_is_the_block_list_by_default_and_prose_on_request():
    blocks = _Scripted([_DONE, _DONE])
    D.drive(blocks, {"steps": [{"user": "a"}, {"user": "b"}]})
    assert blocks.sent[1][1]["messages"][1]["content"] == [{"type": "text", "text": "Done."}]

    prose = _Scripted([_DONE, _DONE])
    D.drive(prose, {"steps": [{"user": "a"}, {"user": "b"}]}, history="text")
    assert prose.sent[1][1]["messages"][1]["content"] == "Done."


def test_blocks_history_keeps_tool_use_blocks():
    """A native tool replay is what the next turn sees: the tool_use id survives."""
    t = _Scripted([_HALT, _DONE], [_DONE])

    def approve(halts, env):
        return t.resume({"decision": "approve", "approval_id": "ap1"})

    D.drive(t, {"steps": [{"user": "run it"}, {"user": "next"}]}, answer=approve)
    turns = [p for op, p in t.sent if op == "turn"]
    content = turns[1]["messages"][1]["content"]
    assert {"type": "tool_use", "id": "t1", "name": "run_playbook", "input": {}} in content


def test_a_history_policy_sees_one_summary_per_step():
    t = _Scripted([_HALT, _DONE], [_DONE])
    seen = []

    def approve(halts, env):
        return t.resume({"decision": "approve", "approval_id": "ap1"})

    D.drive(t, {"steps": [{"user": "run it"}, {"user": "next"}]}, answer=approve,
            history=lambda st: (seen.append(st.index), "(summary)")[1])
    assert seen == [1, 2]  # one summary per step, not one per envelope
    assert t.sent[2][1]["messages"][1] == {"role": "assistant", "content": "(summary)"}


def test_a_bad_history_mode_is_refused():
    with pytest.raises(ValueError):
        D.drive(_Scripted([]), {"steps": []}, history="markdown")


def test_on_step_can_queue_a_repeat_step():
    t = _Scripted([_DONE, _DONE])
    trace = D.drive(t, {"steps": [{"user": "first"}]},
                    on_step=lambda st: [{"user": "again"}] if st.index == 1 else None)
    assert [s.sent for s in trace] == ["first", "again"]


# ------------------------------------------------------------- detached path
def test_detached_turn_refuses_a_turn_that_did_not_answer(monkeypatch):
    """A provider rejection is a drive error, never a graded answer."""
    calls = []

    def execute(op, params, timeout=None):
        calls.append(op)
        if op == "chat_turn":
            return SimpleNamespace(data={"ok": True, "accepted": True}, ok=True, error=None)
        return SimpleNamespace(data={"done": True, "turn": 1, "stop_reason": "error",
                                     "frames": [{"type": "error", "message": "403 model_blocked"}]},
                               ok=True, error=None)

    fsr = SimpleNamespace(execute=execute)
    with pytest.raises(D.DriveError, match="did not answer"):
        D.detached_turn(fsr, session_id="s", intent="build", messages=[])
    assert calls == ["chat_turn", "chat_poll"]


def test_a_failed_ack_is_a_drive_error():
    fsr = SimpleNamespace(execute=lambda op, p, timeout=None: SimpleNamespace(
        data={"ok": False, "error": "no"}, ok=False, error="no"))
    with pytest.raises(D.DriveError, match="ack failed"):
        D.detached_turn(fsr, session_id="s", intent="build", messages=[])


def test_detached_turn_returns_turn_transcript_and_stop():
    fsr = _Fsr({
        "chat_turn": {"ok": True, "accepted": True},
        "chat_poll": {"done": True, "turn": 3, "frames": [
            {"type": "stream_end", "stop_reason": "end_turn",
             "transcript": [{"type": "text", "text": "hi"}]}]},
    })
    turn, transcript, stop = D.detached_turn(fsr, session_id="s", intent="triage",
                                             messages=[{"role": "user", "content": "x"}])
    assert (turn, stop) == (3, "end_turn")
    assert transcript == [{"type": "text", "text": "hi"}]
    op, params, _ = fsr.calls[0]
    assert op == "chat_turn" and params["detached"] is True and params["intent"] == "triage"


def test_detached_ack_accepted_by_stop_reason():
    fsr = _Fsr({
        "chat_turn": {"ok": True, "stop_reason": "accepted"},
        "chat_poll": {"done": True, "turn": 1, "stop_reason": "end_turn", "frames": [
            {"type": "stream_end", "transcript": [{"type": "text", "text": "ok"}]}]},
    })
    turn, transcript, stop = D.detached_turn(fsr, session_id="s", intent="build", messages=[])
    assert turn == 1 and stop == "end_turn"


def test_poll_advances_cursor_and_fences_since_turn(monkeypatch):
    monkeypatch.setattr(D, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None))
    fsr = _Fsr({"chat_poll": [
        {"done": False, "cursor": 3, "frames": []},
        {"done": True, "cursor": 5, "turn": 2, "frames": [
            {"type": "stream_end", "transcript": [], "stop_reason": "end_turn"}]},
    ]})
    D.poll_to_done(fsr, "sess", 7)
    assert [p["cursor"] for _, p, _ in fsr.calls] == [0, 3]
    assert all(p["since_turn"] == 7 for _, p, _ in fsr.calls)


def test_poll_takes_stream_end_transcript_and_stop(monkeypatch):
    monkeypatch.setattr(D, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None))
    fsr = _Fsr({"chat_poll": {"done": True, "turn": 4, "frames": [
        {"type": "text", "text": "partial"},
        {"type": "stream_end", "transcript": [{"type": "text", "text": "full"}],
         "stop_reason": "max_tokens"}]}})
    turn, transcript, stop = D.poll_to_done(fsr, "sess", 0)
    assert (turn, transcript, stop) == (4, [{"type": "text", "text": "full"}], "max_tokens")


def test_poll_stop_reason_falls_back_to_the_response(monkeypatch):
    monkeypatch.setattr(D, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None))
    fsr = _Fsr({"chat_poll": {"done": True, "turn": 1, "stop_reason": "end_turn", "frames": []}})
    assert D.poll_to_done(fsr, "sess", 0) == (1, None, "end_turn")


def test_poll_failure_is_drive_error(monkeypatch):
    monkeypatch.setattr(D, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None))
    fsr = _Fsr({"chat_poll": {"ok": False, "error": "gone"}})
    with pytest.raises(D.DriveError, match="chat_poll failed: gone"):
        D.poll_to_done(fsr, "sess", 0, label="build")


def test_poll_timeout_raises_and_sleeps_between_polls(monkeypatch):
    sleeps = []
    clock = iter([0.0, 0.0, 1.0, 2.0, 1000.0])
    monkeypatch.setattr(D, "time", SimpleNamespace(time=lambda: next(clock),
                                                   sleep=lambda s: sleeps.append(s)))
    fsr = _Fsr({"chat_poll": [{"done": False, "cursor": 0, "frames": []}] * 3})
    with pytest.raises(TimeoutError, match="never reached done within 5s"):
        D.poll_to_done(fsr, "sess", 0, timeout=5)
    assert sleeps == [0.7, 0.7, 0.7]


def test_sync_turn_sends_no_detached_key_and_returns_envelope():
    fsr = _Fsr({"chat_turn": {"ok": True, "stop_reason": "end_turn", "transcript": []}})
    t = D.FsrTransport(fsr, session_id="sess")
    env = t.turn({"session_id": "sess", "intent": "triage", "messages": []})
    op, params, timeout = fsr.calls[0]
    assert op == "chat_turn"
    assert "detached" not in params
    assert env["stop_reason"] == "end_turn"


def test_fsr_transport_default_session_id():
    t = D.FsrTransport(_Fsr({}))
    assert t.session_id.startswith("drive-") and len(t.session_id) == len("drive-") + 10


def test_call_turns_error_only_response_into_failure():
    class ErrOnly:
        def execute(self, op, params, *, timeout=None):
            return SimpleNamespace(data=None, ok=False, error="boom")

    t = D.FsrTransport(ErrOnly())
    assert t.turn({"messages": []}) == {"ok": False, "error": "boom"}


def test_timeout_is_passed_to_execute():
    fsr = _Fsr({"chat_turn": {"ok": True}})
    D.FsrTransport(fsr, timeout=77).turn({"messages": []})
    assert fsr.calls[0][2] == 77


def test_resume_is_a_sync_chat_resume():
    fsr = _Fsr({"chat_resume": {"ok": True, "stop_reason": "end_turn", "transcript": []}})
    env = D.FsrTransport(fsr, session_id="s").resume({"session_id": "s", "decision": "approve"})
    assert fsr.calls[0][0] == "chat_resume"
    assert env["stop_reason"] == "end_turn"


def test_detached_transport_advances_turn_number(monkeypatch):
    monkeypatch.setattr(D, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda s: None))
    fsr = _Fsr({"chat_turn": {"ok": True, "accepted": True},
                "chat_poll": {"done": True, "turn": 4, "frames": [
                    {"type": "stream_end", "transcript": []}]}})
    t = D.FsrTransport(fsr, detached=True, session_id="s")
    t.turn({"messages": []})
    assert t.turn_no == 4


def test_trace_step_guards_and_halt_properties():
    """guards come from every envelope's tags; halt is what the LAST envelope waits on."""
    guarded = {"ok": True, "stop_reason": "end_turn", "tags": {"guards_fired": ["hunt_floor"]},
               "transcript": [{"type": "text", "text": "x"}]}
    t = _Scripted([guarded, _HALT])
    trace = D.drive(t, {"steps": [{"user": "a"}, {"user": "b"}]})
    assert trace[0].guards == ["hunt_floor"]
    assert trace[0].halt is None
    assert trace[1].guards == []
    assert trace[1].halt == {"key": "approval_id", "value": "ap1", "kind": "approval"}
