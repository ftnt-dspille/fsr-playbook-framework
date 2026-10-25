"""Run the problem-solving (repair) eval: inject defects into real corpus
playbooks, drive Claude Code + the toolkit to fix each, grade the repair.

Companion to run_eval.py (authoring). Needs FSR_BASE_URL + FSR_API_KEY (the
box the toolkit's debug/verify tools read) and `claude` on PATH. Start SMALL:
a few tasks, one defect class each, before widening -- every task is a live
subscription drive per injected defect.

    FSRPB_DEV=1 .venv/bin/python -m tooling.evals.corpus_authoring.run_repair \
        --tasks-dir <task dir> --out <local out> --per-bucket 1 --env-file <box>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fsr_playbooks._db import default_db_path

from tooling.evals.corpus_authoring import drive_repair, mutate, repair_grade
from tooling.evals.corpus_authoring.run_eval import _load_tasks, _stratify


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-bucket", type=int, default=1)
    ap.add_argument("--buckets", help="comma-separated buckets to include")
    ap.add_argument("--kinds", help="comma-separated defect kinds to inject (default all)")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--limit", type=int, help="cap total tasks (after stratify)")
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

    tasks = _load_tasks(Path(args.tasks_dir))
    # one task per distinct playbook (repair does not vary by user persona); pick
    # the first style so we don't drive the same playbook five times.
    seen: set[str] = set()
    distinct = []
    for t in sorted(tasks, key=lambda t: t["id"]):
        if t["source_uuid"] in seen:
            continue
        seen.add(t["source_uuid"])
        distinct.append(t)
    buckets = set(args.buckets.split(",")) if args.buckets else None
    chosen = _stratify(distinct, args.per_bucket, buckets)
    if args.limit:
        chosen = chosen[: args.limit]
    if not chosen:
        ap.error("no tasks selected")

    want_kinds = set(args.kinds.split(",")) if args.kinds else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    db = default_db_path()

    rows = []
    n_drives = 0
    print(f"repair eval: {len(chosen)} playbook(s), model {args.model}")
    for t in chosen:
        defects = [d for d in mutate.make_defects(t["real_yaml"])
                   if not want_kinds or d["kind"] in want_kinds]
        for d in defects:
            n_drives += 1
            tag = f"{t['id']}__{d['kind']}"
            try:
                run = drive_repair.drive_repair(t, d, work, model=args.model)
            except Exception as exc:  # noqa: BLE001
                print(f"  DRIVE-FAIL {tag}: {type(exc).__name__}: {exc}")
                rows.append({"id": t["id"], "bucket": t["bucket"], "kind": d["kind"],
                             "detected": None, "repaired": False,
                             "structure_preserved": False, "detail": f"drive error: {exc}"})
                continue
            g = repair_grade.grade_repair(t["real_yaml"], d,
                                          repaired_yaml=run["repaired_yaml"], db=db)
            g.update(id=t["id"], bucket=t["bucket"], tools=run["tools"],
                     used_debug=run["used_debug"], used_verify=run["used_verify"])
            rows.append(g)
            print(f"  {tag:60} debug={run['used_debug']!s:5} "
                  f"detected={g['detected']!s:5} repaired={g['repaired']!s:5} "
                  f"struct={g['structure_preserved']}")

    report = repair_grade.aggregate_repairs(rows)
    (out / "repair_results.json").write_text(json.dumps(rows, indent=2))
    (out / "repair_report.json").write_text(json.dumps(report, indent=2))
    print(f"\n=== repair ({n_drives} drives) ===", json.dumps(report["overall"]))
    print("=== by defect kind ===")
    for k, r in report["by_kind"].items():
        print(f"  {k:28} {json.dumps(r)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
