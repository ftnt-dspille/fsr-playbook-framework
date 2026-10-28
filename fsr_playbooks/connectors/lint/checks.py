"""Static checks for FortiSOAR connectors.

Each check: (ctx: ConnectorCtx) -> Iterable[Issue].
Codes are grouped:
    PKG  - package-level (files, schema)
    INFO - info.json semantics
    OP   - operation dispatch + signatures
    IMP  - imports
    HEALTH - check_health
    ERR  - error handling
    PARAM - parameter usage
"""
from __future__ import annotations

import ast
from collections.abc import Iterable

from .runner import (
    ConnectorCtx,
    Issue,
    Severity,
    find_dispatch_dict,
    module_bound_names,
    module_level_functions,
    resolve_dispatch,
)


def _is_generic_dispatch(ctx: ConnectorCtx) -> bool:
    """True when info.json drives dispatch generically (each op carries its own
    handler_method / endpoint+http_method), so there is no per-op function to find
    in a dict -- e.g. fortiedr. Firing 'op not dispatched' here is a false positive."""
    ops = [o for o in (ctx.info.get("operations") or []) if isinstance(o, dict)]
    if not ops:
        return False
    generic = sum(1 for o in ops
                  if o.get("handler_method") or (o.get("endpoint") and o.get("http_method")))
    return generic >= max(1, len(ops) // 2)


# --------------------------- INFO.json -------------------------------------

REQUIRED_INFO_FIELDS = ("name", "label", "version", "publisher")

def check_info_required_fields(ctx: ConnectorCtx) -> Iterable[Issue]:
    for f in REQUIRED_INFO_FIELDS:
        if not ctx.info.get(f):
            yield Issue("INFO001", Severity.ERROR, f"info.json missing required field {f!r}", file=str(ctx.info_path))


def check_info_operations_shape(ctx: ConnectorCtx) -> Iterable[Issue]:
    ops = ctx.info.get("operations") or []
    if not isinstance(ops, list):
        yield Issue("INFO002", Severity.ERROR, "info.json 'operations' must be a list", file=str(ctx.info_path))
        return
    if not ops:
        yield Issue("INFO003", Severity.WARN, "info.json declares zero operations", file=str(ctx.info_path))
        return
    seen: set[str] = set()
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            yield Issue("INFO004", Severity.ERROR, f"operations[{i}] is not an object", file=str(ctx.info_path))
            continue
        name = op.get("operation")
        if not name or not isinstance(name, str):
            yield Issue("INFO005", Severity.ERROR, f"operations[{i}] missing 'operation' (machine name)", file=str(ctx.info_path))
            continue
        if name in seen:
            yield Issue("INFO006", Severity.ERROR, f"duplicate operation name {name!r}", file=str(ctx.info_path))
        seen.add(name)
        if not op.get("title"):
            yield Issue("INFO007", Severity.WARN, f"operation {name!r} missing 'title'", file=str(ctx.info_path))
        params = op.get("parameters") or []
        if not isinstance(params, list):
            yield Issue("INFO008", Severity.ERROR, f"operation {name!r} 'parameters' must be a list", file=str(ctx.info_path))
            continue
        for j, p in enumerate(params):
            if not isinstance(p, dict):
                yield Issue("INFO009", Severity.ERROR, f"op {name!r} parameters[{j}] is not an object", file=str(ctx.info_path))
                continue
            if not p.get("name"):
                yield Issue("INFO010", Severity.ERROR, f"op {name!r} parameters[{j}] missing 'name'", file=str(ctx.info_path))
            if not p.get("type"):
                yield Issue("INFO011", Severity.WARN, f"op {name!r} parameter {p.get('name')!r} missing 'type'", file=str(ctx.info_path))


# --------------------------- DISPATCH --------------------------------------

def check_dispatch_dict_present(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.operations_tree is None and ctx.connector_tree is None:
        return
    if _is_generic_dispatch(ctx):
        return  # info.json-driven generic dispatch: no dict expected
    disp = resolve_dispatch(ctx)
    if not disp.found:
        yield Issue("OP001", Severity.ERROR,
                    "no operation dispatch found (expected `operations = {...}` or similar, "
                    "incremental registration, or info.json handler_method/endpoint dispatch)",
                    file=str(ctx.operations_py or ctx.connector_py or ctx.root))


def check_dispatch_covers_info(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.operations_tree is None and ctx.connector_tree is None:
        return
    if _is_generic_dispatch(ctx):
        return
    disp = resolve_dispatch(ctx)
    if not disp.found or disp.indirect:
        # indirect registration (.update from another module, ** spread, star
        # imports) can't be resolved statically -- degrade rather than falsely
        # reporting every op as unimplemented.
        return
    where = str(ctx.operations_py if disp.location == "operations" else ctx.connector_py)
    declared = {op.get("operation") for op in (ctx.info.get("operations") or [])
                if isinstance(op, dict) and op.get("operation")}
    dispatched = set(disp.mapping.keys())
    for missing in sorted(declared - dispatched):
        yield Issue("OP002", Severity.ERROR,
                    f"info.json declares op {missing!r} but it is not in the dispatch",
                    file=where, line=disp.lineno,
                    context={"declared_in_info": True, "in_dispatch": False})
    for extra in sorted(dispatched - declared):
        yield Issue("OP003", Severity.WARN,
                    f"dispatch has op {extra!r} not declared in info.json",
                    file=where, line=disp.lineno,
                    context={"declared_in_info": False, "in_dispatch": True})


def check_dispatch_targets_exist(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.operations_tree is None:
        return
    disp = resolve_dispatch(ctx)
    # only meaningful when the handlers should be top-level functions in
    # operations.py; a dict resolved from connector.py or indirect registration
    # points elsewhere.
    if not disp.found or disp.indirect or disp.location != "operations":
        return
    bound = module_bound_names(ctx.operations_tree)
    for op_name, func_name in disp.mapping.items():
        if func_name not in bound:
            yield Issue("OP004", Severity.ERROR,
                        f"op {op_name!r} dispatches to {func_name!r} which is not defined or "
                        f"imported at module level in operations.py",
                        file=str(ctx.operations_py), line=disp.lineno)


def check_handler_signature(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.operations_tree is None:
        return
    disp = resolve_dispatch(ctx)
    if not disp.found or disp.indirect or disp.location != "operations":
        return
    funcs = module_level_functions(ctx.operations_tree)
    for op_name, func_name in disp.mapping.items():
        fn = funcs.get(func_name)
        if fn is None:
            continue  # OP004 already fired
        args = fn.args.args
        if len(args) < 2:
            yield Issue("OP005", Severity.ERROR,
                        f"handler {func_name!r} for op {op_name!r} should accept at least (config, params)",
                        file=str(ctx.operations_py), line=fn.lineno)


# --------------------------- PARAM USAGE ----------------------------------

def _params_arg_name(fn: ast.FunctionDef) -> str | None:
    args = fn.args.args
    if len(args) >= 2:
        return args[1].arg  # second positional is the params dict
    return None


def _receiver_is_params(node: ast.AST, params_arg: str) -> bool:
    """Detect params, (params or {}), (params or other_dict)."""
    if isinstance(node, ast.Name) and node.id == params_arg:
        return True
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_receiver_is_params(v, params_arg) for v in node.values)
    if isinstance(node, ast.IfExp):
        return _receiver_is_params(node.body, params_arg) or _receiver_is_params(node.orelse, params_arg)
    return False


def _keys_read_in(fn: ast.FunctionDef, params_arg: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(fn):
        # params['x'] (and (params or {})['x'])
        if isinstance(node, ast.Subscript) and _receiver_is_params(node.value, params_arg):
            slc = node.slice
            if isinstance(slc, ast.Constant) and isinstance(slc.value, str):
                keys.add(slc.value)
        # params.get('x') / (params or {}).get('x') etc.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if _receiver_is_params(node.func.value, params_arg) and node.func.attr in {"get", "pop", "setdefault"}:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    keys.add(node.args[0].value)
    return keys


def _collect_params_keys(
    fn: ast.FunctionDef,
    params_arg: str,
    module_funcs: dict[str, ast.FunctionDef],
    depth: int = 1,
) -> set[str]:
    """Keys read from the params dict in this handler, plus one hop into module-local callees
    that receive the params dict positionally."""
    keys = _keys_read_in(fn, params_arg)
    if depth <= 0:
        return keys
    # Find module-local calls that pass params (positional or **params)
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        callee_name = node.func.id if isinstance(node.func, ast.Name) else None
        if callee_name is None or callee_name not in module_funcs:
            continue
        # Detect positional position where `params_arg` is passed
        callee = module_funcs[callee_name]
        forwarded_as: str | None = None
        for i, arg in enumerate(node.args):
            if isinstance(arg, ast.Name) and arg.id == params_arg:
                if i < len(callee.args.args):
                    forwarded_as = callee.args.args[i].arg
                break
        # Also: **params forwarding doesn't apply (we want dict access, not kwargs)
        if forwarded_as:
            keys |= _collect_params_keys(callee, forwarded_as, module_funcs, depth=depth - 1)
    return keys


def check_required_params_referenced(ctx: ConnectorCtx) -> Iterable[Issue]:
    """Every required parameter declared in info.json should be read from the params dict somewhere in its handler."""
    if ctx.operations_tree is None:
        return
    var, mapping, _ = find_dispatch_dict(ctx.operations_tree)
    if mapping is None:
        return
    funcs = module_level_functions(ctx.operations_tree)
    info_ops = {op.get("operation"): op for op in (ctx.info.get("operations") or []) if isinstance(op, dict)}
    for op_name, func_name in mapping.items():
        fn = funcs.get(func_name)
        if fn is None:
            continue
        params_arg = _params_arg_name(fn)
        if not params_arg:
            continue
        info_op = info_ops.get(op_name)
        if not info_op:
            continue
        required = [
            p.get("name")
            for p in (info_op.get("parameters") or [])
            if isinstance(p, dict) and p.get("required") and p.get("name")
        ]
        if not required:
            continue
        used = _collect_params_keys(fn, params_arg, funcs, depth=2)
        # Heuristic: if the handler passes the required param's NAME as a string literal
        # to a module-local helper, assume the helper looks it up dynamically.
        literal_names_in_handler: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal_names_in_handler.add(node.value)
        for k in required:
            if k in used:
                continue
            if k in literal_names_in_handler:
                continue  # passed by name to a helper -- likely dynamic lookup
            yield Issue("PARAM001", Severity.WARN,
                        f"op {op_name!r}: required parameter {k!r} declared in info.json is never read from {params_arg!r} in {func_name}()",
                        file=str(ctx.operations_py), line=fn.lineno)


# --------------------------- IMPORTS ---------------------------------------

CYOPS_BAD_IMPORTS = ("cyops_utilities.builtins", "cyops_utilities")
CYOPS_GOOD_PREFIX = "connectors.cyops_utilities"


def _imports(tree: ast.Module) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.append((n.module, n.lineno))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.append((a.name, n.lineno))
    return out


def check_cyops_import_path(ctx: ConnectorCtx) -> Iterable[Issue]:
    for tree, path in [
        (ctx.operations_tree, ctx.operations_py),
        (ctx.connector_tree, ctx.connector_py),
    ]:
        if tree is None:
            continue
        for mod, lineno in _imports(tree):
            if mod == "cyops_utilities.builtins" or mod == "cyops_utilities":
                yield Issue("IMP001", Severity.ERROR,
                            f"import {mod!r} will fail at runtime; use 'from connectors.cyops_utilities.builtins import ...'",
                            file=str(path), line=lineno)


def check_connector_base_import(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.connector_tree is None:
        return
    mods = {m for m, _ in _imports(ctx.connector_tree)}
    if "connectors.core.connector" not in mods:
        yield Issue("IMP002", Severity.ERROR,
                    "connector.py must import from 'connectors.core.connector' (Connector, get_logger, ConnectorError)",
                    file=str(ctx.connector_py))


# --------------------------- CONNECTOR class ------------------------------

def _find_connector_class(tree: ast.Module) -> ast.ClassDef | None:
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            for base in n.bases:
                if isinstance(base, ast.Name) and base.id == "Connector":
                    return n
                if isinstance(base, ast.Attribute) and base.attr == "Connector":
                    return n
    return None


def check_connector_class(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.connector_tree is None:
        return
    cls = _find_connector_class(ctx.connector_tree)
    if cls is None:
        yield Issue("PKG010", Severity.ERROR,
                    "connector.py defines no class inheriting from Connector",
                    file=str(ctx.connector_py))
        return
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    if "execute" not in methods:
        yield Issue("PKG011", Severity.ERROR,
                    f"class {cls.name} is missing an execute() method",
                    file=str(ctx.connector_py), line=cls.lineno)
    if "check_health" not in methods:
        yield Issue("PKG012", Severity.ERROR,
                    f"class {cls.name} is missing a check_health() method",
                    file=str(ctx.connector_py), line=cls.lineno)


def check_check_health_function(ctx: ConnectorCtx) -> Iterable[Issue]:
    if ctx.operations_tree is None:
        return
    funcs = module_level_functions(ctx.operations_tree)
    if not ({"check_health", "_check_health"} & funcs.keys()):
        yield Issue("HEALTH001", Severity.WARN,
                    "operations.py has no module-level check_health() or _check_health() function",
                    file=str(ctx.operations_py))


# --------------------------- ERROR HANDLING -------------------------------

def check_raises_connector_error(ctx: ConnectorCtx) -> Iterable[Issue]:
    """Warn when handlers raise bare Exception/RuntimeError instead of ConnectorError."""
    if ctx.operations_tree is None:
        return
    bad_types = {"Exception", "RuntimeError", "ValueError"}
    for fn in module_level_functions(ctx.operations_tree).values():
        for node in ast.walk(fn):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                fn_called = node.exc.func
                name = fn_called.id if isinstance(fn_called, ast.Name) else (
                    fn_called.attr if isinstance(fn_called, ast.Attribute) else None
                )
                if name in bad_types:
                    yield Issue("ERR001", Severity.WARN,
                                f"{fn.name}() raises {name} on line {node.lineno}; prefer ConnectorError so FSR surfaces a clean error",
                                file=str(ctx.operations_py), line=node.lineno)


# --------------------------- ALL_CHECKS ------------------------------------

ALL_CHECKS = (
    check_info_required_fields,
    check_info_operations_shape,
    check_dispatch_dict_present,
    check_dispatch_covers_info,
    check_dispatch_targets_exist,
    check_handler_signature,
    check_required_params_referenced,
    check_cyops_import_path,
    check_connector_base_import,
    check_connector_class,
    check_check_health_function,
    check_raises_connector_error,
)
