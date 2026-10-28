"""The STANDARD connector-build eval: a small, fixed, box-free benchmark.

For each golden connector:
  BUILD  -- a user-voice spec (no info.json enum / field-type names) is driven
            through `claude -p` + the connector toolkit MCP; the agent writes the
            three files; graded files-present + no hard defect (lint + antipattern).
  FIX    -- each deterministic defect from cmutate is injected into a copy; a
            user-voice symptom spec is driven; the agent edits in place; graded
            by (code, file) DELTA against the clean original.

No FortiSOAR box. The connector toolkit is pointed at by env (see drive_connector).

    FSR_CONN_TOOLKIT_PY=<venv python, mcp<2> \
    FSR_CONN_TOOLKIT_SRC=<parent of fsr_connector_toolkit> \
    FSR_CONN_TOOLKIT_DB=<catalog.sqlite> \
    .venv/bin/python -m tooling.evals.connector_build.run_connector_golden \
        --out <local out> [--runs 2] [--only build|fix]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tooling.evals.connector_build import cgrade, cmutate, drive_connector

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# One user-voice BUILD spec per golden connector. Leakage guard: describe the
# capability, never an info.json field type, operation machine name, or dispatch.
_BUILD_SPEC = {
    "cg1_ipinfo": (
        "Build a connector for an online service that answers questions about IP "
        "addresses. Connecting to the service needs its web address and an API key. "
        "It should offer two actions: one takes an IP address and returns what the "
        "service knows about that address, and one takes an autonomous system number "
        "and returns the organization that owns it."
    ),
}

# A user-voice symptom per injected defect kind -- the problem as a user would
# report it, never the gate code or the exact field/mechanism.
_FIX_SPEC = {
    "info_missing_field": (
        "When I try to import this connector into FortiSOAR it is rejected because "
        "some required information about the connector itself is missing from its "
        "definition. Make it importable."
    ),
    "op_not_dispatched": (
        "This connector advertises an action for looking up an autonomous system "
        "number, but when a playbook runs that action it fails as if the action "
        "isn't implemented. The IP lookup works fine. Please make the ASN lookup work."
    ),
    "verify_false": (
        "A security review flagged this connector for turning off TLS certificate "
        "verification on its outbound HTTPS calls. Please fix that."
    ),
}


def build_tasks(work: Path) -> tuple[list[dict], list[dict]]:
    """Assemble BUILD and FIX tasks for every golden connector."""
    builds, fixes = [], []
    for conn in sorted(p for p in GOLDEN_DIR.iterdir() if p.is_dir()):
        spec = _BUILD_SPEC.get(conn.name)
        if spec:
            builds.append({"id": f"{conn.name}__build", "spec": spec, "clean_dir": str(conn)})
        for d in cmutate.make_defects(conn, work / "defects"):
            fspec = _FIX_SPEC.get(d["kind"])
            if not fspec:
                continue
            fixes.append({
                "id": f"{conn.name}__fix__{d['kind']}",
                "spec": fspec,
                "broken_dir": str(d["dir"]),
                "clean_dir": str(conn),
                "expect_codes": d["expect_codes"],
                "kind": d["kind"],
            })
    return builds, fixes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output dir (local only)")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--runs", type=int, default=2, help="repeats per task (defect twice = defect)")
    ap.add_argument("--only", choices=("build", "fix"))
    args = ap.parse_args(argv)

    out = Path(args.out)
    work = out / "work"
    out.mkdir(parents=True, exist_ok=True)
    builds, fixes = build_tasks(work)

    build_rows, fix_rows = [], []
    for r in range(args.runs):
        if args.only in (None, "build"):
            for t in builds:
                run = drive_connector.drive_build(t, work / f"run{r}", model=args.model)
                g = cgrade.grade_build(Path(run["connector_dir"]))
                g.update(id=t["id"], run=r, tools=run["tools"], rc=run["rc"])
                build_rows.append(g)
                print(f"  BUILD r{r} {t['id']:28} built={g['built']!s:5} "
                      f"lint_clean={g['lint_clean']!s:5} defects={g['defects']}")
        if args.only in (None, "fix"):
            for t in fixes:
                run = drive_connector.drive_fix(t, work / f"run{r}", model=args.model)
                g = cgrade.grade_fix(Path(t["clean_dir"]), Path(t["broken_dir"]),
                                     repaired_root=Path(run["connector_dir"]),
                                     expect_codes=t["expect_codes"])
                g.update(id=t["id"], run=r, kind=t["kind"], tools=run["tools"], rc=run["rc"])
                fix_rows.append(g)
                print(f"  FIX   r{r} {t['id']:32} detected={g['detected']!s:5} "
                      f"repaired={g['repaired']!s:5} no_regression={g['no_regression']}")

    scorecard = {
        "build": cgrade.aggregate(build_rows, ("built", "lint_clean", "passed")),
        "fix": cgrade.aggregate(fix_rows, ("detected", "repaired", "no_regression")),
    }
    (out / "connector_build.json").write_text(json.dumps(build_rows, indent=2))
    (out / "connector_fix.json").write_text(json.dumps(fix_rows, indent=2))
    (out / "connector_scorecard.json").write_text(json.dumps(scorecard, indent=2))
    print("\n=== CONNECTOR SCORECARD ===")
    print(json.dumps(scorecard, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
