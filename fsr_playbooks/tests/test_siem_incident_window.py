"""`siem_search(by="incident")` must find the incident it was asked about.

It needs the incident's time window, which `_resolve_live_incident` reads from
`get_incidents`. Live on a lab box (FortiSIEM v2, 500 incidents) every lookup
failed `no_time_window`, for two independent reasons:

* the call filtered on `incidentStatus: ["Active", "Cleared", "Open"]`, and
  "Cleared"/"Open" are not options on either FortiSIEM connector -- run_op's
  select validation refused the whole call;
* run_op digests large results to a handful of sample rows by default, so even
  a valid call rarely contained the incident being looked up.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import tools_triage


def _rows(n, target):
    return [{"incidentId": target if i == n - 1 else 1000 + i,
             "incidentFirstSeen": 1790553630000, "incidentLastSeen": 1790553690000,
             "incidentSrc": {"srcIpAddr": "10.0.0.5"}} for i in range(n)]


def test_resolver_asks_for_every_incident_unsummarized(monkeypatch):
    seen = {}

    def fake_run_op(connector, op, params, **kw):
        seen.update(op=op, params=params, kw=kw)
        return {"ok": True, "data": {"data": _rows(500, 39486)}}
    import fsr_playbooks.execution_api as ea
    monkeypatch.setattr(ea, "run_op", fake_run_op)
    monkeypatch.setattr(tools_triage, "_siem_connector", lambda: "fortinet-fortisiemv2")

    info = tools_triage._resolve_live_incident("39486", "")
    assert info and info["incident_id"] == "39486" and info["time_from"]
    assert seen["op"] == "get_incidents"
    assert seen["kw"].get("summarize") is False
    # No status/severity filter: a lookup by id wants every incident.
    assert "incidentStatus" not in seen["params"]
    assert "severity" not in seen["params"]



def test_a_soar_uuid_is_refused_with_a_correctable_message(monkeypatch):
    """Live: the model passed the SOAR incident's uuid; FortiSIEM returned a
    non-JSON body and the model saw only a JSON parse error."""
    import fsr_playbooks.execution_api as ea
    monkeypatch.setattr(ea, "run_op", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not reach FortiSIEM")))
    out = tools_triage.siem_events_for_incident("75c03691-875c-4c46-baf3-10e190cbc5f7")
    assert out["ok"] is False and out["code"] == "not_a_fortisiem_incident_id"
    assert "sourceId" in " ".join(out["suggestions"])


def test_a_soar_uuid_with_an_ip_falls_back_to_the_ip_search(monkeypatch):
    called = {}
    monkeypatch.setattr(tools_triage, "_ip_fallback_search",
                        lambda ip, iid, limit: called.setdefault("ip", ip) and {"ok": True})
    tools_triage.siem_events_for_incident("75c03691-aaaa", source_ip="10.0.0.5")
    assert called["ip"] == "10.0.0.5"


def test_an_unfindable_incident_names_the_exact_next_call(monkeypatch):
    """Live (a stuck turn): the refusal listed the parameters to add and the
    model still stopped. Say what happened and spell out the call."""
    from fsr_playbooks.mcp_server import tools_triage as TT
    monkeypatch.setattr(TT, "_resolve_live_incident", lambda *a, **k: None)
    out = TT.siem_events_for_incident("324")
    assert out["code"] == "no_time_window"
    assert "not among its incidents" in out["message"]
    assert 'siem_search(by="incident", value="324", source_ip=' in out["suggestions"][0]


# --- the mounted record named by its own uuid ------------------------------
# Live (two stuck turns): the model passed the mounted incident's uuid as the
# FortiSIEM incident id, was refused, and stopped -- its verdict said it did
# not know where the real id lives. The record carries it in `sourceId`.

_UUID = "75c03691-875c-4c46-baf3-10e190cbc5f7"
_IRI = f"/api/3/incidents/{_UUID}"


class _R:
    def __init__(self, body):
        self.status_code, self._b = 200, body

    def json(self):
        return self._b


def _mount(monkeypatch, record, iri=_IRI):
    from fsr_playbooks.llm import session_state
    from fsr_playbooks.mcp_server import _shared
    tok = session_state.update(record_iri=iri)
    monkeypatch.setattr(_shared, "_live_client", lambda: type("C", (), {"base_url": "https://soar"})())
    monkeypatch.setattr(tools_triage, "_get_with_reauth",
                        lambda client, url: _R({"uuid": _UUID, **record}))
    return tok


def _siem_record(**kw):
    return {"source": "Fortinet FortiSIEM", "sourceId": "11733", "sourceIp": "10.0.0.5", **kw}


def test_the_mounted_records_uuid_resolves_to_its_fortisiem_incident(monkeypatch):
    from fsr_playbooks.llm import session_state
    seen = {}
    monkeypatch.setattr(tools_triage, "_resolve_live_incident", lambda iid, ip: seen.update(
        iid=iid, ip=ip) or {"incident_id": iid, "time_from": "a", "time_to": "b",
                            "coerced": False, "source_ip": ip})
    monkeypatch.setattr(tools_triage, "_siem_run",
                        lambda op, params, limit, echo: {"ok": True, "query": echo, "count": 1})
    tok = _mount(monkeypatch, _siem_record())
    try:
        for value in (_UUID, _IRI):
            out = tools_triage.siem_events_for_incident(value)
            assert out["ok"] is True, value
            assert seen == {"iid": "11733", "ip": "10.0.0.5"}, value
            assert out["query"]["incident_id"] == "11733"
            assert out["query"]["resolved_from"] == value
    finally:
        session_state.reset(tok)


def test_a_record_not_from_fortisiem_says_so_and_searches_its_ip(monkeypatch):
    from fsr_playbooks.llm import session_state
    called = {}
    monkeypatch.setattr(tools_triage, "_ip_fallback_search",
                        lambda ip, iid, limit: called.setdefault("ip", ip) and {"ok": True})
    tok = _mount(monkeypatch, _siem_record(source="FortiAnalyzer", sourceId="77"))
    try:
        tools_triage.siem_events_for_incident(_UUID)
        assert called["ip"] == "10.0.0.5"
    finally:
        session_state.reset(tok)
    tok = _mount(monkeypatch, _siem_record(source="FortiAnalyzer", sourceId="77", sourceIp=""))
    try:
        out = tools_triage.siem_events_for_incident(_UUID)
        assert out["code"] == "not_a_fortisiem_incident_id"
        assert "came from FortiAnalyzer, not FortiSIEM" in out["message"]
    finally:
        session_state.reset(tok)


def test_a_uuid_that_is_not_the_mounted_record_is_still_refused(monkeypatch):
    from fsr_playbooks.llm import session_state
    monkeypatch.setattr(tools_triage, "_resolve_live_incident", lambda *a: (_ for _ in ()).throw(
        AssertionError("must not reach FortiSIEM")))
    tok = _mount(monkeypatch, _siem_record(), iri="/api/3/incidents/other-uuid")
    monkeypatch.setattr(tools_triage, "_get_with_reauth",
                        lambda client, url: _R(_siem_record(uuid="other-uuid")))
    try:
        out = tools_triage.siem_events_for_incident(_UUID)
        assert out["code"] == "not_a_fortisiem_incident_id"
        assert "came from" not in out["message"]
    finally:
        session_state.reset(tok)


def test_an_unfindable_mounted_incident_falls_back_to_the_records_ip(monkeypatch):
    """Live: no_time_window, and the model never sent the source IP the
    refusal asked for. The mounted record has it."""
    from fsr_playbooks.llm import session_state
    monkeypatch.setattr(tools_triage, "_resolve_live_incident", lambda *a, **k: None)
    called = {}
    monkeypatch.setattr(tools_triage, "_ip_fallback_search",
                        lambda ip, iid, limit: called.update(ip=ip, iid=iid) or {"ok": True})
    tok = _mount(monkeypatch, _siem_record())
    try:
        tools_triage.siem_events_for_incident("11733")
        assert called == {"ip": "10.0.0.5", "iid": "11733"}
        called.clear()
        # Another incident than the mounted record's: still the named refusal.
        out = tools_triage.siem_events_for_incident("324")
        assert out["code"] == "no_time_window" and called == {}
    finally:
        session_state.reset(tok)
