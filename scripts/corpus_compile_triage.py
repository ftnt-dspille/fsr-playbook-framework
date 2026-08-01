#!/usr/bin/env python3
"""Compilability triage: of the playbooks that round-trip cleanly, which still
fail to COMPILE, and *why* -- grouped into a work list rather than a wall.

`corpus_gate.py` answers a different question. It measures **fidelity** (does
decompile -> compile preserve every field), and on a real pull that number is
already 495/495. Fidelity being perfect says nothing about whether the emitted
YAML is *accepted* by the compiler: a playbook can round-trip byte-clean and
still raise a blocking `missing_field`. That second property is
**compilability**, it is what Phase 2 of
docs/plans/playbook-compiler-fidelity-and-agent-surface.md is scoped against,
and this script is the instrument for it.

Read it as: fidelity = "did we lose anything", compilability = "would the
compiler accept what a real box already runs". A blocking error here is a
compiler/reference-DB gap, because the input is a playbook the appliance
executes in production.

Each error is collapsed to a PATTERN key -- quoted identifiers, indices and
numbers stripped -- so N concrete errors over K real causes read as K rows.
That grouping is the whole point: the coarse `code` alone (`missing_field`,
`unknown_param`, `bad_value`) is too blunt to scope work against.

Corpus source (first that resolves), same precedence as `corpus_gate.py`:
  --corpus-dir PATH
  $FSRPB_CORPUS_DIR
  fsr_playbooks/tests/fixtures/roundtrip_corpus

Accepts two row shapes: a collection envelope (`{"data":[...]}`, optionally
wrapped as `{"envelope": ...}`) or a bare workflow record as dumped per-file by
the F4 puller, which is wrapped into a synthetic single-workflow collection.

Rows with **zero steps** are skipped and counted separately: a pull made
without `?$relationships=true` returns step-less workflows, and scoring those
as failures invents a bucket that is not a compiler defect.

Rows are also **deduplicated by workflow uuid** by default. A per-file dump
carries the same playbook once per collection that references it -- the F4 dump
is 495 step-bearing rows over only 191 distinct uuids -- so counting rows
inflates every bucket by ~2.6x and makes one cause look like a work list.
Pass `--no-dedup` to score raw rows (e.g. to reproduce an older number).

READ-ONLY: reads the corpus and the reference DB. Nothing is written or pushed.

    FSRPB_DEV=1 .venv/bin/python scripts/corpus_compile_triage.py \
        --corpus-dir scratch/f4_failing --top 25
    ... --markdown          # emit the plan's bucket table
    ... --out /tmp/t.json   # machine-readable, for a ratchet
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.decompiler import decompile_to_yaml
from fsr_playbooks.compiler.pipeline import compile_yaml

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / (
    "fsr_playbooks/tests/fixtures/roundtrip_corpus")


def _resolve_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("FSRPB_CORPUS_DIR")
    if env:
        return Path(env)
    return _DEFAULT_DIR


def _as_envelope(payload: Any) -> dict:
    """Coerce any of the three corpus row shapes to a `{"data":[coll]}` envelope."""
    if isinstance(payload, dict) and "envelope" in payload:
        payload = payload["envelope"]
    if isinstance(payload, dict) and "data" in payload:
        return payload
    # A bare workflow record (the F4 per-file dump). Wrap it so the decompiler,
    # which only accepts a collection, sees its canonical input.
    return {"data": [{
        "name": payload.get("name", "") or "",
        "description": payload.get("description", "") or "",
        "visible": True,
        "workflows": [payload],
    }]}


def _step_count(env: dict) -> int:
    n = 0
    for coll in env.get("data") or []:
        for wf in (coll.get("workflows") or []):
            steps = wf.get("steps")
            if isinstance(steps, dict):          # crudhub `{...}` container form
                steps = list(steps.values())
            n += len(steps or [])
    return n


# Collapse a concrete error message into a reusable pattern key. Order matters:
# these run in sequence, each stripping one source of noise.
_SCRUB: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"'[^']*'"), "'X'"),            # quoted identifiers
    (re.compile(r'"[^"]*"'), "'X'"),
    (re.compile(r"\[\d+\]"), "[i]"),            # list indices
    (re.compile(r"\b\d+\b"), "N"),              # bare numbers
    (re.compile(r"/api/3/\S+"), "<iri>"),       # record/picklist IRIs
    (re.compile(r"\s+"), " "),
]


def _pattern(msg: str) -> str:
    out = msg.strip()
    for rx, repl in _SCRUB:
        out = rx.sub(repl, out)
    return out.strip()


def _uuids(env: dict) -> tuple:
    """Identity of the workflows in a row, for dedup. Falls back to the row's
    own name when a dump carries no uuid, which is weaker but never merges two
    differently-named playbooks."""
    out = []
    for coll in env.get("data") or []:
        for wf in (coll.get("workflows") or []):
            out.append(wf.get("uuid") or wf.get("@id") or wf.get("name") or "")
    return tuple(out)


def triage(corpus_dir: Path, db_path: Path, dedup: bool = True) -> dict:
    files = sorted(corpus_dir.glob("*.json"))
    compiled = 0
    considered = 0
    skipped_no_steps = 0
    skipped_dup = 0
    seen: set[tuple] = set()
    unreadable: list[tuple[str, str]] = []
    by_code: Counter = Counter()
    by_pattern: Counter = Counter()
    pattern_code: dict[str, str] = {}
    pattern_files: dict[str, set] = defaultdict(set)
    # A playbook is attributed to the pattern of its FIRST blocking error, so
    # the buckets partition the failing set instead of double-counting a
    # playbook that trips five checks.
    primary: Counter = Counter()

    for f in files:
        try:
            env = _as_envelope(json.loads(f.read_text()))
        except Exception as exc:
            unreadable.append((f.stem, f"{type(exc).__name__}: {exc}"))
            continue
        if _step_count(env) == 0:
            skipped_no_steps += 1
            continue
        if dedup:
            ident = _uuids(env)
            if ident in seen:
                skipped_dup += 1
                continue
            seen.add(ident)
        considered += 1
        try:
            yaml_text = decompile_to_yaml(env, db_path)
            res = compile_yaml(yaml_text, db_path)
        except Exception as exc:
            unreadable.append((f.stem, f"{type(exc).__name__}: {exc}"))
            primary[f"<crash> {type(exc).__name__}"] += 1
            continue
        blocking = [e for e in res.errors if e.severity != "warning"]
        if res.ok and not blocking:
            compiled += 1
            continue
        first = True
        for e in blocking:
            code = getattr(e.code, "value", str(e.code))
            pat = _pattern(e.message)
            key = f"{code}: {pat}"
            by_code[code] += 1
            by_pattern[key] += 1
            pattern_code[key] = code
            pattern_files[key].add(f.stem)
            if first:
                primary[key] += 1
                first = False

    return {
        "corpus_dir": str(corpus_dir),
        "rows": len(files),
        "skipped_no_steps": skipped_no_steps,
        "skipped_duplicate": skipped_dup,
        "considered": considered,
        "compiled_clean": compiled,
        "failing": considered - compiled,
        "by_code": dict(by_code.most_common()),
        "by_pattern": [
            {
                "code": pattern_code[k],
                "pattern": k.split(": ", 1)[1],
                "errors": n,
                "playbooks": len(pattern_files[k]),
                "primary_for": primary.get(k, 0),
                "example": sorted(pattern_files[k])[0],
            }
            for k, n in by_pattern.most_common()
        ],
        "unreadable": unreadable[:20],
    }


def _print_text(r: dict, top: int) -> None:
    print(f"corpus:            {r['corpus_dir']}")
    print(f"rows on disk:      {r['rows']}")
    print(f"skipped (0 steps): {r['skipped_no_steps']}   "
          f"<- pull lacked ?$relationships=true; NOT a compiler defect")
    print(f"skipped (dup uuid):{r['skipped_duplicate']:>4}   "
          f"<- same playbook dumped once per referencing collection")
    print(f"considered:        {r['considered']}")
    print(f"compiles clean:    {r['compiled_clean']}/{r['considered']}")
    print(f"failing:           {r['failing']}")
    print()
    print("by code (error occurrences, a playbook may trip several):")
    for code, n in r["by_code"].items():
        print(f"  {n:>5}  {code}")
    print()
    print(f"by cause -- top {top} (primary_for partitions the {r['failing']} "
          f"failing playbooks):")
    print(f"  {'errs':>5} {'pbs':>5} {'1st':>5}  cause")
    for row in r["by_pattern"][:top]:
        print(f"  {row['errors']:>5} {row['playbooks']:>5} {row['primary_for']:>5}"
              f"  [{row['code']}] {row['pattern'][:100]}")
    if r["unreadable"]:
        print(f"\nunreadable rows ({len(r['unreadable'])} shown):")
        for name, why in r["unreadable"]:
            print(f"  {name}: {why}")


def _print_markdown(r: dict, top: int) -> None:
    print(f"Measured box-free against `{r['corpus_dir']}` "
          f"({r['rows']} rows, {r['skipped_no_steps']} skipped as step-less).\n")
    print("| property | result |")
    print("|---|---|")
    print(f"| considered | {r['considered']} |")
    print(f"| compiles clean | **{r['compiled_clean']}/{r['considered']}** |")
    print(f"| failing | {r['failing']} |")
    print()
    print("| cause | code | playbooks | primary for |")
    print("|---|---|---|---|")
    for row in r["by_pattern"][:top]:
        pat = row["pattern"].replace("|", "\\|")[:110]
        print(f"| {pat} | `{row['code']}` | {row['playbooks']} | "
              f"{row['primary_for']} |")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir")
    ap.add_argument("--db", help="reference DB path (default: resolved default)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--no-dedup", action="store_true",
                    help="score raw rows instead of distinct workflow uuids")
    ap.add_argument("--markdown", action="store_true",
                    help="emit the plan's bucket table instead of the text report")
    ap.add_argument("--out", help="write the full result as JSON")
    ap.add_argument("--min-pass", type=int,
                    help="ratchet: exit 1 if compiles-clean drops below this")
    a = ap.parse_args(argv)

    corpus_dir = _resolve_dir(a.corpus_dir)
    if not corpus_dir.is_dir():
        print(f"corpus dir not found: {corpus_dir}", file=sys.stderr)
        return 2
    db_path = Path(a.db) if a.db else default_db_path()

    r = triage(corpus_dir, db_path, dedup=not a.no_dedup)
    if a.markdown:
        _print_markdown(r, a.top)
    else:
        _print_text(r, a.top)
    if a.out:
        Path(a.out).write_text(json.dumps(r, indent=2, sort_keys=True))
        print(f"\nwrote {a.out}")
    if a.min_pass is not None and r["compiled_clean"] < a.min_pass:
        print(f"\nFAIL: {r['compiled_clean']} < --min-pass {a.min_pass}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
