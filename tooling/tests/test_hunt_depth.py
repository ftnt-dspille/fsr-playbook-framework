"""B2 — hunt depth/breadth gate (Chat Intelligence Plan).

`_score_investigation_quality` emits a `hunt_depth` gate when a fixture defines
a `hunt_chain`: an ordered list of pivot stages (fact-matchers) the agent should
traverse from the seed IOC. Depth = stages reached; breadth = distinct connectors
exercised. Pure, offline, deterministic — it belongs in `make chat-fast`.

The reference scenario is the seeded multi-hop chain
smithDesktop -> 10.50.60.70 -> 102.220.160.21.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT / "tooling", REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evals.scoring import _score_investigation_quality  # noqa: E402
from evals.levers import lever_for  # noqa: E402

# A 4-stage hunt: pull the incident, correlate on the host, pivot to the
# internal IP, then chase the external C2 endpoint with threat intel.
CHAIN = [
    {"tool": "get_record", "args_contains": ["b4a62c3b"], "label": "pull the incident"},
    {"tool": "search_module_records", "args_contains": ["smithDesktop"],
     "label": "correlate host smithDesktop"},
    {"args_contains": ["10.50.60.70"], "label": "pivot to internal IP 10.50.60.70"},
    {"tool": "run_op", "args_contains": ["102.220.160.21"],
     "label": "enrich external C2 102.220.160.21"},
]


def _trace_through(*stages_present: str) -> list[dict]:
    """Build a trace whose calls satisfy the named indicator stages."""
    calls = []
    if "incident" in stages_present:
        calls.append({"name": "get_record", "args": {"uuid": "b4a62c3b-x"}})
    if "host" in stages_present:
        calls.append({"name": "search_module_records",
                      "args": {"module": "incidents", "query": "smithDesktop"}})
    if "internal" in stages_present:
        calls.append({"name": "search_module_records",
                      "args": {"query": "10.50.60.70"}})
    if "external" in stages_present:
        calls.append({"name": "run_op",
                      "args": {"connector": "virustotal", "op": "query_ip",
                               "params": {"ip": "102.220.160.21"}}})
    return calls


def _gate(trace, quality):
    return _score_investigation_quality(trace, quality)["hunt_depth"]


def test_skips_without_a_chain():
    g = _gate(_trace_through("incident"), {"tool_budget_max": 12})
    assert g["skipped"] is True


def test_full_chain_passes():
    trace = _trace_through("incident", "host", "internal", "external")
    g = _gate(trace, {"hunt_chain": CHAIN})
    assert not g["skipped"] and g["passed"], g
    assert g["depth"] == 4 and g["stages"] == 4
    assert "virustotal" in g["connectors"]


def test_shallow_hunt_fails_default_min_depth():
    # Reaches only the host, never pivots to the IP chain — depth 2 < 4.
    trace = _trace_through("incident", "host")
    g = _gate(trace, {"hunt_chain": CHAIN})
    assert not g["passed"] and g["depth"] == 2
    assert any("10.50.60.70" in m for m in g["missing"])


def test_lowered_min_depth_passes_partial():
    trace = _trace_through("incident", "host", "internal")
    g = _gate(trace, {"hunt_chain": CHAIN, "min_hunt_depth": 3})
    assert g["passed"] and g["depth"] == 3


def test_breadth_floor_can_fail_a_deep_but_narrow_hunt():
    # Reaches all 4 stages but only one connector — breadth gate trips.
    trace = _trace_through("incident", "host", "internal", "external")
    g = _gate(trace, {"hunt_chain": CHAIN, "min_hunt_breadth": 2})
    assert not g["passed"] and g["breadth"] == 1 and g["depth"] == 4


def test_gate_has_a_lever():
    assert lever_for("hunt_depth") != lever_for("__nope__")
