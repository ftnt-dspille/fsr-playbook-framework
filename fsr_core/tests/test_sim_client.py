"""Tests for the simulation-mode FSR client + fixtures."""
from __future__ import annotations

from fsr_core.mcp_server import _sim_client as sc
from fsr_core.mcp_server import _sim_fixtures as fx


def test_config_is_always_live():
    assert sc.get_config().is_live() is True
    assert sc.available() is True


def test_connector_details_returns_healthy_roster():
    client = sc.get_client()
    r = client.session.post(
        "/api/integration/connector_details/?configured=true", json={})
    rows = r.json()["data"]
    names = {row["name"] for row in rows}
    assert "fortinet-fortisiem" in names
    assert "virustotal" in names
    for row in rows:
        assert row["status"] == "Completed"
        assert row["version"]
        assert row["configs"], "each row needs a config so preflight resolves"


def test_healthcheck_is_available_and_names_the_connector():
    client = sc.get_client()
    r = client.session.get(
        "/api/integration/connectors/healthcheck/fortinet-fortisiem/5.4.2/")
    body = r.json()
    assert body["status"] == "available"
    # path parsing keeps working with a ?config= suffix
    name = fx.connector_from_healthcheck_path(
        "/api/integration/connectors/healthcheck/shodan/2.0.0/?config=sim-shodan")
    assert name == "shodan"


def test_execute_routes_to_siem_fixture():
    client = sc.get_client()
    out = client.post("/api/integration/execute/", {
        "connector": "fortinet-fortisiem", "operation": "search_events",
        "params": {}})
    events = out["data"]
    assert isinstance(events, list) and len(events) >= 2
    # events are ordered and link the host to the C2 IP
    assert all(e["srcIpAddr"] == fx._HOST_IP for e in events)
    assert all(e["destIpAddr"] == fx._C2_IP for e in events)
    times = [e["phRecvTime"] for e in events]
    assert times == sorted(times)


def test_execute_ip_context_reflects_requested_ip():
    client = sc.get_client()
    out = client.post("/api/integration/execute/", {
        "connector": "fortinet-fortisiem", "operation": "get_ip_context",
        "params": {"value": fx._C2_IP}})
    ctx = out["data"]
    assert ctx["ipAddress"] == fx._C2_IP
    assert ctx["knownMalicious"] is True


def test_execute_vt_shape_is_summarizer_friendly():
    """The VT fixture must carry the `attributes` block the enrichment
    summarizer (_prune_known_enrichment) keys on."""
    client = sc.get_client()
    out = client.post("/api/integration/execute/", {
        "connector": "virustotal", "operation": "query_ip",
        "params": {"ip": fx._C2_IP}})
    data = out["data"]
    assert "attributes" in data
    assert "last_analysis_stats" in data["attributes"]


def test_execute_unknown_pair_falls_back_generic():
    client = sc.get_client()
    out = client.post("/api/integration/execute/", {
        "connector": "made-up", "operation": "do_thing", "params": {"x": 1}})
    data = out["data"]
    assert data["ok"] is True and data["simulated"] is True
    assert data["connector"] == "made-up"


def test_firewall_block_is_success():
    client = sc.get_client()
    out = client.post("/api/integration/execute/", {
        "connector": "fortigate-firewall", "operation": "block_ip_new",
        "params": {"ip": fx._C2_IP}})
    data = out["data"]
    assert data["status"] == "success"
    assert data["blockedIp"] == fx._C2_IP
