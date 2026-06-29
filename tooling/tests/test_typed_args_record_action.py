"""Typed-args model for the record-action trigger (`start` + `module:`).

Validation-only (the `find_record` precedent): the heavy canonical transform
(route uuid5, displayConditions, the noRecordExecution/singleRecordExecution flag
pair) stays in the resolver, so `expand_record_action` never mutates and always
returns ``None``. These tests pin the scalar-flag validation — the headline win
is catching a mistyped `run_mode`/`requires_record` that would otherwise silently
mis-route the Execute button.

`record_action` is keyed in the registry for schema discoverability even though
it is authored as `type: start` with a `module:` (no distinct authoring type)."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    RecordActionArgs,
    expand_record_action,
    is_modeled,
)


def _expand(args, errs=None):
    return expand_record_action(args, "p.steps[0]", errs if errs is not None else [])


def test_registry_models_record_action():
    assert STEP_ARG_MODELS.get("record_action") is RecordActionArgs
    assert is_modeled("record_action") is True


def test_validation_only_returns_none_and_does_not_mutate():
    args = {"module": "alerts", "requires_record": True, "run_mode": "per_record"}
    snapshot = dict(args)
    assert _expand(args) is None
    assert args == snapshot


def test_valid_run_mode_values_pass():
    for mode in ("per_record", "once_for_all"):
        errs: list[CompileError] = []
        _expand({"module": "alerts", "run_mode": mode}, errs)
        assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_mistyped_run_mode_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"module": "alerts", "run_mode": "per record"}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.run_mode")
        for e in errs
    )


def test_non_bool_requires_record_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"module": "alerts", "requires_record": "maybe"}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.requires_record")
        for e in errs
    )


def test_requires_record_truthy_coerces():
    errs: list[CompileError] = []
    _expand({"module": "alerts", "requires_record": "true"}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_non_string_button_label_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"module": "alerts", "button_label": ["x"]}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.button_label")
        for e in errs
    )


def test_module_list_rides_through_untouched():
    # `module` may be a single name OR a list — left untyped, no false positive.
    errs: list[CompileError] = []
    _expand({"module": ["alerts", "incidents"]}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_non_dict_returns_none():
    assert expand_record_action("nope", "p", []) is None


def test_end_to_end_compile_record_action_bad_run_mode(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        arguments:
          module: alerts
          run_mode: "per record"
"""
    r = compile_yaml(text, db_path)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.run_mode")
        for e in r.errors
    ), [e.to_dict() for e in r.errors]


def test_end_to_end_compile_record_action_valid(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        arguments:
          module: alerts
          run_mode: once_for_all
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
