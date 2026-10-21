"""Token-reduction summarizers for hunt/pivot tool output.

Two seams keep big FortiSOAR/FortiSIEM payloads out of the agent's context:
- `tools_triage._summarize_record` -- prunes a hydrated FSR record (~100KB)
  to a triage projection (drop nulls, collapse picklists, thin relationships).
- `tools_execution._digest_record_list` / `_summarize_op_output` -- collapse a
  long event/alert row list (FortiSIEM/FAZ hunting) into an aggregate digest.
"""
from __future__ import annotations

import json

from fsr_playbooks.mcp_server import tools_emit as tt_emit
from fsr_playbooks.mcp_server import tools_execution as te
from fsr_playbooks.mcp_server.tools_triage import _summarize_record

# --------------------------------------------------------------------------
# Record projection
# --------------------------------------------------------------------------

def test_summarize_record_drops_noise_keeps_indicators():
    rec = {
        "@id": "/api/3/alerts/u1", "@context": "/api/3/contexts/Alert",
        "@type": "Alert", "uuid": "u1", "name": "C2 egress",
        "sourceIp": "192.168.77.49", "destinationIp": "203.0.113.5",
        "destinationPort": "110", "mitreattackid": "T1552.001",
        "severity": {"@id": "/api/3/picklists/x", "itemValue": "Medium"},
        "status": {"@id": "/api/3/picklists/y", "itemValue": "Open"},
        "createUser": {"@id": "/api/3/people/z", "name": "svc"},
        "ackDate": None, "emailBody": "", "events": [], "detail": {},
        "description": "<div><h4>Cleartext</h4></div>",
    }
    out = _summarize_record(rec)
    # identity + indicator scalars preserved
    assert out["uuid"] == "u1" and out["name"] == "C2 egress"
    assert out["sourceIp"] == "192.168.77.49"
    assert out["destinationIp"] == "203.0.113.5"
    assert out["mitreattackid"] == "T1552.001"
    # picklist objects collapsed to their value
    assert out["severity"] == "Medium" and out["status"] == "Open"
    # HTML stripped
    assert "<" not in out["description"]
    # noise + empty fields dropped
    for k in ("@context", "@type", "createUser", "ackDate", "emailBody",
              "events", "detail"):
        assert k not in out


def test_summarize_record_thins_relationship_lists():
    rec = {
        "@id": "/api/3/alerts/u1", "uuid": "u1", "name": "x",
        "indicators": [
            {"@id": f"/api/3/indicators/{i}", "value": f"1.2.3.{i}",
             "type": "IP", "extra": "x" * 500}
            for i in range(12)
        ],
        "mitremitigations": [
            {"@id": f"/api/3/m/{i}", "name": f"Mitigation {i}",
             "body": "y" * 1000} for i in range(8)
        ],
    }
    out = _summarize_record(rec)
    inds = out["indicators"]
    # capped to _REC_MAX_REL + a "more" marker, members thinned to iri+label
    assert len([x for x in inds if isinstance(x, dict)]) == 5
    assert any(isinstance(x, str) and "more" in x for x in inds)
    assert "extra" not in inds[0]  # 500-char field dropped
    # MITRE reference list collapsed to names only (no hydrated bodies)
    assert all(isinstance(x, str) for x in out["mitremitigations"])


# --------------------------------------------------------------------------
# Event-list digest
# --------------------------------------------------------------------------

def _events(n: int) -> list[dict]:
    ips = ["192.168.77.49", "192.168.77.10", "10.0.0.5"]
    dsts = ["203.0.113.5", "35.189.45.227", "8.8.8.8"]
    return [{
        "phRecvTime": 1780142865000 + i * 1000,
        "eventType": "Net-Traffic" if i % 2 else "Auth-Fail",
        "srcIpAddr": ips[i % 3], "destIpAddr": dsts[i % 3],
        "destPort": 110 if i % 2 else 443, "user": f"u{i % 3}",
        "action": "PERMIT" if i % 2 else "DENY",
        "rawEventMsg": "<189>" + "x" * 400,
    } for i in range(n)]


def test_event_list_digest_aggregates_and_shrinks():
    rows = _events(60)
    raw = len(json.dumps(rows))
    out, trunc = te._summarize_op_output("fortinet-fortisiem",
                                         "search_events", rows)
    assert trunc is True
    assert out["_digest"] == "event_list"
    assert out["count"] == 60
    # facets auto-detected from real FortiSIEM field names
    assert out["facets"]["src_ip"]["field"] == "srcIpAddr"
    assert out["facets"]["dst_ip"]["field"] == "destIpAddr"
    assert out["facets"]["src_ip"]["distinct"] == 3
    # time window captured
    assert out["time_window"]["field"] == "phRecvTime"
    # raw blob dropped from sample rows
    assert all("rawEventMsg" not in s for s in out["samples"])
    # big reduction
    assert len(json.dumps(out, default=str)) < raw * 0.2


def test_short_row_list_passes_through_untouched():
    rows = _events(3)  # below _DIGEST_MIN_ROWS
    out, trunc = te._summarize_op_output("fortinet-fortianalyzer",
                                         "get_alerts", rows)
    assert trunc is False
    assert isinstance(out, list) and len(out) == 3


def test_faz_naming_is_faceted():
    # FortiAnalyzer-style field names (srcip/dstip/devname/subtype)
    rows = [{
        "itime": 1780142865 + i, "srcip": f"10.0.0.{i % 4}",
        "dstip": "203.0.113.5", "user": "svc", "devname": "FGT-EDGE",
        "action": "deny", "subtype": "ips", "msg": "z" * 50,
    } for i in range(20)]
    out, trunc = te._summarize_op_output("fortinet-fortianalyzer",
                                         "get_alert_event_logs", rows)
    assert trunc is True and out["_digest"] == "event_list"
    assert out["facets"]["src_ip"]["field"] == "srcip"
    assert out["facets"]["host"]["field"] == "devname"
    assert out["facets"]["event"]["field"] == "subtype"
    assert out["facets"]["dst_ip"]["distinct"] == 1


# NOTE: find_containment_actions tests moved to the framework suite
# (tooling/tests/test_find_containment_actions.py) when that function moved into
# the library -- RECONCILIATION_PLAN D6 (connector-awareness is authoring, not
# investigation). They test `fsr_playbooks.mcp_server.tools_connector_discovery`
# against the full reference catalog, which the connector suite doesn't ship.


# --------------------------------------------------------------------------
# emit_capability_gap_card -- the never-dead-end card
# --------------------------------------------------------------------------

def _good_capgap_kwargs():
    return dict(
        id="capgap_ip",
        missing="IP containment",
        why="no tier-3 block_ip op on a configured connector",
        fix_steps=["Configure the fortigate-firewall connector"],
        resume={"label": "Re-check & continue", "value": "recheck"},
        tips=[{"text": "Keep a response connector configured"}],
        alternatives=[{"label": "Escalate to T2", "value": "escalate"}],
        docs_url="https://docs/connectors",
    )


def test_emit_capability_gap_card_happy_path():
    out = tt_emit.emit_capability_gap_card(**_good_capgap_kwargs())
    assert out["ok"] is True
    card = out["card"]
    assert card["type"] == "capability_gap"
    assert card["missing"] == "IP containment"
    assert card["resume"] == {"label": "Re-check & continue", "value": "recheck"}
    assert card["fix_steps"] and card["tips"] and card["alternatives"]
    assert card["docs_url"] == "https://docs/connectors"


def test_emit_capability_gap_card_requires_fix_steps():
    kw = _good_capgap_kwargs()
    kw["fix_steps"] = []
    out = tt_emit.emit_capability_gap_card(**kw)
    assert out["ok"] is False and out["code"] == "bad_fix_steps"


def test_emit_capability_gap_card_resume_needs_label_and_value():
    kw = _good_capgap_kwargs()
    kw["resume"] = {"value": "recheck"}  # missing label
    out = tt_emit.emit_capability_gap_card(**kw)
    assert out["ok"] is False and out["code"] == "bad_resume"


def test_emit_capability_gap_card_rejects_duplicate_resume_value():
    kw = _good_capgap_kwargs()
    kw["alternatives"] = [{"label": "Re-check", "value": "recheck"}]  # dup
    out = tt_emit.emit_capability_gap_card(**kw)
    assert out["ok"] is False and out["code"] == "duplicate_value"


def test_capability_gap_suggestion_round_trips_through_emitter():
    # The shared builder's output must be valid emit_capability_gap_card kwargs.
    from fsr_playbooks.mcp_server._shared import _capability_gap_suggestion
    sug = _capability_gap_suggestion(
        id="g", missing="X", why="because",
        fix_steps=["do thing"], resume_value="retry",
        tips=[{"text": "tip"}],
        alternatives=[{"label": "Skip", "value": "skip"}])
    assert sug["resume"] == {"label": "Re-check & continue", "value": "retry"}
    assert "type" not in sug  # emitter adds type
    out = tt_emit.emit_capability_gap_card(**sug)
    assert out["ok"] is True and out["card"]["type"] == "capability_gap"


def test_preflight_not_configured_carries_capability_gap_card(monkeypatch):
    # A connector with no active configuration → error envelope must hand the
    # agent a ready-to-forward capability_gap card, not just a dead-end.
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [{"name": "other"}])
    err = te._preflight_connector(client=object(), connector="virustotal")
    assert err is not None and err["code"] == "connector_not_configured"
    card = err["suggested_card"]
    assert "virustotal" in card["missing"]
    assert card["resume"]["value"] == "recheck_connector"
    assert tt_emit.emit_capability_gap_card(**card)["ok"] is True


def test_resolve_config_id_uses_default_agent_config():
    rows = [{
        "name": "fortigate-firewall",
        "configuration": [
            {"config_id": "cfg-default", "name": "FortiGate", "default": True},
            {"config_id": "cfg-test", "name": "test", "default": False},
        ],
    }]

    assert te._resolve_config_id(rows, "fortigate-firewall", "") == "cfg-default"
    assert te._resolve_config_id(rows, "fortigate-firewall", "test") == "cfg-test"
    assert te._resolve_config_id(rows, "fortigate-firewall",
                                 "cfg-test") == "cfg-test"


def test_resolve_config_id_uses_sole_config_when_no_default():
    rows = [{
        "name": "fortigate-firewall",
        "configuration": [
            {"config_id": "cfg-only", "name": "FortiGate"},
        ],
    }]

    assert te._resolve_config_id(rows, "fortigate-firewall", "") == "cfg-only"


def test_preflight_unhealthy_carries_capability_gap_card(monkeypatch):
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client, force=False: [
                            {"name": "fortisiem", "version": "1.0.0"}])
    monkeypatch.setattr(te, "_resolve_config_id",
                        lambda rows, c, n="": "cfg1")
    monkeypatch.setattr(te, "_cached_health",
                        lambda *a, **k: {"status": "Disconnected",
                                         "message": "SIEM unreachable"})
    err = te._preflight_connector(client=object(), connector="fortisiem")
    assert err is not None and err["code"] == "connector_unhealthy"
    card = err["suggested_card"]
    assert "fortisiem" in card["missing"]
    assert "Disconnected" in card["why"]
    assert tt_emit.emit_capability_gap_card(**card)["ok"] is True


def test_emit_capability_gap_card_minimal():
    # tips/alternatives/docs_url are optional; minimal card still valid.
    out = tt_emit.emit_capability_gap_card(
        id="g1", missing="enrichment", why="virustotal not configured",
        fix_steps=["Configure virustotal"],
        resume={"label": "Retry", "value": "retry"})
    assert out["ok"] is True
    card = out["card"]
    assert "tips" not in card and "alternatives" not in card
    assert "docs_url" not in card
