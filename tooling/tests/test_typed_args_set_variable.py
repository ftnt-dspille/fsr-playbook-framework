"""Typed-args layer: the first per-step-type model (`set_variable`, Phase 2).

`expand_set_variable` replaces the imperative `arg_list` → flat-dict unwrap in
`NormalizerMixin._normalize_set_variable_args`. These tests pin parity with
the old behaviour (flat output, sibling precedence, the per-entry guard, the
leave-unchanged early-return) plus the registry/fallback scaffold contract,
and assert end-to-end `compile_yaml` output is unchanged.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args import (
    STEP_ARG_MODELS,
    SetVariableArgs,
    expand_set_variable,
    is_modeled,
)


# ── scaffold: registry + fallback contract ────────────────────────────────
def test_registry_models_set_variable():
    assert STEP_ARG_MODELS.get("set_variable") is SetVariableArgs
    assert is_modeled("set_variable") is True


def test_registry_unmodeled_type_falls_back():
    # Unmodeled step types must report no model so the resolver keeps using
    # the imperative path — the migration's incremental contract. (After the
    # P5 batch + ingest_bulk_feed, only the one-way authoring sugars stop/end
    # remain unmodeled -- they compile down to a connector call and carry no
    # distinct envelope to type.)
    assert is_modeled("stop") is False
    assert STEP_ARG_MODELS.get("stop") is None


# ── unwrap parity ─────────────────────────────────────────────────────────
def test_unwrap_flattens_arg_list():
    errs: list[CompileError] = []
    out = expand_set_variable(
        {"arg_list": [{"name": "sev", "value": "High"},
                      {"name": "count", "value": 3}]},
        "p", errs)
    assert errs == []
    assert out == {"sev": "High", "count": 3}


def test_missing_value_defaults_to_empty_string():
    errs: list[CompileError] = []
    out = expand_set_variable({"arg_list": [{"name": "x"}]}, "p", errs)
    assert errs == []
    assert out == {"x": ""}


def test_siblings_survive_and_win_over_vars():
    errs: list[CompileError] = []
    out = expand_set_variable(
        {"arg_list": [{"name": "x", "value": "from_vars"},
                      {"name": "keep", "value": 1}],
         "step_variables": {"input": []},
         "x": "sibling_wins"},
        "p", errs)
    assert errs == []
    # sibling `x` overrides the unwrapped var `x`; non-arg_list keys survive
    assert out == {"x": "sibling_wins", "keep": 1,
                   "step_variables": {"input": []}}


def test_value_passes_through_complex_types():
    errs: list[CompileError] = []
    out = expand_set_variable(
        {"arg_list": [{"name": "obj", "value": {"a": [1, 2]}},
                      {"name": "jinja", "value": "{{ vars.input.x }}"}]},
        "p", errs)
    assert errs == []
    assert out == {"obj": {"a": [1, 2]}, "jinja": "{{ vars.input.x }}"}


# ── leave-unchanged early-returns (parity with the old `return`) ──────────
def test_no_arg_list_returns_none():
    errs: list[CompileError] = []
    assert expand_set_variable({"already": "flat"}, "p", errs) is None
    assert errs == []


def test_non_list_arg_list_returns_none():
    errs: list[CompileError] = []
    assert expand_set_variable({"arg_list": "nope"}, "p", errs) is None
    assert errs == []


# ── per-entry guard (message + path preserved byte-for-byte) ──────────────
def test_malformed_entry_emits_legacy_error_and_returns_none():
    errs: list[CompileError] = []
    assert expand_set_variable(
        {"arg_list": [{"name": "ok", "value": 1}, "not-a-dict"]},
        "playbooks[0].steps[1]", errs) is None
    assert any(
        e.code == ErrorCode.BAD_VALUE
        and e.message == "arg_list entries must be {name, value} mappings"
        and e.path == "playbooks[0].steps[1].arguments.arg_list[1]"
        for e in errs)


def test_entry_without_name_is_rejected():
    errs: list[CompileError] = []
    assert expand_set_variable(
        {"arg_list": [{"value": "orphan"}]}, "p", errs) is None
    assert any(e.path == "p.arguments.arg_list[0]" for e in errs)


# ── end-to-end: compile_yaml output unchanged ─────────────────────────────
_PB = """\
collection: T
playbooks:
  - name: T
    steps:
      - type: start
        name: Start
        next: SV
      - type: set_variable
        name: SV
        vars:
          severity: High
          note: "{{ vars.input.records[0].name }}"
        next: End
      - type: end
        name: End
"""


def _sv_args(fsr_json: dict) -> dict:
    for c in fsr_json.get("data", []):
        for wf in c.get("workflows", []):
            for s in wf.get("steps", []):
                if s.get("name") == "SV":
                    return s["arguments"]
    return {}


def test_compile_yaml_emits_flat_wire_shape(db_path):
    r = compile_yaml(_PB, db_path)
    assert r.ok, [e.message for e in r.errors]
    assert _sv_args(r.fsr_json) == {
        "severity": "High",
        "note": "{{ vars.input.records[0].name }}",
    }
