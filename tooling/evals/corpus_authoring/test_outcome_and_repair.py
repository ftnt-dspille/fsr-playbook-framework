"""Goal-assertion deriver + problem-solving (repair) eval, box-free, no LLM.

Uses the committed synthetic roundtrip_corpus (the only corpus in the repo).
Run: FSRPB_DEV=1 .venv/bin/python -m pytest \
     tooling/evals/corpus_authoring/test_outcome_and_repair.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml

from tooling.evals.corpus_authoring import mutate, outcome, repair_grade
from tooling.evals.corpus_authoring.sample_corpus import build_tasks

_CORPUS = (Path(__file__).resolve().parents[3]
           / "fsr_playbooks/tests/fixtures/roundtrip_corpus")


@pytest.fixture(scope="module")
def tasks():
    built, _ = build_tasks(_CORPUS, default_db_path(), min_assertions=1)
    assert built
    return built


# --- outcome deriver -------------------------------------------------------
def _coll(yaml_text, db):
    return compile_yaml(yaml_text, db).ir


# A record-writing playbook, hand-built so the deriver is exercised regardless
# of what the synthetic corpus happens to contain. Creates an alert with one
# literal field (name) and one computed field (severity from a prior step).
_WRITE_YAML = """\
collection: Outcome Demo
description: creates an alert
visible: true
playbooks:
- name: Outcome Demo
  description: creates an alert
  trigger_step_id: start
  steps:
  - type: start
    name: start
    button_label: Go
    next: Make
  - type: create_record
    name: Make
    arguments:
      module: alerts
      resource:
        name: Phishing triage
        severity: '{{ vars.steps.start.sev }}'
"""


def test_outcome_assertions_follow_record_writes():
    """A record-writing playbook yields a record_exists on that module, a
    field_equals for the literal field, and NO assertion for the computed one."""
    db = default_db_path()
    coll = _coll(_WRITE_YAML, db)
    asserts = outcome.derive_outcome_assertions(coll)
    kinds = {a["kind"] for a in asserts}
    assert kinds <= {"record_exists", "field_equals"}
    re_mods = {a["module"] for a in asserts if a["kind"] == "record_exists"}
    assert re_mods == {"alerts"}
    fe = {a["field"]: a["value"] for a in asserts if a["kind"] == "field_equals"}
    assert fe.get("name") == "Phishing triage", fe
    assert "severity" not in fe, "computed field must not become a field_equals"


def test_record_less_playbook_yields_no_outcome_assertion(tasks):
    """A playbook that writes no record invents no outcome assertion."""
    db = default_db_path()
    for t in tasks:
        coll = _coll(t["real_yaml"], db)
        writes = any(s.type in ("create_record", "update_record", "delete_record")
                     and ((s.arguments or {}).get("module") or (s.arguments or {}).get("collection"))
                     for pb in coll.playbooks for s in pb.steps)
        if not writes:
            assert not outcome.derive_outcome_assertions(coll), t["id"]


def test_field_equals_only_for_literal_values(tasks):
    """A field_equals value must be a static literal, never a Jinja/vars ref --
    we can't predict a computed value without running the playbook."""
    import re
    db = default_db_path()
    for t in tasks:
        for a in outcome.derive_outcome_assertions(_coll(t["real_yaml"], db)):
            if a["kind"] == "field_equals":
                v = a["value"]
                assert not (isinstance(v, str) and re.search(r"\{\{|\{%|vars\.", v)), \
                    f"{t['id']}: field_equals on a non-literal {v!r}"


# --- defect injection + repair grading -------------------------------------
def test_injectors_produce_detectable_defects(tasks):
    """Every injected defect must be DETECTED: compile/verify surfaces one of
    its expected codes on the broken YAML. An undetectable 'defect' would make
    the problem-solving eval unfair (nothing true to diagnose)."""
    db = default_db_path()
    seen_kinds = set()
    for t in tasks:
        for d in mutate.make_defects(t["real_yaml"]):
            g = repair_grade.grade_repair(t["real_yaml"], d, repaired_yaml=None, db=db)
            assert g["detected"], (
                f"{t['id']}/{d['kind']}: not detected; introduced={g['introduced_codes']} "
                f"expected one of {d['expect_codes']}")
            seen_kinds.add(d["kind"])
    assert seen_kinds, "no defects injected across the whole corpus"


def test_a_correct_repair_grades_repaired_and_structure_preserved(tasks):
    """The ORIGINAL good YAML, offered as the repair of its own broken variant,
    must grade repaired + structure_preserved (restoring the source is a valid
    fix). A grader that fails this would reject correct problem solving."""
    db = default_db_path()
    checked = 0
    for t in tasks:
        for d in mutate.make_defects(t["real_yaml"]):
            g = repair_grade.grade_repair(t["real_yaml"], d,
                                          repaired_yaml=t["real_yaml"], db=db)
            assert g["repaired"], f"{t['id']}/{d['kind']}: restore not graded repaired: {g}"
            assert g["structure_preserved"], f"{t['id']}/{d['kind']}: structure lost: {g}"
            checked += 1
    assert checked, "no defect/repair pair exercised"


def test_no_repair_is_a_clean_fail(tasks):
    """An empty repair must not pass; detection still reports honestly."""
    db = default_db_path()
    d = next((x for t in tasks for x in mutate.make_defects(t["real_yaml"])), None)
    if d is None:
        pytest.skip("no injectable defect in synthetic corpus")
    g = repair_grade.grade_repair(tasks[0]["real_yaml"], d, repaired_yaml="", db=db)
    assert g["repaired"] is False
    assert g["structure_preserved"] is False


def test_leaving_the_defect_in_is_not_a_repair(tasks):
    """Offering the BROKEN YAML back as the 'repair' must grade repaired False
    -- the defect code is still present."""
    db = default_db_path()
    checked = 0
    for t in tasks:
        for d in mutate.make_defects(t["real_yaml"]):
            g = repair_grade.grade_repair(t["real_yaml"], d,
                                          repaired_yaml=d["yaml"], db=db)
            assert g["repaired"] is False, f"{t['id']}/{d['kind']}: broken graded repaired"
            checked += 1
    assert checked
