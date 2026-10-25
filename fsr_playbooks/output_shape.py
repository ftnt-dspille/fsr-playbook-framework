"""Inspect what a step actually returns, so references to it can be checked.

The compiler already knows the output shape of NATIVE steps (find_record,
set_variable, ...) and statically rejects a reference to a field those outputs
do not have (jinja_typing / missing_field_on_step_output). It cannot know the
output of a CONNECTOR operation -- that shape is defined by the connector at run
time -- so a downstream reference like `vars.steps.Enrich.data.verdict` compiles
for any path and only renders empty if the real output has no such field. That
is the one step-output bug class static analysis cannot catch, and debug_run
cannot catch it either: it reads a FAILED run, but an empty render does not fail
the run, it just leaves the field blank.

This module closes that gap. `probe_output` runs a connector operation once and
`shape_of` reduces its real result to a structural descriptor; `suggest_references`
turns that shape into the concrete, resolvable reference paths an author should
use (indexing a list, joining it, iterating it). An agent that has guessed a
reference can probe the op and see what actually resolves, instead of shipping a
silently-empty playbook.

Pure except for `probe_output`, which takes a pyfsr-style client and executes a
real operation.
"""
from __future__ import annotations

from typing import Any

Shape = Any  # "str" | "int" | ... | {"__list_of__": Shape, "__len__": int} | {key: Shape}


def shape_of(value: Any) -> Shape:
    """A structural descriptor of a runtime value: scalars become their type
    name, a list becomes {__list_of__, __len__}, a dict becomes {key: shape}."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return {"__list_of__": shape_of(value[0]) if value else "unknown",
                "__len__": len(value)}
    if isinstance(value, dict):
        return {str(k): shape_of(v) for k, v in value.items()}
    return "unknown"


def _is_list(shape: Shape) -> bool:
    return isinstance(shape, dict) and "__list_of__" in shape


def suggest_references(shape: Shape, root: str, _depth: int = 0) -> list[dict[str, str]]:
    """Concrete, resolvable reference paths into an output of this shape, each
    with a short note. `root` is the base expression, e.g.
    'vars.steps.Enrich'. Guides an author to a path that renders non-empty."""
    out: list[dict[str, str]] = []
    if _depth > 4:
        return out
    if _is_list(shape):
        elem = shape["__list_of__"]
        if isinstance(elem, dict) and not _is_list(elem):
            # list of records: index one, or iterate; never `root.field` (empty).
            out.append({"path": f"{root}[0]", "note": "first item (output is a LIST)"})
            for field in list(elem)[:6]:
                out.append({"path": f"{root}[0].{field}",
                            "note": f"{field} of the first item"})
            out.append({"path": root, "note": "the whole list -- iterate with for_each"})
        else:
            out.append({"path": f"{root} | join(', ')",
                        "note": "output is a list of scalars; join for a string"})
            out.append({"path": f"{root}[0]", "note": "first item"})
            out.append({"path": f"{root} | length", "note": "how many"})
        return out
    if isinstance(shape, dict):
        for key, sub in list(shape.items())[:8]:
            out.extend(suggest_references(sub, f"{root}.{key}", _depth + 1))
        if not out:
            out.append({"path": root, "note": "object (no scalar leaves)"})
        return out
    out.append({"path": root, "note": f"scalar ({shape})"})
    return out


def describe_output(value: Any, root: str) -> dict[str, Any]:
    """Shape + resolvable reference suggestions for a captured output value."""
    shape = shape_of(value)
    return {"shape": shape, "is_list": _is_list(shape),
            "suggested_references": suggest_references(shape, root)}


def _from_grounded(shape: Any) -> Shape:
    """Convert a grounded-store Shape ({"kind": ...}) to this module's shape
    vocabulary, so suggest_references can walk a shape read from the oracle."""
    if not isinstance(shape, dict):
        return "unknown"
    kind = shape.get("kind")
    if kind == "scalar":
        t = shape.get("type")
        return {"string": "str", "integer": "int", "float": "float",
                "boolean": "bool", "null": "null"}.get(t, "str")
    if kind == "list":
        return {"__list_of__": _from_grounded(shape.get("item")), "__len__": 1}
    if kind == "object":
        return {k: _from_grounded(v) for k, v in (shape.get("keys") or {}).items()}
    return "unknown"


def grounded_help(connector: str, operation: str, step_name: str | None = None,
                  store_path: Any = None) -> dict[str, Any]:
    """Resolvable reference paths into a connector op's output, from the grounded
    shape oracle -- the answer to 'I wrote vars.steps.X.<path> and it renders
    empty; what actually resolves?'. Offline: reads the recorded shape, runs
    nothing. When the op is not grounded, says so (its shape is unknown to static
    checks) rather than guessing."""
    from pathlib import Path

    from fsr_playbooks.compiler.grounded_shapes import GroundedShapeStore

    root = f"vars.steps.{(step_name or '<step>').replace(' ', '_')}"
    if store_path is None:
        store_path = Path(__file__).resolve().parent / "_data" / "grounded_shapes.json"
    try:
        shape = GroundedShapeStore.load(Path(store_path)).shape_for(connector, operation)
    except Exception:  # noqa: BLE001
        shape = None
    if not isinstance(shape, dict):
        return {"grounded": False, "connector": connector, "operation": operation,
                "message": (f"{connector}.{operation} is not grounded: its output shape "
                            "is unknown to static checks. Reference it via "
                            f"{root}.data and confirm against a real run (debug_run), "
                            "or ground the op so the shape is known.")}
    # the op output lives under the envelope's `.data`; root suggestions there.
    data = (shape.get("keys") or {}).get("data")
    out_shape = _from_grounded(data if isinstance(data, dict) else shape)
    base = f"{root}.data" if isinstance(data, dict) else root
    refs = suggest_references(out_shape, base)
    return {"grounded": True, "connector": connector, "operation": operation,
            "is_list": isinstance(out_shape, dict) and "__list_of__" in out_shape,
            "shape": out_shape, "suggested_references": refs}


def probe_output(client: Any, connector: str, operation: str,
                 params: dict | None = None, config: str | None = None,
                 root: str | None = None) -> dict[str, Any]:
    """Run a connector operation once and describe its REAL output shape.

    Returns {ok, shape, is_list, suggested_references, raw_keys} or
    {ok: False, error}. `root` defaults to a step reference placeholder so the
    suggested paths read like the ones an author writes.
    """
    root = root or f"vars.steps.<{operation}_step>"
    try:
        res = client.connectors.execute(connector=connector, operation=operation,
                                         params=params or {}, config=config)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    # pyfsr returns a typed ExecuteResult, not a dict -- normalize it (the
    # `isinstance(x, dict)` gotcha). model_dump() gives {operation,status,message,data}.
    if not isinstance(res, dict) and hasattr(res, "model_dump"):
        res = res.model_dump()
    # connector results usually arrive as {status, message, data: <payload>};
    # describe the whole envelope and also surface the `data` payload directly.
    payload = res.get("data") if isinstance(res, dict) and "data" in res else res
    desc = describe_output(payload, f"{root}.data" if isinstance(res, dict) and "data" in res else root)
    return {"ok": True, "raw_keys": sorted(res) if isinstance(res, dict) else None,
            **desc}
