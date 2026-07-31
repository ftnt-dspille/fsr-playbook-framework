"""Corpus conformance: compile every shipped playbook we have on disk.

The question this answers is "is the compiler solid?", and it answers it
against 1,300+ playbooks Fortinet actually ships rather than against fixtures
we wrote ourselves. Fixtures encode what we thought the wire format was;
solution packs encode what it is.

Two paths are measured separately, because they fail for different reasons:

  **ir**   -- decompile -> emit -> semantic diff. Exercises the decompiler and
              emitter only. A diff here means the compiler cannot reproduce a
              playbook it was just handed: an outright fidelity bug.

  **yaml** -- decompile -> YAML -> compile_yaml -> semantic diff. Adds the
              parser, the typed (pydantic) argument models, the resolver and
              every validator. A block here is usually one of three things,
              and the report separates them rather than lumping them as
              "failures":

                * a real gap in our models (a key real playbooks use that a
                  StrictArgs model rejects),
                * a validator false positive (a rule too strict for a shape
                  that ships and works),
                * a genuine defect in the vendor pack (dangling step
                  references are common) -- which is the linter EARNING its
                  keep, not failing.

Runs entirely offline against `data/solution_packs`; no appliance needed, so
it is safe in CI. `--json` writes the full per-file detail for drilling.

Usage::

    python -m tooling.probes.probe_corpus_conformance
    python -m tooling.probes.probe_corpus_conformance --path ir --limit 200
    python -m tooling.probes.probe_corpus_conformance --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from .common import DB_PATH, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))

PACKS_DIR = REPO_ROOT / "data" / "solution_packs"

# Non-playbook JSON that lives alongside the playbooks in a pack bundle.
SKIP_NAMES = {"globalVariables.json", "tags.json", "info.json", "data.json",
              "_catalog.json"}


def _load_playbook(path: Path) -> dict[str, Any] | None:
    """Return a single-Workflow dict in the API shape, or None if not a playbook.

    Pack bundles ship playbooks in TWO shapes and only one is the shape the
    decompiler reads:

        steps/routes            -- the API shape (1,274 files)
        workflowSteps/…Routes   -- the pack-export shape (61 files)

    Normalizing the second is not cosmetic. Without it the decompiler returns a
    playbook with zero steps, the round-trip compares empty against empty, and
    those files report a PASS while never having been tested at all -- which is
    exactly what this probe was measuring on its first run.

    Pack bundles also contain notification rules (`entity_type`/`actions`, ~150
    files), which are not playbooks and are skipped rather than counted as
    failures.
    """
    try:
        doc = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    if isinstance(doc.get("workflowSteps"), list):
        doc = dict(doc)
        doc["steps"] = doc.pop("workflowSteps")
        doc["routes"] = doc.pop("workflowRoutes", [])
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    return doc


def _iter_playbooks(limit: int | None = None) -> Iterator[tuple[Path, dict]]:
    n = 0
    for path in sorted(PACKS_DIR.rglob("*.json")):
        if path.name in SKIP_NAMES:
            continue
        doc = _load_playbook(path)
        if doc is None:
            continue
        yield path, doc
        n += 1
        if limit and n >= limit:
            return


def _wrap(doc: dict, name: str) -> dict:
    """Wrap a bare Workflow in the `{data: [WorkflowCollection]}` envelope."""
    return {"data": [{
        "@type": "WorkflowCollection", "name": name,
        "uuid": "00000000-0000-0000-0000-000000000000",
        "visible": True, "workflows": [doc],
    }]}


def _is_reference_block(doc: dict) -> bool:
    """True for a playbook that is documentation, not something FSR can run.

    A runnable FortiSOAR playbook always has a trigger step -- even a
    referenced sub-playbook carries `cybersponse.abstract_trigger`. The
    exception is the reference blocks shipped in sOARFramework and a few
    feature packs: worked examples an author copies steps OUT of ("Check if an
    IP address is Internal or External", "Execute Playbook Step using Do-Until
    Loop"). FSR marks them with `hasTriggerStep: false`, they have no trigger
    step at all, and nothing in the corpus calls them.

    They are the reason `NO_TRIGGER` fires 37 times against shipped content.
    That is the validator being RIGHT: these would not run. They belong outside
    the conformance denominator, not inside a relaxed rule.
    """
    return doc.get("hasTriggerStep") is False


def _known_dangling(msg: str, doc: dict) -> bool:
    """True when a broken reference is broken in the SOURCE pack, not by us.

    Vendor packs ship playbooks whose Jinja still points at a step that was
    later renamed. Reporting those as compiler failures would bury the real
    ones, so they are counted in their own bucket.
    """
    import re
    m = re.search(r"vars\.steps\.([A-Za-z0-9_]+)", msg or "")
    if not m:
        return False
    have = {re.sub(r"\W", "_", (s.get("name") or "")) for s in doc.get("steps", [])}
    return m.group(1) not in have


def run(*, path_mode: str = "both", limit: int | None = None,
        db_path: Path | None = None) -> dict:
    from fsr_playbooks.compiler import compile_yaml
    from fsr_playbooks.compiler.decompiler import decompile_to_yaml
    from fsr_playbooks.compiler.roundtrip import roundtrip

    db = Path(db_path or DB_PATH)
    ir_ok = ir_diff = ir_err = 0
    yaml_ok = yaml_blocked = yaml_err = 0
    ir_kinds: Counter = Counter()
    yaml_kinds: Counter = Counter()
    examples: dict[str, str] = {}
    detail: list[dict] = []
    total = 0

    for pb_path, doc in _iter_playbooks(limit):
        total += 1
        src = _wrap(doc, pb_path.parent.name)
        rec: dict[str, Any] = {"file": str(pb_path.relative_to(REPO_ROOT))}

        if path_mode in ("both", "ir"):
            try:
                good, diffs = roundtrip(src, db)
                if good:
                    ir_ok += 1
                else:
                    ir_diff += 1
                    rec["ir_diffs"] = diffs[:10]
                    for dtext in diffs:
                        key = dtext.split(":")[0][:90]
                        ir_kinds[key] += 1
                        examples.setdefault(f"ir/{key}", f"{pb_path.name}: {dtext[:180]}")
            except Exception as exc:  # noqa: BLE001 - probe reports, never aborts
                ir_err += 1
                key = f"{type(exc).__name__}: {exc}"[:90]
                ir_kinds[key] += 1
                examples.setdefault(f"ir/{key}", str(pb_path))

        if path_mode in ("both", "yaml"):
            try:
                result = compile_yaml(decompile_to_yaml(src, db), db)
            except Exception as exc:  # noqa: BLE001
                yaml_err += 1
                key = f"EXC {type(exc).__name__}: {exc}"[:90]
                yaml_kinds[key] += 1
                examples.setdefault(f"yaml/{key}", str(pb_path))
                detail.append(rec)
                continue
            blocking = [e for e in (result.errors or []) if e.severity != "warning"]
            if not blocking:
                yaml_ok += 1
            else:
                yaml_blocked += 1
                rec["yaml_errors"] = [e.to_dict() for e in blocking[:10]]
                ref_block = _is_reference_block(doc)
                rec["reference_block"] = ref_block
                for err in blocking:
                    key = err.code.name
                    if _known_dangling(err.message, doc):
                        key = "SOURCE_PACK_DANGLING_REF"
                    # A reference block is documentation, not a runnable
                    # playbook -- see _is_reference_block. Errors against one
                    # are the validator working, and are bucketed apart so they
                    # cannot be mistaken for compiler gaps.
                    if ref_block:
                        key = f"{key} [reference-block]"
                    yaml_kinds[key] += 1
                    examples.setdefault(f"yaml/{key}",
                                        f"{pb_path.name}: {err.message[:160]}")
        if len(rec) > 1:
            detail.append(rec)

    return {
        "playbooks": total,
        "ir": {"ok": ir_ok, "diff": ir_diff, "error": ir_err,
               "kinds": dict(ir_kinds.most_common())},
        "yaml": {"ok": yaml_ok, "blocked": yaml_blocked, "error": yaml_err,
                 "kinds": dict(yaml_kinds.most_common())},
        "examples": examples,
        "detail": detail,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", choices=("both", "ir", "yaml"), default="both")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--json", type=Path, help="write full per-file detail here")
    args = ap.parse_args()

    result = run(path_mode=args.path, limit=args.limit, db_path=args.db)
    detail = result.pop("detail")
    if args.json:
        args.json.write_text(json.dumps(detail, indent=2))
        print(f"detail -> {args.json} ({len(detail)} files)", file=sys.stderr)

    examples = result.pop("examples")
    print(f"playbooks: {result['playbooks']}")
    for mode in ("ir", "yaml"):
        block = result[mode]
        if not any(v for k, v in block.items() if k != "kinds"):
            continue
        head = ", ".join(f"{k}={v}" for k, v in block.items() if k != "kinds")
        print(f"\n[{mode}] {head}")
        for key, n in block["kinds"].items():
            print(f"  {n:5d}  {key}")
            eg = examples.get(f"{mode}/{key}")
            if eg:
                print(f"         e.g. {eg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
