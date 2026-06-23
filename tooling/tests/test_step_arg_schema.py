"""JSON Schema emission from typed step-arg models — G9.4.

Covers ``compiler/typed_args/schema.py``: modeled types emit a valid object
schema exposing their fields; unmodeled types return ``None`` (not an empty
schema); the registry enumeration stays in sync.
"""
from __future__ import annotations

from fsr_playbooks.compiler.typed_args.schema import (
    all_step_arg_schemas,
    emit_step_arg_schema,
    list_modeled_step_types,
)
from fsr_playbooks.compiler.typed_args.steps import STEP_ARG_MODELS


def test_list_modeled_matches_registry():
    assert list_modeled_step_types() == sorted(STEP_ARG_MODELS)
    # The two Phase-2 models shipped so far.
    assert "set_variable" in list_modeled_step_types()
    assert "decision" in list_modeled_step_types()


def test_set_variable_schema_is_object_with_arg_list():
    schema = emit_step_arg_schema("set_variable")
    assert schema is not None
    assert schema.get("type") == "object"
    assert "arg_list" in schema.get("properties", {})


def test_decision_schema_exposes_conditions():
    schema = emit_step_arg_schema("decision")
    assert schema is not None
    assert "conditions" in schema.get("properties", {})


def test_decision_condition_forbids_extra_keys():
    # DecisionCondition uses extra="forbid" → its object schema (in $defs)
    # must set additionalProperties: false. This is the typo-catching contract.
    schema = emit_step_arg_schema("decision")
    defs = schema.get("$defs", {})
    cond = defs.get("DecisionCondition")
    assert cond is not None, "DecisionCondition should appear in $defs"
    assert cond.get("additionalProperties") is False


def test_unmodeled_type_returns_none():
    # connector is catalog-validated imperatively — not modeled yet.
    assert emit_step_arg_schema("connector") is None
    assert emit_step_arg_schema("does_not_exist") is None


def test_all_schemas_covers_every_modeled_type():
    schemas = all_step_arg_schemas()
    assert set(schemas) == set(STEP_ARG_MODELS)
    for name, s in schemas.items():
        assert s.get("type") == "object", f"{name} schema should be an object"
