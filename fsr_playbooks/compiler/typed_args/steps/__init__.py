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
from .decision import DecisionArgs, DecisionCondition, expand_decision
from .delay import DelayArgs, expand_delay
from .code_snippet import CodeSnippetArgs, expand_code_snippet
from .find_record import FindRecordArgs, expand_find_record
from .delete_record import DeleteRecordArgs, expand_delete_record
from .record_crud import RecordCrudArgs, expand_record_crud
from .record_action import RecordActionArgs, expand_record_action
from .manual_input import ManualInputArgs, expand_manual_input

# Step type → typed argument model. Grows incrementally through Phase 2.
#
# Keys are FSR-friendly step types. `record_action` is the one entry that is not
# a distinct *authoring* type — it is authored as `type: start` with a `module:`
# (the manual record-action trigger; see `validator.py` TRIGGER_TYPES and the
# `cybersponse.action` mapping). It is keyed here so its schema is discoverable
# via `get_step_arg_schema("record_action")`; the resolver wires its validation
# into the `start`+`module` normalizer, not by a type-map lookup.
STEP_ARG_MODELS: dict[str, type[StrictArgs]] = {
    "set_variable": SetVariableArgs,
    "decision": DecisionArgs,
    "delay": DelayArgs,
    "code_snippet": CodeSnippetArgs,
    "find_record": FindRecordArgs,
    "delete_record": DeleteRecordArgs,
    "create_record": RecordCrudArgs,
    "insert_record": RecordCrudArgs,
    "update_record": RecordCrudArgs,
    "record_action": RecordActionArgs,
    # Validation-only model (the friendly→canonical transform stays in the
    # imperative normalizer; see manual_input.py). Registered for the JSON-schema
    # introspection surface + typed scalar validation.
    "manual_input": ManualInputArgs,
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
    "DecisionArgs",
    "DecisionCondition",
    "expand_decision",
    "DelayArgs",
    "expand_delay",
    "CodeSnippetArgs",
    "expand_code_snippet",
    "FindRecordArgs",
    "expand_find_record",
    "DeleteRecordArgs",
    "expand_delete_record",
    "RecordCrudArgs",
    "expand_record_crud",
    "RecordActionArgs",
    "expand_record_action",
    "ManualInputArgs",
    "expand_manual_input",
]
