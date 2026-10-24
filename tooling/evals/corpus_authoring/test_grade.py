"""Grader controls, box-free, no LLM.

Positive: a task's own real YAML must pass `draft` and `ir` (it compiles and, by
construction, satisfies its own assertions) and therefore `fair_pass`.
Negative: non-playbook YAML must fail every gate -- a grader that passes garbage
proves nothing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks._db import default_db_path

from tooling.evals.corpus_authoring.grade import aggregate, grade_yaml
from tooling.evals.corpus_authoring.sample_corpus import build_tasks

_CORPUS = (Path(__file__).resolve().parents[3]
           / "fsr_playbooks/tests/fixtures/roundtrip_corpus")


@pytest.fixture(scope="module")
def tasks():
    built, _ = build_tasks(_CORPUS, default_db_path(), min_assertions=1)
    assert built
    return built


def test_real_yaml_passes_draft_ir_and_fair(tasks):
    for t in tasks:
        r = grade_yaml(t["real_yaml"], t)
        assert r["draft"], f"{t['id']}: real YAML did not compile: {r['compile_errors']}"
        assert r["ir_passed"], f"{t['id']}: real YAML failed its own assertions: {r['ir_failures']}"
        # fair_pass must hold for the source: it reproduces itself and meets
        # verified unless it itself cannot.
        assert r["fair_pass"], f"{t['id']}: source not fair_pass: {r}"


def test_garbage_fails_every_gate(tasks):
    g = grade_yaml("name: nope\nnot_a_playbook: true\n", tasks[0])
    assert not g["draft"]
    assert not g["verified"]
    assert not g["ir_passed"]
    assert not g["passed"]
    assert not g["fair_pass"]


def test_empty_yaml_is_a_clean_fail(tasks):
    g = grade_yaml("", tasks[0])
    assert g["passed"] is False and g["fair_pass"] is False
    assert "no YAML" in g["detail"]


def test_goal_style_does_not_gate_on_structure(tasks):
    """A goal-only task grades sound+runnable; structural ir is reported but
    must NOT sink fair_pass (many valid designs). A broken-structure but
    compiling+verifying answer should still fair_pass under goal style."""
    t = dict(tasks[0])
    t["style"] = "goal"
    t["strict_ir"] = False
    t["source_verified"] = False  # don't let verify gate the point
    # an answer that compiles but misses the real structure
    r = grade_yaml("name: minimal\nsteps:\n  - id: s\n    type: start\n", t)
    if r["draft"]:  # if it compiles, goal style forgives the structural miss
        assert r["fair_pass"] is True
        assert r["ir_passed"] in (True, False)  # reported either way


def test_prescriptive_style_gates_on_structure(tasks):
    """The same miss under prescriptive style must fail fair_pass."""
    t = dict(tasks[0])
    t["style"] = "prescriptive"
    t["strict_ir"] = True
    t["source_verified"] = False
    r = grade_yaml("name: minimal\nsteps:\n  - id: s\n    type: start\n", t)
    if r["draft"] and not r["ir_passed"]:
        assert r["fair_pass"] is False


def test_aggregate_shapes(tasks):
    rows = [grade_yaml(t["real_yaml"], t) for t in tasks]
    agg = aggregate(rows)
    assert agg["n"] == len(rows)
    for gate in ("draft", "verified", "ir_passed", "passed", "fair_pass", "source_verified"):
        assert gate in agg["overall"]
