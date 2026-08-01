"""Ground `compiler/wire.py` against what a live appliance actually returns.

The wire models were written from two observed shapes (export JSON's record
lists, and a live GET's id-keyed maps). Written-from-observation is exactly
how the original bug got in: the compiler-side assumption "steps is a list"
was true of every fixture anyone had looked at. So this probe stops guessing
and asks the box.

READ-ONLY. It pages `workflow_collections`, re-GETs each with
`$relationships=true` (the shape the pre-write gate diffs against), and:

  * validates every collection against `LiveEnvelope`, reporting each
    failure by field path rather than a pass/fail count;
  * tallies the CONTAINER SHAPE actually seen per field (list vs id-keyed
    map vs absent), so "we handle both" is evidence, not belief;
  * tallies the observed Python type of every modelled scalar, so a field
    we typed `str` that is sometimes null shows up here rather than as a
    ValidationError on a customer's box;
  * lists unmodelled step/route keys by frequency -- candidates for the
    next round of typing.

Usage:
    python tooling/probes/probe_wire_shapes.py             # whole box
    python tooling/probes/probe_wire_shapes.py --limit 25
    python tooling/probes/probe_wire_shapes.py --uuid <collection-uuid>
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

from probes._env import get_client  # noqa: E402

from fsr_playbooks.compiler.wire import (  # noqa: E402
    LiveEnvelope,
    WireShapeError,
    normalize_live_collection,
)

# Fields whose container shape we claim to accept either way.
_CONTAINERS = (
    ("collection", "workflows"),
    ("workflow", "steps"),
    ("workflow", "routes"),
)

# Scalars the models declare. If the box disagrees with any of these, the
# model is wrong -- not the box.
_MODELLED = {
    "workflow": ("uuid", "name"),
    "step": ("uuid", "name", "stepType", "arguments"),
    "route": ("uuid", "name", "label", "sourceStep", "targetStep"),
}


def _shape(value: Any) -> str:
    if value is None:
        return "absent/null"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "id-keyed map"
    return f"!! {type(value).__name__}"


class Findings:
    def __init__(self) -> None:
        self.containers: dict[str, Counter] = defaultdict(Counter)
        self.scalars: dict[str, Counter] = defaultdict(Counter)
        self.extra_keys: dict[str, Counter] = defaultdict(Counter)
        self.failures: list[tuple[str, str]] = []
        self.collections = 0
        self.workflows = 0
        self.steps = 0

    def record_record(self, kind: str, rec: dict[str, Any]) -> None:
        for field in _MODELLED[kind]:
            if field in rec:
                self.scalars[f"{kind}.{field}"][type(rec[field]).__name__] += 1
        for key in rec:
            if key not in _MODELLED.get(kind, ()):
                self.extra_keys[kind][key] += 1


def _inspect(payload: dict[str, Any], f: Findings) -> None:
    """Walk the RAW payload for shape evidence, then validate it."""
    coll = payload
    name = coll.get("name") or coll.get("uuid") or "<unnamed>"
    f.collections += 1

    f.containers["collection.workflows"][_shape(coll.get("workflows"))] += 1
    workflows = coll.get("workflows")
    wf_iter = (workflows.values() if isinstance(workflows, dict)
               else (workflows or []))
    for wf in wf_iter:
        if not isinstance(wf, dict):
            f.failures.append((name, f"workflows member is {type(wf).__name__}"))
            continue
        f.workflows += 1
        f.record_record("workflow", wf)
        for field, kind in (("steps", "step"), ("routes", "route")):
            f.containers[f"workflow.{field}"][_shape(wf.get(field))] += 1
            raw = wf.get(field)
            members = raw.values() if isinstance(raw, dict) else (raw or [])
            for rec in members:
                if not isinstance(rec, dict):
                    f.failures.append((name, f"{field} member is {type(rec).__name__}"))
                    continue
                if kind == "step":
                    f.steps += 1
                f.record_record(kind, rec)

    # Now the real gate: does our model accept what the box sent?
    try:
        LiveEnvelope.model_validate({"data": [coll]})
        normalize_live_collection({"data": [coll]})
    except WireShapeError as exc:
        f.failures.append((name, f"WireShapeError: {exc}"))
    except Exception as exc:  # pydantic ValidationError and anything else
        for line in str(exc).splitlines()[:6]:
            f.failures.append((name, line.strip()))


def _report(f: Findings) -> int:
    print(f"\ninspected {f.collections} collection(s), {f.workflows} workflow(s), "
          f"{f.steps} step(s)\n")

    print("container shapes actually returned")
    for _, field in _CONTAINERS:
        key = next(k for k in f.containers if k.endswith(f".{field}"))
        seen = ", ".join(f"{shape} x{n}" for shape, n in f.containers[key].most_common())
        print(f"  {key:24s} {seen or '(never present)'}")

    print("\nobserved types of modelled fields")
    for key in sorted(f.scalars):
        seen = ", ".join(f"{t} x{n}" for t, n in f.scalars[key].most_common())
        print(f"  {key:24s} {seen}")

    print("\nunmodelled keys (candidates for the next typing pass)")
    for kind in sorted(f.extra_keys):
        top = ", ".join(f"{k} x{n}" for k, n in f.extra_keys[kind].most_common(12))
        print(f"  {kind:9s} {top}")

    if f.failures:
        print(f"\n{len(f.failures)} MODEL MISMATCH(ES) -- the model is wrong, not the box:")
        for name, msg in f.failures[:40]:
            print(f"  [{name}] {msg}")
        return 1
    print("\nno mismatches: every live collection validated against the wire models.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="stop after N collections")
    ap.add_argument("--uuid", help="inspect a single collection")
    ap.add_argument("--dump", type=Path, help="write raw payloads here for offline fixtures")
    ap.add_argument("--census", type=Path,
                    help="write the SHAPE CENSUS (types + counts only, no playbook "
                         "content) for the box-free conformance test")
    args = ap.parse_args()

    client = get_client()
    if client is None:
        print("no live FSR configured (see .env) -- this probe needs a box", file=sys.stderr)
        return 2

    if args.uuid:
        uuids = [args.uuid]
    else:
        listing = client.get("/api/3/workflow_collections", params={"$limit": 500})
        uuids = [c.get("uuid") for c in (listing or {}).get("hydra:member", [])
                 if c.get("uuid")]
        if args.limit:
            uuids = uuids[:args.limit]
    print(f"{len(uuids)} collection(s) to inspect", file=sys.stderr)

    f = Findings()
    dumped = []
    for i, u in enumerate(uuids, 1):
        try:
            payload = client.get(
                f"/api/3/workflow_collections/{u}?$relationships=true&$versions=true")
        except Exception as exc:  # noqa: BLE001
            f.failures.append((u, f"GET failed: {type(exc).__name__}: {exc}"))
            continue
        if not isinstance(payload, dict):
            f.failures.append((u, f"GET returned {type(payload).__name__}"))
            continue
        _inspect(payload, f)
        if args.dump:
            dumped.append(payload)
        if i % 10 == 0:
            print(f"  ...{i}/{len(uuids)}", file=sys.stderr)

    if args.census:
        # Types and counts ONLY -- no names, no arguments, no host. This is the
        # artifact the committed conformance test reads, so the models stay
        # pinned to real appliance behaviour without needing a box (and without
        # putting a customer's playbooks in a public repo).
        args.census.write_text(json.dumps({
            "note": ("shape census from a live 8.0.0 appliance; regenerate with "
                     "`probe_wire_shapes.py --census`. Types and counts only."),
            "collections": f.collections,
            "workflows": f.workflows,
            "steps": f.steps,
            "containers": {k: dict(v) for k, v in sorted(f.containers.items())},
            "field_types": {k: dict(v) for k, v in sorted(f.scalars.items())},
            "unmodelled_keys": {k: dict(v) for k, v in sorted(f.extra_keys.items())},
        }, indent=2, sort_keys=True) + "\n")
        print(f"wrote shape census to {args.census}", file=sys.stderr)

    if args.dump and dumped:
        args.dump.write_text(json.dumps({"data": dumped}, indent=2))
        print(f"wrote {len(dumped)} payload(s) to {args.dump}", file=sys.stderr)

    return _report(f)


if __name__ == "__main__":
    raise SystemExit(main())
