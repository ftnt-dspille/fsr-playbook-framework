"""The trace-fixture builder is the trace-compiler side of the default-flip
parity evidence: replay a coherent investigation through run_op (sim) with the
recorder on, then assert every value-matched wire of the resulting trace
resolves. Deterministic + offline → CI-safe (no live FSR, no Anthropic).

Guards three things at once:
  1. the sim replay still succeeds for every scenario (preflight/param-gate
     regressions surface here, not as a silently-bad baked fixture),
  2. each fixture carries a real cross-step value coincidence (so wiring isn't
     passing trivially), and
  3. `score_wiring_resolution` reports all wires resolved with no static error.
"""
from __future__ import annotations

import importlib

bt = importlib.import_module("evals.build_trace_fixture")


def test_all_scenarios_build_and_fully_wire():
    # write=False: verify without touching the checked-in fixtures.
    results = bt.build_all(write=False)
    assert set(results) == set(bt._SCENARIOS), results
    for scenario, r in results.items():
        assert r["wiring_passed"] is True, (scenario, r)
        assert r["unresolved_wires"] == [], (scenario, r)
        assert r["static_errors"] == [], (scenario, r)


def test_replayed_fixture_feeds_score_wiring_resolution():
    bt._install_sim_bridge()
    trace_json = bt.build_trace("c2_containment")
    # the coincidence gate must hold (raises otherwise)
    bt.assert_cross_step_coincidence(trace_json)
    lv = bt.verify_wiring(trace_json)
    assert lv["passed"] is True
    assert lv["skipped"] is False


def test_enrich_then_block_has_block_after_enrich():
    bt._install_sim_bridge()
    import json
    calls = json.loads(bt.build_trace("enrich_then_block"))["calls"]
    ops = [c["resolved_inputs"]["operation"] for c in calls]
    assert ops == ["query_ip", "block_ip_new"], ops
