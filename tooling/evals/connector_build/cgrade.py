"""Grade a built or repaired connector against the connector domain gates.

Box-free and no code execution: the ONLY graders used are the static AST/JSON
checks `fsr_playbooks.connectors.validate_connector` (INFO*/OP*/IMP*/PKG*/ERR*/
PARAM*) and `fsr_playbooks.connectors.scan` (AP0*). The execute-the-op graders
(request_body_lint, lint.replay, generated scaffold tests) are deliberately NOT
used -- running an agent's unverified operations.py is a separate, opt-in,
sandboxed tier.

The static core lives in the domain layer (fsr_playbooks.connectors), so grading
needs no external package or PYTHONPATH -- it imports from the framework itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# A defect is keyed by (code, filename-basename), NOT the absolute path: a clean
# original, its broken copy and the agent's repair live in different directories,
# so an absolute path would never match across them. Basename + code still
# isolates "this defect, in this file" from unrelated pre-existing findings.
Defect = tuple[str, str]


def _toolkit():
    # The connector static-validation core now lives in the domain layer
    # (fsr_playbooks.connectors), folded in from the standalone toolkit.
    from fsr_playbooks.connectors import Severity, scan, validate_connector
    return validate_connector, scan, Severity


def _files_present(root: Path) -> dict[str, bool]:
    return {
        "info.json": (root / "info.json").is_file(),
        "operations.py": (root / "operations.py").is_file(),
        "connector.py": (root / "connector.py").is_file(),
    }


def defects(root: Path) -> set[Defect]:
    """The connector's hard defects: every ERROR-severity lint Issue plus every
    antipattern Finding, keyed (code, basename). WARN-level lint is advisory and
    left out so the delta isolates real breakage."""
    validate_connector, scan, Severity = _toolkit()
    out: set[Defect] = set()
    for i in validate_connector(root):
        if i.severity == Severity.ERROR:
            out.add((i.code, Path(i.file).name if i.file else ""))
    for f in scan(root):
        out.add((f.code, "operations.py"))
    return out


def grade_build(root: Path) -> dict[str, Any]:
    """Grade a from-scratch build: files present, no hard defects."""
    root = Path(root)
    present = _files_present(root)
    built = all(present.values())
    dset = defects(root) if present["info.json"] else {("PKG001", "")}
    out = {
        "built": built,
        "files_present": present,
        "defects": sorted(dset),
        "lint_clean": not dset,
        "passed": bool(built and not dset),
    }
    return out


def grade_fix(clean_root: Path, broken_root: Path, repaired_root: Path | None,
              expect_codes: list[str] | None = None) -> dict[str, Any]:
    """Grade a repair by (code, file) DELTA against the clean original.

      detected   -- the injected defect is statically visible on the broken copy
                    (sanity: a diagnosis has something true to find)
      repaired   -- the repaired connector still has all three files AND none of
                    the introduced defect pairs remain
      no_regression -- the repair introduced no NEW hard defect beyond baseline
    """
    expect = set(expect_codes or [])
    baseline = defects(Path(clean_root))
    broken = defects(Path(broken_root))
    introduced = broken - baseline
    detected = any(code in expect for code, _ in introduced) if expect else bool(introduced)

    out: dict[str, Any] = {
        "detected": detected,
        "introduced": sorted(introduced),
    }
    if repaired_root is None or not Path(repaired_root).exists():
        out.update(repaired=False, no_regression=False, detail="no repair produced")
        return out

    present = _files_present(Path(repaired_root))
    rep = defects(Path(repaired_root)) if present["info.json"] else {("PKG001", "")}
    defect_gone = not (introduced & rep)
    out["remaining_introduced"] = sorted(introduced & rep)
    out["new_defects"] = sorted(rep - baseline - introduced)
    out["repaired"] = bool(all(present.values()) and defect_gone)
    out["no_regression"] = not out["new_defects"]
    return out


def aggregate(rows: list[dict], gates: tuple[str, ...]) -> dict[str, Any]:
    def rate(key: str) -> str:
        return f"{sum(1 for r in rows if r.get(key))}/{len(rows)}" if rows else "0/0"
    return {"n": len(rows), "overall": {g: rate(g) for g in gates}}
