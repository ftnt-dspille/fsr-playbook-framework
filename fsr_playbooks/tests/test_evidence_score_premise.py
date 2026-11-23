"""Phase 2 step 2e (shadow): the premise check and the explained-rating rule.

The premise is a separate signal beside the score: did the turn read the subject's
OWN records (asset role, an approved change), and does one contradict the verdict?
A rating that an approved change or asset record explains does not contradict a
benign call.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._evidence_score import (
    event_facts,
    identifiers,
    premise_check,
    premise_facts,
    score_verdict,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card

IP = "203.0.113.77"
HOST = "sec-host-02"
HOST_IP = "100.64.9.14"
RECORD = "11111111-2222-3333-4444-555555555555"
MAL = {"source": "VirusTotal", "verdict": "malicious", "severity": "error",
       "score_str": "31/94"}
REAL_LOW = {"source": "VirusTotal", "verdict": "malicious", "severity": "error",
            "score_str": "8/94"}
SOURCES = {"siem_": "FortiSIEM"}
CONNECTORS = {"virustotal": {"label": "VirusTotal", "kind": "intel"}}

ALERT = {"uuid": RECORD, "computerName": HOST, "sourceIp": HOST_IP,
         "destinationIp": IP, "description": f"beaconing from {HOST} to {IP}"}
SANDBOX_ASSET = {"data": [{"name": HOST, "ipAddress": HOST_IP,
                           "description": f"Malware analysis sandbox. Samples are detonated "
                                          f"here, so sessions to {IP} are expected."}]}
OTHER_ASSET = {"data": [{"name": "eng-ws-044", "ipAddress": "100.64.30.40",
                         "description": "Engineering workstation."}]}
PLAIN_ASSET = {"data": [{"name": HOST, "ipAddress": HOST_IP,
                         "description": "Windows server, owned by IT."}]}
CHANGE = {"result": [{"number": "CHG-1", "approval": "approved",
                      "description": f"Approved: {HOST} may reach {IP}."}]}


def entry(name, args, result, **kw):
    e = {"name": name, "ok": True, "args": args, "idents": identifiers(result),
         "premise": premise_facts(result), **kw}
    return e


def alert_read():
    return entry("get_record", {"iri": f"/api/3/alerts/{RECORD}"}, ALERT)


def asset_read(result):
    return entry("get_record", {"module": "assets", "query": HOST}, result)


def change_read(result=CHANGE):
    return entry("run_op", {"connector": "servicenow", "op": "get_all_change_requests"},
                 result)


def vt(finding=MAL, ip=IP):
    return {"name": "run_op", "ok": True, "finding": finding, "idents": [ip],
            "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": ip}}}


def card(disposition="true_positive"):
    s = f"{HOST} ({HOST_IP}) beaconing to {IP}"
    return {"id": "v", "disposition": disposition, "confidence": 0.9, "summary": s,
            "findings": [{"claim": s, "evidence": ["a"]}]}


def check(c, reg, **kw):
    return premise_check(c, reg, record_subject=RECORD, **kw)


# ---- premise ------------------------------------------------------------------

def test_conviction_of_a_sandbox_read_past_is_contradicted():
    p = check(card(), {"v": vt(), "alert": alert_read(), "asset": asset_read(SANDBOX_ASSET)})
    assert p["status"] == "contradicted"
    assert p["contradicted_by"] == [{"call": "asset",
                                     "roles": ["detonation", "malware_analysis", "sandbox"]}]
    assert p["records"] == ["asset"]


def test_conviction_without_the_subjects_own_records_is_unread():
    reg = {"v": vt(), "alert": alert_read(), "other": asset_read(OTHER_ASSET)}
    assert check(card(), reg)["status"] == "unread"
    assert check(card(), {"v": vt(), "alert": alert_read()})["status"] == "unread"


def test_a_plain_asset_record_is_read_not_contradicted():
    p = check(card(), {"v": vt(), "alert": alert_read(), "asset": asset_read(PLAIN_ASSET)})
    assert p["status"] == "read" and p["records"] == ["asset"]


def test_a_scoped_approval_contradicts_only_when_it_names_the_verdicts_external_address():
    reg = {"v": vt(), "alert": alert_read(), "chg": change_read()}
    assert check(card(), reg)["status"] == "contradicted"
    scope = {"result": [{"number": "CHG-2", "approval": "approved",
                         "description": f"Approved: {HOST} scans 100.64.60.0/24 on Sundays."}]}
    assert check(card(), {"v": vt(), "alert": alert_read(),
                          "chg": change_read(scope)})["status"] == "read"


def test_a_record_of_another_host_does_not_contradict():
    other = {"data": [{"name": "eng-ws-044", "ipAddress": "100.64.30.40",
                       "description": f"Malware analysis sandbox; {IP} expected."}]}
    assert check(card(), {"alert": alert_read(),
                          "o": asset_read(other)})["status"] == "unread"


def test_the_record_under_triage_is_not_a_premise_read():
    alert_like = entry("get_record", {"module": "assets", "iri": f"/api/3/assets/{RECORD}"},
                       SANDBOX_ASSET)
    assert check(card(), {"alert": alert_like})["status"] == "unread"


def test_a_failed_read_is_not_a_read():
    a = asset_read(SANDBOX_ASSET)
    a["ok"] = False
    assert check(card(), {"alert": alert_read(), "asset": a})["status"] == "unread"


def test_benign_verdict_on_a_host_recorded_as_compromised_is_contradicted():
    bad = {"data": [{"name": HOST, "ipAddress": HOST_IP,
                     "description": "Host was compromised last week and reimaged."}]}
    reg = {"alert": alert_read(), "asset": asset_read(bad)}
    assert check(card("benign"), reg)["status"] == "contradicted"
    assert check(card("benign"), {"alert": alert_read(),
                                  "asset": asset_read(PLAIN_ASSET)})["status"] == "read"


def test_host_bound_context_names_the_subject_without_an_alert_read():
    names = premise_facts(ALERT)["names"]
    p = check(card(), {"asset": asset_read(SANDBOX_ASSET)}, known_names=names)
    assert p["status"] == "contradicted"


def test_premise_facts_are_bounded_and_shaped():
    f = premise_facts({"d": [{"name": f"h-{i}", "description": "sandbox"}
                             for i in range(100)]})
    assert len(f["rows"]) <= 20 and len(f["names"]) <= 60
    assert premise_facts({"x": 1}) == {}
    assert premise_facts("not json") == {}


# ---- the contradiction cap: an explained rating -----------------------------------

CDN = "198.51.100.60"
CDN_ASSET = {"data": [{"name": "mkt-ws-31", "ipAddress": "100.64.31.18",
                       "description": f"Sync client pulls from the vendor CDN at {CDN} "
                                      "every hour (change CHG-5120)."}]}
CDN_CHANGE = {"result": [{"number": "CHG-5120", "approval": "approved",
                          "description": f"Approved standing change: pull from {CDN}."}]}


def benign_card():
    s = f"mkt-ws-31 syncs from the vendor CDN {CDN}"
    return {"id": "v", "disposition": "benign", "confidence": 0.9, "summary": s,
            "findings": [{"claim": s, "evidence": ["a"]}]}


def score(c, reg):
    return score_verdict(c, reg, record_subject=RECORD, unchecked_sources=[],
                         ready_sources=SOURCES, ready_connectors=CONNECTORS)


def cdn_alert():
    return entry("get_record", {"iri": f"/api/3/alerts/{RECORD}"},
                 {"uuid": RECORD, "computerName": "mkt-ws-31", "destinationIp": CDN})


@pytest.mark.parametrize("record", [
    entry("get_record", {"module": "assets", "query": "mkt-ws-31"}, CDN_ASSET),
    entry("run_op", {"connector": "servicenow", "op": "get_all_change_requests"}, CDN_CHANGE),
])
def test_a_real_rating_explained_by_an_approved_change_or_asset_role_is_no_contradiction(record):
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(), "r": record}
    s = score(benign_card(), reg)
    assert "contradiction" not in s["capped_by"] and s["components"]["no_contradiction"]
    assert s["score"] >= 0.8


def test_a_rating_no_record_explains_still_contradicts():
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(),
           "r": entry("get_record", {"module": "assets", "query": "mkt-ws-31"},
                      {"data": [{"name": "mkt-ws-31", "description": "Design workstation."}]})}
    assert "contradiction" in score(benign_card(), reg)["capped_by"]


def test_a_record_that_does_not_name_the_rated_address_does_not_explain_it():
    other = {"data": [{"name": "mkt-ws-31", "description": "Approved: syncs from 198.51.100.99 "
                                                          "(change CHG-1)."}]}
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(),
           "r": entry("get_record", {"module": "assets", "query": "mkt-ws-31"}, other)}
    assert "contradiction" in score(benign_card(), reg)["capped_by"]


def test_a_prior_case_or_alert_text_never_explains_a_rating():
    case = entry("search_records", {"module": "alerts", "query": CDN},
                 {"data": [{"closureNotes": f"approved, expected traffic to {CDN}"}]})
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(), "r": case}
    assert "contradiction" in score(benign_card(), reg)["capped_by"]


def test_an_explained_rating_does_not_excuse_a_conviction():
    c = benign_card()
    c["disposition"] = "true_positive"
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(),
           "r": entry("get_record", {"module": "assets", "query": "mkt-ws-31"}, CDN_ASSET)}
    s = score(c, reg)
    assert "contradiction" not in s["capped_by"]  # a rating agrees with a conviction
    assert s["score"] <= 0.95


# ---- recorded on the card, and no decision reads it ---------------------------------

@pytest.fixture
def turn():
    cv.clear_tool_registry()
    cv.set_result_reader(lambda c, o, p, r: MAL if c == "virustotal" else None)
    cv.register_tool_result("call_vt", "run_op", True,
                            {"connector": "virustotal", "op": "query_ip",
                             "params": {"ip": IP}}, {"ok": True, "data": {"malicious": 40}})
    cv.register_tool_result("call_asset", "get_record", True,
                            {"module": "assets", "query": HOST}, SANDBOX_ASSET)
    yield
    cv.set_result_reader(None)
    cv.clear_tool_registry()


def test_the_card_carries_the_premise_beside_the_score(turn):
    r = emit_card(card_type="verdict", payload={
        "disposition": "true_positive", "severity": "high", "confidence": 0.9,
        "summary": f"{HOST} ({HOST_IP}) beacons to {IP}", "unknowns": [],
        "findings": [{"claim": f"{HOST} contacted {IP}", "evidence": ["call_vt"]}]})
    c = r["card"]
    assert c["premise"]["status"] == "contradicted"
    assert c["premise"]["contradicted_by"][0]["call"] == "call_asset"
    assert "evidence_score" in c and c["confidence"] == 0.9
    assert cv.get_turn_evidence().verdicts()[-1]["premise"]["status"] == "contradicted"


def test_event_facts_unaffected_by_premise_wiring():
    assert event_facts({"srcIpAddr": "100.64.0.1", "destIpAddr": "100.64.0.2"})
