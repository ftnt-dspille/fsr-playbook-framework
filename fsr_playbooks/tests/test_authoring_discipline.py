"""Phase 7.3 -- detect skipped authoring tools (discipline post-turn check).

The system prompt tells the agent to call ``get_step_type`` before
drafting non-trivial step types and ``find_connector`` /
``find_operation`` before drafting connector steps. This module
analyzes a completed turn's transcript and flags when those tools
were skipped, or when the agent's text contains hedging language
suggesting it is guessing at parameter shapes.
"""
from __future__ import annotations

from fsr_playbooks.llm.discipline import detect_skipped_authoring_tools
from fsr_playbooks.llm.provider import (
    DoneEvent,
    TextEvent,
    ToolUseEvent,
)


# ──────────── helpers ────────────

_YAML_MANUAL_INPUT = """\
```yaml
collection: t
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Ask
      - type: manual_input
        name: Ask
        arguments:
          title: Approve?
        options:
          - display: Yes
            next: Done
      - type: end
        name: Done
```
"""

_YAML_CONNECTOR = """\
```yaml
collection: t
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Query
      - type: connector
        name: Query
        connector: vt
        operation: get_ip_report
        arguments:
          params:
            ip: "{{ vars.input.params.ip }}"
        next: Done
      - type: end
        name: Done
```
"""

_YAML_SET_VAR = """\
```yaml
collection: t
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Set
      - type: set_variable
        name: Set
        vars:
          x: hello
        next: Done
      - type: end
        name: Done
```
"""


def _tool_use(name: str, call_id: str = "c1", **args) -> ToolUseEvent:
    return ToolUseEvent(name=name, arguments=args, call_id=call_id)


# ──────────── skipped step-type lookup ────────────

def test_skipped_step_type_no_lookup_at_all():
    """manual_input in YAML, but get_step_type never called."""
    transcript = [
        TextEvent(text="Let me draft this.\n"),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert len(warnings) == 1
    assert warnings[0].kind == "skipped_step_type"
    assert "manual_input" in warnings[0].step_types


def test_skipped_step_type_looked_up_different_type():
    """manual_input in YAML, but get_step_type called for a different type."""
    transcript = [
        _tool_use("get_step_type", step_type="set_variable"),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert len(warnings) == 1
    assert warnings[0].kind == "skipped_step_type"
    assert "manual_input" in warnings[0].step_types


def test_step_type_looked_up_no_warning():
    """manual_input in YAML, get_step_type called for manual_input."""
    transcript = [
        _tool_use("get_step_type", step_type="manual_input"),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "skipped_step_type" for w in warnings)


def test_find_step_examples_satisfies_requirement():
    """find_step_examples(manual_input) also satisfies the requirement."""
    transcript = [
        _tool_use("find_step_examples", step_type="manual_input"),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "skipped_step_type" for w in warnings)


def test_set_variable_does_not_require_lookup():
    """set_variable is not in the requiring-lookup set."""
    transcript = [
        TextEvent(text=_YAML_SET_VAR),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "skipped_step_type" for w in warnings)


# ──────────── skipped connector lookup ────────────

def test_skipped_connector_no_lookup():
    """connector step in YAML, but find_connector/find_operation never called."""
    transcript = [
        TextEvent(text=_YAML_CONNECTOR),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    kinds = {w.kind for w in warnings}
    assert "skipped_connector" in kinds


def test_connector_find_operation_called_no_warning():
    """connector step in YAML, find_operation was called."""
    transcript = [
        _tool_use("find_operation", connector="vt"),
        TextEvent(text=_YAML_CONNECTOR),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "skipped_connector" for w in warnings)


def test_connector_find_connector_called_no_warning():
    """connector step in YAML, find_connector was called."""
    transcript = [
        _tool_use("find_connector", q="vt"),
        TextEvent(text=_YAML_CONNECTOR),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "skipped_connector" for w in warnings)


# ──────────── guessing language ────────────

def test_guessing_language_detected():
    """Hedging phrase + YAML block → guessing warning."""
    transcript = [
        TextEvent(text="I think the args are something like this:\n"),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    kinds = {w.kind for w in warnings}
    assert "guessing" in kinds


def test_guessing_language_without_yaml_not_flagged():
    """Hedging phrase without YAML → no guessing warning."""
    transcript = [
        TextEvent(text="I think we should create an alert."),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "guessing" for w in warnings)


def test_no_hedging_no_guessing_warning():
    """No hedging language → no guessing warning."""
    transcript = [
        _tool_use("get_step_type", step_type="manual_input"),
        TextEvent(text="Here is the YAML:\n"),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    assert not any(w.kind == "guessing" for w in warnings)


# ──────────── edge cases ────────────

def test_empty_transcript():
    assert detect_skipped_authoring_tools([]) == []


def test_text_only_no_yaml():
    """Text without a YAML block → no warnings."""
    transcript = [
        TextEvent(text="Hello, how can I help?"),
        DoneEvent(stop_reason="end_turn"),
    ]
    assert detect_skipped_authoring_tools(transcript) == []


def test_synthetic_tool_use_ignored():
    """Synthetic tool uses (from resume) should not count as lookups."""
    transcript = [
        ToolUseEvent(
            name="get_step_type",
            arguments={"step_type": "manual_input"},
            call_id="c1",
            synthetic=True,
        ),
        TextEvent(text=_YAML_MANUAL_INPUT),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    # The synthetic tool use doesn't count, so we should still see
    # the skipped_step_type warning.
    assert any(w.kind == "skipped_step_type" for w in warnings)


def test_multiple_skipped_types_reported_together():
    """YAML with manual_input + decision, no lookups → one warning
    listing both types."""
    yaml_block = """\
```yaml
collection: t
playbooks:
  - name: P
    steps:
      - type: start
        name: Start
        next: Decide
      - type: decision
        name: Decide
        conditions:
          - display: Yes
            when: "true"
            next: Ask
          - display: Else
            default: true
            next: Done
      - type: manual_input
        name: Ask
        options:
          - display: Ok
            next: Done
      - type: end
        name: Done
```
"""
    transcript = [
        TextEvent(text=yaml_block),
        DoneEvent(stop_reason="end_turn"),
    ]
    warnings = detect_skipped_authoring_tools(transcript)
    skipped = [w for w in warnings if w.kind == "skipped_step_type"]
    assert len(skipped) == 1
    assert set(skipped[0].step_types) == {"decision", "manual_input"}
