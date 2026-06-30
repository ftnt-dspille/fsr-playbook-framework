"""Typed-args model for `manual_input` steps — registry contract + the new
scalar validation. The friendly→canonical transform (the F3 bug site) stays in
the imperative normalizer; `ManualInputArgs` is validation-only:
`expand_manual_input` always returns None and never mutates the args.

The model also backs `emit_step_arg_schema("manual_input")` (the introspection
surface). Structural fields (`input`, `type`, `options`, `inputs`, `record`)
are intentionally left untyped — their shape rules stay in the imperative path,
so this layer must not duplicate or false-positive on them."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    ManualInputArgs,
    expand_manual_input,
    is_modeled,
)


def test_registry_models_manual_input():
    assert STEP_ARG_MODELS.get("manual_input") is ManualInputArgs
    assert is_modeled("manual_input") is True


def test_schema_surface_exposed():
    # The done-when: manual_input is now discoverable as a JSON Schema.
    schema = emit_step_arg_schema("manual_input")
    assert schema is not None
    assert "title" in schema["properties"]
    assert "is_approval" in schema["properties"]


def test_valid_friendly_args_no_errors_and_unchanged():
    errs: list[CompileError] = []
    args = {"title": "Approve?", "description": "body", "options": ["Continue"]}
    out = expand_manual_input(args, "p.steps[0]", errs)
    # Validation-only: never mutates, always returns None.
    assert out is None
    assert errs == []
    assert args == {"title": "Approve?", "description": "body",
                    "options": ["Continue"]}


def test_string_bool_coerced_no_error():
    # pydantic's lax bool accepts the usual spellings — no false positive on a
    # common `is_approval: "true"` form.
    errs: list[CompileError] = []
    expand_manual_input({"is_approval": "true"}, "p.steps[0]", errs)
    assert errs == []


def test_non_bool_flag_is_clean_bad_value():
    errs: list[CompileError] = []
    expand_manual_input({"title": "T", "is_approval": "maybe"},
                        "p.steps[0]", errs)
    assert errs and errs[0].code is ErrorCode.BAD_VALUE
    assert errs[0].path.endswith("arguments.is_approval")


def test_non_int_timeout_is_clean_bad_value():
    errs: list[CompileError] = []
    expand_manual_input({"timeout": "soon"}, "p.steps[0]", errs)
    assert errs and errs[0].code is ErrorCode.BAD_VALUE
    assert errs[0].path.endswith("arguments.timeout")


def test_structural_keys_pass_through_untyped():
    # input/record/options/inputs are owned by the imperative transform, so the
    # model must not reject their authored shapes.
    errs: list[CompileError] = []
    expand_manual_input(
        {"input": {"schema": {}}, "record": "", "owner_detail": {"isAssigned": False},
         "options": [{"option": "yes", "primary": True}],
         "inputs": [{"name": "c", "kind": "textarea"}]},
        "p.steps[0]", errs,
    )
    assert errs == []


def test_non_dict_returns_none():
    assert expand_manual_input("nope", "p", []) is None


def test_end_to_end_compile_friendly_manual_input(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        title: "Approve?"
        description: "Please review"
        options: [Continue]
        inputs:
          - {name: comment, kind: textarea, label: "Comment"}
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]


def test_end_to_end_bad_flag_flags_error(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        title: "Approve?"
        arguments:
          is_approval: maybe
"""
    r = compile_yaml(text, db_path)
    codes = [e.code for e in r.errors if e.severity == "error"]
    assert ErrorCode.BAD_VALUE in codes, [e.to_dict() for e in r.errors]
