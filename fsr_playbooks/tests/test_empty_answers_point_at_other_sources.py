"""An empty or unserved answer is one source holding nothing, not the end of the
hunt. The per-round tail note names the sources that came back empty (typed
flags on the evidence registry, not wording) and says the other configured
sources can take the same key."""
from fsr_playbooks.mcp_server import _citation_validator as cv

READY = {"servicenow": {"label": "ServiceNow", "kind": "tickets"}}


def setup_function(_):
    cv.set_turn_ready_connectors(READY)


def teardown_function(_):
    cv.set_turn_ready_connectors(None)


def _e(name, ok, thin=None, connector=None):
    e = {"name": name, "ok": ok}
    if connector:
        e["args"] = {"connector": connector}
    if thin is not None:
        e["thin"] = thin
    return e


def test_empty_hunt_calls_are_named_as_dry():
    reg = {"a": _e("siem_search", False), "b": _e("prior_cases", True, thin=True),
           "c": _e("run_op", True, thin=True, connector="activedirectory")}
    assert cv.dry_sources(reg) == ["siem_search", "prior_cases", "activedirectory"]


def test_a_source_that_also_answered_is_not_dry():
    reg = {"a": _e("run_op", True, thin=True, connector="servicenow"),
           "b": _e("run_op", True, thin=False, connector="servicenow")}
    assert cv.dry_sources(reg) == []


def test_discovery_and_record_reads_are_never_dry():
    reg = {"a": _e("find", True, thin=True), "b": _e("search_module_records", True, thin=True)}
    assert cv.dry_sources(reg) == []


def test_the_note_points_the_empty_result_at_other_sources():
    reg = {"a": _e("siem_search", False), "b": _e("prior_cases", True, thin=True),
           "c": _e("run_op", True, thin=False, connector="virustotal")}
    note = cv.unchecked_ready_note(reg)
    assert "Came back empty or errored: the log search, earlier cases" in note
    assert "ServiceNow" in note and "same key" in note


def test_no_empty_call_no_such_sentence():
    reg = {"c": _e("run_op", True, thin=False, connector="virustotal")}
    assert "empty or errored" not in cv.unchecked_ready_note(reg)


def test_a_plain_question_is_not_turned_into_a_hunt():
    # Not investigating (no run_op, no checked source): the empty result of a
    # record read adds nothing.
    reg = {"a": _e("find", True, thin=True)}
    assert cv.unchecked_ready_note(reg) == ""


def test_search_envelope_with_no_rows_is_empty():
    assert cv.payload_is_empty({"result": []})
    assert cv.payload_is_empty([])
    assert not cv.payload_is_empty({"result": [{"a": 1}]})
    assert not cv.payload_is_empty({"count": 0})
