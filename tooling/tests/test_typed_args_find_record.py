"""Typed-args model for `find_record` steps — registry contract and the new
validation behaviour: a wrong-typed scalar field (`partial`, `module`,
`checkboxFields`) is a clean BAD_VALUE instead of silently riding through to
the `find_data` handler, which drops garbage kwargs without complaint.

find_record has no friendly→canonical transform, so the model is validation-only:
`expand_find_record` always returns None and never mutates the args."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    FindRecordArgs,
    expand_find_record,
    is_modeled,
)


def test_registry_models_find_record():
    assert STEP_ARG_MODELS.get("find_record") is FindRecordArgs
    assert is_modeled("find_record") is True


def test_valid_args_no_errors_and_unchanged():
    errs: list[CompileError] = []
    args = {
        "module": "indicators",
        "query": {"logic": "AND", "filters": []},
        "partial": True,
    }
    out = expand_find_record(args, "p.steps[0]", errs)
    # Validation-only: never mutates, always returns None.
    assert out is None
    assert errs == []


def test_string_bool_coerced_no_error():
    # pydantic's lax bool accepts the usual true/false spellings — no false
    # positive on the common `partial: "true"` authoring form.
    errs: list[CompileError] = []
    expand_find_record({"partial": "true"}, "p.steps[0]", errs)
    assert errs == []


def test_non_bool_partial_is_clean_bad_value():
    errs: list[CompileError] = []
    expand_find_record({"module": "alerts", "partial": "maybe"},
                       "p.steps[0]", errs)
    assert errs and errs[0].code is ErrorCode.BAD_VALUE
    assert errs[0].path.endswith("arguments.partial")


def test_non_string_module_is_clean_bad_value():
    errs: list[CompileError] = []
    expand_find_record({"module": [1, 2]}, "p.steps[0]", errs)
    assert errs and errs[0].code is ErrorCode.BAD_VALUE
    assert errs[0].path.endswith("arguments.module")


def test_query_passes_through_untyped():
    # A whole-query Jinja string renders to a dict at runtime, so it must NOT
    # be rejected (query is intentionally left untyped).
    errs: list[CompileError] = []
    expand_find_record({"module": "alerts", "query": "{{ vars.saved_query }}"},
                       "p.steps[0]", errs)
    assert errs == []


def test_siblings_allowed():
    errs: list[CompileError] = []
    expand_find_record(
        {"module": "alerts", "mock_result": {"x": 1}, "condition": "{{ ok }}",
         "step_variables": []},
        "p.steps[0]", errs,
    )
    assert errs == []


def test_non_dict_returns_none():
    assert expand_find_record("nope", "p", []) is None


def test_end_to_end_compile_find_record(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: find
      - name: find
        type: find_record
        arguments:
          module: indicators
          query:
            logic: AND
            filters:
              - field: value
                operator: eq
                value: "x"
          partial: true
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]


def test_end_to_end_bad_partial_flags_error(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: find
      - name: find
        type: find_record
        arguments:
          module: indicators
          partial: maybe
"""
    r = compile_yaml(text, db_path)
    codes = [e.code for e in r.errors if e.severity == "error"]
    assert ErrorCode.BAD_VALUE in codes, [e.to_dict() for e in r.errors]
