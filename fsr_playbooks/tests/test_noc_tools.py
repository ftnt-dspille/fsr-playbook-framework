"""Tests for the NOC / FortiManager + FortiAnalyzer device-diagnostic tools.

Like the FAZ/SIEM tests, run_op is monkeypatched so these are offline + fast,
asserting each wrapper's contract: right connector/op/params, the compact
digest shape, tier=1, and the device-down sim fixtures' round-trip.
"""
from __future__ import annotations

import pytest

import fsr_playbooks.mcp_server.tools_execution as texec
from fsr_playbooks.mcp_server import _noc_scenarios as _noc
from fsr_playbooks.mcp_server import _sim_fixtures as fx
from fsr_playbooks.mcp_server import (
    faz_event_summary,
    faz_search_by_serial,
    faz_search_device_events,
    fmg_get_device_list,
    fmg_get_device_status,
    fmg_get_ha_status,
    fmg_get_policy_package_status,
)
from fsr_playbooks.llm.tools import SAFE_TOOLS, TOOL_TIERS

_NOC_TOOLS = [
    "fmg_get_device_list", "fmg_get_device_status", "fmg_get_ha_status",
    "fmg_get_policy_package_status", "faz_search_device_events",
    "faz_search_by_serial", "faz_event_summary",
]


# --- FMG: json_rpc_get is the single transport; the fixture branches on url ---
@pytest.fixture
def fmg(monkeypatch):
    """Route json_rpc_get through the NOC sim fixture; capture the calls."""
    calls = []

    def fake_run_op(connector, op, params=None, **kw):
        calls.append({"connector": connector, "op": op, "params": params or {},
                      "confirm": kw.get("confirm"),
                      "summarize": kw.get("summarize")})
        data = fx._fmg_json_rpc_get(params or {})
        return {"ok": True, "data": data}

    monkeypatch.setattr(texec, "run_op", fake_run_op)
    return calls


def test_device_list_targets_dvmdb_and_digests(fmg):
    out = fmg_get_device_list(adom="root")
    # BRANCH-04 (down) + HQ-01 (up) + every manifest NOC scenario's device.
    assert out["ok"] and out["count"] == 2 + len(_noc.scenarios())
    call = fmg[0]
    assert call["connector"] == "fortinet-fortimanager-json-rpc"
    assert call["op"] == "json_rpc_get"
    assert call["params"]["url"] == "/dvmdb/adom/root/device"
    assert call["confirm"] is True
    # Must bypass run_op's generic summarization: it caps dicts to the first 40
    # keys, which silently strips late-ordered FMG fields (name/sn/ip). The
    # wrapper digests + bounds the rows itself, so it asks for raw output.
    assert call["summarize"] is False
    # And it projects the query to just the digest fields (small payload that
    # also keeps name/sn/ip inside any downstream key cap).
    fields = call["params"]["data"]["fields"]
    assert {"name", "sn", "ip", "conn_status"} <= set(fields)
    down = next(d for d in out["devices"] if d["name"] == "FGT-BRANCH-04")
    assert down["conn_status"] == "down"  # int 0 normalized
    assert down["serial"] == "FGT60F0000000404"
    up = next(d for d in out["devices"] if d["name"] == "FGT-HQ-01")
    assert up["conn_status"] == "up"


def test_device_status_single_device_url(fmg):
    out = fmg_get_device_status("FGT-BRANCH-04")
    assert out["ok"] and out["count"] == 1
    assert fmg[0]["params"]["url"] == "/dvmdb/adom/root/device/FGT-BRANCH-04"
    assert out["devices"][0]["conn_status"] == "down"


def test_ha_status_peer_is_up(fmg):
    out = fmg_get_ha_status("FGT-BRANCH-04")
    assert out["ok"]
    assert fmg[0]["params"]["url"].endswith("/ha_slave")
    roles = {m["name"]: m["conn_status"] for m in out["members"]}
    assert roles["FGT-BRANCH-04"] == "down"
    assert roles["FGT-BRANCH-04-B"] == "up"  # failover survived


def test_policy_package_status_clean_and_device_filter(fmg):
    out = fmg_get_policy_package_status("FGT-BRANCH-04")
    assert out["ok"]
    assert "/_package/status" in fmg[0]["params"]["url"]
    assert out["count"] == 1
    assert out["packages"][0]["status"] == "installed"  # rules out bad push
    assert out["packages"][0]["device"] == "FGT-BRANCH-04"


def test_conn_state_keeps_unknown_distinct_from_down():
    from fsr_playbooks.mcp_server.tools_noc import _fmg_conn_state
    assert _fmg_conn_state(1) == "up"
    assert _fmg_conn_state(0) == "down"
    assert _fmg_conn_state("down") == "down"
    # never-connected / model device must NOT be reported as an outage
    assert _fmg_conn_state("UNKNOWN") == "unknown"
    assert _fmg_conn_state("") == "unknown"


def test_digest_tags_model_device():
    from fsr_playbooks.mcp_server.tools_noc import _fmg_digest_device
    model = _fmg_digest_device({
        "name": "Branch1", "conn_status": "UNKNOWN",
        "flags": ["is_model", "linked_to_model"], "platform_str": "FortiGate-30G",
    })
    assert model["conn_status"] == "unknown"
    assert model["is_model"] is True
    real = _fmg_digest_device({
        "name": "Branch2", "sn": "FGVM...", "ip": "10.99.250.17",
        "conn_status": 0, "flags": None,
    })
    assert real["conn_status"] == "down"
    assert "is_model" not in real  # omitted unless a model device


def test_fmg_error_passthrough(monkeypatch):
    def failing(connector, op, params=None, **kw):
        return {"ok": False, "status": "connector_unhealthy",
                "message": "FortiManager unreachable"}
    monkeypatch.setattr(texec, "run_op", failing)
    out = fmg_get_device_status("FGT-BRANCH-04")
    assert out["ok"] is False
    assert out["code"] == "connector_unhealthy"
    assert "unreachable" in out["message"]


# --- FAZ device-hunt: reuse the FAZ plumbing, scoped to a devid/serial --------
@pytest.fixture
def faz(monkeypatch):
    calls = []

    def fake_run_op(connector, op, params=None, **kw):
        calls.append({"connector": connector, "op": op, "params": params or {}})
        return {"ok": True, "data": fx._faz_device_logs(params or {})}

    monkeypatch.setattr(texec, "run_op", fake_run_op)
    return calls


def test_device_events_scopes_to_devid_and_digests(faz):
    out = faz_search_device_events("FGT-BRANCH-04", window="6h")
    assert out["ok"] and out["count"] == 3
    call = faz[0]
    assert call["connector"] == "fortinet-fortianalyzer"
    assert call["op"] == "start_and_fetch_bulk_device_logs"
    assert call["params"]["devid"] == "FGT-BRANCH-04"
    assert call["params"]["start"].endswith("Z")
    assert call["params"]["wait_for_search_process_to_complete"] is True
    msgs = " ".join(e.get("msg", "") for e in out["events"])
    assert "WAN1" in msgs  # the smoking gun


def test_device_events_optional_filter(faz):
    faz_search_device_events("FGT-BRANCH-04", event_filter="level=critical")
    assert faz[0]["params"]["filter"] == "level=critical"


def test_search_by_serial_uses_serial_as_devid(faz):
    faz_search_by_serial("FGT60F0000000404")
    assert faz[0]["params"]["devid"] == "FGT60F0000000404"


def test_event_summary_rolls_up_by_type_and_action(faz):
    out = faz_event_summary("FGT-BRANCH-04")
    assert out["ok"] and out["scanned"] == 3
    assert out["by_event_type"]["event"] == 3
    assert "link-monitor" in out["by_action"]
    assert out["first_ts"] and out["last_ts"]


# --- manifest-driven NOC scenarios (vpn_tunnel_down) --------------------------

def test_manifest_loads_vpn_tunnel_down():
    sc = _noc.load().get("vpn_tunnel_down")
    assert sc and sc["device"] == "FGT-BRANCH-07"
    assert _noc.by_device("FGT-BRANCH-07")["id"] == "vpn_tunnel_down"
    assert _noc.by_device("FGT60F0000000407")["id"] == "vpn_tunnel_down"  # by serial
    # the manifest carries an induce/teardown recipe for the FS fault driver
    assert sc["induce"]["setup"] and sc["induce"]["teardown"]


def test_fleet_list_includes_manifest_device_as_up(fmg):
    out = fmg_get_device_list(adom="root")
    br07 = next(d for d in out["devices"] if d["name"] == "FGT-BRANCH-07")
    # the device is REACHABLE — a dead tunnel is a VPN failure, not an outage
    assert br07["conn_status"] == "up"


def test_faz_returns_vpn_phase2_logs_for_manifest_device(faz):
    out = faz_search_device_events("FGT-BRANCH-07", logtype="vpn")
    actions = [e["action"] for e in out["events"]]
    assert "phase2-down" in actions and "tunnel-down" in actions
    assert faz[0]["params"]["devid"] == "FGT-BRANCH-07"


def test_faz_default_device_still_tells_device_down_story(faz):
    # an unknown / BRANCH-04 device keeps the original link-down narrative
    out = faz_search_device_events("FGT-BRANCH-04")
    assert any(e["action"] == "link-monitor" for e in out["events"])


# --- registration -------------------------------------------------------------
def test_all_noc_tools_registered_tier_1():
    for name in _NOC_TOOLS:
        assert name in SAFE_TOOLS, f"{name} missing from SAFE_TOOLS"
        assert TOOL_TIERS.get(name) == 1, f"{name} not tier 1"
