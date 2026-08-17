"""The consolidated `picklist` and `connector_health` tools route right
(Phase 1).

Unit-level: constituents are stubbed, so these pin the ROUTING contract
(mode selection from the args, error shapes, pass-through of constituent
results) without a box or a warmed reference DB.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import connector_health, picklist


# ── picklist ────────────────────────────────────────────────────────────────

def _stub_picklists(monkeypatch):
    import fsr_playbooks.mcp_server as m
    monkeypatch.setattr(m, "list_picklists",
                        lambda: {"names": ["Severity", "AlertStatus"]})
    monkeypatch.setattr(m, "get_picklist",
                        lambda name: {"name": name,
                                      "items": [{"itemValue": "High"}]})
    monkeypatch.setattr(m, "picklist_for_field",
                        lambda module, field: {"module": module,
                                               "field": field,
                                               "picklist_name": "Severity"})
    monkeypatch.setattr(
        m, "resolve_picklist_value",
        lambda value, picklist_name=None, module=None, field=None: {
            "ok": True, "value": value, "picklist_name": picklist_name,
            "module": module, "field": field, "iri": "/api/3/picklists/x"})


def test_no_args_lists_names(monkeypatch):
    _stub_picklists(monkeypatch)
    r = picklist()
    assert r["mode"] == "list" and "Severity" in r["names"]


def test_name_alone_lists_items(monkeypatch):
    _stub_picklists(monkeypatch)
    r = picklist(name="Severity")
    assert r["mode"] == "items" and r["items"][0]["itemValue"] == "High"


def test_module_and_field_find_the_backing_picklist(monkeypatch):
    _stub_picklists(monkeypatch)
    r = picklist(module="alerts", field="severity")
    assert r["mode"] == "field" and r["picklist_name"] == "Severity"


def test_module_without_field_names_both_args(monkeypatch):
    _stub_picklists(monkeypatch)
    r = picklist(module="alerts")
    assert r["ok"] is False and r["code"] == "missing_field"
    assert "field" in r["message"]


def test_value_routes_to_resolution(monkeypatch):
    _stub_picklists(monkeypatch)
    r = picklist(name="Severity", value="High")
    assert r["mode"] == "resolve" and r["iri"].startswith("/api/3/")
    assert r["picklist_name"] == "Severity"


def test_value_with_module_field_auto_discovers(monkeypatch):
    _stub_picklists(monkeypatch)
    r = picklist(module="alerts", field="severity", value="High")
    assert r["mode"] == "resolve"
    assert r["module"] == "alerts" and r["field"] == "severity"


def test_picklist_is_in_the_llm_registry():
    from fsr_playbooks.llm.tools import REGISTRY, SAFE_TOOLS, TOOL_TIERS
    assert "picklist" in SAFE_TOOLS and TOOL_TIERS["picklist"] == 0
    spec = REGISTRY["picklist"]
    # Selection guidance lives in the description (assessment Phase 1.5).
    assert "Which args to pass" in spec.description


# ── connector_health ────────────────────────────────────────────────────────

def test_not_installed_short_circuits_with_suggestions(monkeypatch):
    import fsr_playbooks.mcp_server as m
    monkeypatch.setattr(m, "precheck_connector_installed",
                        lambda name, version=None: {
                            "ok": False, "code": "connector_not_installed",
                            "suggestions": ["fortinet-fortigate"]})
    monkeypatch.setattr(m, "healthcheck_connector",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            AssertionError("must not probe health")))
    r = connector_health("fortigate")
    assert r["ok"] is False and r["stage"] == "installed"
    assert r["suggestions"] == ["fortinet-fortigate"]


def test_installed_proceeds_to_reachability(monkeypatch):
    import fsr_playbooks.mcp_server as m
    monkeypatch.setattr(m, "precheck_connector_installed",
                        lambda name, version=None: {"ok": True})
    monkeypatch.setattr(m, "healthcheck_connector",
                        lambda name, version=None, config=None: {
                            "name": name, "status": "Available"})
    r = connector_health("fortinet-fortigate")
    assert r["stage"] == "health" and r["status"] == "Available"
    assert r["installed"] is True


def test_connector_health_is_in_the_llm_registry():
    from fsr_playbooks.llm.tools import REGISTRY, SAFE_TOOLS, TOOL_TIERS
    assert "connector_health" in SAFE_TOOLS
    assert TOOL_TIERS["connector_health"] == 1
    assert "installed" in REGISTRY["connector_health"].description
