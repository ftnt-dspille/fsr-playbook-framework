"""Typed-argument layer for the compiler.

Pydantic models that validate playbook step argument shapes, bridged into
the accumulating CompileError pipeline (never raising into it). See
`base.py` for the design contract and `_bridge.py` for the adapter.
"""
from __future__ import annotations

from ._bridge import loc_to_path, validate_args
from .base import StrictArgs, add_warning
from .field_validator import FieldValueValidator
from .steps import (
    STEP_ARG_MODELS,
    ArgListEntry,
    DecisionArgs,
    DecisionCondition,
    SetVariableArgs,
    expand_decision,
    expand_set_variable,
    is_modeled,
)
from .trigger import (
    _TRIGGER_OP_ALIASES,
    _TRIGGER_OP_REWRITE,
    _TRIGGER_OPS,
    WhenGroup,
    WhenLeaf,
    _wrap_like_value,
    expand_when,
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
    "DecisionArgs",
    "DecisionCondition",
    "expand_decision",
    "FieldValueValidator",
]
