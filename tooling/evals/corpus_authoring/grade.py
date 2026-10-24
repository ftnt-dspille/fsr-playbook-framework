"""Grade an authored playbook against a corpus-authoring task.

Three gates, reusing the framework's own graders so this never drifts from the
product's definition of "good":
  draft    -- compiles to FSR JSON (fsr_playbooks.compiler.compile_yaml)
  verified -- statically sound (verify_playbook.ready_to_push)
  ir       -- behavioral assertions hold (ir_assertions.check_ir_assertions)

A task passes when all three hold. `verified` implies `draft`, but both are
reported so a compile break is distinguishable from a soundness break.
Box-free; no live execution (that is a later, opt-in gate).
"""
from __future__ import annotations

from typing import Any

from fsr_playbooks._db import default_db_path

from tooling.evals.ir_assertions import check_ir_assertions


def grade_yaml(authored_yaml: str, task: dict[str, Any], db_path: Any = None) -> dict[str, Any]:
    db = db_path or default_db_path()
    out: dict[str, Any] = {"id": task.get("id"), "bucket": task.get("bucket")}

    if not (authored_yaml or "").strip():
        out.update(draft=False, verified=False, ir_passed=False,
                   passed=False, fair_pass=False,
                   source_verified=task.get("source_verified", True),
                   detail="no YAML authored")
        return out

    # draft: does it compile?
    try:
        from fsr_playbooks.compiler.pipeline import compile_yaml
        cres = compile_yaml(authored_yaml, db)
        ir = getattr(cres, "ir", None)
        draft = bool(ir and ir.playbooks)
        compile_errors = [str(e) for e in (getattr(cres, "errors", None) or [])]
    except Exception as exc:  # noqa: BLE001
        draft = False
        compile_errors = [f"{type(exc).__name__}: {exc}"]
    out["draft"] = draft
    out["compile_errors"] = compile_errors[:5]

    # verified: statically sound per the product's own pre-submit gate
    verified = False
    verify_fixes: list = []
    try:
        from fsr_playbooks.mcp_server.tools_verify import verify_playbook
        v = verify_playbook(authored_yaml, db_path=str(db) if db else None)
        verified = bool(v.get("ready_to_push"))
        verify_fixes = v.get("required_fixes") or v.get("required_fix_codes") or []
    except Exception as exc:  # noqa: BLE001
        verify_fixes = [f"{type(exc).__name__}: {exc}"]
    out["verified"] = verified
    out["required_fixes"] = verify_fixes[:5] if isinstance(verify_fixes, list) else verify_fixes

    # ir: behavioral assertions
    ires = check_ir_assertions(authored_yaml, task.get("ir_assertions"), db)
    out["ir_passed"] = bool(ires.get("passed"))
    out["ir_checked"] = ires.get("checked")
    out["ir_failures"] = ires.get("failures")

    # strict: compiles, statically sound, AND matches the required structure.
    out["passed"] = bool(draft and verified and out["ir_passed"])
    # fair: the author reproduced the real playbook's structure and compiled it,
    # and met `verified` UNLESS the real playbook itself cannot (compilability
    # gaps the source shares). This is the honest "did it match the real thing".
    source_verified = task.get("source_verified", True)
    out["source_verified"] = source_verified
    out["fair_pass"] = bool(draft and out["ir_passed"] and (verified or not source_verified))
    return out


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Pass rates overall and per bucket, per gate."""
    def rate(rows: list[dict], key: str) -> str:
        n = sum(1 for r in rows if r.get(key))
        return f"{n}/{len(rows)}"

    buckets: dict[str, list] = {}
    for r in results:
        buckets.setdefault(r.get("bucket", "?"), []).append(r)

    gates = ("draft", "verified", "ir_passed", "passed", "fair_pass", "source_verified")
    report: dict[str, Any] = {
        "n": len(results),
        "overall": {g: rate(results, g) for g in gates},
        "by_bucket": {
            b: {g: rate(rows, g) for g in gates}
            for b, rows in sorted(buckets.items())
        },
    }
    return report
