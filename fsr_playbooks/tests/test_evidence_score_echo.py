"""Phase 2 step 2d: echo detection (still shadow). A log hit that only returns the
alert's own events (same event or incident id, or the alert's source and
destination at the alert's moment) is not corroboration of a conviction.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._evidence_score import event_facts, is_echo, score_verdict
from fsr_playbooks.mcp_server.tools_emit import emit_card

IP = "203.0.113.9"
HOST_IP = "100.64.4.5"
RECORD = "11111111-2222-3333-4444-555555555555"
MAL = {"source": "VirusTotal", "verdict": "malicious", "severity": "error",
       "score_str": "14/94"}
SOURCES = {"siem_": "FortiSIEM"}
CONNECTORS = {"virustotal": {"label": "VirusTotal", "kind": "intel"}}
T0 = 1_790_550_000.0

ALERT_BODY = {"uuid": RECORD, "id": 94101, "sourceId": "141201", "sourceIp": HOST_IP,
              "destinationIp": IP, "createDate": T0}


def ev(**kw):
    return {"srcIpAddr": HOST_IP, "destIpAddr": IP, "phRecvTime": T0 + 1, **kw}


def vt():
    return {"name": "run_op", "ok": True, "finding": MAL, "idents": [IP],
            "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": IP}}}


def alert_read(body=None):
    return {"name": "get_record", "ok": True, "idents": [HOST_IP, IP],
            "args": {"iri": f"/api/3/alerts/{RECORD}"},
            "events": event_facts(body or ALERT_BODY)}


def siem(rows):
    return {"name": "siem_search_events", "ok": True, "idents": [IP, HOST_IP],
            "args": {"query": IP}, "events": event_facts({"data": rows})}


def card(disposition="true_positive"):
    s = f"beaconing from {HOST_IP} to {IP}"
    return {"id": "v", "disposition": disposition, "confidence": 0.9, "summary": s,
            "findings": [{"claim": s, "evidence": ["a"]}]}


def score(c, registry, **kw):
    return score_verdict(c, registry, record_subject=RECORD, unchecked_sources=[],
                         ready_sources=SOURCES, ready_connectors=CONNECTORS, **kw)


def test_a_siem_hit_with_the_alerts_incident_id_is_an_echo_not_corroboration():
    reg = {"a": vt(), "alert": alert_read(),
           "s": siem([ev(incidentId="141201"), ev(incidentId="141201")])}
    s = score(card(), reg)
    assert s["echo"] == ["s"]
    assert s["tier"] == "support_covered" and s["score"] == 0.85
    assert "the only log hit returns the alert's own events" in s["missing"]


def test_a_siem_hit_with_events_the_alert_does_not_hold_still_corroborates():
    rows = [ev(incidentId="141201"), ev(incidentId="777001", phRecvTime=T0 - 3600),
            ev(incidentId="777002", phRecvTime=T0 - 7200)]
    s = score(card(), {"a": vt(), "alert": alert_read(), "s": siem(rows)})
    assert s["echo"] == [] and s["score"] == 0.95


def test_same_source_and_destination_at_the_alerts_moment_is_an_echo():
    rows = [ev(), ev(phRecvTime=T0 + 4)]
    s = score(card(), {"a": vt(), "alert": alert_read(), "s": siem(rows)})
    assert s["echo"] == ["s"] and s["score"] == 0.85


def test_same_pair_hours_apart_is_a_pattern_not_an_echo():
    rows = [ev(phRecvTime=T0 + 3600 * k) for k in (-3, -2, -1, 0)]
    s = score(card(), {"a": vt(), "alert": alert_read(), "s": siem(rows)})
    assert s["echo"] == [] and s["score"] == 0.95


def test_a_mixed_result_is_not_an_echo():
    rows = [ev(incidentId="141201"), ev(incidentId="999", phRecvTime=T0 - 500)]
    assert is_echo(event_facts(rows), event_facts(ALERT_BODY)) is False


def test_nothing_known_about_the_alert_means_no_echo_is_claimed():
    s = score(card(), {"a": vt(), "s": siem([ev(incidentId="141201")])})
    assert s["echo"] == [] and s["score"] == 0.95


def test_an_unparsed_log_result_is_not_called_an_echo():
    s = score(card(), {"a": vt(), "alert": alert_read(),
                       "s": {"name": "siem_search_events", "ok": True,
                             "idents": [IP], "args": {"query": IP}}})
    assert s["echo"] == [] and s["score"] == 0.95


def test_the_hosts_bound_record_body_is_the_alerts_own_rows():
    reg = {"a": vt(), "s": siem([ev(incidentId="141201")])}
    s = score(card(), reg, known_events=event_facts(ALERT_BODY))
    assert s["echo"] == ["s"] and s["score"] == 0.85


def test_a_clean_rating_still_contradicts_a_conviction_backed_only_by_an_echo():
    clean = {"name": "run_op", "ok": True, "idents": [IP],
             "finding": {"source": "VirusTotal", "verdict": "clean", "severity": "ok",
                         "score_str": "0/94"},
             "args": {"connector": "virustotal", "op": "query_ip", "params": {"ip": IP}}}
    echo = {"alert": alert_read(), "s": siem([ev(incidentId="141201")])}
    s = score(card(), {"a": clean, **echo})
    assert s["capped_by"] == ["contradiction"] and s["score"] == 0.5
    # the same clean rating next to a real (non-echo) log pattern is a young address
    rows = [ev(incidentId=f"x{k}", phRecvTime=T0 - 600 * k) for k in range(1, 5)]
    s = score(card(), {"a": clean, "alert": alert_read(), "s": siem(rows)})
    assert s["capped_by"] == []


def test_event_facts_reads_json_text_and_ignores_prose():
    assert event_facts("not json") == []
    rows = event_facts(f'{{"data": [{{"incidentId": "141201", "srcIpAddr": "{HOST_IP}", '
                       f'"destIpAddr": "{IP}", "phRecvTime": "2026-09-27T09:00:01Z"}}]}}')
    assert rows[0]["ids"] == ["141201"] and rows[0]["t"] > 1.7e9


def test_the_siem_helpers_normalized_rows_are_read_by_time():
    # siem_search hands back ts/src/dst rows with no event id
    rows = [{"ts": f"2026-09-27T23:00:{k:02d}Z", "src": HOST_IP, "dst": IP, "dport": 443}
            for k in (1, 11, 21)]
    own = event_facts({"sourceIp": HOST_IP, "destinationIp": IP, "createDate": T0})
    assert is_echo(event_facts({"ok": True, "events": rows}), own) is True
    later = [{**rows[0], "ts": "2026-09-27T21:00:00Z"}]
    assert is_echo(event_facts({"events": rows + later}), own) is False


def test_the_register_path_records_events_and_the_emit_path_scores_the_echo():
    cv.clear_tool_registry()
    cv.set_turn_ready_sources(SOURCES)
    try:
        cv.register_tool_result("call_vt", "run_op", True,
                                {"connector": "virustotal", "op": "query_ip",
                                 "params": {"ip": IP}}, {"ok": True, "data": {"ip": IP}})
        cv.register_tool_result("call_siem", "siem_search_events", True, {"query": IP},
                                {"events": [ev(incidentId="141201")]})
        assert cv.get_turn_evidence().valid_ids()["call_siem"]["events"][0]["ids"] == ["141201"]
        cv.set_turn_known_context(ALERT_BODY)
        payload = {"disposition": "true_positive", "severity": "high", "confidence": 0.8,
                   "summary": f"beaconing from {HOST_IP} to {IP}", "unknowns": [],
                   "findings": [{"claim": f"{HOST_IP} to {IP}",
                                 "evidence": ["call_vt", "call_siem"]}]}
        r = emit_card(card_type="verdict", payload=payload)
        assert r["card"]["evidence_score"]["echo"] == ["call_siem"]
    finally:
        cv.set_turn_ready_sources(None)
        cv.set_turn_known_context(None)
        cv.clear_tool_registry()


@pytest.mark.parametrize("own,events,echo", [
    ([{"ids": ["abcd1"]}], [{"ids": ["abcd1"]}], True),
    ([{"ids": ["abcd1"]}], [{"ids": ["zzzz9"]}], False),
    ([], [{"ids": ["abcd1"]}], False),
])
def test_is_echo_cases(own, events, echo):
    assert is_echo(events, own) is echo
