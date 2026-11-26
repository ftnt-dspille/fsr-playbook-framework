"""A result reveals a key; nothing searches it; the turn is not done.

Live (round 8): a weak model stops once hop 1 gives a benign story and never sends
the host, account or address a result just named back to the source holding its
activity. The check reads typed values off run_op results (shape and field name,
never prose) and holds the turn open, bounded, naming the key and the sources
that can take it.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._pivot_keys import pivot_keys
from fsr_playbooks.mcp_server.tools_emit import emit_verdict


@pytest.fixture(autouse=True)
def _turn():
    ev = cv.TurnEvidence()
    cv.set_turn_evidence(ev)
    cv.set_turn_ready_connectors({
        "servicenow": {"label": "ServiceNow", "kind": "tickets"},
        "virustotal": {"label": "VirusTotal", "kind": "intel"}})
    cv.set_turn_ready_sources({})
    yield ev
    cv.set_turn_evidence(None)
    cv.set_turn_ready_connectors(None)
    cv.set_turn_ready_sources(None)


def _run(ev, cid, connector, params, result):
    args = {"connector": connector, "op": "search", "params": params}
    cv.register_tool_result(cid, "run_op", True, args, result)


AD = {"ok": True, "data": [{"sAMAccountName": "kfenwick", "displayName": "Kay Fenwick",
                            "description": "Primary device: wks-eng-31"}]}


def test_values_are_read_by_type_not_by_prose():
    keys = {k["v"]: k["t"] for k in pivot_keys(AD)}
    assert keys["kfenwick"] == "entity"
    assert keys["wks-eng-31"] == "name"
    # words, counts, times and dates are not keys
    assert "Primary" not in keys and "device" not in keys
    junk = {"note": "Closed on 2026-06-29 at 02:15 after version 3.4.0 shipped, e.g. ok"}
    assert pivot_keys(junk) == []


def test_ip_hash_domain_shapes_and_any_language():
    row = {"msg": "接続 192.0.2.31 から wks-eng-31 へ mail.corp.example "
                  + "a" * 32}
    got = {k["v"]: k["t"] for k in pivot_keys(row)}
    assert got["192.0.2.31"] == "address"
    assert got["wks-eng-31"] == "name"
    assert got["mail.corp.example"] == "domain"
    assert got["a" * 32] == "hash"


def test_a_revealed_unsearched_key_is_open_and_names_the_sources(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    open_ = cv.open_pivot_keys(_turn.valid_ids())
    assert [k["v"] for k in open_] == ["wks-eng-31"]
    assert open_[0]["sources"] == ["ServiceNow", "activedirectory"]
    assert "wks-eng-31" in cv.pivot_note(_turn.valid_ids())


def test_a_searched_value_is_not_open(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    _run(_turn, "c2", "servicenow", {"q": "WKS-ENG-31"}, {"data": {"result": []}})
    assert cv.open_pivot_keys(_turn.valid_ids()) == []


def test_a_call_that_errored_did_not_search(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    cv.register_tool_result("c2", "run_op", False,
                            {"connector": "servicenow", "params": {"q": "wks-eng-31"}},
                            {"ok": False, "code": "unserved_op"})
    assert [k["v"] for k in cv.open_pivot_keys(_turn.valid_ids())] == ["wks-eng-31"]


def test_threat_intel_reports_reveal_nothing(_turn):
    report = {"data": {"resolutions": ["198.51.100.9", "bad-domain-01.example"]}}
    _run(_turn, "c1", "virustotal", {"ip": "203.0.113.9"}, report)
    assert cv.open_pivot_keys(_turn.valid_ids()) == []


def test_intel_takes_an_indicator_but_not_a_name(_turn):
    row = {"data": [{"hostname": "wks-eng-31", "ip_address": "192.0.2.31"}]}
    _run(_turn, "c1", "servicenow", {"q": "kfenwick"}, row)
    # VirusTotal was never queried, so it is not in play; ready tickets only.
    by = {k["v"]: k["sources"] for k in cv.open_pivot_keys(_turn.valid_ids(), limit=5)}
    assert "VirusTotal" not in by["wks-eng-31"]


def test_empty_answers_reveal_nothing(_turn):
    _run(_turn, "c1", "servicenow", {"q": "x"}, {"data": {"result": []}})
    assert cv.open_pivot_keys(_turn.valid_ids()) == []


def test_the_turn_is_held_open_at_most_the_cap(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    texts = [cv.pivot_hold(_turn) for _ in range(cv.PIVOT_NUDGE_CAP + 2)]
    assert all(t for t in texts[:cv.PIVOT_NUDGE_CAP])
    assert "wks-eng-31" in texts[0]
    assert texts[cv.PIVOT_NUDGE_CAP:] == ["", ""]


def test_hold_survives_a_suspended_session(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    cv.pivot_hold(_turn)
    again = cv.TurnEvidence.from_dict(_turn.to_dict())
    assert again.pivot_nudges() == 1
    assert [k["v"] for k in cv.open_pivot_keys(again.valid_ids())] == ["wks-eng-31"]


def _verdict(cite):
    return emit_verdict(
        disposition="false_positive", severity="low", confidence=0.8,
        summary="Benign.", findings=[{"claim": "ok", "evidence": [cite]}])


def test_a_verdict_over_an_open_lead_is_refused_then_accepted_when_searched(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    refused = _verdict("c1")
    assert refused.get("ok") is False
    assert refused["code"] == "open_lead_unsearched"
    assert "wks-eng-31" in refused["message"] and "ServiceNow" in refused["message"]
    _run(_turn, "c2", "servicenow", {"q": "wks-eng-31"}, {"data": {"result": []}})
    assert _verdict("c1").get("code") != "open_lead_unsearched"


def test_a_verdict_is_never_refused_more_than_the_cap(_turn):
    _run(_turn, "c1", "activedirectory", {"q": "kfenwick"}, AD)
    assert cv.PIVOT_NUDGE_CAP >= 1
    codes = [_verdict("c1").get("code") for _ in range(cv.PIVOT_NUDGE_CAP + 1)]
    assert codes[:cv.PIVOT_NUDGE_CAP] == ["open_lead_unsearched"] * cv.PIVOT_NUDGE_CAP
    assert codes[-1] != "open_lead_unsearched"


def test_no_lead_no_hold(_turn):
    assert cv.pivot_hold(_turn) == ""
    assert cv.pivot_note(_turn.valid_ids()) == ""
