"""Render-path probe fixture tests.

These run our offline simulator (`step_through_playbook`) against
each YAML scenario captured by ``probes.probe_render_path`` and assert
the simulator's output_shape lines up with what FSR actually produced
at runtime. Tests skip cleanly when fixtures haven't been recorded
yet — re-run the probe to populate them:

    python -m probes.probe_render_path

Each fixture is a JSON dump of `{yaml, env, steps[]}` from a real
FSR workflow run. The tests don't dictate what the truth IS — they
just pin "the simulator's prediction matches whatever the probe last
captured." That way drift on either side surfaces immediately.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import fsr_playbooks.mcp_server as mcp_server  # noqa: E402
import fsr_playbooks.mcp_server._shared  # noqa: E402, F401

REPO = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO / "tooling" / "tests" / "fixtures" / "render_path_probe"


def _load_fixtures() -> list[Path]:
    if not FIXTURE_DIR.exists():
        return []
    return sorted(FIXTURE_DIR.glob("*.json"))


FIXTURES = _load_fixtures()
if not FIXTURES:
    pytest.skip(
        f"no render-path probe fixtures in {FIXTURE_DIR.relative_to(REPO)} — "
        "run `python -m probes.probe_render_path` against your FSR to "
        "populate them",
        allow_module_level=True,
    )


@pytest.fixture(autouse=True)
def _no_live_fsr(monkeypatch):
    """Pin the simulator offline for these comparison tests."""
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)


@pytest.mark.parametrize("fixture_path", FIXTURES,
                         ids=lambda p: p.stem)
def test_simulator_runs_scenario_to_completion(fixture_path):
    """Smoke: the simulator can step through every scenario without
    errors, and the trace contains the same step names FSR ran.
    """
    data = json.loads(fixture_path.read_text())
    sim = mcp_server.step_through_playbook(
        data["yaml"], playbook=data.get("playbook_name"))
    assert sim.get("trace"), f"empty trace for {fixture_path.name}"

    fsr_step_names = [s["name"] for s in data["steps"] if s.get("name")]
    sim_step_names = [r.get("name") for r in sim["trace"]]

    # Every step FSR executed should also appear in our simulator
    # trace (allowing extras — e.g. terminals we synthesize). A real
    # divergence here means the simulator's navigation is wrong.
    for name in fsr_step_names:
        assert name in sim_step_names, (
            f"{fixture_path.name}: FSR ran {name!r} but simulator did not — "
            f"sim trace: {sim_step_names}")


@pytest.mark.parametrize("fixture_path", FIXTURES,
                         ids=lambda p: p.stem)
def test_simulator_decisions_match_fsr_runtime_shape(fixture_path):
    """For each step FSR executed with status=finished, the
    simulator's output_shape should at minimum predict the same
    top-level keys (when known)."""
    data = json.loads(fixture_path.read_text())
    sim = mcp_server.step_through_playbook(
        data["yaml"], playbook=data.get("playbook_name"))
    by_name = {r["name"]: r for r in sim["trace"]}

    env = data.get("env") or {}
    for step in data["steps"]:
        name = step.get("name")
        status = step.get("status")
        if not name or status != "finished":
            continue
        sim_rec = by_name.get(name)
        if sim_rec is None:
            continue  # covered by the smoke test above

        # FSR exposes the step's output as env["steps"][<jkey>] in
        # the run dump. Compare its top-level keys (when both sides
        # are dicts) to the simulator's prediction.
        jkey = name.replace(" ", "_")
        env_steps = env.get("steps") or {}
        real = env_steps.get(jkey) or env_steps.get(name) or {}
        if not isinstance(real, dict) or not real:
            continue
        sim_shape = sim_rec.get("output_shape") or {}
        if sim_shape.get("kind") != "dict":
            continue
        sim_keys = set(sim_shape.get("top_keys") or [])
        real_keys = set(real.keys())
        # The simulator may legitimately know FEWER keys than reality
        # (e.g. for_each iteration accumulators). Flag only when the
        # simulator predicts a key FSR didn't produce — that's a bug.
        spurious = sim_keys - real_keys
        assert not spurious, (
            f"{fixture_path.name} step {name!r}: simulator predicted "
            f"keys {spurious} that FSR did not produce "
            f"(real keys: {sorted(real_keys)})")
