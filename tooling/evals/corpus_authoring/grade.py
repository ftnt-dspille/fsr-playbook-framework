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

# A hard verify failure whose only cause is that THIS install lacks the corpus
# playbook's connector or custom module. The product's own remediation calls
# these "a fact about the box, not a defect in the playbook" -- so grading an
# authored playbook as unsound for them punishes the author for the test box.
_ENVIRONMENT_CODES = {"unknown_connector", "unknown_module"}


def _hard_fixes(fixes: Any) -> list[dict]:
    if not isinstance(fixes, list):
        return []
    return [f for f in fixes if isinstance(f, dict) and f.get("severity") == "error"]


def _environment_blocked(fixes: Any) -> bool:
    """True when verify failed ONLY because the box lacks a connector/module the
    corpus playbook names -- an environment fact, not an authoring defect."""
    hard = _hard_fixes(fixes)
    if not hard:
        return False
    return all(f.get("environment") is True or f.get("code") in _ENVIRONMENT_CODES
               for f in hard)


def _authored_has_loop(authored_yaml: str, db: Any) -> bool:
    """Field-agnostic 'this playbook iterates': does any step carry a for_each?
    A user-voice prompt can't name the exact loop variable, so exact-field
    for_each_over is unfair as a structural signal; loop PRESENCE is fair."""
    try:
        from fsr_playbooks.compiler.pipeline import compile_yaml
        ir = getattr(compile_yaml(authored_yaml, db), "ir", None)
        if not ir or not ir.playbooks:
            return False
        return any(getattr(s, "for_each", None) for s in (ir.playbooks[0].steps or []))
    except Exception:  # noqa: BLE001
        return False


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

    # environment-blocked: the only hard verify failures are "this box lacks that
    # connector/module". Sound modulo the test environment.
    env_blocked = (not verified) and _environment_blocked(verify_fixes)
    out["env_blocked"] = env_blocked
    verified_fair = verified or env_blocked
    out["verified_fair"] = verified_fair

    # ir: behavioral assertions
    ires = check_ir_assertions(authored_yaml, task.get("ir_assertions"), db)
    out["ir_passed"] = bool(ires.get("passed"))
    out["ir_checked"] = ires.get("checked")
    out["ir_failures"] = ires.get("failures")

    # field-agnostic structural signals a user-voice prompt CAN be held to even
    # when it cannot name the exact loop variable / op id the corpus used.
    wants_loop = any(a.get("kind") == "for_each_over" for a in (task.get("ir_assertions") or []))
    out["loop_present"] = _authored_has_loop(authored_yaml, db) if wants_loop else None

    # strict: compiles, statically sound, AND matches the required structure.
    out["passed"] = bool(draft and verified and out["ir_passed"])
    # fair: the author reproduced the real playbook's structure and compiled it,
    # and met `verified` UNLESS the real playbook itself cannot (compilability
    # gaps the source shares). This is the honest "did it match the real thing".
    source_verified = task.get("source_verified", True)
    out["source_verified"] = source_verified
    out["style"] = task.get("style", "prescriptive")
    # A prescriptive question names the structure, so fidelity (ir) is part of
    # the bar. A goal-only question names intent, so many valid designs exist:
    # grade sound+runnable and report structural overlap WITHOUT gating on it.
    strict_ir = task.get("strict_ir", True)
    # Sound enough: it verifies, OR the only blocker is this box's missing
    # connector/module, OR the real source itself can't verify either.
    verified_ok = verified_fair or not source_verified
    if strict_ir:
        out["fair_pass"] = bool(draft and out["ir_passed"] and verified_ok)
    else:
        out["fair_pass"] = bool(draft and verified_ok)
    return out


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Pass rates overall and per bucket, per gate."""
    def rate(rows: list[dict], key: str) -> str:
        n = sum(1 for r in rows if r.get(key))
        return f"{n}/{len(rows)}"

    buckets: dict[str, list] = {}
    for r in results:
        buckets.setdefault(r.get("bucket", "?"), []).append(r)

    gates = ("draft", "verified", "verified_fair", "env_blocked",
             "ir_passed", "passed", "fair_pass", "source_verified")
    report: dict[str, Any] = {
        "n": len(results),
        "overall": {g: rate(results, g) for g in gates},
        "by_bucket": {
            b: {g: rate(rows, g) for g in gates}
            for b, rows in sorted(buckets.items())
        },
    }
    return report
