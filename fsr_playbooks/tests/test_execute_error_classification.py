"""`run_op` must not mislabel a connector-side HTTP error as a connectivity
failure. A 4xx/5xx with a body means the request reached a HEALTHY connector
and it rejected the call (session yq8nhcix: FortiSIEM returned "Invalid Incident
Id" for a wrong param, yet the agent saw `transport_failed` + "check
connectivity" and dead-ended on a healthy connector).
"""
from __future__ import annotations

import types

from fsr_playbooks.mcp_server import tools_execution as te
from fsr_playbooks.mcp_server.tools_execution import _classify_execute_error


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


# --- Healthcheck probe-failure must not be persisted as an unhealthy verdict.
# A timed-out / unreachable healthcheck is NOT an authoritative "connector
# down" result; caching it as "error" poisons the 5-min unhealthy TTL and
# silently drops containment/enrichment ops even after the connector recovers
# (GA-demo repro: find_containment_actions returned count:0 on a healthy box).

def _fake_client_raising(exc: Exception):
    """Minimal client whose healthcheck GET raises -- simulates a timeout."""
    def _get(*_a, **_k):
        raise exc
    session = types.SimpleNamespace(get=_get)
    return types.SimpleNamespace(session=session, base_url="", verify_ssl=False)


def test_healthcheck_timeout_is_tagged_probe_failed():
    hc = te._live_healthcheck(
        _fake_client_raising(TimeoutError("read timed out")),
        "fortiedr", "1.0.0")
    # Tagged so callers can fail open AND skip caching it.
    assert hc.get("_probe_failed") is True
    assert hc.get("status") == "error"


def test_probe_failure_is_not_cached(monkeypatch):
    """A `_probe_failed` verdict must never reach the health cache -- otherwise
    the unhealthy TTL keeps dropping the connector's ops after it recovers."""
    stored: list = []
    monkeypatch.setattr(te, "_store_health",
                        lambda *a, **k: stored.append((a, k)))
    monkeypatch.setattr(te, "_live_healthcheck",
                        lambda *a, **k: {"status": "error", "_probe_failed": True})
    monkeypatch.setattr(te, "_cached_health", lambda *a, **k: None)
    monkeypatch.setattr(
        te, "_configured_rows",
        lambda client: [{"name": "fortiedr", "version": "1.0.0"}])
    monkeypatch.setattr(te, "_row_config_ids", lambda row: [])

    out = te.populate_connector_health(client=object(), force=True)
    assert out["ok"] is True
    # The probe failed → nothing cached, so the next turn re-probes live.
    assert stored == [], f"probe failure was cached: {stored}"


def test_genuine_unhealthy_status_is_still_cached(monkeypatch):
    """A real vendor 'Disconnected' verdict (no _probe_failed) must still be
    cached -- we only stop persisting probe *failures*, not real bad news."""
    stored: list = []
    monkeypatch.setattr(te, "_store_health",
                        lambda *a, **k: stored.append(a))
    monkeypatch.setattr(te, "_live_healthcheck",
                        lambda *a, **k: {"status": "Disconnected"})
    monkeypatch.setattr(te, "_cached_health", lambda *a, **k: None)
    monkeypatch.setattr(
        te, "_configured_rows",
        lambda client: [{"name": "fortiedr", "version": "1.0.0"}])
    monkeypatch.setattr(te, "_row_config_ids", lambda row: [])

    te.populate_connector_health(client=object(), force=True)
    assert any(a[2] == "Disconnected" for a in stored), stored
