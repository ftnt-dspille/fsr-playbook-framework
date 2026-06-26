"""Grounded output-shape oracle (pilot gap D).

The typed walker synthesizes a `Shape` for each step so it can validate
`vars.steps.<step>.<path>` references. For connector ops it can only do this
when a `ProbeCallback` supplies the shape — otherwise the op degrades to
`{kind: unknown}` and every downstream reference goes unchecked. The pilot's E5
(`output.data.code_output` vs `data.code_output`) is exactly the failure that
slips through when the output shape is *inferred or unknown* rather than
**measured from a real run**.

This module closes that gap by deriving shapes from captured live executions
(`get_run_env` → per-step `result` values) and serving them back through the
walker's `probe` hook. The flow:

    live run  ──get_run_env──▶  {step_name: result}      (the oracle values)
       │            +playbook def: step_name → connector/op
       ▼
    shape_from_value(result)  ──▶  Shape   (measured, not inferred)
       │
       ▼
    GroundedShapeStore[connector:op]  ──merge across runs──▶  durable oracle
       │
       ▼
    grounded_probe(store)  ──▶  ProbeCallback  →  typed_walker.walk_playbook

`shape_from_value` is pure and offline-testable. The store is a plain JSON
sidecar so captures accumulate across sessions; `merge_shape` unions keys seen
across runs and marks any key absent from some observation as `optional` — that
optionality is the seed for the data-presence checks (gap A of the type work).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# Shape vocabulary mirrors compiler.typed_walker (kept in sync by hand; both are
# small and stable). Duplicated rather than imported to keep this module free of
# the walker's heavier dependencies.
Shape = dict[str, Any]

_MAX_DEPTH = 12


def _scalar(t: str) -> Shape:
    return {"kind": "scalar", "type": t}


def shape_from_value(value: Any, _depth: int = 0) -> Shape:
    """Derive a typed_walker `Shape` from a concrete (JSON) runtime value.

    This is the measurement function: given what a step *actually produced*,
    return its shape. Lists fold their elements into a single representative
    item shape (so `vars.steps.X[0].field` resolves); dicts keep per-key shapes.
    Mixed-type or over-deep structures degrade to `any` rather than guess.
    """
    if _depth > _MAX_DEPTH:
        return _scalar("any")
    if isinstance(value, bool):
        return _scalar("boolean")
    if value is None:
        return _scalar("null")
    if isinstance(value, int):
        return _scalar("integer")
    if isinstance(value, float):
        return _scalar("float")
    if isinstance(value, str):
        return _scalar("string")
    if isinstance(value, list):
        return {"kind": "list", "item": _list_item_shape(value, _depth)}
    if isinstance(value, dict):
        return {
            "kind": "object",
            "keys": {str(k): shape_from_value(v, _depth + 1)
                     for k, v in value.items()},
        }
    return _scalar("any")


def _list_item_shape(items: list, depth: int) -> Shape:
    """Fold a list's elements into one item shape by merging element shapes.

    An empty list yields `any` (we can't measure an item type from zero
    samples — and that's honest: downstream `[0]` access may be undefined).
    """
    if not items:
        return _scalar("any")
    item: Optional[Shape] = None
    for el in items:
        s = shape_from_value(el, depth + 1)
        item = s if item is None else merge_shape(item, s)
    return item or _scalar("any")


# --------------------------------------------------------------------------- #
# Merge — union two shapes observed for the same producer across runs.
# --------------------------------------------------------------------------- #

def merge_shape(a: Shape, b: Shape) -> Shape:
    """Combine two observed shapes for the same producer into one.

    - object ∪ object: union of keys. A key present in only one observation is
      marked `"optional": true` (it may be absent at runtime — the seed for
      data-presence checks). Each key's value shape is merged recursively.
    - list ∪ list: merge item shapes.
    - scalar ∪ scalar (same type): unchanged; differing types widen to `any`.
    - anything ∪ a differing kind: `any` (honest "we've seen both shapes").
    """
    if a == b:
        return a
    ka, kb = a.get("kind"), b.get("kind")
    if ka != kb:
        return _scalar("any")
    if ka == "scalar":
        ta, tb = a.get("type"), b.get("type")
        if ta == tb:
            return a
        # null widens the other type to "optional scalar of that type".
        if ta == "null":
            return dict(b, nullable=True)
        if tb == "null":
            return dict(a, nullable=True)
        if {ta, tb} <= {"integer", "float"}:
            return _scalar("float")
        return _scalar("any")
    if ka == "list":
        return {"kind": "list",
                "item": merge_shape(a.get("item") or _scalar("any"),
                                    b.get("item") or _scalar("any"))}
    if ka == "object":
        ak = a.get("keys") or {}
        bk = b.get("keys") or {}
        out: dict[str, Shape] = {}
        for name in set(ak) | set(bk):
            in_a, in_b = name in ak, name in bk
            if in_a and in_b:
                out[name] = merge_shape(ak[name], bk[name])
            else:
                only = ak.get(name) or bk.get(name) or _scalar("any")
                out[name] = dict(only, optional=True)
        return {"kind": "object", "keys": out}
    return _scalar("any")


# --------------------------------------------------------------------------- #
# Store — a JSON sidecar mapping "connector:op" → measured Shape.
# --------------------------------------------------------------------------- #

def _key(connector: str, op: str) -> str:
    return f"{(connector or '').strip()}:{(op or '').strip()}"


class GroundedShapeStore:
    """Persistent oracle of measured connector-op output shapes.

    Keyed by ``"<connector>:<op>"``. ``observe`` folds a freshly measured shape
    into the stored one (so repeated runs strengthen the oracle and reveal
    optional keys); ``shape_for`` serves the current best shape.
    """

    def __init__(self, shapes: Optional[dict[str, Shape]] = None,
                 path: Optional[Path] = None):
        self._shapes: dict[str, Shape] = dict(shapes or {})
        self._path = path

    # -- persistence ------------------------------------------------------- #
    @classmethod
    def load(cls, path: Path) -> "GroundedShapeStore":
        p = Path(path)
        data: dict[str, Shape] = {}
        if p.exists():
            try:
                data = json.loads(p.read_text()) or {}
            except Exception:  # noqa: BLE001 — a corrupt sidecar shouldn't crash compile
                data = {}
        return cls(data, path=p)

    def save(self, path: Optional[Path] = None) -> None:
        target = Path(path or self._path) if (path or self._path) else None
        if target is None:
            raise ValueError("no path to save GroundedShapeStore")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self._shapes, indent=2, sort_keys=True))

    # -- access ------------------------------------------------------------ #
    def shape_for(self, connector: str, op: str) -> Optional[Shape]:
        return self._shapes.get(_key(connector, op))

    def observe(self, connector: str, op: str, value: Any) -> Shape:
        """Measure `value`'s shape and fold it into the stored oracle."""
        measured = shape_from_value(value)
        k = _key(connector, op)
        prior = self._shapes.get(k)
        merged = measured if prior is None else merge_shape(prior, measured)
        self._shapes[k] = merged
        return merged

    def as_dict(self) -> dict[str, Shape]:
        return dict(self._shapes)

    def __len__(self) -> int:
        return len(self._shapes)


def grounded_probe(store: GroundedShapeStore):
    """Build a `typed_walker.ProbeCallback` backed by measured shapes.

    Signature matches `ProbeCallback = (connector, op, arguments) -> Shape|None`.
    Returns None for un-observed ops so the walker falls back to its existing
    inference (never worse than today; strictly better where we have data).
    """
    def _probe(connector: str, op: str, _arguments: dict) -> Optional[Shape]:
        return store.shape_for(connector, op)
    return _probe
