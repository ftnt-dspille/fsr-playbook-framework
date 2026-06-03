"""P3 — low-signal input gate.

`test`, `hi`, and `what's next` must NOT launch a full autonomous
investigation; a real directive must. The classifier is the testable unit;
`triage_preflight` wires its directive into the system prompt.
"""
from __future__ import annotations

import pytest

from fsr_core.llm.intents import (
    CONTINUE,
    DIRECTIVE,
    TRIVIAL,
    classify_message,
    gate_directive,
)
from fsr_core.llm.triage_preflight import triage_preflight


@pytest.mark.parametrize("text,expected", [
    ("test", TRIVIAL),
    ("Test", TRIVIAL),
    ("hi", TRIVIAL),
    ("hello there", DIRECTIVE),   # has content beyond the greeting token
    ("", TRIVIAL),
    ("   ", TRIVIAL),
    ("ok", TRIVIAL),
    ("thanks", TRIVIAL),
    ("?", TRIVIAL),
    ("what's next", CONTINUE),
    ("whats next?", CONTINUE),
    ("ok what's next", CONTINUE),
    ("continue", CONTINUE),
    ("build the attack timeline", DIRECTIVE),
    ("is 87.224.7.73 malicious?", DIRECTIVE),
    ("isolate the host", DIRECTIVE),
])
def test_classify(text, expected):
    assert classify_message(text) == expected


def test_only_directive_has_no_gate():
    assert gate_directive(DIRECTIVE) == ""
    assert gate_directive(TRIVIAL)
    assert gate_directive(CONTINUE)


def test_non_string_is_directive():
    assert classify_message(None) == DIRECTIVE
    assert classify_message(123) == DIRECTIVE


def test_preflight_trivial_appends_orientation_gate():
    bundle = triage_preflight(raw_record={}, user_message="test")
    assert bundle["message_class"] == TRIVIAL
    assert "Low-signal input" in bundle["system"]
    assert "Do NOT" in bundle["system"]


def test_preflight_directive_leaves_prompt_clean():
    base = triage_preflight(raw_record={})
    gated = triage_preflight(raw_record={}, user_message="build the timeline")
    assert gated["message_class"] == DIRECTIVE
    # No gate text appended for a real directive.
    assert gated["system"] == base["system"]


def test_preflight_continue_appends_advance_gate():
    bundle = triage_preflight(raw_record={}, user_message="what's next")
    assert bundle["message_class"] == CONTINUE
    assert "Continue" in bundle["system"]
    assert "re-run" in bundle["system"]
