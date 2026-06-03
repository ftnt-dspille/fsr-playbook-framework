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


def test_events_for_incident_uses_associated_events_op(captured):
    out = siem_events_for_incident("10868")
    assert captured[0]["op"] == "get_associated_events_new"
    assert captured[0]["params"]["incident_id"] == "10868"
    assert out["count"] == 1


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
