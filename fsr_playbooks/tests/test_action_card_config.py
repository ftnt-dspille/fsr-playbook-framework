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
               summary="Block 203.0.113.9", args={"method": "Quarantine Based",
                                      "ip_addresses": "203.0.113.9", "time_to_live": "1 Hour"},
               editable_fields=[])["card"]
    assert card["config"]["id"] == "loc-1" and "config_options" not in card


def test_emit_card_passes_config_through(options, monkeypatch):
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    fn = getattr(tools_emit.emit_card, "fn", tools_emit.emit_card)
    out = fn("action", {"connector": "fortigate-firewall", "op": "block_ip_new",
                        "title": "Block 203.0.113.9", "config": "agt-1",
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


def test_configless_builtin_passes_preflight_with_no_configuration(monkeypatch):
    """cyops_utilities ships with FortiSOAR and has no saved configuration; the
    preflight must not report it as unconfigured (action cards and run_op)."""
    monkeypatch.setattr(tools_execution, "_configured_rows", lambda *a, **k: [])
    assert tools_execution._preflight_connector(object(), "cyops_utilities") is None
    err = tools_execution._preflight_connector(object(), "some-other-connector")
    assert err and err["code"] == "connector_not_configured"


# --- several configs, none default: the card carries the one the reads used ---
# Live (FortiManager with five configs, only one reachable): the card had no
# config, the approval ran on none and failed INTEGRATION-12, and the approval
# was consumed. The investigation's own reads had already answered on one.
FIVE = [{"id": f"fmg-{i}", "name": f"managerID_{i}", "default": False,
         "runs_on_agent": False, "agent_id": "", "agent_name": ""}
        for i in range(1, 6)]


@pytest.fixture
def five(monkeypatch):
    monkeypatch.setattr(tools_execution, "connector_config_options",
                        lambda client, connector: [dict(o) for o in FIVE])
    tools_execution._CONFIG_USED.clear()
    yield
    tools_execution._CONFIG_USED.clear()


def test_no_default_and_nothing_read_leaves_the_card_without_a_config(five):
    chosen, opts = _card_config(object(), "fortinet-fortimanager-json-rpc", None)
    assert chosen is None and len(opts) == 5


def test_the_card_carries_the_config_the_reads_answered_on(five):
    tools_execution.note_config_used("fortinet-fortimanager-json-rpc", "fmg-2")
    chosen, opts = _card_config(object(), "fortinet-fortimanager-json-rpc", None)
    assert chosen["id"] == "fmg-2" and len(opts) == 5


def test_a_config_used_by_another_connector_is_not_borrowed(five):
    tools_execution.note_config_used("fortigate-firewall", "fmg-2")
    assert _card_config(object(), "fortinet-fortimanager-json-rpc", None)[0] is None


def test_a_config_no_longer_offered_is_not_carried(five):
    tools_execution.note_config_used("fortinet-fortimanager-json-rpc", "gone")
    assert _card_config(object(), "fortinet-fortimanager-json-rpc", None)[0] is None


def test_an_explicit_config_still_wins_over_the_one_used(five):
    tools_execution.note_config_used("fortinet-fortimanager-json-rpc", "fmg-2")
    chosen, _ = _card_config(object(), "fortinet-fortimanager-json-rpc", "managerID_4")
    assert chosen["id"] == "fmg-4"


def test_the_emitted_card_carries_the_used_config(five, monkeypatch):
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)
    tools_execution.note_config_used("fortinet-fortimanager-json-rpc", "fmg-2")
    out = _fn(id="c1", connector="fortinet-fortimanager-json-rpc",
              operation="json_rpc_execute", summary="Install the package",
              args={"url": "/securityconsole/install/package", "data": {}},
              editable_fields=[])
    assert out["ok"], out
    assert out["card"]["config"]["id"] == "fmg-2"


# --- no read of the connector in the session, none default: ask the health ---
# Live: a bare "stage an install" card (no investigation first) had no config
# and five options; approving it failed INTEGRATION-12 and consumed the card.
FMG = "fortinet-fortimanager-json-rpc"


def _health(monkeypatch, verdicts):
    """Per-config healthcheck verdicts by config id (status string, or None =
    the probe failed). Probes are counted in the returned list."""
    probed: list[str] = []
    monkeypatch.setattr(tools_execution, "_configured_rows",
                        lambda client: [{"name": FMG, "version": "1.0"}])
    monkeypatch.setattr(tools_execution, "_cached_health", lambda *a, **k: None)
    monkeypatch.setattr(tools_execution, "_store_health", lambda *a, **k: None)

    def live(client, connector, version, config="", agent_id=""):
        probed.append(config)
        st = verdicts[config]
        return ({"status": "error", "_probe_failed": True} if st is None
                else {"status": st})

    monkeypatch.setattr(tools_execution, "_live_healthcheck", live)
    return probed


def test_the_one_healthy_config_is_preselected(five, monkeypatch):
    _health(monkeypatch, {o["id"]: "Disconnected" for o in FIVE} | {"fmg-2": "Available"})
    chosen, opts = _card_config(object(), FMG, None)
    assert chosen["id"] == "fmg-2" and len(opts) == 5


def test_two_healthy_configs_leave_the_pick_to_the_analyst(five, monkeypatch):
    _health(monkeypatch, {o["id"]: "Disconnected" for o in FIVE}
            | {"fmg-2": "Available", "fmg-3": "Available"})
    assert _card_config(object(), FMG, None)[0] is None


def test_a_config_that_could_not_be_judged_is_not_guessed_around(five, monkeypatch):
    _health(monkeypatch, {o["id"]: "Disconnected" for o in FIVE}
            | {"fmg-2": "Available", "fmg-5": None})
    assert _card_config(object(), FMG, None)[0] is None


def test_reads_already_made_skip_the_probe(five, monkeypatch):
    probed = _health(monkeypatch, {})
    tools_execution.note_config_used(FMG, "fmg-4")
    assert _card_config(object(), FMG, None)[0]["id"] == "fmg-4"
    assert probed == []


def _emit(**kw):
    return _fn(id="c1", connector=FMG, operation="json_rpc_execute",
               summary="Install the package", editable_fields=[],
               args={"url": "/securityconsole/install/package",
                     "data": {"adom": "root", "pkg": "default", "flags": None,
                              "scope": [{"name": "fgt-1", "vdom": "root"}]}},
               **kw)


@pytest.fixture
def emit_env(five, monkeypatch):
    monkeypatch.setattr(tools_execution, "_live_client_for_grounding", lambda: object())
    monkeypatch.setattr(tools_execution, "_preflight_connector", lambda *a, **k: None)


def test_a_card_with_no_config_to_run_on_requires_the_pick(emit_env, monkeypatch):
    _health(monkeypatch, {o["id"]: "Disconnected" for o in FIVE})
    card = _emit()["card"]
    assert "config" not in card and card["config_required"] is True
    assert len(card["config_options"]) == 5


def test_a_card_that_found_its_config_does_not_require_one(emit_env, monkeypatch):
    _health(monkeypatch, {o["id"]: "Disconnected" for o in FIVE} | {"fmg-2": "Available"})
    card = _emit()["card"]
    assert card["config"]["id"] == "fmg-2" and "config_required" not in card


def test_an_omitted_member_is_absent_not_null(emit_env, monkeypatch):
    _health(monkeypatch, {o["id"]: "Disconnected" for o in FIVE})
    data = _emit()["card"]["args"]["data"]
    assert "flags" not in data
    assert data["scope"] == [{"name": "fgt-1", "vdom": "root"}] and data["pkg"] == "default"
