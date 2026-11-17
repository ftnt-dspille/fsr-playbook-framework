"""find(containment) says which configured connectors it dropped, and why.

Live: "block ip 13.246.44.9" -- the box's FortiGate was configured but
Disconnected, so the health probe dropped it without a word. The only action
left was NinjaOne Run Script, and the agent staged that with "<required>"
placeholders as an IP block. Dropping is right (never stage on a known-dead
connector); hiding it is not -- the analyst needs "FortiGate can block this,
once its connection is fixed", not a script runner in its place.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_connector_discovery as tcd


@pytest.fixture
def probed(monkeypatch):
    monkeypatch.setattr(tcd, "list_configured_connectors", lambda **_: {
        "configured": [{"name": "fortigate-firewall", "status": "Completed",
                        "version": "5.4.0"}]})
    monkeypatch.setattr(_shared, "_live_client", lambda: object())
    monkeypatch.setattr(tcd, "_healthcheck_many",
                        lambda client, targets, **_: {t[0]: "Disconnected" for t in targets})
    return tcd.find_containment_actions(target_type="ip", probe=True)


def test_a_disconnected_connector_is_dropped_but_named(probed):
    assert probed["actions"] == []
    gone = {(u["connector"], u["op"]) for u in probed["unavailable"]}
    assert ("fortigate-firewall", "block_ip_new") in gone
    assert all(u["status"] == "Disconnected" for u in probed["unavailable"])
    assert "fortigate-firewall" in probed["message"]
    assert "connection" in probed["message"].lower()


def test_find_surfaces_the_dropped_list_at_the_top(monkeypatch, probed):
    from fsr_playbooks.mcp_server.tools_find import _find_actions
    out = _find_actions(lambda **_: probed, lambda **_: {"actions": []},
                        lambda **_: {"actions": []}, query="", target_type="ip",
                        action_type="containment", module="", limit=10)
    assert {u["connector"] for u in out["unavailable"]} == {"fortigate-firewall"}
