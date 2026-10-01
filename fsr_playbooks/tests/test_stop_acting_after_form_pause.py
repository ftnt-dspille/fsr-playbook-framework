"""Once a playbook run pauses on a form, the analyst is the next actor.

Live, the model read the pause result's "resume it with resume_playbook(...)",
resumed the run itself four seconds later with no inputs, and the run failed
on the empty device pick. The transcript, cut at the form card, showed none of
it, and the analyst's submit then found the form gone.

Same seat as the approval-card stop: `TriageDiscipline`, which all three
providers route their dispatch through.
"""
from __future__ import annotations

from fsr_playbooks.llm._loop_helpers import TriageDiscipline

_FORM = {"ok": False, "code": "awaiting_input", "run_pk": "80926",
         "awaiting": {"manual_input_id": 650, "title": "Choose a Manager and a Device",
                      "fields": [{"name": "managerAndDevice", "data_type": "dynamicList"}],
                      "options": [{"option": "Ok", "primary": True}]}}
_BUTTONS_ONLY = {"ok": False, "code": "awaiting_input", "run_pk": "80926",
                 "awaiting": {"manual_input_id": 651, "title": "Results",
                              "fields": [], "options": [{"option": "Ok", "primary": True}]}}


def _paused(result=_FORM) -> TriageDiscipline:
    d = TriageDiscipline(authoring=False, user_text="validate this metadata source")
    d.note_result("run_playbook", {"playbook": "Get Metadata Source Data on Device"}, result)
    return d


def test_the_model_cannot_answer_the_form_itself() -> None:
    guard = _paused().evaluate("resume_playbook", {"run": "80926", "decision": "approve"})
    assert guard is not None, "the agent resumed a form the analyst had not filled"
    assert guard["form_pending"] is True


def test_nothing_else_runs_either_and_it_is_a_deferral() -> None:
    guard = _paused().evaluate("get_record", {"module": "ztpf_devices", "uuid": "x"})
    assert guard["ok"] is True and guard["kind"] == "guard_defer"
    assert "do not resume" in guard["directive"].lower()


def test_a_buttons_only_pause_does_not_stop_the_agent() -> None:
    """A pause with nothing to fill is the model's to answer."""
    assert _paused(_BUTTONS_ONLY).evaluate("resume_playbook", {"run": "80926"}) is None


def test_a_run_that_did_not_pause_does_not_stop_the_agent() -> None:
    d = TriageDiscipline(authoring=False, user_text="run it")
    d.note_result("run_playbook", {}, {"ok": True, "status": "finished"})
    assert d.evaluate("get_record", {"module": "alerts", "uuid": "x"}) is None
