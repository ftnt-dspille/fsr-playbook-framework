"""Task-gen correctness, box-free, no LLM.

The load-bearing property: every authoring task we derive from a real playbook
must be satisfiable by that playbook itself -- if the source fails its own
derived assertions, the derivation is wrong and the task would unfairly fail a
correct author. We prove it over the committed synthetic roundtrip_corpus (the
only corpus that ships in the repo; the real F4 pull is local-only).

Run: FSRPB_DEV=1 .venv/bin/python -m pytest tooling/evals/corpus_authoring/test_task_gen.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml

from tooling.evals.corpus_authoring import derive
from tooling.evals.corpus_authoring.sample_corpus import build_tasks
from tooling.evals.ir_assertions import _check_one, check_ir_assertions

_CORPUS = (Path(__file__).resolve().parents[3]
           / "fsr_playbooks/tests/fixtures/roundtrip_corpus")


@pytest.fixture(scope="module")
def tasks():
    built, _stats = build_tasks(_CORPUS, default_db_path(), min_assertions=1)
    assert built, "no tasks built from the synthetic corpus"
    return built


def test_every_task_self_verifies(tasks):
    """The real playbook passes every assertion the task carries (the sampler
    only keeps self-consistent ones, so this must hold end to end)."""
    db = default_db_path()
    for t in tasks:
        res = check_ir_assertions(t["real_yaml"], t["ir_assertions"], db)
        assert res["passed"], (
            f"{t['id']}: source fails its own assertions: {res.get('failures')}")


def test_assertions_use_known_kinds_only(tasks):
    """No derived assertion uses a kind the grader would reject as unknown."""
    known = {"step_type_present", "step_type_absent", "connector_op",
             "for_each_over", "arg_text_contains", "arg_text_absent",
             "branch_count", "reachable"}
    for t in tasks:
        for a in t["ir_assertions"]:
            assert a["kind"] in known, f"{t['id']}: unknown kind {a['kind']}"


def test_spec_names_the_trigger_not_set_variable(tasks):
    """Regression: the trigger was mis-derived as the first step's type
    (set_variable for child playbooks). It must name the real trigger."""
    for t in tasks:
        assert "triggers on set_variable" not in t["spec"], t["id"]


def test_each_task_has_a_substantive_assertion(tasks):
    """A task must require more than 'has a trigger' -- at least one connector
    op, loop, decision, or distinctive step type -- or it grades nothing."""
    trivial = {"start", "set_variable"}
    for t in tasks:
        substantive = [
            a for a in t["ir_assertions"]
            if a["kind"] != "step_type_present" or a.get("type") not in trivial
        ]
        assert substantive, f"{t['id']}: only trivial assertions"
