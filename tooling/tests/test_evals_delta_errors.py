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


# --- the same rule one level up: is the WORLD the same? --------------------
#
# `tool_substrate` / `record_substrate` / `offline` have been recorded since
# the registry seam landed, along with the rule that follows from them -- a run
# is only comparable to another with the SAME substrate -- but nothing enforced
# it. The pinned tool-gate baseline `20260813T153315Z` predates the fields and
# carries none of them, so every diff against it has been against a run whose
# tool set is unknown.

def _labeled(run_id, rows, **substrate):
    r = _run(run_id, rows)
    r.update(substrate)
    return r


_SAME = {"tool_substrate": "framework+connector",
         "record_substrate": "soc_invest_surface", "offline": True}


def test_matching_substrates_compare_normally():
    d = harness.delta_vs(_labeled("a", [_ok("x")], **_SAME),
                         _labeled("b", [_ok("x", 0.5)], **_SAME))
    assert d["substrate"]["comparable"] is True
    assert d["cells"][0]["status"] == "regressed"
    assert "SUBSTRATE MISMATCH" not in harness.render_delta(d)


def test_a_different_tool_set_makes_the_two_runs_incomparable():
    d = harness.delta_vs(
        _labeled("a", [_ok("x")], **{**_SAME, "tool_substrate": "framework-only"}),
        _labeled("b", [_ok("x", 0.5)], **_SAME))
    assert d["substrate"]["comparable"] is False
    out = harness.render_delta(d)
    assert "SUBSTRATE MISMATCH" in out
    assert "framework-only → framework+connector" in out
    # Above the table. By the time someone has read the cells they have
    # already formed an opinion about the agent.
    assert out.index("SUBSTRATE MISMATCH") < out.index("status")


def test_an_UNLABELED_run_is_a_mismatch_not_a_pass():
    """The case that actually bit: a baseline older than the fields.

    Treating absent-as-matching is how an unlabeled run gets diffed against a
    labeled one forever without anyone being told.
    """
    d = harness.delta_vs(_run("old-baseline", [_ok("x")]),
                         _labeled("b", [_ok("x")], **_SAME))
    assert d["substrate"]["comparable"] is False
    assert "unknown" in harness.render_delta(d)
