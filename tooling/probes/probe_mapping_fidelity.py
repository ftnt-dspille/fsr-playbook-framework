"""Measure the wire<->IR mapping over every playbook on a live box.

`make corpus-gate` proves the mapping holds for five committed fixtures.
`probe_round_trip_audit` proves live playbooks COMPILE clean. Neither asks the
question that actually matters for a stable mapping: **does decompile ->
recompile preserve meaning on real playbooks we did not write?**

Five fixtures is five playbooks someone already thought of -- the same blind
spot that let `for_each` and declared `parameters` go missing twice. This probe
runs the identical semantic projection `roundtrip` uses (per-step
type/arguments/for_each, the routing graph, declared parameters) against every
collection the appliance has, and groups the diffs by PATTERN so the output is
a work list rather than a wall.

READ-ONLY: it pulls and compares in memory. Nothing is pushed, written, or
deleted.

Usage:
    python tooling/probes/probe_mapping_fidelity.py
    python tooling/probes/probe_mapping_fidelity.py --limit 25
    python tooling/probes/probe_mapping_fidelity.py --filter Schedule
    python tooling/probes/probe_mapping_fidelity.py --out /tmp/fidelity.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

from probes._env import get_client  # noqa: E402

from fsr_playbooks.compiler.decompiler import decompile  # noqa: E402
from fsr_playbooks.compiler.emitter import emit  # noqa: E402
from fsr_playbooks.compiler.roundtrip import diff, normalize_collection  # noqa: E402
from fsr_playbooks.compiler.wire import normalize_live_collection  # noqa: E402

DB = ROOT / "data" / "fsr_reference.db"

# Collapse a concrete diff line into a reusable pattern key, so 400 diffs over
# 12 real causes read as 12 rows. Order matters -- first match wins.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("step.arguments.<key>: only on one side",
     re.compile(r"steps\[[^\]]+\]\.arguments\.([\w.]+): only in")),
    ("step.arguments.<key>: value differs",
     re.compile(r"steps\[[^\]]+\]\.arguments\.([\w.]+): .* != ")),
    ("step: present on only one side",
     re.compile(r"workflows\[\d+\]\.steps\[[^\]]+\]: only in")),
    ("route: present on only one side",
     re.compile(r"routes\[[^\]]+\]: only in")),
    ("route label differs", re.compile(r"routes\[[^\]]+\]\.label")),
    ("step.for_each differs", re.compile(r"\.for_each")),
    ("step.stepType differs (canonical remap)", re.compile(r"\.stepType:")),
    ("declared parameters differ", re.compile(r"\.parameters")),
    ("trigger step differs", re.compile(r"trigger_step_name")),
    ("workflow present on only one side", re.compile(r"workflows: list length")),
]


def _pattern_of(line: str) -> tuple[str, str]:
    """(pattern key, captured detail) for one diff line."""
    for key, rx in _PATTERNS:
        m = rx.search(line)
        if m:
            return key, (m.group(1) if m.groups() else "")
    return "other", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--filter", help="only collections whose name contains this")
    ap.add_argument("--out", type=Path, help="write the full per-collection detail here")
    args = ap.parse_args()

    client = get_client()
    if client is None:
        print("no live FSR configured (.env) -- this probe needs a box", file=sys.stderr)
        return 2

    listing = client.get("/api/3/workflow_collections", params={"$limit": 500})
    members = (listing or {}).get("hydra:member", [])
    if args.filter:
        members = [c for c in members if args.filter.lower() in (c.get("name") or "").lower()]
    if args.limit:
        members = members[:args.limit]
    print(f"{len(members)} collection(s) to round-trip", file=sys.stderr)

    clean = 0
    crashed: list[tuple[str, str]] = []
    by_pattern: dict[str, Counter] = defaultdict(Counter)
    example: dict[str, str] = {}
    per_collection: list[dict[str, Any]] = []
    worst: list[tuple[int, str]] = []

    for i, c in enumerate(members, 1):
        name = c.get("name") or c.get("uuid") or "<unnamed>"
        try:
            payload = client.get(f"/api/3/workflow_collections/{c['uuid']}"
                                 "?$relationships=true&$versions=true")
            live = normalize_live_collection({"data": [payload]})
            ir = decompile(live, DB)
            regen = emit(ir)
            diffs = diff(normalize_collection(live), normalize_collection(regen),
                         "collection")
        except Exception as exc:  # noqa: BLE001
            crashed.append((name, f"{type(exc).__name__}: {exc}"))
            continue

        if not diffs:
            clean += 1
        else:
            worst.append((len(diffs), name))
            for line in diffs:
                key, detail = _pattern_of(line)
                by_pattern[key][detail or "-"] += 1
                example.setdefault(key, f"[{name}] {line[:220]}")
        per_collection.append({"name": name, "diffs": diffs})
        if i % 10 == 0:
            print(f"  ...{i}/{len(members)}", file=sys.stderr)

    total = len(members)
    compared = total - len(crashed)
    print(f"\nsemantic round-trip: {clean}/{compared} collection(s) clean"
          f"  ({len(crashed)} could not be compared)")

    if by_pattern:
        print("\ndiffs by pattern (count -- top offending keys)")
        rows = sorted(by_pattern.items(), key=lambda kv: -sum(kv[1].values()))
        for key, details in rows:
            n = sum(details.values())
            top = ", ".join(f"{d} x{k}" for d, k in details.most_common(6))
            print(f"  {n:6d}  {key}")
            print(f"          {top}")
            print(f"          e.g. {example[key]}")

    if worst:
        print("\nnoisiest collections")
        for n, name in sorted(worst, reverse=True)[:10]:
            print(f"  {n:6d}  {name}")

    if crashed:
        print(f"\n{len(crashed)} could not be compared at all:")
        for name, msg in crashed[:20]:
            print(f"  [{name}] {msg}")

    if args.out:
        args.out.write_text(json.dumps(per_collection, indent=2))
        print(f"\nfull detail -> {args.out}", file=sys.stderr)

    # Non-zero only when a collection could not be compared. Semantic diffs are
    # a work list to triage, not a build break -- some are known-lossy authoring
    # sugars (see decompiler's `_EXTRA_CANONICAL_TO_SHORT` notes).
    return 1 if crashed else 0


if __name__ == "__main__":
    raise SystemExit(main())
