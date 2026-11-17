"""Validator core: AST helpers, Issue dataclass, runner."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass
class Issue:
    code: str            # stable identifier (e.g. "OP001")
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None
    context: dict = field(default_factory=dict)

    def fmt(self) -> str:
        loc = ""
        if self.file:
            loc = f"{self.file}"
            if self.line is not None:
                loc += f":{self.line}"
            loc = f"  ({loc})"
        return f"  [{self.severity.value.upper():5}] {self.code}  {self.message}{loc}"


@dataclass
class ConnectorCtx:
    """Parsed view of a connector directory passed to each check."""
    root: Path
    info: dict
    info_path: Path
    operations_py: Path | None
    operations_tree: ast.Module | None
    operations_src: str | None
    connector_py: Path | None
    connector_tree: ast.Module | None
    connector_src: str | None

    @property
    def name(self) -> str:
        return self.info.get("name") or self.root.name


def _read_text(path: Path) -> str:
    """Read a connector source file. FortiSOAR loads connector sources as latin-1
    on the box, and real info.json/operations.py files carry latin-1 bytes (e.g.
    a (R) sign), so fall back to latin-1 rather than crashing on invalid utf-8."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _parse(path: Path) -> tuple[ast.Module | None, str | None]:
    if not path.exists():
        return None, None
    try:
        src = _read_text(path)
        return ast.parse(src), src
    except (OSError, SyntaxError):
        return None, None


def load_connector(root: Path) -> tuple[ConnectorCtx | None, list[Issue]]:
    issues: list[Issue] = []
    info_path = root / "info.json"
    if not info_path.exists():
        issues.append(Issue("PKG001", Severity.ERROR, "info.json not found", file=str(root)))
        return None, issues
    try:
        info = json.loads(_read_text(info_path))
    except json.JSONDecodeError as e:
        issues.append(Issue("PKG002", Severity.ERROR, f"info.json invalid JSON: {e}", file=str(info_path)))
        return None, issues

    ops_path = root / "operations.py"
    conn_path = root / "connector.py"
    ops_tree, ops_src = _parse(ops_path)
    conn_tree, conn_src = _parse(conn_path)
    if not ops_path.exists():
        issues.append(Issue("PKG003", Severity.ERROR, "operations.py not found", file=str(root)))
    if not conn_path.exists():
        issues.append(Issue("PKG004", Severity.ERROR, "connector.py not found", file=str(root)))
    if ops_path.exists() and ops_tree is None:
        issues.append(Issue("PKG005", Severity.ERROR, "operations.py has syntax error", file=str(ops_path)))
    if conn_path.exists() and conn_tree is None:
        issues.append(Issue("PKG006", Severity.ERROR, "connector.py has syntax error", file=str(conn_path)))

    ctx = ConnectorCtx(
        root=root,
        info=info,
        info_path=info_path,
        operations_py=ops_path if ops_path.exists() else None,
        operations_tree=ops_tree,
        operations_src=ops_src,
        connector_py=conn_path if conn_path.exists() else None,
        connector_tree=conn_tree,
        connector_src=conn_src,
    )
    return ctx, issues


def validate_connector(root: Path) -> list[Issue]:
    from .checks import ALL_CHECKS
    ctx, issues = load_connector(root)
    if ctx is None:
        return issues
    for check in ALL_CHECKS:
        try:
            issues.extend(check(ctx))
        except Exception as e:  # never let a check crash the run
            issues.append(Issue(
                "CHK999", Severity.WARN,
                f"check {check.__name__!r} crashed: {type(e).__name__}: {e}",
                file=str(ctx.root),
            ))
    # stable ordering: file, line, code
    issues.sort(key=lambda i: (i.file or "", i.line or 0, i.code))
    return issues


# ----------------- AST helpers shared by checks ----------------------------

def module_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def find_assign(tree: ast.Module, name: str) -> ast.Assign | None:
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return n
    return None


def find_dispatch_dict(tree: ast.Module) -> tuple[str | None, dict[str, str] | None, int | None]:
    """Find the operation→function dispatch dict.

    Looks for: <name> = { '<op>': <func>, ... } where every value is a Name node.
    Tries common identifiers, then falls back to any dict-of-Name top-level assignment.
    Returns (dict_var_name, {op_name: func_name}, lineno).
    """
    candidates = ("operations", "OPERATIONS", "http_ops", "FUNCTION_MAP", "operation_map", "ops_map")
    for var in candidates:
        a = find_assign(tree, var)
        if a is None:
            continue
        mapping = _assign_to_str_to_name(a)
        if mapping is not None:
            return var, mapping, a.lineno
    # Fallback: any top-level dict literal where all values are Names
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    mapping = _assign_to_str_to_name(n)
                    if mapping:
                        return t.id, mapping, n.lineno
    return None, None, None


def _assign_to_str_to_name(a: ast.Assign) -> dict[str, str] | None:
    if not isinstance(a.value, ast.Dict):
        return None
    out: dict[str, str] = {}
    for k, v in zip(a.value.keys, a.value.values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            return None
        if isinstance(v, ast.Name):
            out[k.value] = v.id
        elif isinstance(v, ast.Attribute):
            out[k.value] = v.attr
        else:
            return None
    return out


# --------------------------------------------------------------------------
# Robust dispatch resolution (handles the construction variety real connectors
# show: incremental registration, .update() from another module, generic
# info.json-driven dispatch, dicts in __init__/execute, star imports). The
# guiding rule, learned the hard way on playbooks: when the real wiring can't be
# resolved statically, DEGRADE (mark it indirect and don't fire a hard "missing
# op" error) rather than false-positive.

_DISPATCH_NAMES = (
    "operations", "OPERATIONS", "http_ops", "FUNCTION_MAP", "operation_map",
    "ops_map", "supported_operation", "supported_operations",
)


@dataclass
class Dispatch:
    mapping: dict[str, str]   # resolved {op_name: func_name} (may be partial)
    lineno: int | None
    found: bool               # a dispatch mechanism was located at all
    indirect: bool            # registration we cannot fully resolve statically
    location: str             # "operations" | "connector" | "none"


def _dict_entries(d: ast.Dict) -> tuple[dict[str, str], bool]:
    """Resolve a dict literal to {str_key: func_name}; second value is True when
    some entry could not be resolved (a ** spread, a non-str key, or a value that
    is not a plain Name/Attribute)."""
    out: dict[str, str] = {}
    unresolved = False
    for k, v in zip(d.keys, d.values):
        if k is None:  # {**OTHER}
            unresolved = True
            continue
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            unresolved = True
            continue
        if isinstance(v, ast.Name):
            out[k.value] = v.id
        elif isinstance(v, ast.Attribute):
            out[k.value] = v.attr
        else:
            unresolved = True
    return out, unresolved


def _target_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for t in getattr(node, "targets", []) or ([node.target] if getattr(node, "target", None) else []):
        if isinstance(t, ast.Name):
            out.add(t.id)
        elif isinstance(t, ast.Attribute):
            out.add(t.attr)  # self.supported_operations -> "supported_operations"
    return out


def _pick_dispatch_dict(tree: ast.Module) -> tuple[str | None, ast.Dict | None, int | None]:
    """Best dict-of-handlers anywhere in the tree (module level, or in a method as
    a local or self.<x>). Prefers a conventional name, else the dict literal with
    the most string->Name/Attribute entries."""
    best: tuple[int, str | None, ast.Dict | None, int | None] = (-1, None, None, None)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        names = _target_names(node)
        entries, _ = _dict_entries(value)
        # keep an EMPTY dict only when it carries a conventional dispatch name --
        # it is the `operations = {}` later filled by `operations['x'] = fn`.
        if not entries and not (names & set(_DISPATCH_NAMES)):
            continue
        score = len(entries) + (100 if names & set(_DISPATCH_NAMES) else 0)
        if score > best[0]:
            var = next(iter(names & set(_DISPATCH_NAMES)), next(iter(names), None))
            best = (score, var, value, node.lineno)
    return best[1], best[2], best[3]


def _augment_incremental(tree: ast.Module, var: str) -> tuple[dict[str, str], bool]:
    """Collect `var['x'] = fn` (and `self.var['x'] = fn`) registrations and detect
    `var.update(...)` indirection."""
    extra: dict[str, str] = {}
    indirect = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if (isinstance(t, ast.Subscript) and _subscript_on(t.value, var)
                    and isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str)):
                v = node.value
                if isinstance(v, ast.Name):
                    extra[t.slice.value] = v.id
                elif isinstance(v, ast.Attribute):
                    extra[t.slice.value] = v.attr
                else:
                    indirect = True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "update" and _subscript_on(node.func.value, var):
            indirect = True
    return extra, indirect


def _subscript_on(node: ast.AST, var: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == var) or (
        isinstance(node, ast.Attribute) and node.attr == var)


def _has_star_import(tree: ast.Module) -> bool:
    return any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
               for n in ast.walk(tree))


def module_bound_names(tree: ast.Module) -> set[str]:
    """Every name bound at module level: functions, classes, imports (the common
    `from .x import handler` per-op pattern), and plain assignments. A dispatch
    target is 'exists' when it is bound here, not only when it is a local def."""
    out: set[str] = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
    return out


def resolve_dispatch(ctx: ConnectorCtx) -> Dispatch:
    """Locate the operation dispatch across operations.py and connector.py,
    resolving as much as possible and flagging when it is indirect."""
    mapping: dict[str, str] = {}
    lineno = None
    indirect = False
    location = "none"
    for tree, loc in ((ctx.operations_tree, "operations"), (ctx.connector_tree, "connector")):
        if tree is None:
            continue
        var, d, ln = _pick_dispatch_dict(tree)
        if d is None:
            if _has_star_import(tree) and loc == "operations":
                indirect = True  # handler names likely come via `import *`
            continue
        entries, unresolved = _dict_entries(d)
        mapping.update(entries)
        indirect = indirect or unresolved or _has_star_import(tree)
        if var:
            inc, upd = _augment_incremental(tree, var)
            mapping.update(inc)
            indirect = indirect or upd
        lineno = ln
        location = loc
        break
    return Dispatch(mapping, lineno, bool(mapping) or location != "none", indirect, location)
