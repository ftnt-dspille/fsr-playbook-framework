"""Build deterministic trace fixtures for the wiring-resolution parity campaign.

Replays a *coherent* investigation through the real ``run_op`` tool in SIM mode
with the skill-trace recorder installed, then dumps ``SkillTrace.to_json()``.

Why replay instead of hand-authoring (the original method): a hand-written
trace re-introduces the very failure mode the trace compiler removes — guessing
each op's output shape and the cross-step value coincidences. The sim fixtures
(``fsr_core/mcp_server/_sim_fixtures.py``) encode a C2 investigation whose values
are cross-referenced by construction (``_C2_IP`` shows up in
``get_incidents.indicator`` / ``search_events.destIpAddr`` and is the input to
``block_ip_new``; ``_HOST_IP`` from ``search_events.srcIpAddr`` feeds
``get_host_context``). Replaying through ``run_op`` records exactly the
``ref_prefix`` the live path would (``data``-nesting flag), so the fixture is a
faithful stand-in. Deterministic + offline → CI-safe.

These fixtures are the trace-compiler side of the **default-flip** parity
evidence: feed each into ``scoring.score_wiring_resolution`` and assert every
value-matched wire resolves with no static error.

Run as a script to (re)write ``store/trace_fixtures/<scenario>.json``:

    python python/evals/build_trace_fixture.py            # write + verify all
    python python/evals/build_trace_fixture.py --check    # verify only, no write
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from typing import Any

# These two IPs are the cross-referenced anchors the sim fixtures share; the
# value-match wiring must recover them across steps.
from fsr_core.mcp_server._sim_fixtures import _C2_IP, _HOST_IP

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "store" / "trace_fixtures"


def _install_sim_bridge() -> None:
    """Point the ``probes._env`` seam at the simulated client, mirroring the
    connector's ``simulation_mode`` bridge, and clear preflight caches so each
    build is independent. Same wiring as test_sim_run_op_integration's fixture,
    minus pytest."""
    from fsr_core.mcp_server import _sim_client as sc
    from fsr_core.mcp_server import tools_execution as te

    env_mod = types.ModuleType("probes._env")
    env_mod.get_client = sc.get_client          # type: ignore[attr-defined]
    env_mod.get_config = sc.get_config          # type: ignore[attr-defined]
    probes_mod = types.ModuleType("probes")
    probes_mod._env = env_mod                    # type: ignore[attr-defined]
    sys.modules["probes"] = probes_mod
    sys.modules["probes._env"] = env_mod
    te._CONFIGURED_CACHE["rows"] = None
    te._CONFIGURED_CACHE["ts"] = 0.0


# Each scenario is an ordered list of (connector, op, params, confirm) — exactly
# what an analyst would pivot through. Only SIM-covered ops are used.
_SCENARIOS: dict[str, list[tuple[str, str, dict[str, Any], bool]]] = {
    # Full C2 containment: incident → events → enrich the external IP and the
    # internal host → confirm malicious on VT → block the C2 IP.
    "c2_containment": [
        ("fortinet-fortisiem", "get_incidents",
         {"timeFrom": "2026-05-29T00:00:00Z",
          "timeTo": "2026-05-29T23:59:59Z"}, False),
        ("fortinet-fortisiem", "search_events",
         {"attribute": f"destIpAddr = {_C2_IP}",
          "select_clause": "eventType, srcIpAddr, destIpAddr, user"}, False),
        ("fortinet-fortisiem", "get_ip_context", {"value": _C2_IP}, False),
        ("fortinet-fortisiem", "get_host_context", {"value": _HOST_IP}, False),
        ("virustotal", "query_ip", {"ip": _C2_IP}, False),
        ("fortigate-firewall", "block_ip_new",
         {"method": "Quarantine Based", "ip_addresses": _C2_IP, "time_to_live": "1 Hour"}, True),
    ],
    # Minimal enrich-then-block: the smallest coherent containment, the shape a
    # direct-containment chat produces.
    "enrich_then_block": [
        ("virustotal", "query_ip", {"ip": _C2_IP}, False),
        ("fortigate-firewall", "block_ip_new",
         {"method": "Quarantine Based", "ip_addresses": _C2_IP, "time_to_live": "1 Hour"}, True),
    ],
}


def build_trace(scenario: str) -> str:
    """Replay one scenario through run_op (sim) with the recorder on; return the
    trace JSON. Raises if an op didn't execute cleanly (a broken sim fixture or a
    preflight regression — we want that to fail loudly, not bake a bad fixture)."""
    from fsr_core.agent import skill_trace as st
    from fsr_core.mcp_server import tools_execution as te

    steps = _SCENARIOS[scenario]
    trace = st.SkillTrace()
    st.set_active_trace(trace)
    try:
        for connector, op, params, confirm in steps:
            out = te.run_op(connector, op, params=params, confirm=confirm)
            if not out.get("ok"):
                raise RuntimeError(
                    f"{scenario}: run_op {connector}.{op} did not succeed: {out}")
    finally:
        st.set_active_trace(None)
    if len(trace) != len(steps):
        raise RuntimeError(
            f"{scenario}: recorded {len(trace)} calls, expected {len(steps)} "
            "(is the recorder installed / are all ops sim-covered?)")
    return trace.to_json()


def assert_cross_step_coincidence(trace_json: str) -> None:
    """Sanity-gate that the fixture actually carries the cross-step value
    coincidence the wiring match exists to recover: the IP a containment op
    blocks must appear in a PRIOR op's recorded output. Without this the fixture
    would 'pass' wiring trivially (nothing to wire) and prove nothing."""
    from fsr_core.agent.skill_trace import SkillTrace

    trace = SkillTrace.from_json(trace_json)
    block = next((c for c in trace.calls
                  if "block_ip" in (c.resolved_inputs.get("operation") or "")), None)
    if block is None:
        return  # an enrich-only scenario has no containment to anchor
    earlier = trace.calls[: trace.calls.index(block)]
    blob = json.dumps([c.observed_output for c in earlier])
    # resolved_inputs is FLAT: the op's params sit at top level alongside the
    # meta keys. Any scalar param value that also appears in a prior op's output
    # is a wire the value-match must recover. Require at least one.
    _meta = {"connector", "operation", "config", "agent"}
    params = {k: v for k, v in block.resolved_inputs.items() if k not in _meta}
    matched = [v for v in params.values()
               if isinstance(v, str) and v and v in blob]
    if not matched:
        raise RuntimeError(
            f"no cross-step coincidence: none of the containment params "
            f"{list(params.values())} appear in any prior op output — fixture "
            "would not exercise value-match wiring")


def verify_wiring(trace_json: str) -> dict[str, Any]:
    """Run the parity dimension over a fixture and return its level dict."""
    from evals import scoring
    return scoring.score_wiring_resolution(trace_json)


def build_all(write: bool = True) -> dict[str, dict[str, Any]]:
    """Build, gate, and wiring-verify every scenario. Returns a per-scenario
    summary; writes the JSON fixtures when ``write`` is True."""
    _install_sim_bridge()
    if write:
        _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    for scenario in _SCENARIOS:
        trace_json = build_trace(scenario)
        assert_cross_step_coincidence(trace_json)
        wiring = verify_wiring(trace_json)
        if write:
            (_FIXTURE_DIR / f"{scenario}.json").write_text(trace_json)
        results[scenario] = {
            "calls": len(json.loads(trace_json).get("calls", [])),
            "wiring_passed": wiring.get("passed"),
            "unresolved_wires": wiring.get("unresolved_wires"),
            "static_errors": wiring.get("static_errors"),
        }
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify only; do not (re)write the fixtures")
    args = ap.parse_args(argv)
    results = build_all(write=not args.check)
    ok = True
    for scenario, r in results.items():
        status = "OK " if r["wiring_passed"] else "FAIL"
        if not r["wiring_passed"]:
            ok = False
        print(f"  {status} {scenario}: {r['calls']} calls, "
              f"wiring_passed={r['wiring_passed']} "
              f"unresolved={r['unresolved_wires']} static={r['static_errors']}")
    dest = "checked" if args.check else f"written to {_FIXTURE_DIR}"
    print(f"{'all wiring resolved' if ok else 'WIRING FAILURES'} ({dest})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
