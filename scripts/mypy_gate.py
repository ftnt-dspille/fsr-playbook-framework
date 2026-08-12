#!/usr/bin/env python3
"""mypy ratchet gate for fsr_playbooks/llm/ and fsr_playbooks/mcp_server/.

These two packages are the most dynamic code in the framework (LLM dispatch,
MCP tool schema generation, `**kwargs` plumbing).  A silent ``{}`` from the
annotation mapper hid here for days and surfaced three layers away as bad model
behaviour.  Extending mypy here is the highest-value type-safety win.

The current error count is a *baseline*, not a goal.  The gate **fails on NEW
errors** and **passes when the count stays the same or drops**.  When you fix
errors, update the baseline in ``docs/typing/mypy_ratchet.json`` so the floor
moves down and can never move back up.

Usage::

    make mypy-gate                         # check all modules against baseline
    .venv/bin/python scripts/mypy_gate.py  # same
    .venv/bin/python scripts/mypy_gate.py --update   # write the current counts
    .venv/bin/python scripts/mypy_gate.py --module fsr_playbooks/llm/

The baseline file is ``docs/typing/mypy_ratchet.json``::

    {"fsr_playbooks/llm": 40, "fsr_playbooks/mcp_server": 26}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO / "docs" / "typing" / "mypy_ratchet.json"

MODULES = ["fsr_playbooks/llm", "fsr_playbooks/mcp_server"]


def _run_mypy(module: str) -> tuple[int, list[str]]:
    """Run mypy on *module*; return (error_count, error_lines)."""
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", module],
        capture_output=True, text=True, cwd=REPO,
    )
    lines = [l for l in proc.stdout.splitlines() if ": error:" in l]
    return len(lines), lines


def _load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text())


def _save_baseline(data: dict[str, int]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true",
                    help="write the current error counts as the new baseline")
    ap.add_argument("--module", default=None,
                    help="check only this module (for debugging)")
    args = ap.parse_args(argv)

    modules = [args.module] if args.module else MODULES
    baseline = _load_baseline()

    if args.update:
        new = {}
        for m in MODULES:
            count, _ = _run_mypy(m)
            new[m] = count
        _save_baseline(new)
        print(f"mypy-ratchet: baseline written to {BASELINE_PATH}")
        for m, c in sorted(new.items()):
            print(f"  {m}: {c}")
        return 0

    failed = False
    for m in modules:
        count, lines = _run_mypy(m)
        floor = baseline.get(m)
        if floor is None:
            print(f"  ? {m}: {count} errors (no baseline -- run --update)")
            failed = True
            continue
        if count > floor:
            print(f"  ✗ {m}: {count} errors (baseline {floor}, +{count - floor} NEW)")
            # Show the new errors (ones not in the baseline set)
            for l in lines:
                print(f"    {l}")
            failed = True
        elif count < floor:
            print(f"  ✓ {m}: {count} errors (baseline {floor}, -{floor - count} fixed! "
                  f"--update to lower the floor)")
        else:
            print(f"  ✓ {m}: {count} errors (baseline {floor})")

    if failed:
        return 1
    print("mypy-ratchet: all modules at or below baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
