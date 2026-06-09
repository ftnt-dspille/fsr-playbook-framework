"""Tests for the first-class FortiAnalyzer search wrappers.

These wrap run_op; we monkeypatch run_op so the tests are offline + fast and
assert the wrapper's contract: right op/params, uniform digest, IP direction
filter, raw-query passthrough, and clean error pass-through.
"""
from __future__ import annotations

import pytest

import fsr_core.mcp_server.tools_execution as texec
from fsr_core.mcp_server import faz_get_alerts, faz_raw_query, faz_search_ip

# get_alerts nests rows under JSON-RPC result.data.
_ALERT = {
    "alerttime": "1780425264",
    "alertid": "202606021000000012",
    "subject": "Device stopped logging more than 7 days",
    "severity": "low",
    "triggername": "0005-05_FAZ-Application-Log_Logging-Issue",
    "devname": "FAZ-K8S-CLOUD",
    "devid": "FSOCLDTM26000080",
    "logtype": "app-ctrl",
    "logcount": "1",
}

# A FAZ traffic log row uses lowercase field names.
_LOG = {
    "itime": "1780425000",
    "type": "traffic",
    "srcip": "10.50.60.70",
    "dstip": "8.8.8.8",
    "dstport": "443",
    "action": "accept",
    "service": "HTTPS",
    "sentbyte": "1024",
    "rcvdbyte": "2048",
    "dstcountry": "United States",
}


def _alert_payload(rows):
    return {"ok": True, "data": {"result": {"data": rows}}}


def _log_payload(rows):
    return {"ok": True, "data": {"result": {"data": rows, "total-count": len(rows)}}}


@pytest.fixture
def captured(monkeypatch):
    """Capture run_op calls; return canned alert rows."""
    calls = []

    def fake_run_op(connector, op, params=None, **kw):
        calls.append({"connector": connector, "op": op, "params": params or {},
                      "confirm": kw.get("confirm")})
        if op == "get_alerts":
            return _alert_payload([_ALERT])
        if op == "start_and_fetch_bulk_device_logs":
            return _log_payload([_LOG])
        return {"ok": True, "data": {}}

    monkeypatch.setattr(texec, "run_op", fake_run_op)
    return calls


def test_get_alerts_targets_op_with_adom_window(captured):
    out = faz_get_alerts(adom="root", window="7d", limit=5)
    assert out["ok"] and out["count"] == 1
    call = captured[0]
    assert call["connector"] == "fortinet-fortianalyzer"
    assert call["op"] == "get_alerts"
    assert call["params"]["adom_name"] == "root"
    assert call["params"]["start"] and call["params"]["end"]
    assert call["confirm"] is True  # read-only, but cache may not be warmed


def test_get_alerts_emits_alert_digest(captured):
    out = faz_get_alerts()
    ev = out["events"][0]
    assert ev["alert_id"] == "202606021000000012"
    assert ev["subject"].startswith("Device stopped")
    assert ev["severity"] == "low"
    assert ev["devname"] == "FAZ-K8S-CLOUD"
    assert ev["trigger"].startswith("0005-05")


def test_search_ip_any_builds_or_filter_and_log_digest(captured):
    out = faz_search_ip("8.8.8.8", direction="any", window="24h")
    call = captured[0]
    assert call["op"] == "start_and_fetch_bulk_device_logs"
    assert call["params"]["filter"] == "srcip=8.8.8.8 or dstip=8.8.8.8"
    assert call["params"]["wait_for_search_process_to_complete"] is True
    # log-format times carry the microsecond-Z suffix FAZ demands.
    assert call["params"]["start"].endswith("Z")
    ev = out["events"][0]
    assert ev["src"] == "10.50.60.70" and ev["dst"] == "8.8.8.8"
    assert ev["bytes_in"] == "2048" and ev["action"] == "accept"


def test_search_ip_direction_src_dst(captured):
    faz_search_ip("1.2.3.4", direction="src")
    faz_search_ip("1.2.3.4", direction="dst")
    assert captured[0]["params"]["filter"] == "srcip=1.2.3.4"
    assert captured[1]["params"]["filter"] == "dstip=1.2.3.4"


def test_search_ip_devid_logtype_overrides(captured):
    faz_search_ip("1.2.3.4", devid="All_FortiProxy", logtype="Web Filter")
    assert captured[0]["params"]["devid"] == "All_FortiProxy"
    assert captured[0]["params"]["logtype"] == "Web Filter"


def test_limit_and_truncation(monkeypatch):
    def many(connector, op, params=None, **kw):
        return _log_payload([dict(_LOG) for _ in range(40)])
    monkeypatch.setattr(texec, "run_op", many)
    out = faz_search_ip("1.2.3.4", limit=10)
    assert out["count"] == 10 and out["truncated"] is True


def test_error_passthrough(monkeypatch):
    def failing(connector, op, params=None, **kw):
        return {"ok": False, "status": "connector_unhealthy",
                "message": "FortiAnalyzer unreachable"}
    monkeypatch.setattr(texec, "run_op", failing)
    out = faz_get_alerts()
    assert out["ok"] is False
    assert out["code"] == "connector_unhealthy"
    assert "unreachable" in out["message"]


def test_raw_query_digests_log_rows(monkeypatch):
    def fake(connector, op, params=None, **kw):
        assert op == "json_rpc_freeform"
        assert params["data"]["method"] == "get"
        return _log_payload([_LOG])
    monkeypatch.setattr(texec, "run_op", fake)
    out = faz_raw_query({"method": "get", "params": [{"url": "/x"}]})
    assert out["ok"] and out["count"] == 1
    assert out["events"][0]["src"] == "10.50.60.70"


def test_raw_query_passes_through_non_log_rows(monkeypatch):
    """Device/config rows aren't log-shaped → returned raw, not mangled."""
    dev = {"name": "FGT-1", "sn": "FGVM123", "os_ver": 7}
    def fake(connector, op, params=None, **kw):
        return {"ok": True, "data": {"result": {"data": [dev]}}}
    monkeypatch.setattr(texec, "run_op", fake)
    out = faz_raw_query({"method": "get", "params": [{"url": "/dvmdb"}]})
    assert out["ok"] and "events" not in out
    assert out["raw"]["result"]["data"][0]["name"] == "FGT-1"


def test_raw_query_bad_json_string(monkeypatch):
    def fake(connector, op, params=None, **kw):  # pragma: no cover
        raise AssertionError("should not run on bad json")
    monkeypatch.setattr(texec, "run_op", fake)
    out = faz_raw_query("{not json")
    assert out["ok"] is False and out["code"] == "bad_json"
