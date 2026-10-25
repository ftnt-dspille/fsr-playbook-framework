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


def test_trigger_rendered_in_user_language_not_enum():
    """A create-trigger must be described in user words, never the enum."""
    from fsr_playbooks.compiler.ir import Playbook, Step
    pb = Playbook(name="x", trigger="start", description="do a thing", steps=[
        Step(id="t", type="start_on_create"),
        Step(id="d", type="decision", branches={"yes": "a", "no": "a"}),
        Step(id="a", type="set_variable"),
    ])
    assert derive._trigger_type(pb) == "start_on_create"
    asserts = derive.derive_assertions(pb)
    spec = derive.derive_operational_spec(pb, asserts) or ""
    assert "run automatically whenever a new record" in spec
    assert "start_on_create" not in spec


def test_no_spec_leaks_an_internal_term(tasks):
    """The load-bearing rule: a user-voice question must not contain any FSR
    step-type enum, op id, or loop-variable name the grader checks -- or it is
    a lookup, not a design task. Scan every spec for leak tokens as whole words
    and for any asserted op id / loop fragment."""
    import re
    for t in tasks:
        low = t["spec"].lower()
        for tok in derive.LEAK_TOKENS:
            assert not re.search(rf"\b{re.escape(tok)}\b", low), \
                f"{t['id']}: spec leaks internal term {tok!r}"
        # the exact op ids and loop fragments the grader checks must not appear
        for a in t["ir_assertions"]:
            if a["kind"] == "connector_op" and a.get("operation_contains"):
                assert a["operation_contains"].lower() not in low, \
                    f"{t['id']}: spec leaks op id {a['operation_contains']!r}"
            if a["kind"] == "for_each_over" and a.get("contains"):
                assert a["contains"].lower() not in low, \
                    f"{t['id']}: spec leaks loop field {a['contains']!r}"


def test_tasks_come_in_user_voice_styles(tasks):
    """Every task is one of the registered user-voice personas, never the old
    prescriptive enum-naming style."""
    known = {name for name, _fn, _strict in derive.SPEC_BUILDERS}
    styles = {t.get("style") for t in tasks}
    assert styles and styles <= known, (styles, known)


def test_loop_assertion_is_field_agnostic():
    """A looping playbook yields a for_each_over with EMPTY contains (loop
    presence), never the exact looped field a user-voice prompt can't name."""
    from fsr_playbooks.compiler.ir import Playbook, Step
    pb = Playbook(name="x", trigger="start", description="loop over stuff", steps=[
        Step(id="t", type="start"),
        Step(id="l", type="set_variable",
             for_each={"item": "{{ vars.steps.fetch.data.emails_data }}"}),
    ])
    loops = [a for a in derive.derive_assertions(pb) if a["kind"] == "for_each_over"]
    assert loops, "a looping playbook must yield a for_each_over assertion"
    assert all(a.get("contains") == "" for a in loops), loops
    # and it must grade TRUE for a playbook that loops over a DIFFERENT field
    other = Playbook(name="y", trigger="start", description="d", steps=[
        Step(id="t", type="start"),
        Step(id="l", type="set_variable", for_each={"item": "{{ vars.other_field }}"}),
    ])
    for a in loops:
        assert _check_one(other, a)[0], f"field-agnostic loop should match: {a}"


def test_internal_utility_ops_are_not_asserted():
    """Decompiler plumbing ops (make_cyops_request, no_op) are not user-meaningful
    intent and must not become connector_op assertions."""
    from fsr_playbooks.compiler.ir import Playbook, Step
    pb = Playbook(name="x", trigger="start", description="d", steps=[
        Step(id="t", type="start"),
        Step(id="c", type="connector",
             arguments={"connector": "Utilities", "operation": "make_cyops_request"}),
    ])
    ops = [a for a in derive.derive_assertions(pb) if a["kind"] == "connector_op"]
    assert all("make_cyops_request" not in (a.get("operation_contains") or "")
               for a in ops), ops


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
