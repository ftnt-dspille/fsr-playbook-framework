"""Inject deterministic, statically-detectable defects into a clean connector.

Each injector copies the connector dir to `dest`, breaks one thing, and returns
the defect descriptor (dir, kind, expect_codes, detail) or None when the source
has no suitable target. Every defect is caught by the connector toolkit's static
gates (no live install, no code execution needed to detect it):

  info_missing_field    -> INFO001  (drop a required info.json field)
  op_not_dispatched      -> OP002    (declared in info.json, cut from dispatch)
  verify_false           -> AP002    (TLS verification disabled in a request)

The injectors operate on files so they work on ANY connector, not just the
golden ones -- the same set can target a real ConnectorsV2 connector in a sweep.
"""
from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path


def _read_text(path: Path) -> str:
    """Read a connector source file with a latin-1 fallback -- real info.json and
    operations.py files on the box carry latin-1 bytes that break strict utf-8."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


#: Noise dirs never needed for the static gates; skipping them also dodges real
#: connectors' broken symlinks (e.g. jirav2's tests/.playwright-profile).
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "*.pyc", "node_modules", ".venv", "venv",
    "tests", ".playwright-profile", "dist", ".pytest_cache", ".mypy_cache", ".ruff_cache",
)


def _fresh_copy(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=_COPY_IGNORE, ignore_dangling_symlinks=True)
    return dest


def inject_info_missing_field(src: Path, dest: Path, field: str = "publisher") -> dict | None:
    """Drop a required top-level info.json field -> INFO001."""
    dest = _fresh_copy(src, dest)
    info_path = dest / "info.json"
    info = json.loads(_read_text(info_path))
    if field not in info:
        return None
    info.pop(field)
    info_path.write_text(json.dumps(info, indent=2))
    return {"dir": dest, "kind": "info_missing_field",
            "expect_codes": ["INFO001"],
            "detail": f"removed required info.json field {field!r}"}


def _dispatch_assign(tree: ast.Module) -> ast.Assign | None:
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in (
                        "operations", "OPERATIONS", "http_ops", "FUNCTION_MAP",
                        "operation_map", "ops_map"):
                    return n
    return None


def inject_op_not_dispatched(src: Path, dest: Path) -> dict | None:
    """Remove one op from the dispatch dict while leaving it declared in
    info.json -> OP002 (declared but not dispatched)."""
    dest = _fresh_copy(src, dest)
    ops_path = dest / "operations.py"
    try:
        tree = ast.parse(_read_text(ops_path))
    except SyntaxError:
        return None
    assign = _dispatch_assign(tree)
    if assign is None or len(assign.value.keys) < 2:
        return None
    d = assign.value
    # drop the LAST entry (deterministic), remember which op it was
    dropped_key = d.keys[-1]
    dropped = dropped_key.value if isinstance(dropped_key, ast.Constant) else None
    d.keys = d.keys[:-1]
    d.values = d.values[:-1]
    ops_path.write_text(ast.unparse(tree))
    return {"dir": dest, "kind": "op_not_dispatched",
            "expect_codes": ["OP002"],
            "detail": f"cut op {dropped!r} from the dispatch dict"}


class _VerifyFalse(ast.NodeTransformer):
    """Set the first request `verify=` keyword to the literal False."""

    def __init__(self):
        self.hit = False

    def visit_Call(self, node: ast.Call):  # noqa: N802
        self.generic_visit(node)
        if self.hit:
            return node
        for kw in node.keywords:
            if kw.arg == "verify" and not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is False):
                kw.value = ast.copy_location(ast.Constant(False), kw.value)
                self.hit = True
                break
        return node


def inject_verify_false(src: Path, dest: Path) -> dict | None:
    """Disable TLS verification in a request call -> AP002."""
    dest = _fresh_copy(src, dest)
    ops_path = dest / "operations.py"
    try:
        tree = ast.parse(_read_text(ops_path))
    except SyntaxError:
        return None
    tr = _VerifyFalse()
    tr.visit(tree)
    if not tr.hit:
        return None
    ops_path.write_text(ast.unparse(tree))
    return {"dir": dest, "kind": "verify_false",
            "expect_codes": ["AP002"],
            "detail": "set verify=False on a request call"}


INJECTORS = (inject_info_missing_field, inject_op_not_dispatched, inject_verify_false)


def make_defects(src: Path, work: Path) -> list[dict]:
    """Every defect that applies to this connector, one per injector that fit.
    Each broken copy lands in work/<connector>__<kind>/."""
    src = Path(src)
    out = []
    for inj in INJECTORS:
        kind = inj.__name__.replace("inject_", "")
        dest = Path(work) / f"{src.name}__{kind}"
        d = inj(src, dest)
        if d:
            d["injector"] = inj.__name__
            out.append(d)
    return out
