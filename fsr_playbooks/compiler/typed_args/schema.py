"""JSON Schema emission from the typed step-argument models (Phase 4 / G9.4).

The ``STEP_ARG_MODELS`` registry (see ``steps/__init__.py``) is the single
introspection surface for per-step-type argument shapes. This module turns those
pydantic models into standard JSON Schema so the MCP authoring tools and the web
inspector can offer structural validation *before* a compile — agents and humans
get "this field is unknown / wrong type" feedback up front instead of a compile
error round-trip.

Coverage grows with the registry: today ``set_variable`` and ``decision`` are
modeled, the rest of the step types are not. Unmodeled types return ``None``
(callers surface a clear "not yet modeled" signal) rather than a misleading empty
schema. The emitted schema is the raw ``model_json_schema()`` — faithful to the
model; any prettifying/filtering is a UI concern, not done here.

Pure introspection — no DB, no network — so it ships in the wheel.
"""
from __future__ import annotations

from typing import Any

from .steps import STEP_ARG_MODELS


def list_modeled_step_types() -> list[str]:
    """Step types that currently have a typed-args model, sorted."""
    return sorted(STEP_ARG_MODELS)


def emit_step_arg_schema(step_type: str) -> dict[str, Any] | None:
    """JSON Schema for ``step_type``'s arguments, or ``None`` if not modeled.

    ``None`` is deliberate: it lets callers distinguish "no schema yet" from a
    model that genuinely accepts an empty object.
    """
    model = STEP_ARG_MODELS.get(step_type)
    if model is None:
        return None
    return model.model_json_schema()


def all_step_arg_schemas() -> dict[str, dict[str, Any]]:
    """Map every modeled step type to its JSON Schema (skips unmodeled types)."""
    return {name: model.model_json_schema() for name, model in STEP_ARG_MODELS.items()}
