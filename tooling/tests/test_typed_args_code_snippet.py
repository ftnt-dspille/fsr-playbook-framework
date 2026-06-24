"""Typed-args model for `code_snippet` steps — registry contract, expand parity,
and the new clean-error behaviour."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    CodeSnippetArgs,
    expand_code_snippet,
    is_modeled,
)


def test_registry_models_code_snippet():
    assert STEP_ARG_MODELS.get("code_snippet") is CodeSnippetArgs
    assert is_modeled("code_snippet") is True


def test_friendly_code_expands_to_canonical():
    errs: list[CompileError] = []
    out = expand_code_snippet({"code": "print('hi')"}, "p.steps[0]", errs)
    assert errs == []
    assert out["connector"] == "code-snippet"
    assert out["operation"] == "python_inline_code_editor"
    assert out["operationTitle"] == "Execute Python Code"
    assert out["version"] == "2.1.4"
    assert out["params"]["python_function"] == "print('hi')"
    assert out["step_variables"] == []
    # The friendly code key is consumed, not left alongside params.
    assert "code" not in out


def test_python_alias_expands_like_code():
    errs: list[CompileError] = []
    out = expand_code_snippet({"python": "x=1"}, "p.steps[0]", errs)
    assert errs == []
    assert out["params"]["python_function"] == "x=1"
    assert "python" not in out


def test_config_field_passthrough():
    # Config field is NOT consumed by expand; it's left for resolver to handle.
    errs: list[CompileError] = []
    out = expand_code_snippet(
        {"code": "x=1", "config": "my_config"},
        "p.steps[0]", errs,
    )
    assert errs == []
    assert out["config"] == "my_config"


def test_canonical_passthrough_returns_none():
    # Already-canonical input is left unchanged (caller keeps step.arguments).
    assert expand_code_snippet(
        {
            "connector": "code-snippet",
            "operation": "python_inline_code_editor",
            "params": {"python_function": "x=1"},
        },
        "p", [],
    ) is None


def test_non_dict_returns_none():
    assert expand_code_snippet("nope", "p", []) is None


def test_non_string_code_is_clean_bad_value():
    # Non-string code fields should trigger a BAD_VALUE error.
    errs: list[CompileError] = []
    out = expand_code_snippet({"code": 123}, "p.steps[0]", errs)
    assert out is None
    assert errs and errs[0].code is ErrorCode.BAD_VALUE


def test_empty_code_handled_by_resolver():
    # expand_code_snippet does not check for empty code — that's the resolver's job.
    errs: list[CompileError] = []
    out = expand_code_snippet({}, "p.steps[0]", errs)
    assert out is not None
    assert out["params"]["python_function"] == ""


def test_end_to_end_compile_friendly_code(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: snippet
      - name: snippet
        type: code_snippet
        arguments:
          code: |
            print("hello world")
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"],         [e.to_dict() for e in r.errors]
