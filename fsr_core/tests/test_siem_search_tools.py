"""Tests for the first-class FortiSIEM search wrappers.

These wrap run_op; we monkeypatch run_op so the tests are offline + fast and
assert the wrapper's contract: right op/params, uniform event digest, direction
merge, and clean error pass-through.
"""
from __future__ import annotations

import pytest

import fsr_core.mcp_server.tools_execution as texec
from fsr_core.mcp_server import (
    siem_events_for_incident,
    siem_raw_query,
    siem_search_host,
    siem_search_ip,
)

# A live search_events row uses lower-camel phoenix field names.
_ROW = {
    "phRecvTime": "Fri May 29 14:31:02 UTC 2026",
    "eventType": "FortiGate-traffic-forward",
    "srcIpAddr": "10.50.60.70",
    "destIpAddr": "102.220.160.21",
    "destIpPort": 443,
    "sentBytes64": 1994596242,
    "rcvdBytes64": 4849007121,
    "hostName": "smithDesktop",
}


@pytest.fixture
def captured(monkeypatch):
    """Capture run_op calls and return one canned event row (legacy ops that
    still go straight through run_op, e.g. get_associated_events_new)."""
    calls = []

    def fake_run_op(connector, op, params=None, **kw):
        calls.append({"connector": connector, "op": op, "params": params or {}})
        return {"ok": True, "data": [_ROW]}

    monkeypatch.setattr(texec, "run_op", fake_run_op)
    return calls


@pytest.fixture
def pubv2(monkeypatch):
    """Mock the pub/v2 cycle (submit → progress → results) the siem_search_*
    helpers + siem_raw_query now ride. Captures submitted where clauses and
    serves ``pubv2.rows`` from the results leg."""
    class Recorder:
        wheres: list[str] = []
        rows = [_ROW]

    rec = Recorder()

    def fake(connector, op, params=None, **kw):
        assert op == "execute_api_request", f"must use pub/v2, not {op}"
        ep = params["endpoint"]
        if ep.endswith("/query/eventQuery"):
            rec.wheres.append(params["payload"]["where"])
            return {"ok": True, "data": {"queryId": "999"}}
        if ep.endswith("/query/progress"):
            return {"ok": True, "data": {"progress": 100}}
        if ep.endswith("/query/events/results"):
            return {"ok": True, "data": {"rows": rec.rows}}
        raise AssertionError(f"unexpected endpoint {ep}")

    monkeypatch.setattr(texec, "run_op", fake)
    return rec


def test_search_ip_dst_builds_dest_clause(pubv2):
    out = siem_search_ip("102.220.160.21", direction="dst", window="1d")
    assert out["ok"] and out["count"] == 1 and out["op"] == "siem_search_ip"
    assert pubv2.wheres == ['destIpAddr="102.220.160.21"']


def test_search_ip_emits_normalized_digest(pubv2):
    out = siem_search_ip("102.220.160.21", direction="dst")
    ev = out["events"][0]
    # same digest keys the record normalizer produces
    assert ev["dst"] == "102.220.160.21"
    assert ev["bytes_in"] == 4849007121
    assert ev["bytes_out"] == 1994596242
    assert ev["src_host"] == "smithDesktop"
    assert ev["dport"] == 443


def test_search_ip_any_ors_both_directions(pubv2):
    siem_search_ip("10.50.60.70", direction="any")
    assert pubv2.wheres == ['(srcIpAddr="10.50.60.70" OR destIpAddr="10.50.60.70")']


def test_search_host_uses_hostname_clause(pubv2):
    siem_search_host("smithDesktop")
    assert pubv2.wheres == ['hostName="smithDesktop"']


# A live get_incidents row (subset of the real shape) for incident 10868.
_INC_ROW = {
    "incidentId": 10868,
    "incidentFirstSeen": 1772143815000,
    "incidentLastSeen": 1772143815000,
    "incidentSrc": {"srcIpAddr": "10.50.60.70"},
    "incidentTitle": "Excessive DNS Queries",
}

_DT_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"


@pytest.fixture
def incident_box(monkeypatch):
    """Mock a live box: get_incidents lists _INC_ROW; get_associated_events_new
    succeeds only when given a timeFrom/timeTo window (mirrors FSM 6.0.0)."""
    calls = []

    def fake(connector, op, params=None, **kw):
        params = params or {}
        calls.append({"op": op, "params": params})
        if op == "get_incidents":
            return {"ok": True, "data": [_INC_ROW]}
        if op == "get_associated_events_new":
            if not (params.get("timeFrom") and params.get("timeTo")):
                return {"ok": False, "status": "400",
                        "message": 'Invalid Incident Id'}
            return {"ok": True, "data": [_ROW]}
        raise AssertionError(f"unexpected op {op}")

    monkeypatch.setattr(texec, "run_op", fake)
    return calls


def test_events_for_incident_auto_windows_from_get_incidents(incident_box):
    import re
    out = siem_events_for_incident("10868")
    ops = [c["op"] for c in incident_box]
    assert ops[0] == "get_incidents"          # resolves the window first
    assert "get_associated_events_new" in ops
    aen = next(c for c in incident_box if c["op"] == "get_associated_events_new")
    assert aen["params"]["incident_id"] == "10868"
    # window was supplied in the connector's microsecond-Z format
    assert re.fullmatch(_DT_RE, aen["params"]["timeFrom"])
    assert re.fullmatch(_DT_RE, aen["params"]["timeTo"])
    assert out["ok"] and out["count"] == 1


def test_events_for_incident_explicit_window_skips_lookup(captured):
    """An explicit window goes straight to the op (no get_incidents lookup),
    and epoch inputs are coerced to the microsecond-Z format."""
    import re
    out = siem_events_for_incident("10868", time_from=1772143815,
                                   time_to=1772147415)
    assert [c["op"] for c in captured] == ["get_associated_events_new"]
    p = captured[0]["params"]
    assert re.fullmatch(_DT_RE, p["timeFrom"]) and re.fullmatch(_DT_RE, p["timeTo"])
    assert out["count"] == 1


def test_events_for_incident_coerces_stale_id_by_source_ip(monkeypatch):
    """A stale id that isn't live coerces to the live incident matching the
    source IP, and the envelope records the coercion."""
    def fake(connector, op, params=None, **kw):
        params = params or {}
        if op == "get_incidents":
            return {"ok": True, "data": [_INC_ROW]}
        if op == "get_associated_events_new":
            assert params["incident_id"] == "10868"  # coerced from 17
            assert params.get("timeFrom") and params.get("timeTo")
            return {"ok": True, "data": [_ROW]}
        raise AssertionError(op)
    monkeypatch.setattr(texec, "run_op", fake)
    out = siem_events_for_incident("17", source_ip="10.50.60.70")
    assert out["ok"] and out["count"] == 1
    assert out["query"]["coerced_from"] == "17"


def test_events_for_incident_falls_back_to_ip_search(monkeypatch):
    """No live incident anywhere → pivot to a pub/v2 IP search, tagged."""
    def fake(connector, op, params=None, **kw):
        params = params or {}
        if op == "get_incidents":
            return {"ok": True, "data": []}            # nothing live
        if op == "execute_api_request":                # pub/v2 fallback
            ep = params["endpoint"]
            if ep.endswith("/query/eventQuery"):
                return {"ok": True, "data": {"queryId": "999"}}
            if ep.endswith("/query/progress"):
                return {"ok": True, "data": {"progress": 100}}
            if ep.endswith("/query/events/results"):
                return {"ok": True, "data": {"rows": [_ROW]}}
        raise AssertionError(f"unexpected {op} {params}")
    monkeypatch.setattr(texec, "run_op", fake)
    out = siem_events_for_incident("17", source_ip="10.50.60.70")
    assert out["ok"] and out["count"] == 1
    assert out["fallback"] == "siem_search_ip"
    assert "10.50.60.70" in out["note"]


def test_events_for_incident_fallback_widens_lookback(monkeypatch):
    """The IP fallback widens its lookback until events appear: the 1d window
    returns nothing, 7d returns events. Asserts it advanced past 1d."""
    windows_tried = []

    def fake(connector, op, params=None, **kw):
        params = params or {}
        if op == "get_incidents":
            return {"ok": True, "data": []}            # nothing live
        if op == "execute_api_request":
            ep = params["endpoint"]
            if ep.endswith("/query/eventQuery"):
                # window is encoded in the timeRange span; recover it in days
                tr = params["payload"]["timeRange"]
                days = round((tr["to"] - tr["from"]) / 86400)
                windows_tried.append(days)
                # remember which span this queryId is for
                return {"ok": True, "data": {"queryId": f"q{days}"}}
            if ep.endswith("/query/progress"):
                return {"ok": True, "data": {"progress": 100}}
            if ep.endswith("/query/events/results"):
                qid = params["query_params"]["queryId"]
                rows = [_ROW] if qid != "q1" else []    # empty at 1d, hit at 7d
                return {"ok": True, "data": {"rows": rows}}
        raise AssertionError(f"unexpected {op} {params}")

    monkeypatch.setattr(texec, "run_op", fake)
    out = siem_events_for_incident("17", source_ip="10.50.60.70")
    assert out["ok"] and out["count"] == 1
    assert out["fallback"] == "siem_search_ip"
    assert windows_tried[:2] == [1, 7]                  # widened 1d -> 7d
    assert "7d" in out["note"]


def test_events_for_incident_no_window_no_ip_gives_accurate_error(monkeypatch):
    """Can't derive a window and no IP to fall back on → an accurate error,
    NOT the connector's misleading 'Invalid Incident Id'."""
    def fake(connector, op, params=None, **kw):
        if op == "get_incidents":
            return {"ok": True, "data": []}
        raise AssertionError(op)
    monkeypatch.setattr(texec, "run_op", fake)
    out = siem_events_for_incident("17")
    assert out["ok"] is False
    assert out["code"] == "no_time_window"
    assert "Invalid Incident Id" not in out["message"]


def test_error_passthrough(monkeypatch):
    """A failed pub/v2 submit surfaces as a clean error envelope, not a raise."""
    def failing(connector, op, params=None, **kw):
        return {"ok": False, "status": "connector_unhealthy",
                "message": "FortiSIEM unreachable"}
    monkeypatch.setattr(texec, "run_op", failing)
    out = siem_search_host("smithDesktop")
    assert out["ok"] is False
    assert out["code"] == "connector_unhealthy"
    assert "unreachable" in out["message"]


def test_limit_and_truncation(pubv2):
    pubv2.rows = [dict(_ROW) for _ in range(40)]
    out = siem_search_host("h", limit=10)
    assert out["count"] == 10 and out["truncated"] is True


def test_raw_query_accepts_dict_where(pubv2):
    """P2: a {field: value} dict is mapped to a backend clause (friendly names
    aliased, fields AND-ed) instead of erroring."""
    out = siem_raw_query(where={"sourceIPv4": "10.50.60.70", "destPort": 443})
    assert out["ok"]
    assert pubv2.wheres == ['srcIpAddr="10.50.60.70" AND destIpPort="443"']


def test_raw_query_pubv2_submit_progress_results(monkeypatch):
    """Escape hatch stays on the pub/v2 subsystem: submit → progress → results,
    all via execute_api_request (never the XML get_events_by_query_id)."""
    endpoints = []

    def fake(connector, op, params=None, **kw):
        assert op == "execute_api_request", f"must not use {op} (wrong id space)"
        ep = params["endpoint"]
        endpoints.append(ep)
        if ep.endswith("/query/eventQuery"):
            # FortiSOC: no customer exclude
            assert "exclude" not in params["payload"]["customerScope"]
            return {"ok": True, "data": {"queryId": "999"}}
        if ep.endswith("/query/progress"):
            assert params["query_params"]["queryId"] == "999"
            return {"ok": True, "data": {"progress": 100}}
        if ep.endswith("/query/events/results"):
            assert params["query_params"]["queryId"] == "999"
            return {"ok": True, "data": {"rows": [_ROW],
                                         "pagination": {"total": 1}}}
        raise AssertionError(f"unexpected endpoint {ep}")

    monkeypatch.setattr(texec, "run_op", fake)
    out = siem_raw_query('srcIpAddr="10.50.60.70"')
    assert out["ok"] and out["count"] == 1
    assert out["query_id"] == "999"
    assert any(e.endswith("/query/eventQuery") for e in endpoints)
    assert any(e.endswith("/query/progress") for e in endpoints)
    assert any(e.endswith("/query/events/results") for e in endpoints)
    assert out["events"][0]["src"] == "10.50.60.70"


def test_raw_query_no_query_id(monkeypatch):
    def fake(connector, op, params=None, **kw):
        return {"ok": True, "data": {"error": {"code": 5}}}  # no queryId
    monkeypatch.setattr(texec, "run_op", fake)
    out = siem_raw_query('reptDevIpAddr="10.10.100.1"')
    assert out["ok"] is False and out["code"] == "no_query_id"
