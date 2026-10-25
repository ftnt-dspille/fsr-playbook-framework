"""Grade a repair: did the defect get detected, then actually fixed?

Three signals, all offline:
  detected  -- compile/verify surfaces one of the defect's expected codes on the
               BROKEN playbook (a diagnosis has something true to find).
  repaired  -- the repaired playbook compiles AND no longer carries any expected
               code (the specific defect is gone, not merely a different error).
  structure_preserved -- the repaired playbook still satisfies the ORIGINAL
               playbook's derived structural assertions (the fix didn't gut it).

`repaired` deliberately does not require full verify ready_to_push: the source
may have been environment-blocked to begin with (missing connector on this box).
It requires that the injected defect's code is gone and the playbook compiles.
"""
from __future__ import annotations

import re
from typing import Any

from fsr_playbooks._db import default_db_path

from tooling.evals.corpus_authoring import derive
from tooling.evals.ir_assertions import check_ir_assertions

_CODE_RE = re.compile(r"ErrorCode\.[A-Z_]+:\s*'([a-z_]+)'")
_PATH_RE = re.compile(r"path='([^']*)'")


def _codes(yaml_text: str, db) -> set[tuple[str, str]]:
    """Every (code, path) pair compile + verify report for this YAML.

    Keyed by path, not code alone: a playbook may legitimately carry a generic
    `missing_field` / `bad_value` warning elsewhere (e.g. a defaulted
    button_label), so only a (code, path) delta against the clean original
    isolates the injected defect from pre-existing diagnostics.
    """
    out: set[tuple[str, str]] = set()
    try:
        from fsr_playbooks.compiler.pipeline import compile_yaml
        cres = compile_yaml(yaml_text, db)
        for e in (getattr(cres, "errors", None) or []):
            c = getattr(e, "code", None)
            code = getattr(c, "value", None) if c is not None else None
            if code is None:
                m = _CODE_RE.search(str(e))
                code = m.group(1) if m else None
            path = getattr(e, "path", None)
            if path is None:
                pm = _PATH_RE.search(str(e))
                path = pm.group(1) if pm else ""
            if code:
                out.add((code, str(path or "")))
    except Exception as exc:  # noqa: BLE001
        out.add((f"compile_threw:{type(exc).__name__}", ""))
    try:
        from fsr_playbooks.mcp_server.tools_verify import verify_playbook
        v = verify_playbook(yaml_text, db_path=str(db) if db else None)
        for f in (v.get("required_fixes") or []):
            if isinstance(f, dict) and f.get("code"):
                out.add((f["code"], str(f.get("path") or "")))
    except Exception:  # noqa: BLE001
        pass
    return out


def _compiles(yaml_text: str, db) -> bool:
    try:
        from fsr_playbooks.compiler.pipeline import compile_yaml
        ir = getattr(compile_yaml(yaml_text, db), "ir", None)
        return bool(ir and ir.playbooks)
    except Exception:  # noqa: BLE001
        return False


def grade_repair(original_yaml: str, defect: dict, repaired_yaml: str | None,
                 db: Any = None) -> dict[str, Any]:
    db = db or default_db_path()
    expect = set(defect.get("expect_codes") or [])

    # Codes the injection INTRODUCED, relative to the clean original: isolates
    # the defect from the playbook's pre-existing (unrelated) diagnostics.
    baseline = _codes(original_yaml, db)
    broken_codes = _codes(defect["yaml"], db)
    introduced = broken_codes - baseline
    detected = any(code in expect for code, _path in introduced)

    out: dict[str, Any] = {
        "kind": defect.get("kind"),
        "detected": detected,
        "introduced_codes": sorted(introduced),
    }

    if not (repaired_yaml or "").strip():
        out.update(repaired=False, structure_preserved=False,
                   detail="no repair produced")
        return out

    rep_codes = _codes(repaired_yaml, db)
    compiles = _compiles(repaired_yaml, db)
    # repaired: compiles AND none of the introduced defect pairs remain.
    defect_gone = not (introduced & rep_codes)
    out["repaired"] = bool(compiles and defect_gone)
    out["remaining_introduced"] = sorted(introduced & rep_codes)

    # structure preserved: the repaired playbook still satisfies the original's
    # own derived assertions (keep only those the original itself satisfied, so
    # a derivation quirk never fails a correct repair).
    try:
        from fsr_playbooks.compiler.pipeline import compile_yaml
        orig_ir = compile_yaml(original_yaml, db).ir.playbooks[0]
        asserts = [a for a in derive.derive_assertions(orig_ir)]
        from tooling.evals.ir_assertions import _check_one
        kept = [a for a in asserts if _check_one(orig_ir, a)[0]]
        res = check_ir_assertions(repaired_yaml, kept, db)
        out["structure_preserved"] = bool(res.get("passed"))
        out["structure_failures"] = res.get("failures")
    except Exception as exc:  # noqa: BLE001
        out["structure_preserved"] = False
        out["structure_failures"] = [f"{type(exc).__name__}: {exc}"]
    return out


def aggregate_repairs(rows: list[dict]) -> dict[str, Any]:
    def rate(key: str) -> str:
        return f"{sum(1 for r in rows if r.get(key))}/{len(rows)}"
    by_kind: dict[str, list] = {}
    for r in rows:
        by_kind.setdefault(r.get("kind", "?"), []).append(r)
    gates = ("detected", "repaired", "structure_preserved")
    return {
        "n": len(rows),
        "overall": {g: rate(g) for g in gates},
        "by_kind": {k: {g: f"{sum(1 for r in v if r.get(g))}/{len(v)}" for g in gates}
                    for k, v in sorted(by_kind.items())},
    }
