"""An infrastructure failure must not read as an agent regression.

Rule #2 of docs/AGENT_INTELLIGENCE_PLAN.md. An ERR row (the provider call
raised) scores 0/0 -- deliberately absent from the aggregate -- but carries
`fraction: 0.0`, so a naive cell diff shows the agent falling from 100% to 0%.
Frank was reported as `failing` partly on that basis, when every ERR in that
session was our own client read timeout firing.
"""
from __future__ import annotations

import importlib

harness = importlib.import_module("evals.harness")


def _run(run_id, rows):
    return {"run_id": run_id, "rows": rows,
            "summary": {"agentic_frank": {"fraction": 1.0}}}


def _ok(task, fraction=1.0):
    return {"model": "agentic_frank", "task": task, "fraction": fraction}


def _err(task, msg="provider call: ReadTimeout(...)"):
    return {"model": "agentic_frank", "task": task, "fraction": 0.0,
            "score": 0, "max": 0, "error": msg}


def test_a_timed_out_cell_is_errored_not_regressed():
    d = harness.delta_vs(_run("a", [_ok("soc_phish_block_with_approval")]),
                         _run("b", [_err("soc_phish_block_with_approval")]))
    cell = d["cells"][0]
    assert cell["status"] == "errored"
    assert "ReadTimeout" in cell["detail"]


def test_an_error_on_the_PRIOR_side_is_not_an_improvement_either():
    d = harness.delta_vs(_run("a", [_err("x")]), _run("b", [_ok("x")]))
    assert d["cells"][0]["status"] == "errored"


def test_a_real_drop_is_still_a_regression():
    d = harness.delta_vs(_run("a", [_ok("x")]), _run("b", [_ok("x", 0.5)]))
    assert d["cells"][0]["status"] == "regressed"


def test_the_render_names_the_error_instead_of_a_minus_sign():
    d = harness.delta_vs(_run("a", [_ok("x")]), _run("b", [_err("x")]))
    out = harness.render_delta(d)
    assert "errored" in out and "ReadTimeout" in out
    assert "- regressed" not in out
