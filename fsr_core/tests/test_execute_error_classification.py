"""`run_op` must not mislabel a connector-side HTTP error as a connectivity
failure. A 4xx/5xx with a body means the request reached a HEALTHY connector
and it rejected the call (session yq8nhcix: FortiSIEM returned "Invalid Incident
Id" for a wrong param, yet the agent saw `transport_failed` + "check
connectivity" and dead-ended on a healthy connector).
"""
from __future__ import annotations

from fsr_core.mcp_server.tools_execution import _classify_execute_error


def test_4xx_is_request_rejected_not_transport():
    out = _classify_execute_error(
        "fortinet-fortisiem", "get_associated_events_new", 400,
        '{"result":{"code":255,"description":"Invalid Incident Id 562"}}')
    assert out["code"] == "op_request_rejected"
    assert "Invalid Incident Id 562" in out["message"]
    # Must NOT emit the transport_failed "Check FSR connectivity" dead-end.
    assert not any("check fsr connectivity" in s.lower()
                   for s in out["suggestions"])
    assert out["status"] == "400"


def test_5xx_is_upstream_error():
    out = _classify_execute_error(
        "fortinet-fortisiem", "search_events", 500, "Internal Server Error")
    assert out["code"] == "upstream_error"
    assert "Internal Server Error" in out["message"]


def test_no_status_is_genuine_transport_failure():
    out = _classify_execute_error(
        "fortinet-fortisiem", "search_events", None,
        "Connection refused")
    assert out["code"] == "transport_failed"
    assert any("connectivity" in s.lower() for s in out["suggestions"])
