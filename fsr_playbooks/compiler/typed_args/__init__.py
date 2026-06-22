"""Typed-argument layer for the compiler.

Pydantic models that validate playbook step argument shapes, bridged into
the accumulating CompileError pipeline (never raising into it). See
`base.py` for the design contract and `_bridge.py` for the adapter.
"""
from __future__ import annotations

from .base import StrictArgs, add_warning
from ._bridge import loc_to_path, validate_args
from .trigger import (
    WhenGroup,
    WhenLeaf,
    expand_when,
    _TRIGGER_OPS,
    _TRIGGER_OP_ALIASES,
    _TRIGGER_OP_REWRITE,
    _wrap_like_value,
)
from .steps import (
    STEP_ARG_MODELS,
    is_modeled,
    SetVariableArgs,
    ArgListEntry,
    expand_set_variable,
)

__all__ = [
    "StrictArgs",
    "add_warning",
    "validate_args",
    "loc_to_path",
    "WhenGroup",
    "WhenLeaf",
    "expand_when",
    "_TRIGGER_OPS",
    "_TRIGGER_OP_ALIASES",
    "_TRIGGER_OP_REWRITE",
    "_wrap_like_value",
    "STEP_ARG_MODELS",
    "is_modeled",
    "SetVariableArgs",
    "ArgListEntry",
    "expand_set_variable",
]
