#!/usr/bin/env python3
"""Round-trip fidelity gate: does every playbook survive decompile -> compile?

For each collection envelope in the corpus, run the semantic round-trip
(`fsr_playbooks.compiler.roundtrip.roundtrip`): wire JSON -> IR -> wire JSON,
projected onto compiler-owned semantic fields (per-step type/arguments/for_each,
routing graph, declared parameters), and diffed against the original. A dropped
field is data loss — the widget saves the agent's last ```yaml fence back OVER
the record, so any field the decompiler cannot read is deleted from the
customer's playbook. See docs/plans/playbook-compiler-fidelity-and-agent-surface.md.

Corpus source (first that resolves):
  --corpus-dir PATH
  $FSRPB_CORPUS_DIR
  fsr_playbooks/tests/fixtures/roundtrip_corpus   (the committed synthesized set)

The committed corpus is synthesized and expected to pass 100%. Point
`--corpus-dir` at a real box pull (F4-style, `?$relationships=true`) to measure
the corpus rate; there `--min-pass` is the ratchet — a fix that regresses a
different field drops the count and fails the gate (R2 in the plan).

Fixture shape: either a bare `{"data":[...]}` envelope, or `{"envelope": {...}}`
(the committed corpus wraps the envelope alongside an `_intent` note).

    make corpus-gate
    FSRPB_DEV=1 .venv/bin/python scripts/corpus_gate.py --corpus-dir /path/to/pull --min-pass 178
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.roundtrip import roundtrip

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / (
    "fsr_playbooks/tests/fixtures/roundtrip_corpus")


def _resolve_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("FSRPB_CORPUS_DIR")
    if env:
        return Path(env)
    return _DEFAULT_DIR


def _envelope(payload: dict) -> dict:
    """Unwrap the committed `{_intent, envelope}` form, else assume a bare env."""
    if isinstance(payload, dict) and "envelope" in payload:
        return payload["envelope"]
    return payload


def run_gate(corpus_dir: Path, db_path) -> tuple[int, int, list[tuple[str, str]]]:
    """Return (passed, total, failures) where failures is [(name, first-diffs)]."""
    files = sorted(corpus_dir.glob("*.json"))
    passed = 0
    failures: list[tuple[str, str]] = []
    for f in files:
        try:
            env = _envelope(json.loads(f.read_text()))
            ok, diffs = roundtrip(env, db_path)
        except Exception as exc:  # a fixture that explodes is a failure, loudly
            failures.append((f.stem, f"ERROR: {type(exc).__name__}: {exc}"))
            continue
        if ok:
            passed += 1
        else:
            failures.append((f.stem, "\n      ".join(diffs[:6])))
    return passed, len(files), failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", default=None)
    ap.add_argument(
        "--min-pass", type=int, default=None,
        help="Ratchet floor: fail if fewer playbooks pass. Default: require all.")
    ap.add_argument("--db", default=None, help="Reference DB (default: resolver).")
    args = ap.parse_args(argv)

    corpus_dir = _resolve_dir(args.corpus_dir)
    if not corpus_dir.is_dir():
        print(f"corpus-gate: no such corpus dir: {corpus_dir}", file=sys.stderr)
        return 2
    db_path = Path(args.db) if args.db else default_db_path()

    passed, total, failures = run_gate(corpus_dir, db_path)
    if total == 0:
        print(f"corpus-gate: no fixtures in {corpus_dir}", file=sys.stderr)
        return 2

    floor = args.min_pass if args.min_pass is not None else total
    print(f"corpus-gate: {passed}/{total} playbooks round-trip clean "
          f"(floor {floor})  [{corpus_dir}]")
    for name, detail in failures:
        print(f"  ✗ {name}:\n      {detail}")

    if passed < floor:
        print(f"corpus-gate: FAIL — {passed} < floor {floor} "
              f"(a field stopped surviving the round-trip)", file=sys.stderr)
        return 1
    print("corpus-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
