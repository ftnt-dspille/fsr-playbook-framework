"""X7: the "What would help" lines on an uncertain verdict card."""
from __future__ import annotations

import re

import pytest

from fsr_playbooks.mcp_server._citation_validator import (
    TurnEvidence,
    register_tool_result,
    set_turn_evidence,
    set_turn_ready_connectors,
    set_turn_ready_sources,
)
from fsr_playbooks.mcp_server.tools_emit import emit_verdict

SNOW = {"servicenow": {"label": "ServiceNow", "kind": "tickets"}}
VT = {"virustotal": {"label": "VirusTotal", "kind": "intel"}}
BOTH = {**SNOW, **VT}
READY = {"siem_": "FortiSIEM"}
_FULL = {"ok": True, "count": 2, "events": [{"a": 1}, {"a": 2}]}
_THIN = {"ok": True, "count": 0, "events": []}

U_TICKET = "Whether this host's admin activity was approved is unknown"
U_INTEL = "The reputation of the destination address is unknown"
U_OTHER = "The user's intent is unclear"


@pytest.fixture(autouse=True)
def _reset():
    set_turn_evidence(TurnEvidence())
    yield
    set_turn_ready_sources(None)
    set_turn_ready_connectors(None)
    set_turn_evidence(None)


def _card(disposition="needs_more_info", unknowns=(U_TICKET,), cite="c1"):
    out = emit_verdict(
        disposition=disposition, severity="medium", confidence=0.4,
        summary="Unclear.", findings=[{"claim": "Host was active.", "evidence": [cite]}],
        unknowns=list(unknowns))
    assert out["ok"] is True, out
    return out["card"]


def _lines(card):
    return [h["line"] for h in card.get("what_would_help", [])]


# (case id, ready connectors, unknowns, expected kinds in order, sentence fragments)
NOT_CONNECTED = [
    ("no_tickets", INTEL := VT, [U_TICKET], ["tickets"],
     ["No ticket system is connected", "past tickets could show whether this activity was approved"]),
    ("no_intel", SNOW, [U_INTEL], ["intel"],
     ["No threat intelligence source is connected", "known to be malicious"]),
    ("neither", {}, [U_TICKET, U_INTEL], ["tickets", "intel"],
     ["No ticket system is connected", "No threat intelligence source is connected"]),
    ("tickets_present", BOTH, [U_TICKET, U_INTEL], [], []),
    ("unknown_unrelated", {}, [U_OTHER], [], []),
]


@pytest.mark.parametrize("cid,conns,unknowns,kinds,frags", NOT_CONNECTED,
                         ids=[c[0] for c in NOT_CONNECTED])
def test_not_connected_line(cid, conns, unknowns, kinds, frags):
    register_tool_result("c1", "siem_search", True, {}, _FULL)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(conns)
    card = _card(unknowns=unknowns)
    helps = card.get("what_would_help", [])
    assert [h["kind"] for h in helps if h["state"] == "not_connected"] == kinds
    text = " ".join(_lines(card))
    for f in frags:
        assert f in text
    for h in helps:
        assert h["unknown"] in unknowns  # tied to a verdict unknown


def test_each_line_is_tied_to_the_matching_unknown():
    register_tool_result("c1", "siem_search", True, {}, _FULL)
    set_turn_ready_connectors({})
    helps = {h["kind"]: h for h in _card(unknowns=[U_OTHER, U_INTEL, U_TICKET])["what_would_help"]}
    assert helps["tickets"]["unknown"] == U_TICKET
    assert helps["intel"]["unknown"] == U_INTEL


def test_unreported_connectors_make_no_not_connected_claim():
    """The host never said what is configured: silence, not a guess."""
    register_tool_result("c1", "siem_search", True, {}, _FULL)
    set_turn_ready_connectors(None)
    assert "what_would_help" not in _card()


@pytest.mark.parametrize("disp", ["true_positive", "false_positive", "benign", "suspicious"])
def test_no_line_on_a_confident_verdict(disp):
    register_tool_result("c1", "siem_search", True, {}, _FULL)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors({})
    assert "what_would_help" not in _card(disposition=disp)


def test_no_line_without_unknowns():
    register_tool_result("c1", "siem_search", True, {}, _FULL)
    set_turn_ready_connectors({})
    out = emit_verdict(disposition="needs_more_info", severity="low", confidence=0.3,
                       summary="x", findings=[{"claim": "y", "evidence": ["c1"]}])
    assert "what_would_help" not in out.get("card", {})


def test_failed_source_line_names_the_label():
    register_tool_result("c1", "siem_search", False, {}, {"ok": False, "error": "timeout"})
    register_tool_result("c2", "run_op", True, {"connector": "servicenow"}, _FULL)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(SNOW)
    card = _card(unknowns=[U_OTHER], cite="c2")
    (h,) = card["what_would_help"]
    assert h["state"] == "failed" and h["sources"] == ["FortiSIEM"]
    assert h["line"].startswith("FortiSIEM returned an error this turn")
    assert h["unknown"] == U_OTHER


def test_a_source_that_failed_once_but_answered_is_not_failed():
    register_tool_result("c1", "siem_search", False, {}, {"ok": False})
    register_tool_result("c2", "siem_search", True, {}, _FULL)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(BOTH)
    assert "what_would_help" not in _card(unknowns=[U_OTHER], cite="c2")


def test_data_gap_line():
    register_tool_result("c1", "siem_search", True, {}, _THIN)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(BOTH)
    card = _card(unknowns=[U_OTHER])
    (h,) = card["what_would_help"]
    assert h["state"] == "no_data" and h["sources"] == ["FortiSIEM"]
    assert "FortiSIEM was searched and returned nothing" in h["line"]


def test_at_most_three_lines():
    register_tool_result("c1", "siem_search", False, {}, {"ok": False})
    register_tool_result("c2", "run_op", True, {"connector": "x"}, _THIN)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors({})
    card = _card(unknowns=[U_TICKET, U_INTEL], cite="c2")
    assert 1 <= len(card["what_would_help"]) <= 3


def test_analyst_text_has_no_tool_names_dashes_or_emoji():
    register_tool_result("c1", "siem_search", False, {}, {"ok": False})
    register_tool_result("c2", "run_op", True, {"connector": "virustotal"}, _THIN)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(VT)
    card = _card(unknowns=[U_TICKET, U_INTEL], cite="c2")
    assert len(card["what_would_help"]) >= 2
    for line in _lines(card):
        assert not re.search(r"\b[a-z]+_[a-z_]+\b", line)
        assert "run_op" not in line
        assert "—" not in line and "–" not in line
        assert line.isascii()


# ---- plural grammar, genuine searches only, and the log-source kind ----------
U_LOGS = "Firewall or flow logs for the three connections (bytes, direction, process)"


def test_two_empty_sources_read_in_the_plural():
    register_tool_result("c1", "siem_search", True, {}, _THIN)
    register_tool_result("c2", "run_op", True,
                         {"connector": "servicenow", "op": "search_records"}, _THIN)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(SNOW)
    (h,) = _card(unknowns=[U_OTHER], cite="c2")["what_would_help"]
    assert h["line"].startswith("FortiSIEM and ServiceNow were searched and returned nothing")
    assert "no data from them either way" in h["line"]


def test_two_failed_sources_read_in_the_plural():
    register_tool_result("c1", "siem_search", False, {}, {"ok": False})
    register_tool_result("c2", "run_op", False, {"connector": "servicenow"}, {"ok": False})
    register_tool_result("c3", "run_op", True, {"connector": "virustotal"}, _FULL)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors({**SNOW, **VT})
    (h,) = _card(unknowns=[U_OTHER], cite="c3")["what_would_help"]
    assert h["line"].startswith("FortiSIEM and ServiceNow returned an error this turn")
    assert "their answers are missing" in h["line"]
    assert "fixing the connections would let me check them" in h["line"]


_NOT_SEARCHES = [
    ("op_unavailable_error", {"ok": True, "error": "operation not available"}),
    ("op_unavailable_text", {"ok": True, "message": "no such operation"}),
    ("missing_body", None),
]


@pytest.mark.parametrize("cid,result", _NOT_SEARCHES, ids=[c[0] for c in _NOT_SEARCHES])
def test_a_call_that_did_not_search_is_not_a_data_gap(cid, result):
    register_tool_result("c1", "siem_search", True, {}, _FULL)
    register_tool_result("c2", "run_op", True, {"connector": "servicenow"}, result)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(BOTH)
    card = _card(unknowns=[U_OTHER], cite="c1")
    assert not [h for h in card.get("what_would_help", []) if h["state"] == "no_data"]


def test_a_source_with_one_empty_search_and_one_answer_is_not_a_data_gap():
    register_tool_result("c1", "siem_search", True, {}, _THIN)
    register_tool_result("c2", "siem_search", True, {}, _FULL)
    set_turn_ready_sources(READY)
    set_turn_ready_connectors(BOTH)
    assert "what_would_help" not in _card(unknowns=[U_OTHER], cite="c2")


LOG_CASES = [
    ("no_log_source_ready", {}, [U_LOGS], True),
    ("log_source_ready_not_queried", READY, [U_LOGS], False),
    ("roster_unreported", None, [U_LOGS], False),
    ("unrelated_unknown", {}, [U_OTHER], False),
]


@pytest.mark.parametrize("cid,ready,unknowns,expect", LOG_CASES, ids=[c[0] for c in LOG_CASES])
def test_no_log_source_line(cid, ready, unknowns, expect):
    register_tool_result("c1", "get_record", True, {}, _FULL)
    set_turn_ready_sources(ready)
    set_turn_ready_connectors(BOTH)
    card = _card(unknowns=unknowns)
    logs = [h for h in card.get("what_would_help", []) if h["kind"] == "logs"]
    if not expect:
        assert logs == []
        return
    (h,) = logs
    assert h["state"] == "not_connected"
    assert h["unknown"] == U_LOGS
    assert h["line"] == ("No log source such as a SIEM or firewall log store is connected; "
                         "session logs could show whether these connections completed and "
                         "how much data moved.")


_OPS = [("search_incidents", True), ("query_ip", True), ("list_tickets", True),
        ("create_alert", False), ("add_note", False), ("", False)]


@pytest.mark.parametrize("op,counts", _OPS, ids=[o[0] or "no_op" for o in _OPS])
def test_only_a_read_operation_that_came_back_empty_is_a_data_gap(op, counts):
    """An action op that hands back an empty body searched nothing."""
    register_tool_result("c1", "run_op", True, {"connector": "servicenow", "op": op}, _THIN)
    set_turn_ready_sources({})
    set_turn_ready_connectors(SNOW)
    card = _card(unknowns=[U_OTHER], cite="c1")
    gaps = [h for h in card.get("what_would_help", []) if h["state"] == "no_data"]
    assert bool(gaps) is counts
    if counts:
        assert gaps[0]["sources"] == ["ServiceNow"]


# X7: a lookup that could not run its search is not a data gap.
_COULD_NOT_SEARCH = [
    ("outbreak_blank_params", "get_outbreak_alert_iocs", {"campaign_tag": ""},
     {"ok": True, "data": []}),
    ("outbreak_empty_params", "get_outbreak_alert_iocs", {},
     {"ok": True, "data": []}),
    ("skipped_flag", "search_incidents", {"ip": "1.2.3.4"},
     {"ok": True, "data": [], "skipped": True}),
    ("refused_flag", "search_incidents", {"ip": "1.2.3.4"},
     {"ok": True, "records": [], "refused": True}),
    ("noop_status", "search_incidents", {"ip": "1.2.3.4"},
     {"ok": True, "records": [], "status": "no-op"}),
    ("nested_flag", "search_incidents", {"ip": "1.2.3.4"},
     {"ok": True, "data": {"records": [], "skipped": True}}),
]


@pytest.mark.parametrize("cid,op,params,result", _COULD_NOT_SEARCH,
                         ids=[c[0] for c in _COULD_NOT_SEARCH])
def test_a_lookup_that_could_not_search_is_not_a_data_gap(cid, op, params, result):
    register_tool_result("c1", "run_op",
                         True, {"connector": "servicenow", "op": op, "params": params},
                         result)
    set_turn_ready_sources({})
    set_turn_ready_connectors(SNOW)
    card = _card(unknowns=[U_OTHER], cite="c1")
    assert not [h for h in card.get("what_would_help", []) if h["state"] == "no_data"]


_REAL_EMPTY = [
    ("window_search", "search_incidents", {"ip": "1.2.3.4", "hours": 24},
     {"ok": True, "records": []}),
    ("indicator_lookup", "get_ioc_matches", {"indicator": "evil.example"},
     {"ok": True, "data": [], "count": 0}),
    ("no_params_listing", "list_tickets", None, {"ok": True, "records": []}),
    # Prose only: no structured signal, so it stays counted as a search (the
    # words are not read, in any language).
    ("prose_only_message", "get_outbreak_alert_iocs", {"campaign_tag": "x"},
     {"ok": True, "data": [], "message": "campaign tag is required"}),
]


@pytest.mark.parametrize("cid,op,params,result", _REAL_EMPTY, ids=[c[0] for c in _REAL_EMPTY])
def test_a_real_search_that_matched_nothing_is_still_a_data_gap(cid, op, params, result):
    args = {"connector": "servicenow", "op": op}
    if params is not None:
        args["params"] = params
    register_tool_result("c1", "run_op", True, args, result)
    set_turn_ready_sources({})
    set_turn_ready_connectors(SNOW)
    card = _card(unknowns=[U_OTHER], cite="c1")
    gaps = [h for h in card.get("what_would_help", []) if h["state"] == "no_data"]
    assert gaps and gaps[0]["sources"] == ["ServiceNow"]
