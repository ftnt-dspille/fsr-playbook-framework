"""Run the corpus-authoring eval: drive tasks through Claude Code + toolkit,
grade each, report pass rates by bucket.

Needs FSR_BASE_URL + FSR_API_KEY in the environment (a box the toolkit's orient
can read) and `claude` on PATH. Start SMALL: a stratified handful, one run each,
then widen once the breakpoints are known.

    FSRPB_DEV=1 .venv/bin/python -m tooling.evals.corpus_authoring.run_eval \
        --tasks-dir <local task dir> --out <local out> --per-bucket 1 --model claude-sonnet-5-5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from fsr_playbooks._db import default_db_path

from tooling.evals.corpus_authoring import drive, grade


def _load_tasks(tasks_dir: Path) -> list[dict]:
    out = []
    for f in sorted(tasks_dir.glob("*.json")):
        if f.name == "manifest.json":
            continue
        out.append(json.loads(f.read_text()))
    return out


def _stratify(tasks: list[dict], per_bucket: int, buckets: set[str] | None) -> list[dict]:
    """Up to per_bucket tasks per bucket, spread round-robin across the user-voice
    personas so a sample covers the range of users, not one voice."""
    by: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for t in tasks:
        if buckets and t["bucket"] not in buckets:
            continue
        by[t["bucket"]][t.get("style", "?")].append(t)
    chosen = []
    for b in sorted(by):
        styles = {s: sorted(v, key=lambda t: t["id"]) for s, v in by[b].items()}
        picked: list[dict] = []
        i = 0
        while len(picked) < per_bucket and any(i < len(v) for v in styles.values()):
            for s in sorted(styles):
                if i < len(styles[s]) and len(picked) < per_bucket:
                    picked.append(styles[s][i])
            i += 1
        chosen.extend(picked)
    return chosen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks-dir", required=True, help="dir of task JSONs (from sample_corpus)")
    ap.add_argument("--out", required=True, help="output dir (local only)")
    ap.add_argument("--per-bucket", type=int, default=1)
    ap.add_argument("--buckets", help="comma-separated buckets to include")
    ap.add_argument("--runs", type=int, default=1, help="runs per task (defect twice = defect)")
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
    buckets = set(args.buckets.split(",")) if args.buckets else None
    chosen = _stratify(tasks, args.per_bucket, buckets)
    if args.limit:
        chosen = chosen[: args.limit]
    if not chosen:
        ap.error("no tasks selected")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    db = default_db_path()

    results = []
    print(f"running {len(chosen)} task(s) x {args.runs} run(s), model {args.model}")
    for t in chosen:
        for run_i in range(args.runs):
            tag = f"{t['id']}#{run_i + 1}"
            try:
                run = drive.drive_task(t, work, model=args.model)
            except Exception as exc:  # noqa: BLE001
                print(f"  DRIVE-FAIL {tag}: {type(exc).__name__}: {exc}")
                results.append({"id": t["id"], "bucket": t["bucket"], "run": run_i + 1,
                                "draft": False, "verified": False, "ir_passed": False,
                                "passed": False, "fair_pass": False,
                                "source_verified": t.get("source_verified", True),
                                "detail": f"drive error: {exc}"})
                continue
            g = grade.grade_yaml(run["authored_yaml"], t, db)
            g["run"] = run_i + 1
            g["used_build_playbook"] = run["used_build_playbook"]
            g["tools"] = run["tools"]
            results.append(g)
            print(f"  {tag:50} build={run['used_build_playbook']!s:5} "
                  f"draft={g['draft']!s:5} verified={g['verified']!s:5} "
                  f"ir={g['ir_passed']!s:5} fair={g['fair_pass']}")

    report = grade.aggregate(results)
    (out / "results.json").write_text(json.dumps(results, indent=2))
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print("\n=== overall ===", json.dumps(report["overall"]))
    print("=== by bucket ===")
    for b, r in report["by_bucket"].items():
        print(f"  {b:16} {json.dumps(r)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
