"""Turn the real playbook corpus into a stratified set of AUTHORING tasks.

Deterministic, box-free, LLM-free. For each distinct corpus playbook:
  wire JSON -> decompile_to_yaml -> compile_yaml(...).ir  (the resolved IR)
  -> derive a spec + ir_assertions (derive.py)
  -> SELF-CHECK: compile the real YAML and keep only the assertions the real
     playbook itself satisfies. An assertion the source fails is a derivation
     bug, not a task; dropping it keeps every task satisfiable by a correct
     author.
Tasks are bucketed by the step-types that are the known coverage gaps
(workflow_reference / approval / loops / code / multi-branch / large) and a
stratified sample is written out.

Output tasks carry the source uuid/name and the real YAML for reference; they
are LOCAL ONLY (real-box provenance) -- write under a gitignored dir.

    FSRPB_DEV=1 .venv/bin/python -m tooling.evals.corpus_authoring.sample_corpus \
        --corpus-dir <dir> --out <gitignored dir> --per-bucket 2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.decompiler import decompile_to_yaml
from fsr_playbooks.compiler.pipeline import compile_yaml

# repo root on path so `tooling.evals...` imports resolve under FSRPB_DEV
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tooling.evals.corpus_authoring import derive  # noqa: E402
from tooling.evals.ir_assertions import _check_one  # noqa: E402


# --- corpus row coercion (mirrors scripts/corpus_compile_triage.py) ---------
def _as_envelope(payload: Any) -> dict:
    if isinstance(payload, dict) and "envelope" in payload:
        payload = payload["envelope"]
    if isinstance(payload, dict) and "data" in payload:
        return payload
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
            if isinstance(steps, dict):
                steps = list(steps.values())
            n += len(steps or [])
    return n


def _uuids(env: dict) -> tuple:
    out = []
    for coll in env.get("data") or []:
        for wf in (coll.get("workflows") or []):
            out.append(wf.get("uuid") or wf.get("@id") or wf.get("name") or "")
    return tuple(out)


# --- bucketing --------------------------------------------------------------
def _bucket(pb) -> str:
    """The hardest coverage-gap class this playbook exercises (first match wins
    so each playbook lands in exactly one bucket, hardest-first)."""
    types = {s.type for s in (pb.steps or [])}
    n = len(pb.steps or [])
    if "workflow_reference" in types:
        return "child_playbook"
    if "approval_manual_input" in types:
        return "approval"
    if "code_snippet" in types or "run_script" in types:
        return "code"
    if any(s.for_each for s in (pb.steps or [])):
        return "loop"
    decisions = [s for s in (pb.steps or []) if s.type == "decision"]
    if any(len(s.branches or {}) >= 3 for s in decisions):
        return "multi_branch"
    if n >= 15:
        return "large"
    if "manual_input" in types:
        return "manual_input"
    if "decision" in types:
        return "decision"
    if "connector" in types:
        return "connector"
    return "simple"


_TRIVIAL_TYPES = {"start", "set_variable"}


def _source_verified(real_yaml: str, db_path) -> bool:
    """Whether the real playbook passes verify_playbook.ready_to_push."""
    try:
        from fsr_playbooks.mcp_server.tools_verify import verify_playbook
        v = verify_playbook(real_yaml, db_path=str(db_path) if db_path else None)
        return bool(v.get("ready_to_push"))
    except Exception:  # noqa: BLE001
        return False


def _has_substantive(assertions: list[dict]) -> bool:
    """True if some assertion requires more than a trivial step's presence."""
    for a in assertions:
        if a["kind"] != "step_type_present":
            return True
        if a.get("type") not in _TRIVIAL_TYPES:
            return True
    return False


def _task_id(bucket: str, name: str, uuid: str) -> str:
    h = hashlib.sha1((uuid or name).encode()).hexdigest()[:8]
    slug = "".join(c if c.isalnum() else "_" for c in (name or "pb").lower())[:40]
    return f"{bucket}__{slug}__{h}"


def build_tasks(corpus_dir: Path, db_path, min_assertions: int = 2) -> list[dict]:
    files = sorted(corpus_dir.glob("*.json"))
    seen: set[tuple] = set()
    tasks: list[dict] = []
    stats = defaultdict(int)
    for f in files:
        try:
            env = _as_envelope(json.loads(f.read_text()))
        except Exception:
            stats["unreadable"] += 1
            continue
        if _step_count(env) == 0:
            stats["no_steps"] += 1
            continue
        ident = _uuids(env)
        if ident in seen:
            stats["dup"] += 1
            continue
        seen.add(ident)
        try:
            real_yaml = decompile_to_yaml(env, db_path)
            res = compile_yaml(real_yaml, db_path)
        except Exception:
            stats["decompile_fail"] += 1
            continue
        ir = getattr(res, "ir", None)
        if ir is None or not ir.playbooks:
            stats["no_ir"] += 1
            continue
        pb = ir.playbooks[0]
        # derive, then keep only self-consistent assertions
        derived = derive.derive_assertions(pb)
        kept = [a for a in derived if _check_one(pb, a)[0]]
        if len(kept) < min_assertions:
            stats["too_few_assertions"] += 1
            continue
        # a task must require something beyond "has a trigger / a set_variable",
        # or it grades nothing an author could get wrong
        if not _has_substantive(kept):
            stats["trivial_only"] += 1
            continue
        bucket = _bucket(pb)
        # Does the REAL playbook pass the product's own pre-submit gate? Many do
        # not (compilability != fidelity), so grading an author against a bar the
        # source cannot meet would be unfair; store it so grading can be fair.
        source_verified = _source_verified(real_yaml, db_path)
        uuid = ident[0] if ident else ""
        base = {
            "bucket": bucket,
            "source_uuid": uuid,
            "source_name": pb.name,
            "ir_assertions": kept,
            "real_yaml": real_yaml,
            "n_steps": len(pb.steps or []),
            "source_verified": source_verified,
        }
        # A mix of question TYPES in USER language (never the FSR step-type/op
        # enums the grader checks -- that would be a lookup, not a design task):
        #   goal        -- non-expert, states only the real-world goal;
        #   operational -- analyst, describes the behaviours in plain language.
        # Both grade sound+runnable; structural overlap with the real playbook
        # is reported but not gated (many valid designs satisfy one ask).
        variants = []
        goal = derive.derive_goal_spec(pb)
        if goal:
            variants.append(("goal", goal, False))
        op = derive.derive_operational_spec(pb, kept)
        if op:
            variants.append(("operational", op, False))
        if not variants:
            stats["no_user_spec"] += 1
            continue
        for style, spec, strict_ir in variants:
            tasks.append({
                **base,
                "id": _task_id(bucket, pb.name, uuid) + f"__{style}",
                "style": style,
                "strict_ir": strict_ir,
                "spec": spec,
            })
            stats[f"built_{style}"] += 1
        stats["built"] += 1
    tasks.sort(key=lambda t: (t["bucket"], t["id"]))
    return tasks, dict(stats)


def stratified(tasks: list[dict], per_bucket: int, seed: int = 0) -> list[dict]:
    import random
    rng = random.Random(seed)
    by_bucket: dict[str, list] = defaultdict(list)
    for t in tasks:
        by_bucket[t["bucket"]].append(t)
    out = []
    for bucket in sorted(by_bucket):
        pool = sorted(by_bucket[bucket], key=lambda t: t["id"])
        rng.shuffle(pool)
        out.extend(pool[:per_bucket])
    out.sort(key=lambda t: (t["bucket"], t["id"]))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", default=os.environ.get("FSRPB_CORPUS_DIR"),
                    help="dir of wire-JSON corpus rows (F4 pull)")
    ap.add_argument("--out", required=True, help="output dir for task JSONs (gitignored)")
    ap.add_argument("--per-bucket", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--all", action="store_true", help="write every buildable task, not a sample")
    args = ap.parse_args(argv)
    if not args.corpus_dir:
        ap.error("--corpus-dir or FSRPB_CORPUS_DIR required")

    db = default_db_path()
    tasks, stats = build_tasks(Path(args.corpus_dir), db)
    chosen = tasks if args.all else stratified(tasks, args.per_bucket, args.seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for t in chosen:
        (out / f"{t['id']}.json").write_text(json.dumps(t, indent=2))
    manifest = {
        "stats": stats,
        "buckets": {b: sum(1 for t in tasks if t["bucket"] == b)
                    for b in sorted({t["bucket"] for t in tasks})},
        "written": [t["id"] for t in chosen],
        "written_buckets": {b: sum(1 for t in chosen if t["bucket"] == b)
                            for b in sorted({t["bucket"] for t in chosen})},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"corpus: built {stats.get('built', 0)} tasks "
          f"({stats.get('dup', 0)} dup, {stats.get('no_steps', 0)} no-steps, "
          f"{stats.get('too_few_assertions', 0)} too-few-assertions, "
          f"{stats.get('decompile_fail', 0)} decompile-fail)")
    print("buckets:", manifest["buckets"])
    print(f"wrote {len(chosen)} tasks -> {out}  ({manifest['written_buckets']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
