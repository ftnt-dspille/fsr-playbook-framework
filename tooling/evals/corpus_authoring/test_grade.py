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


# A minimal, box-independent playbook that compiles but names a connector no
# install has, so verify fails for one reason only: unknown_connector.
_ENV_FAIL_YAML = """\
collection: Env Blocked Demo
description: compiles but names a connector no install has
visible: true
playbooks:
- name: Env Blocked Demo
  description: compiles but names a connector no install has
  trigger_step_id: start
  steps:
  - type: start
    name: start
    button_label: Go
    next: Act
  - type: connector
    name: Act
    connector: zzz_not_installed
    operation: do_a_thing
    arguments: {}
"""


def test_environment_classifier_unit():
    """Pure classifier: a hard fix flagged environment, or an unknown
    connector/module code, is environment-blocked; a plain error is not."""
    from tooling.evals.corpus_authoring.grade import _environment_blocked
    assert _environment_blocked([{"severity": "error", "code": "unknown_connector"}])
    assert _environment_blocked([{"severity": "error", "code": "x", "environment": True}])
    assert not _environment_blocked([{"severity": "error", "code": "bad_value"}])
    assert not _environment_blocked([])  # nothing hard -> not env-blocked
    # a real error mixed with an environment one is NOT purely environment
    assert not _environment_blocked([
        {"severity": "error", "code": "unknown_connector"},
        {"severity": "error", "code": "unreachable_step"}])


def test_environment_only_verify_failure_does_not_sink_fair_pass(tasks):
    """A playbook that compiles but fails verify ONLY because this box lacks the
    connector it names is sound-modulo-env; the product's own remediation calls
    that 'not a defect in the playbook'. env_blocked/verified_fair/fair_pass
    must all hold under strict, source-verified grading.

    Red without the fix: the old grader set verified_ok = verified (False here),
    so fair_pass was False whenever source_verified and the box lacked a
    corpus connector -- the artifact that dominated the first real run."""
    t = dict(tasks[0])
    t["source_verified"] = True
    t["strict_ir"] = False  # isolate the verify dimension
    r = grade_yaml(_ENV_FAIL_YAML, t)
    assert r["draft"], r["compile_errors"]
    assert r["verified"] is False, "demo YAML should fail verify on the missing connector"
    assert r["env_blocked"] is True, r["required_fixes"]
    assert r["verified_fair"] is True
    assert r["fair_pass"] is True


def test_real_soundness_failure_still_sinks_verified_fair(tasks):
    """A non-environment verify failure (garbage) must NOT be excused: it has no
    hard environment fix, so env_blocked is False and verified_fair is False."""
    g = grade_yaml("name: nope\nnot_a_playbook: true\n", tasks[0])
    assert g["env_blocked"] is False
    assert g["verified_fair"] is False


def test_loop_present_is_field_agnostic(tasks):
    """loop_present reports whether ANY step iterates, regardless of the exact
    loop variable a user-voice prompt could never name. For a task that wants a
    loop, the real YAML (which loops) must read loop_present True."""
    t = next((x for x in tasks
              if any(a.get("kind") == "for_each_over" for a in x["ir_assertions"])), None)
    if t is None:
        pytest.skip("no loop task in synthetic corpus")
    r = grade_yaml(t["real_yaml"], t)
    assert r["loop_present"] is True
    # a non-looping task reports None, not False
    t2 = next((x for x in tasks
               if not any(a.get("kind") == "for_each_over" for a in x["ir_assertions"])), None)
    if t2 is not None:
        assert grade_yaml(t2["real_yaml"], t2)["loop_present"] is None


def test_aggregate_shapes(tasks):
    rows = [grade_yaml(t["real_yaml"], t) for t in tasks]
    agg = aggregate(rows)
    assert agg["n"] == len(rows)
    for gate in ("draft", "verified", "ir_passed", "passed", "fair_pass", "source_verified"):
        assert gate in agg["overall"]
