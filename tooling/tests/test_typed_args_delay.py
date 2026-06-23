"""Typed-args model for `delay` steps — registry contract, expand parity,
and the new clean-error behaviour (a non-numeric duration is a BAD_VALUE
diagnostic, not an uncaught int() crash)."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    DelayArgs,
    expand_delay,
    is_modeled,
)

_RESUME_CHANNEL = "e2ce87c2-c55a-11ec-9d64-0242ac120002"


def test_registry_models_delay():
    assert STEP_ARG_MODELS.get("delay") is DelayArgs
    assert is_modeled("delay") is True


def test_friendly_seconds_expands_to_timebased():
    errs: list[CompileError] = []
    out = expand_delay({"seconds": 5}, "p.steps[0]", errs)
    assert errs == []
    assert out["type"] == "TimeBased"
    assert out["delay"] == {"days": 0, "hours": 0, "minutes": 0, "seconds": 5}
    assert out["rule"]["actions"][0]["channel_uuid"] == _RESUME_CHANNEL
    assert out["rule"]["is_active"] is True
    assert out["rule"]["event_source"] == "crudhub"
    # The friendly key is consumed, not left alongside the canonical delay.
    assert "seconds" not in out


def test_string_number_coerced():
    errs: list[CompileError] = []
    out = expand_delay({"minutes": "5"}, "p.steps[0]", errs)
    assert errs == []
    assert out["delay"]["minutes"] == 5


def test_zero_delay_defaults_to_one_second():
    out = expand_delay({}, "p.steps[0]", [])
    assert out["delay"] == {"days": 0, "hours": 0, "minutes": 0, "seconds": 1}


def test_siblings_preserved():
    out = expand_delay(
        {"seconds": 3, "mock_result": {"x": 1}, "condition": "{{ ok }}"},
        "p.steps[0]", [],
    )
    assert out["mock_result"] == {"x": 1}
    assert out["condition"] == "{{ ok }}"


def test_canonical_passthrough_returns_none():
    # Already-canonical input is left unchanged (caller keeps step.arguments).
    assert expand_delay({"rule": {}, "delay": {"seconds": 1}}, "p", []) is None


def test_non_dict_returns_none():
    assert expand_delay("nope", "p", []) is None


def test_non_numeric_duration_is_clean_bad_value():
    # The imperative path did `int(a.pop(k))` → an uncaught ValueError mid-compile.
    # The typed model surfaces it as a BAD_VALUE and leaves the step unchanged.
    errs: list[CompileError] = []
    out = expand_delay({"seconds": "abc"}, "p.steps[0]", errs)
    assert out is None
    assert errs and errs[0].code is ErrorCode.BAD_VALUE


def test_end_to_end_compile_delay_minutes(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: d
      - name: d
        type: delay
        arguments:
          minutes: 5
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
