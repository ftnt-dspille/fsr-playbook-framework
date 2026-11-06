"""An offer on a connector THIS box has not configured is delivered with a
warning, not refused.

The offer used to refuse such a step (`offer_uses_unconfigured_connector`),
and the build prompt told the model to "hold the line". Analysts asked for a
playbook and got none. Now the step is written on the real operation, the
offer goes out, and the card carries `runs_after_setup`: which connector, why
it will not run yet (not configured / not shared with the analyst's team), and
the setup steps. Create and edit offers behave the same. A misspelled config
name is still refused: that is a typo, not a missing connector.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import tools_connector_discovery as tcd
from fsr_playbooks.mcp_server import tools_emit
from fsr_playbooks.mcp_server.tools_emit import _offer_from_yaml

YAML = """\
playbooks:
  - name: Block bad IP
    parameters: []
    steps:
      - name: Start
        type: start
        module: alerts
        next: Block IP
      - name: Block IP
        type: connector
        connector: fortigate-firewall
        operation: block_ip
"""


def _offer(yaml_text=YAML):
    return _offer_from_yaml("c1", "save it", yaml_text,
                            title_suggestion=None, editable_title=True)


def _inventory(monkeypatch, listing):
    def fake(probe=False, verbose=False, only=None, **kw):
        if isinstance(listing, Exception):
            raise listing
        return listing
    monkeypatch.setattr(tcd, "list_configured_connectors", fake)


def test_unconfigured_connector_is_offered_with_a_setup_warning(monkeypatch):
    _inventory(monkeypatch, {"configured": [{"name": "fortinet-fortiedr"},
                                            {"name": "smtp"}]})
    res = _offer()
    assert res["ok"] is True, res
    card = res["card"]
    assert card["type"] == "playbook_offer"
    assert "operation: block_ip" in card["final_yaml"]
    [w] = card["runs_after_setup"]
    assert w["connector"] == "fortigate-firewall"
    assert w["reason"] == "not_configured"
    assert "will not run until" in w["message"]
    assert any("Content Hub" in s for s in w["setup_steps"])
    assert "fortigate-firewall" in res["note"] and "will not run" in res["note"]


def test_not_shared_connector_is_offered_with_a_share_warning(monkeypatch):
    _inventory(monkeypatch, {"configured": [{"name": "smtp"}],
                             "not_shared_with_you": ["fortigate-firewall"]})
    res = _offer()
    assert res["ok"] is True, res
    [w] = res["card"]["runs_after_setup"]
    assert w["connector"] == "fortigate-firewall"
    assert w["reason"] == "not_shared"
    assert "administrator shares" in w["message"]
    assert any("Add your team" in s for s in w["setup_steps"])


def test_configured_connector_carries_no_warning(monkeypatch):
    _inventory(monkeypatch, {"configured": [{"name": "fortigate-firewall"}]})
    res = _offer()
    assert res["ok"] is True
    assert "runs_after_setup" not in res["card"] and "note" not in res


@pytest.mark.parametrize("listing", [
    {"error": "FSR instance not configured"},
    {"configured": []},
    RuntimeError("listing endpoint down"),
])
def test_fails_open_when_the_box_cannot_be_asked(monkeypatch, listing):
    _inventory(monkeypatch, listing)
    res = _offer()
    assert res["ok"] is True and "runs_after_setup" not in res["card"]


def test_misspelled_config_still_blocks(monkeypatch):
    """A wrong config name on a connector the box HAS is a typo, not a missing
    connector: still refused, so the analyst is not handed a step that names
    a configuration that does not exist."""
    _inventory(monkeypatch, {"configured": [{"name": "fortigate-firewall"}]})
    monkeypatch.setattr(tools_emit, "_box_config_names",
                        lambda: {"fortigate-firewall": ["Lab Gate"]})
    res = _offer(YAML.rstrip("\n") + "\n        config: lab gate\n")
    assert res["ok"] is False
    assert res["code"] == "offer_uses_unknown_config"
    assert res["unknown_configs"][0]["near"] == ["Lab Gate"]


def test_enhancement_offer_warns_like_the_create_offer(monkeypatch):
    pytest.importorskip("mcp.server.mcpserver")
    from fsr_playbooks.mcp_server import _verified_yaml, emit_enhancement_offer
    _inventory(monkeypatch, {"configured": [{"name": "smtp"}],
                             "not_shared_with_you": ["fortigate-firewall"]})
    monkeypatch.setattr(tools_emit, "get_grounded_source", lambda: "open")
    vid = _verified_yaml.remember(YAML, diff_summary={})
    res = emit_enhancement_offer("e1", "adds a block", vid)
    assert res["ok"] is True, res
    assert res["card"]["type"] == "enhancement_offer"
    [w] = res["card"]["runs_after_setup"]
    assert (w["connector"], w["reason"]) == ("fortigate-firewall", "not_shared")
    assert "will not run" in res["note"]


def test_a_connector_that_needs_no_configuration_is_never_flagged(monkeypatch):
    # cyops_utilities declares no config fields: it runs without one.
    from fsr_playbooks.mcp_server.tools_emit import _needs_configuration
    assert _needs_configuration("cyops_utilities") is False
    assert _needs_configuration("fortigate-firewall") is True
    assert _needs_configuration("no-such-connector-xyz") is False


def _warmed_row_db(schema_json: str):
    """An in-memory catalog shaped like a box-warmed one: the box listing puts
    the SAVED CONFIGURATIONS (a list) where the schema column is."""
    import sqlite3
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE connectors (name TEXT, version TEXT, config_schema_json TEXT)")
    db.execute("INSERT INTO connectors VALUES ('crowd-strike-falcon', '3.2.0', ?)",
               (schema_json,))
    return db


def test_box_warmed_row_reads_the_schema_from_the_box(monkeypatch):
    # Seen live: every connector on a warmed box read as config-free, so an
    # offer on an unconfigured CrowdStrike Falcon carried no setup notice.
    from fsr_playbooks.mcp_server import tools_emit
    monkeypatch.setattr(tools_emit, "_db", lambda: _warmed_row_db("[]"))
    monkeypatch.setattr(tools_emit, "_LIVE_SCHEMA_CACHE", {})
    asked = []

    def fake(connector, version):
        asked.append((connector, version))
        return {"fields": [{"name": "server_url", "required": True}]}
    monkeypatch.setattr(tools_emit, "_box_config_schema", fake)
    assert tools_emit._needs_configuration("crowd-strike-falcon") is True
    assert asked == [("crowd-strike-falcon", "3.2.0")]


def test_box_warmed_row_fails_open_when_the_box_cannot_be_asked(monkeypatch):
    from fsr_playbooks.mcp_server import tools_emit
    monkeypatch.setattr(tools_emit, "_db", lambda: _warmed_row_db('[{"name": "x"}]'))
    monkeypatch.setattr(tools_emit, "_box_config_schema", lambda c, v: None)
    assert tools_emit._needs_configuration("crowd-strike-falcon") is False
