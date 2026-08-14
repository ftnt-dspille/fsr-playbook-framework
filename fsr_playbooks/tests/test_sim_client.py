"""Tests for the simulation-mode FSR client + fixtures."""
from __future__ import annotations

from fsr_playbooks.mcp_server import _sim_client as sc
from fsr_playbooks.mcp_server import _sim_fixtures as fx


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


def test_client_exposes_a_typed_connectors_api():
    """`client.connectors.list_configured()` -- the pyfsr shape, not a dict.

    `list_configured_connectors` reads attributes off these objects. When the
    attribute was missing entirely the call raised, and EVERY caller downstream
    reported `no_fsr_configured` -- which is how `find_enrichment_actions` and
    `find_containment_actions` came to fail on 9 of 9 calls in an offline
    investigation run while looking like the agent choosing to overspend.
    """
    client = sc.get_client()
    rows = client.connectors.list_configured()
    assert rows, "the simulated roster must not be empty"
    names = {c.name for c in rows}
    assert {"virustotal", "fortigate-firewall"} <= names
    for c in rows:
        # Every attribute the listing reads. A missing one is an AttributeError
        # inside a bare `except`, i.e. silently `no_fsr_configured` again.
        assert c.name and c.status and c.version
        assert c.label is not None
        assert c.configurations, "no config => preflight rejects the connector"


def test_the_connectors_api_and_the_details_route_agree():
    """One definition of what is configured offline, not two.

    The typed API and `/api/integration/connector_details/` are read by
    different callers; if they could disagree, a connector would be offerable
    by one path and rejected by the other -- the false-positive the listing's
    active-config filter exists to prevent, reintroduced offline.
    """
    client = sc.get_client()
    typed = {c.name for c in client.connectors.list_configured()}
    route = {r["name"] for r in client.session.post(
        "/api/integration/connector_details/", json={}).json()["data"]}
    assert typed == route


def _siem_exec(endpoint: str, **extra):
    client = sc.get_client()
    params = {"endpoint": endpoint, "method": "GET", **extra}
    return client.post("/api/integration/execute/", {
        "connector": "fortinet-fortisiem", "operation": "execute_api_request",
        "params": params})["data"]


def test_the_siem_event_query_engine_answers_offline():
    """Submit -> progress -> results, the pub/v2 triple.

    Every first-class SIEM pivot (`siem_search`, `siem_raw_query`) is three
    `execute_api_request` calls, not the `search_events` op. With no fixture
    for it they fell to the generic envelope, which carries no `queryId` -- so
    the wrapper retried the submit three times, slept between each, and
    returned `no_query_id`. Eight dead calls across the five `invest_*`
    fixtures, every one charged to the agent's tool budget.
    """
    sub = _siem_exec("/rest/pub/v2/query/eventQuery", method="POST",
                     payload={"where": 'srcIpAddr="10.0.0.1"'})
    qid = sub.get("queryId")
    assert qid, f"no queryId from the sim event-query submit: {sub}"

    prog = _siem_exec("/rest/pub/v2/query/progress",
                      query_params={"queryId": qid})
    assert prog.get("progress") == 100, prog

    res = _siem_exec("/rest/pub/v2/query/events/results",
                     query_params={"queryId": qid, "offset": 0, "limit": 25})
    # Empty ON PURPOSE: the fixture bundles carry alerts/incidents and no event
    # table, and synthesizing rows from the where-clause would hand the agent
    # fabricated confirmation for any indicator it asked about. Assert the
    # SHAPE, so serving a real captured event table later is a data change.
    assert isinstance(res.get("events"), list), res


def test_two_different_siem_queries_get_different_ids():
    """One id per payload -- a submit/poll/fetch triple must not collide with
    another query's results."""
    a = _siem_exec("/rest/pub/v2/query/eventQuery", method="POST",
                   payload={"where": 'srcIpAddr="10.0.0.1"'})["queryId"]
    b = _siem_exec("/rest/pub/v2/query/eventQuery", method="POST",
                   payload={"where": 'srcIpAddr="10.0.0.2"'})["queryId"]
    assert a != b
