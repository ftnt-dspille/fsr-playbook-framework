"""Contract tests for the NOC manifest -> FS recipe generator + alert seeder.

Offline only (no live box). Locks: the manifest is loadable, the generator
emits one baseline recipe per side + one fault recipe with the right
destructive flags and surfaced ${VAR} params, and the seeder maps alert.* to
the alerts-module payload.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "python"))

import gen_fs_recipes as gen  # noqa: E402
import seed_noc_alert as seed  # noqa: E402

SID = "vpn_tunnel_down"


def test_manifest_has_baseline_and_target():
    m = gen._load_manifest()
    sc = m[SID]
    assert "baseline" in sc and "target" in sc
    # both sides of the VPN slice present
    assert sc["baseline"].get("setup_hq") and sc["baseline"].get("setup_branch")
    assert sc["target"]["hq"]["device"].startswith("${")  # placeholder until filled


def test_generator_emits_baseline_per_side_plus_fault():
    recipes = gen.generate(SID)
    slugs = {r["slug"]: r for r in recipes}
    assert "noc-baseline-vpn-tunnel-down-hq" in slugs
    assert "noc-baseline-vpn-tunnel-down-branch" in slugs
    assert "noc-fault-vpn-tunnel-down" in slugs
    # baselines are non-destructive; the fault is destructive + has a revert
    assert slugs["noc-baseline-vpn-tunnel-down-hq"]["is_destructive"] is False
    fault = slugs["noc-fault-vpn-tunnel-down"]
    assert fault["is_destructive"] is True
    assert fault["teardown"], "fault must carry a revert"


def test_generator_surfaces_placeholders_as_params():
    branch = next(r for r in gen.generate(SID)
                  if r["slug"] == "noc-baseline-vpn-tunnel-down-branch")
    names = {p["name"] for p in branch.get("params_schema", [])}
    # ${VAR} tokens from the CLI must become declared params
    assert {"FAZ_IP", "FMG_IP", "IPSEC_PSK"} <= names


def test_seeder_payload_maps_to_alerts_module():
    sc = seed._load_scenario(SID)
    payload = seed._build_payload(sc["alert"])
    assert seed.ALERTS_MODULE == "alerts"
    assert payload["name"]  # title -> name
    assert payload["severity"] == "High"
    assert "title" not in payload  # mapped, not passed through raw
