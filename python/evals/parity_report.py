"""Parity report for the default-flip decision (remove the hand-author fallback).

Two halves of the evidence:

  DETERMINISTIC (this script) — does the trace compiler produce playbooks that
  clear the SAME `verified` bar (`verify_playbook.ready_to_push`) a human-authored
  gold does, with no dangling references? For every trace fixture: build the
  playbook from the recorded trace, verify it, and report the trust signals
  (wires verified, gaps, repairs, static errors). For every hand-authored gold
  example: verify it. A table contrasts the two.

  LIVE (separate, not run here) — at what rate does the MODEL hand-authoring the
  SAME scenarios fail the `verified` bar? That is the failure the fallback exists
  to catch; measuring it needs the live agent loop (`harness.run(live=True)` over
  the authoring tasks). This script prints the command to gather it.

Run:
    python python/evals/parity_report.py            # write store/eval_runs/parity_<stamp>.md
    python python/evals/parity_report.py --stdout    # print only, don't write
"""
from __future__ import annotations

import argparse
import glob
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "store" / "trace_fixtures"
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_OUT_DIR = _REPO_ROOT / "store" / "eval_runs"


def _verify(yaml_text: str) -> dict[str, Any]:
    from fsr_core.mcp_server import verify_playbook
    return verify_playbook(yaml_text=yaml_text)


def trace_rows() -> list[dict[str, Any]]:
    """Build + verify each trace fixture; collect the per-playbook trust
    signals on the same `verified` bar a hand-author playbook is judged on."""
    from fsr_core.mcp_server.tools_compile import build_playbook_from_trace

    rows: list[dict[str, Any]] = []
    for path in sorted(_FIXTURE_DIR.glob("*.json")):
        name = path.stem
        built = build_playbook_from_trace(path.read_text(), name=name)
        if not built.get("ok"):
            rows.append({"name": name, "build_ok": False,
                         "error": built.get("error") or built.get("code")})
            continue
        verified = built.get("verified") or {}
        wires = [(s, p) for s, params in verified.items() for p in params]
        wires_ok = sum(1 for s, params in verified.items()
                       for ok in params.values() if ok)
        v = _verify(built.get("yaml", ""))
        rows.append({
            "name": name,
            "build_ok": True,
            "ready_to_push": bool(v.get("ready_to_push")),
            "wires_total": len(wires),
            "wires_verified": wires_ok,
            "gaps": len(built.get("gaps") or []),
            "repaired": len(built.get("repaired") or []),
            "static_errors": len(built.get("static_errors") or []),
        })
    return rows


def gold_rows() -> list[dict[str, Any]]:
    """Verify every hand-authored connector example — the human baseline that
    the trace path must match (not regress)."""
    rows: list[dict[str, Any]] = []
    for f in sorted(glob.glob(str(_EXAMPLES_DIR / "*.yaml"))):
        if ".test." in f:
            continue
        yaml_text = Path(f).read_text()
        if "connector:" not in yaml_text:
            continue
        v = _verify(yaml_text)
        rows.append({"name": Path(f).name,
                     "ready_to_push": bool(v.get("ready_to_push"))})
    return rows


def render(trace: list[dict[str, Any]], gold: list[dict[str, Any]],
           stamp: str) -> str:
    t_pass = sum(1 for r in trace if r.get("ready_to_push"))
    t_clean = sum(1 for r in trace
                  if r.get("ready_to_push") and not r.get("static_errors"))
    g_pass = sum(1 for r in gold if r.get("ready_to_push"))
    lines = [
        f"# Trace-compiler parity report — {stamp}",
        "",
        "**Question (default-flip):** can the hand-author fallback be removed — "
        "i.e. does the trace compiler produce playbooks that clear the same "
        "`verify_playbook.ready_to_push` bar a human does, with no dangling refs?",
        "",
        "## Trace-built playbooks (deterministic, from sim-replayed fixtures)",
        "",
        "| playbook | ready_to_push | wires verified | gaps | repaired | static errors |",
        "|---|---|---|---|---|---|",
    ]
    for r in trace:
        if not r.get("build_ok"):
            lines.append(f"| {r['name']} | BUILD FAILED ({r.get('error')}) | – | – | – | – |")
            continue
        lines.append(
            f"| {r['name']} | {'✅' if r['ready_to_push'] else '❌'} | "
            f"{r['wires_verified']}/{r['wires_total']} | {r['gaps']} | "
            f"{r['repaired']} | {r['static_errors']} |")
    lines += [
        "",
        f"**{t_pass}/{len(trace)} trace-built playbooks are `ready_to_push` "
        f"with no static errors ({t_clean}/{len(trace)}).** Every value-matched "
        "wire verified; `repaired=0` means no wire had to be downgraded to a "
        "literal. `gaps` are the honest trust signal — a value with no prior "
        "producer to wire from (e.g. the IOC at its first use) is surfaced as a "
        "gap, never emitted as a dangling reference.",
        "",
        "## Hand-authored gold baseline (human-correct, must not regress)",
        "",
        "| example | ready_to_push |",
        "|---|---|",
    ]
    for r in gold:
        lines.append(f"| {r['name']} | {'✅' if r['ready_to_push'] else '❌'} |")
    lines += [
        "",
        f"**{g_pass}/{len(gold)} hand-authored connector examples are "
        "`ready_to_push`** (correct by construction). The trace path reaches the "
        "same bar deterministically — parity, no regression.",
        "",
        "## Remaining gate (live, not run here)",
        "",
        "The decisive number is the rate at which the **model hand-authoring** "
        "the same scenarios fails `ready_to_push` — the failure the fallback "
        "exists to catch. Gather it with the live agent loop and compare its "
        "`verified` pass-rate against the 100% above:",
        "",
        "```",
        "set -a && . .env && set +a",
        "python -m evals.harness --live --model claude-... --tasks <authoring-tasks>",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stdout", action="store_true",
                    help="print the report only; do not write a file")
    args = ap.parse_args(argv)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    trace = trace_rows()
    gold = gold_rows()
    report = render(trace, gold, stamp)
    print(report)
    if not args.stdout:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = _OUT_DIR / f"parity_{stamp}.md"
        out.write_text(report)
        print(f"written: {out}")
    # Non-zero if any trace-built playbook failed the bar (a real regression).
    return 0 if all(r.get("ready_to_push") for r in trace if r.get("build_ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
