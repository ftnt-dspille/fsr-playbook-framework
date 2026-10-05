"""An action card says which connector configuration it runs on.

The card used to carry no config, so an approved action always ran on the
connector's default: asked live to block an address with the agent-bound
FortiGate config, the chat staged a card without it and the block ran on the
master's default config instead. An agent-only target was unreachable from the
chat, though run_op itself routes an agent config correctly.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import tools_emit, tools_execution
from fsr_playbooks.mcp_server.tools_emit import _card_config, emit_action_card

_fn = getattr(emit_action_card, "fn", emit_action_card)
LOCAL = {"id": "loc-1", "name": "fortigate-lab", "default": True,
         "runs_on_agent": False, "agent_id": "", "agent_name": ""}
AGENT = {"id": "agt-1", "name": "Lab FortiGate (edge-agent)", "default": False,
         "runs_on_agent": True, "agent_id": "a1", "agent_name": "edge-agent"}


@pytest.fixture
def options(monkeypatch):
    opts = [dict(LOCAL), dict(AGENT)]
    monkeypatch.setattr(tools_execution, "connector_config_options",
                        lambda client, connector: opts)
    return opts


def test_named_config_is_chosen_by_name_or_id(options):
    assert _card_config(object(), "fortigate-firewall", "Lab FortiGate (edge-agent)")[0]["id"] == "agt-1"
    assert _card_config(object(), "fortigate-firewall", "agt-1")[0]["runs_on_agent"] is True
    assert _card_config(object(), "fortigate-firewall", "lab fortigate (EDGE-AGENT)")[0]["id"] == "agt-1"


def test_no_config_means_the_default(options):
    chosen, opts = _card_config(object(), "fortigate-firewall", None)
    assert chosen["id"] == "loc-1" and len(opts) == 2


def test_an_unknown_config_is_refused_naming_the_real_ones(options):
    chosen, _ = _card_config(object(), "fortigate-firewall", "nope")
    assert chosen["ok"] is False and chosen["code"] == "unknown_config"
    assert "Lab FortiGate (edge-agent)" in chosen["message"]


def test_no_live_box_fails_open():
    assert _card_config(None, "fortigate-firewall", "anything") == (None, [])


def test_the_card_carries_the_config_and_the_choices(options, monkeypatch):
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    out = _fn(id="c1", connector="fortigate-firewall", operation="block_ip_new",
              summary="Block the C2",
              args={"method": "Quarantine Based", "ip_addresses": "203.0.113.9",
                    "time_to_live": "1 Hour"},
              editable_fields=[], config="Lab FortiGate (edge-agent)")
    assert out["ok"], out
    card = out["card"]
    assert card["config"]["id"] == "agt-1" and card["config"]["agent_name"] == "edge-agent"
    assert [o["id"] for o in card["config_options"]] == ["loc-1", "agt-1"]


def test_a_single_config_needs_no_picker(monkeypatch):
    monkeypatch.setattr(tools_execution, "connector_config_options", lambda c, n: [dict(LOCAL)])
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    card = _fn(id="c1", connector="fortigate-firewall", operation="block_ip_new",
               summary="Block", args={"method": "Quarantine Based",
                                      "ip_addresses": "203.0.113.9", "time_to_live": "1 Hour"},
               editable_fields=[])["card"]
    assert card["config"]["id"] == "loc-1" and "config_options" not in card


def test_emit_card_passes_config_through(options, monkeypatch):
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    fn = getattr(tools_emit.emit_card, "fn", tools_emit.emit_card)
    out = fn("action", {"connector": "fortigate-firewall", "op": "block_ip_new",
                        "title": "Block", "config": "agt-1",
                        "params": {"method": "Quarantine Based",
                                   "ip_addresses": "203.0.113.9", "time_to_live": "1 Hour"}})
    assert out["ok"], out
    assert out["card"]["config"]["id"] == "agt-1"


@pytest.mark.parametrize("notes", [{"notes": "self-contained path"},
                                   {"preferred_params": {"method": "Quarantine Based"}},
                                   ["x"], 1])
def test_config_used_as_notes_is_not_a_crash(options, monkeypatch, notes):
    """Live regression: the model already sent `config` as free-form notes on
    action cards; once `config` meant the run-on configuration, that dict hit
    the name lookup and the card emit raised -- no card, a dead containment
    turn. Notes are not a choice: the card runs on the default, and says so."""
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    fn = getattr(tools_emit.emit_card, "fn", tools_emit.emit_card)
    out = fn("action", {"id": "c1", "connector": "fortigate-firewall", "operation": "block_ip_new",
                        "summary": "Block the address now", "editable_fields": [],
                        "args": {"method": "Quarantine Based", "ip_addresses": "203.0.113.9",
                                 "time_to_live": "1 Day"},
                        "config": notes})
    assert out["ok"], out
    assert out["card"]["config"]["id"] == "loc-1"
    assert "runs on fortigate-lab" in out["note"]


def test_a_config_object_that_names_one_is_honored(options, monkeypatch):
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    fn = getattr(tools_emit.emit_card, "fn", tools_emit.emit_card)
    out = fn("action", {"id": "c1", "connector": "fortigate-firewall", "operation": "block_ip_new",
                        "summary": "Block the address now", "editable_fields": [],
                        "args": {"method": "Quarantine Based", "ip_addresses": "203.0.113.9",
                                 "time_to_live": "1 Day"},
                        "config": {"name": "Lab FortiGate (edge-agent)"}})
    assert out["card"]["config"]["id"] == "agt-1" and "note" not in out
