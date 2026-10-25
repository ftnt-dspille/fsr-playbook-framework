"""The standard golden benchmark, pinned box-free and LLM-free.

Guards the properties the golden set must keep to be a fair, repeatable
intelligence eval:
  - every golden playbook compiles with no hard errors and verifies ready.
  - a self-checked expert spec is derivable for each, and it does NOT leak the
    FSR step-type / op vocabulary the grader checks (else it is a lookup, not a
    design task).
  - the mapped defect for each playbook injects AND is detected (so the repair
    half has something true to diagnose).
The six live drives are exercised separately; this pins everything up to them.
"""
from __future__ import annotations

import re

import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml

from tooling.evals.corpus_authoring import repair_grade, run_golden

# vocabulary a user-voice spec must never contain (step-type enums, op ids,
# loop field, connector api names) -- leaking these turns design into dictation.
_LEAK = re.compile(
    r"\b(update_record|create_record|delete_record|set_variable|for_each|"
    r"decision|workflow_reference|cyops_utilities|get_macro_list|"
    r"ingest_bulk_feed|manual_input)\b")


@pytest.fixture(scope="module")
def db():
    return default_db_path()


@pytest.fixture(scope="module")
def tasks(db):
    t = run_golden.build_golden_tasks(db)
    assert len(t) == 3, [x["id"] for x in t]
    return t


def test_every_golden_compiles_clean_and_verifies(db):
    from fsr_playbooks.mcp_server.tools_verify import verify_playbook
    files = sorted(run_golden.GOLDEN_DIR.glob("*.yaml"))
    assert len(files) >= 4, files
    for f in files:
        y = f.read_text()
        r = compile_yaml(y, db)
        hard = [e for e in (r.errors or []) if getattr(e, "severity", None) != "warning"]
        assert not hard, f"{f.name}: hard errors {[str(getattr(e,'code','')) for e in hard]}"
        warn = [e for e in (r.errors or []) if getattr(e, "severity", None) == "warning"]
        assert not warn, f"{f.name}: warnings {[str(getattr(e,'message','')) for e in warn]}"
        v = verify_playbook(y, db_path=str(db))
        assert v.get("ready_to_push"), f"{f.name}: not ready {v.get('required_fixes')}"


def test_each_task_has_substantive_assertions(tasks):
    for t in tasks:
        kinds = {a["kind"] for a in t["ir_assertions"]}
        # more than just "there is a start/trigger"
        assert any(k != "step_type_present" or a.get("type") not in ("start", "set_variable")
                   for a in t["ir_assertions"] for k in [a["kind"]]), t["id"]
        assert kinds, t["id"]


def test_specs_do_not_leak_fsr_vocabulary(tasks):
    for t in tasks:
        m = _LEAK.search(t["spec"].lower())
        assert not m, f"{t['id']}: spec leaks grader vocabulary: {m.group(0)!r}"


def test_mapped_defect_injects_and_is_detected(tasks, db):
    """Each golden's mapped defect must apply and be detected -- the repair half
    needs a real, diagnosable break per playbook."""
    for t in tasks:
        d = run_golden._pick_defect(t)
        assert d, f"{t['id']}: no injectable defect"
        want = run_golden._DEFECT_BY_FILE.get(t["id"])
        assert d["kind"] == want, f"{t['id']}: got {d['kind']}, wanted mapped {want}"
        g = repair_grade.grade_repair(t["real_yaml"], d, repaired_yaml=None, db=db)
        assert g["detected"], f"{t['id']}/{d['kind']}: not detected {g['introduced_codes']}"


def test_runtime_dependency_passes_static_but_fails_resolve(db):
    """The defining property of the runtime golden: the wrong-output-path variant
    compiles clean and verifies ready (every static gate passes), yet its
    reference does NOT resolve against the producer's real captured shape -- and
    the correct playbook's reference does. This is the bug class static checks
    structurally cannot catch."""
    from fsr_playbooks.compiler.pipeline import compile_yaml
    from fsr_playbooks.mcp_server.tools_verify import verify_playbook
    from tooling.evals.corpus_authoring import runtime_dep, step_output
    for stem, cfg in run_golden._RUNTIME_GOLDEN.items():
        f = run_golden.GOLDEN_DIR / f"{stem}.yaml"
        good = f.read_text()
        shape_doc = step_output.load_shape(cfg["connector"], cfg["operation"])
        assert shape_doc, f"{stem}: no captured shape fixture"
        shape = shape_doc["shape"]
        # correct playbook resolves at runtime
        assert runtime_dep.grade_runtime_dependency(good, cfg["producer"], shape)["resolves"]
        # inject the wrong path
        d = runtime_dep.inject_wrong_output_path(good, cfg["producer"], shape)
        assert d, f"{stem}: nothing to break"
        # STATIC: still clean + ready
        r = compile_yaml(d["yaml"], db)
        hard = [e for e in (r.errors or []) if getattr(e, "severity", None) != "warning"]
        assert not hard, f"{stem}: broken variant has hard errors {hard}"
        assert verify_playbook(d["yaml"], db_path=str(db)).get("ready_to_push"), \
            f"{stem}: broken variant should still verify ready (static cannot see it)"
        # RUNTIME: does not resolve
        assert not runtime_dep.grade_runtime_dependency(
            d["yaml"], cfg["producer"], shape)["resolves"], \
            f"{stem}: broken variant should render empty at runtime"


def test_restoring_source_grades_as_repaired(tasks, db):
    """Offering the clean original as the fix must grade repaired + structure --
    the grader must accept a correct repair (teeth: a no-op repair must not)."""
    for t in tasks:
        d = run_golden._pick_defect(t)
        good = repair_grade.grade_repair(t["real_yaml"], d, repaired_yaml=t["real_yaml"], db=db)
        assert good["repaired"] and good["structure_preserved"], (t["id"], good)
        left_broken = repair_grade.grade_repair(t["real_yaml"], d, repaired_yaml=d["yaml"], db=db)
        assert left_broken["repaired"] is False, f"{t['id']}: broken graded repaired"
