"""Per-step-type typed argument models (Phase 2).

The migration lands type-by-type behind a registry + fallback: a step type
with a model routes its arguments through the typed layer; everything else
keeps using the imperative normalizer in `resolver/normalizers.py`. This keeps
every intermediate commit shippable (zero corpus-emit diff at each step).

`STEP_ARG_MODELS` maps an FSR-friendly step type to its pydantic model — the
introspection surface Phase 4 will emit JSON Schema from. Types whose wire
output is not a fixed-field record (e.g. set_variable, whose flat output keys
are the author's variable names) also expose an `expand_*` walk that owns the
semantic transform + precise CompileError paths, mirroring the trigger layer's
`expand_when`. The resolver calls that walk; the model backs it.
"""
from __future__ import annotations

from ..base import StrictArgs  # noqa: F401  (re-export for symmetry)
from .set_variable import SetVariableArgs, ArgListEntry, expand_set_variable

# Step type → typed argument model. Grows incrementally through Phase 2.
STEP_ARG_MODELS: dict[str, type[StrictArgs]] = {
    "set_variable": SetVariableArgs,
}


def is_modeled(step_type: str) -> bool:
    """True if `step_type` has a typed-args model (vs. the imperative path)."""
    return step_type in STEP_ARG_MODELS


__all__ = [
    "STEP_ARG_MODELS",
    "is_modeled",
    "SetVariableArgs",
    "ArgListEntry",
    "expand_set_variable",
]
