"""Phase B: NOC device-down routing + scenario wiring.

The FMG/FAZ read tools (Phase A) are only useful if the triage layer routes a
device-down record to them. These cover the fortimanager source toolset, the
device-centric pivots, and the `device_down` scenario classification + recipes.
"""
from __future__ import annotations

from fsr_core.llm.triage_sources import (
    build_source_routing_block,
    canonical_source,
    toolset_for,
)
from fsr_core.llm.triage_scenarios import classify_alert, render_recipes


def _noc_norm(source="Fortinet FortiManager", device="FGT-BRANCH-04",
              name="FGT-BRANCH-04 stopped reporting to FortiManager"):
    return {
        "name": name,
        "source_connector": source,
        "related_sources": [],
        "incident_id": None,
        "mitre": [],
        "evidence_events": [],
        "indicators": {"ips": [], "hosts": [device] if device else [],
                       "users": []},
    }


def test_canonical_source_maps_fortimanager():
    assert canonical_source("Fortinet FortiManager") == "fortimanager"
    assert canonical_source("fortinet-fortimanager-json-rpc") == "fortimanager"
    assert canonical_source("FMG") == "fortimanager"


def test_fortimanager_toolset_is_device_centric():
    ts = toolset_for("FortiManager")
    assert ts["connector"] == "fortinet-fortimanager-json-rpc"
    assert ts["device"].startswith("fmg_get_device_status")
    assert any("fmg_get_ha_status" in t for t in ts["device_extra"])


def test_routing_block_fills_device_pivots():
    block = build_source_routing_block(_noc_norm())
    assert "FortiManager" in block
    assert 'fmg_get_device_status(device="FGT-BRANCH-04")' in block
    assert "fmg_get_ha_status" in block
    assert "fmg_get_policy_package_status" in block
    assert "faz_search_device_events" in block


def test_classify_picks_device_down_scenario():
    sc = classify_alert(_noc_norm())
    assert sc["id"] == "device_down"
    assert sc["ti_targets"] == []  # no external TI for a device-down


def test_device_down_recipes_are_entity_filled():
    sc = classify_alert(_noc_norm())
    recipes = render_recipes(sc, _noc_norm())
    joined = " ".join(recipes)
    assert 'fmg_get_device_status(device="FGT-BRANCH-04")' in joined
    assert "faz_search_device_events" in joined


def test_device_down_matches_on_keyword_without_fmg_source():
    # A FAZ-sourced "device stopped logging" record should still classify NOC
    # and route to FAZ device events (no FMG device tool in the FAZ toolset).
    norm = _noc_norm(source="Fortinet FortiAnalyzer",
                     name="Device stopped logging for more than 1 hour")
    sc = classify_alert(norm)
    assert sc["id"] == "device_down"
    recipes = render_recipes(sc, norm)
    assert any("faz_search_device_events" in r for r in recipes)


def test_security_alert_does_not_misclassify_as_device_down():
    norm = {
        "name": "Outbound C2 beacon to known malware IP",
        "source_connector": "Fortinet FortiSIEM",
        "related_sources": [], "incident_id": None, "mitre": [],
        "evidence_events": [],
        "indicators": {"ips": [{"value": "185.220.101.47", "internal": False}],
                       "hosts": [], "users": []},
    }
    assert classify_alert(norm)["id"] != "device_down"


# ----- vpn_tunnel_down scenario --------------------------------------------

def test_classify_picks_vpn_tunnel_down():
    norm = _noc_norm(source="Fortinet FortiAnalyzer", device="FGT-BRANCH-07",
                     name="Site-to-site VPN HQ↔BRANCH07 is down — branch isolated")
    sc = classify_alert(norm)
    assert sc["id"] == "vpn_tunnel_down"
    assert sc["ti_targets"] == []  # no external TI for a NOC tunnel event


def test_vpn_tunnel_down_recipes_confirm_device_then_read_vpn_logs():
    norm = _noc_norm(source="Fortinet FortiAnalyzer", device="FGT-BRANCH-07",
                     name="IPsec phase2 renegotiation failed on HQ-BRANCH07 tunnel")
    sc = classify_alert(norm)
    assert sc["id"] == "vpn_tunnel_down"
    joined = " ".join(render_recipes(sc, norm))
    # confirm reachability first (rules out a device outage)…
    assert 'fmg_get_device_status(device="FGT-BRANCH-07")' in joined
    # …then read the VPN logs
    assert 'logtype="vpn"' in joined


def test_vpn_tunnel_down_beats_device_down_on_tunnel_wording():
    # "VPN ... is down" should NOT fall through to device_down — the device is up.
    norm = _noc_norm(source="Fortinet FortiAnalyzer", device="FGT-BRANCH-07",
                     name="VPN tunnel HQ-BRANCH07 is down, branch isolated")
    assert classify_alert(norm)["id"] == "vpn_tunnel_down"
