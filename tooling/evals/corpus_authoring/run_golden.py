"""The STANDARD intelligence eval: a small, fixed, committed benchmark.

Six `claude -p` drives total -- three authoring, three repair -- over three
committed golden playbooks (golden/*.yaml) that each probe one intelligence-
relevant structure:

    g1  multi-branch decision   (route by severity, 3 ways)
    g2  loop / for_each         (update every item in a list)
    g3  connector + record write(call an op, then create a record)

Unlike the corpus sweep, this needs no local corpus, picks the same tasks every
run, and is cheap enough to run routinely. The golden playbooks are synthetic
and env-stable (core step types + cyops_utilities), so they compile and verify
on any standard box with no connector-install noise.

Authoring: a user-voice spec is derived from each golden playbook (expert
persona, so structural fidelity is gradeable), driven, and graded draft /
verified_fair / ir. Repair: one deterministic defect is injected per playbook,
driven through the toolkit's fix path, and graded detected / repaired /
structure_preserved.

    FSRPB_DEV=1 .venv/bin/python -m tooling.evals.corpus_authoring.run_golden \
        --out <local out> --env-file <box>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.pipeline import compile_yaml

from tooling.evals.corpus_authoring import (derive, drive, drive_repair, grade,
                                            mutate, repair_grade, runtime_dep,
                                            step_output)
from tooling.evals.ir_assertions import _check_one

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# Runtime goldens are graded against a captured real output SHAPE, not static
# gates -- they probe the step-output-dependency bug class static checks cannot
# see. Kept out of the static g1-g3 loops.
_RUNTIME_GOLDEN = {
    "g4_macro_digest": {"producer": "Get Macros",
                        "connector": "cyops_utilities",
                        "operation": "get_macro_list"},
}

# The persona whose spec gets driven (detailed enough that structural fidelity
# is a fair signal) and, per golden playbook, the single defect class to inject
# so the three repair drives cover three distinct problem-solving skills.
_STYLE = "expert"
_DEFECT_BY_FILE = {
    "g1_alert_severity_triage": "unknown_step_reference",
    "g2_tag_each_indicator": "orphan_step",
    "g3_enrich_and_record": "missing_required_field",
}


def _should_run(only: str | None, section: str) -> bool:
    """Which sections run for --only. None runs all; otherwise only that one."""
    return only is None or only == section


def _expert_spec(pb, kept):
    for style, builder, strict_ir in derive.SPEC_BUILDERS:
        if style == _STYLE:
            spec = builder(pb, kept)
            if spec:
                return spec, strict_ir
    return None, False


def build_golden_tasks(db) -> list[dict]:
    """Compile each STATIC golden playbook and derive a self-checked task."""
    tasks: list[dict] = []
    for f in sorted(GOLDEN_DIR.glob("*.yaml")):
        if f.stem in _RUNTIME_GOLDEN:
            continue
        real_yaml = f.read_text()
        pb = compile_yaml(real_yaml, db).ir.playbooks[0]
        derived = derive.derive_assertions(pb)
        kept = [a for a in derived if _check_one(pb, a)[0]]
        spec, strict_ir = _expert_spec(pb, kept)
        if not spec:
            raise SystemExit(f"no expert spec for {f.name}")
        tasks.append({
            "id": f.stem,
            "bucket": "golden",
            "style": _STYLE,
            "strict_ir": strict_ir,
            "spec": spec,
            "ir_assertions": kept,
            "real_yaml": real_yaml,
            "source_uuid": f.stem,
            "source_name": pb.name,
            "source_verified": True,
            "n_steps": len(pb.steps or []),
        })
    return tasks


def _pick_defect(task: dict) -> dict | None:
    """The deterministic defect for this golden playbook (mapped kind if it
    applies, else the first injector that fits)."""
    defects = mutate.make_defects(task["real_yaml"])
    want = _DEFECT_BY_FILE.get(task["id"])
    for d in defects:
        if d["kind"] == want:
            return d
    return defects[0] if defects else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output dir (local only)")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--only", choices=("authoring", "repair", "runtime"),
                    help="run only one section (default: all)")
    ap.add_argument("--env-file", help="file of KEY=VALUE box creds (FSR_*); never printed")
    args = ap.parse_args(argv)

    if args.env_file:
        for line in Path(args.env_file).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not (os.environ.get("FSR_BASE_URL") and os.environ.get("FSR_API_KEY")):
        ap.error("FSR_BASE_URL and FSR_API_KEY must be set (the toolkit's box)")

    db = default_db_path()
    tasks = build_golden_tasks(db)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"

    authoring, repairs = [], []
    if _should_run(args.only, "authoring"):
        print("=== authoring (3 drives) ===")
        for t in tasks:
            run = drive.drive_task(t, work, model=args.model)
            g = grade.grade_yaml(run["authored_yaml"], t, db)
            g["id"] = t["id"]
            authoring.append(g)
            print(f"  {t['id']:28} draft={g['draft']!s:5} "
                  f"verified_fair={g.get('verified_fair')!s:5} ir={g['ir_passed']}")
    if _should_run(args.only, "repair"):
        print("=== repair (3 drives) ===")
        for t in tasks:
            d = _pick_defect(t)
            if not d:
                print(f"  {t['id']:28} (no injectable defect) SKIP")
                continue
            run = drive_repair.drive_repair(t, d, work, model=args.model)
            g = repair_grade.grade_repair(t["real_yaml"], d,
                                          repaired_yaml=run["repaired_yaml"], db=db)
            g["id"] = t["id"]
            repairs.append(g)
            print(f"  {t['id']:28} kind={d['kind']:22} detected={g['detected']!s:5} "
                  f"repaired={g['repaired']!s:5} struct={g['structure_preserved']}")

    runtime = []
    if _should_run(args.only, "runtime"):
        print("=== runtime step-output dependency (compiles clean, wrong at run time) ===")
        for stem, cfg in _RUNTIME_GOLDEN.items():
            f = GOLDEN_DIR / f"{stem}.yaml"
            if not f.exists():
                continue
            shape_doc = step_output.load_shape(cfg["connector"], cfg["operation"])
            if not shape_doc:
                print(f"  {stem:28} (no captured shape; run capture_shape) SKIP")
                continue
            shape = shape_doc["shape"]
            good_yaml = f.read_text()
            defect = runtime_dep.inject_wrong_output_path(good_yaml, cfg["producer"], shape)
            if not defect:
                print(f"  {stem:28} (no resolving ref to break) SKIP")
                continue
            # detection: the broken reference does NOT resolve against the real shape
            broken = runtime_dep.grade_runtime_dependency(defect["yaml"], cfg["producer"], shape)
            detected = not broken["resolves"]
            task = {"id": stem, "real_yaml": good_yaml}
            run = drive_repair.drive_repair(task, defect, work, model=args.model)
            fixed = runtime_dep.grade_runtime_dependency(
                run["repaired_yaml"] or "", cfg["producer"], shape)
            row = {"id": stem, "kind": "runtime_output_dependency",
                   "detected": detected,
                   "repaired": bool(fixed["has_ref"] and fixed["resolves"]),
                   "kept_dependency": fixed["has_ref"],
                   "broken_ref": defect["broken_ref"], "fixed_refs": fixed["refs"],
                   "used_debug": run["used_debug"]}
            runtime.append(row)
            print(f"  {stem:28} detected={row['detected']!s:5} repaired={row['repaired']!s:5} "
                  f"kept_dep={row['kept_dependency']!s:5} used_debug={row['used_debug']}")

    def rate(rows, key):
        return f"{sum(1 for r in rows if r.get(key))}/{len(rows)}" if rows else "0/0"

    scorecard = {
        "authoring": {k: rate(authoring, k) for k in ("draft", "verified_fair", "ir_passed")},
        "repair": {k: rate(repairs, k) for k in ("detected", "repaired", "structure_preserved")},
        "runtime": {k: rate(runtime, k) for k in ("detected", "repaired", "kept_dependency")},
    }
    (out / "golden_authoring.json").write_text(json.dumps(authoring, indent=2))
    (out / "golden_repair.json").write_text(json.dumps(repairs, indent=2))
    (out / "golden_runtime.json").write_text(json.dumps(runtime, indent=2))
    (out / "golden_scorecard.json").write_text(json.dumps(scorecard, indent=2))
    print("\n=== INTELLIGENCE SCORECARD ===")
    print(json.dumps(scorecard, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
