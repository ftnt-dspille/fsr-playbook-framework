"""A run_op that errored did not check its source: the coverage ledger keeps it
unchecked and the round note says it failed (retry or report), so one error
never reads as "ServiceNow has nothing"."""
from __future__ import annotations

from fsr_playbooks.mcp_server import _citation_validator as cv

READY = {"servicenow": {"label": "ServiceNow", "kind": "tickets"},
         "virustotal": {"label": "VirusTotal", "kind": "intel"}}


def _reg(**calls):
    return {k: {"name": "run_op", "ok": ok, "args": {"connector": c}}
            for k, (c, ok) in calls.items()}


def setup_function(_):
    cv.set_turn_ready_connectors(READY)


def teardown_function(_):
    cv.set_turn_ready_connectors(None)


def test_an_errored_call_leaves_the_source_unchecked():
    reg = _reg(a=("servicenow", False), b=("virustotal", True))
    assert "ServiceNow" in cv.unchecked_ready_sources(reg)
    assert "ServiceNow" not in cv.checked_ready_sources(reg)


def test_the_note_says_it_errored_and_is_worth_retrying():
    reg = _reg(a=("servicenow", False))
    note = cv.unchecked_ready_note(reg)
    assert "Tried and errored" in note and "ServiceNow" in note and "Retry" in note


def test_a_successful_call_still_checks_the_source():
    reg = _reg(a=("servicenow", True), b=("virustotal", True))
    assert cv.unchecked_ready_sources(reg) == []
    assert cv.unchecked_ready_note(reg) == ""
