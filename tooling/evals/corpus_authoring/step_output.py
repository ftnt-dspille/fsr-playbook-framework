"""Real step-output shapes: the ground truth static checks can't know.

A downstream step that reads `vars.steps.<A>.<path>` depends on the runtime
SHAPE of step A's output. Any syntactically valid path compiles -- the compiler
cannot know what A actually returns -- so a plausible-but-wrong path
(`.data.macros` when `.data` is a flat list) passes every static gate and then
renders empty at run time, silently corrupting everything downstream. The only
authority on A's real shape is running A and looking.

This module captures that shape once (live), SANITIZES it to structure only
(keys/types/list-ness; scalar values and id-bearing keys dropped, so nothing
box-specific is committed), and then lets candidate references be graded offline
by rendering them against a representative sample built from the shape -- exactly
what debug_run does when it re-renders Jinja against a run's own vars.

Captured shapes live in golden/shapes/<connector>__<operation>.json and ARE
committed (sanitized). Capturing is a separate live step (capture_shape)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SHAPES_DIR = Path(__file__).resolve().parent / "golden" / "shapes"

# keys that carry a box-specific token (uuid / long hex suffix / epoch-ish id);
# genericized so a committed shape leaks no provenance.
_TOKEN = re.compile(r"[0-9a-fA-F]{8}[-_][0-9a-fA-F]{4}|_[0-9a-fA-F]{16,}|\d{10,}")


def _san_key(k: Any) -> str:
    s = str(k)
    return "<id>" if _TOKEN.search(s) else s


def shape_of(value: Any) -> Any:
    """A sanitized structural descriptor of a runtime value: scalar -> type
    name; list -> {__list_of__, __len__}; dict -> {key: shape}. Scalar VALUES
    are dropped (only their type is kept) and id-bearing keys are genericized,
    so the result carries structure, never box data."""
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
        return {_san_key(k): shape_of(v) for k, v in value.items()}
    return "unknown"


def sample_of(shape: Any) -> Any:
    """A representative concrete value for a shape, for rendering references
    against. Lists get >=1 element so an index/attr reference can be tried."""
    if shape == "str":
        return "sample"
    if shape == "int":
        return 1
    if shape == "float":
        return 1.0
    if shape == "bool":
        return True
    if shape == "null":
        return None
    if isinstance(shape, dict):
        if "__list_of__" in shape:
            n = max(1, min(int(shape.get("__len__") or 1), 2))
            return [sample_of(shape["__list_of__"]) for _ in range(n)]
        return {k: sample_of(v) for k, v in shape.items()}
    return "x"


def _render(expr: str, ctx: dict) -> str:
    try:
        import jinja2
        env = jinja2.Environment(undefined=jinja2.ChainableUndefined)
        return env.from_string(expr).render(**ctx)
    except Exception:
        return ""


_JINJA_BLOCK = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def reference_resolves(expr: str, step_shapes: dict[str, Any]) -> bool:
    """True if every Jinja expression embedded in `expr` renders to a non-empty
    value against samples built from the given step output shapes. Each embedded
    `{{ ... }}` is rendered in ISOLATION so surrounding literal text (e.g. a
    'First open alert: ' prefix) can't mask an expression that renders empty --
    an empty render is runtime-broken even though it compiled."""
    ctx = {"vars": {"steps": {name: sample_of(shape)
                              for name, shape in step_shapes.items()}}}
    blocks = _JINJA_BLOCK.findall(expr) or [expr]
    for block in blocks:
        out = _render(block, ctx)
        if not (out and out.strip() and out.strip() != "None"):
            return False
    return True


def load_shape(connector: str, operation: str) -> dict[str, Any] | None:
    f = SHAPES_DIR / f"{connector}__{operation}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def save_shape(connector: str, operation: str, raw_output: Any,
               note: str = "") -> Path:
    """Sanitize a captured raw output to a committed shape fixture."""
    SHAPES_DIR.mkdir(parents=True, exist_ok=True)
    f = SHAPES_DIR / f"{connector}__{operation}.json"
    f.write_text(json.dumps(
        {"connector": connector, "operation": operation,
         "shape": shape_of(raw_output), "note": note}, indent=2))
    return f
