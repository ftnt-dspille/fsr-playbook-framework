"""#126 -- diff_summary must explain the edit, not just name it.

The name lists (steps_added / steps_removed / steps_modified) are an index;
they cannot answer "what changed about that step?". `diff_summary.changes`
carries the per-step before/after projections `_diff_collections` already
computes, so the enhancement_offer card can lead with a diff instead of a
YAML dump.
"""
from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.mcp_server.tools_enhancement import _diff_collections

_BEFORE = """
collection: Diff Fixtures
description: before/after fixture for the enhancement diff.

playbooks:
  - name: Triage
    description: fixture.
    steps:
      - name: start
        type: start
        next: Set Severity
      - name: Set Severity
        type: set_variable
        next: Note
        vars:
          severity: low
      - name: Note
        type: set_variable
        vars:
          note: done
"""

_AFTER_MODIFIED = _BEFORE.replace("severity: low", "severity: high")

_AFTER_ADDED = _BEFORE.replace(
    "      - name: Note\n        type: set_variable\n        vars:\n          note: done\n",
    "      - name: Note\n        type: set_variable\n        next: Extra\n        vars:\n"
    "          note: done\n      - name: Extra\n        type: set_variable\n        vars:\n"
    "          extra: 1\n",
)

_AFTER_REMOVED = _BEFORE.replace(
    "        next: Note\n", "\n"
).replace(
    "      - name: Note\n        type: set_variable\n        vars:\n          note: done\n", ""
)


def _diff(before_text: str, after_text: str):
    before, berrs = parse_yaml(before_text)
    after, aerrs = parse_yaml(after_text)
    assert before is not None, berrs
    assert after is not None, aerrs
    return _diff_collections(before, after, None)


def _by_step(changes, name):
    return next(c for c in changes if c["step"] == name)


def test_modified_step_carries_before_and_after():
    _, summary = _diff(_BEFORE, _AFTER_MODIFIED)
    assert summary["steps_modified"] == ["Set Severity"]
    entry = _by_step(summary["changes"], "Set Severity")
    assert entry["kind"] == "modified"
    assert entry["playbook"] == "Triage"
    # set_variable arguments normalize to an arg_list of {name, value}.
    assert entry["before"]["arguments"]["arg_list"] == [
        {"name": "severity", "value": "low"}]
    assert entry["after"]["arguments"]["arg_list"] == [
        {"name": "severity", "value": "high"}]
    assert entry["changed_fields"] == ["arguments"]


def test_unchanged_steps_are_not_in_changes():
    _, summary = _diff(_BEFORE, _AFTER_MODIFIED)
    assert {c["step"] for c in summary["changes"]} == {"Set Severity"}
    assert summary["unchanged"] == 2  # start + Note


def test_added_step_has_after_only():
    _, summary = _diff(_BEFORE, _AFTER_ADDED)
    entry = _by_step(summary["changes"], "Extra")
    assert entry["kind"] == "added"
    assert entry["before"] is None
    assert entry["after"]["arguments"]["arg_list"] == [
        {"name": "extra", "value": 1}]


def test_removed_step_has_before_only():
    _, summary = _diff(_BEFORE, _AFTER_REMOVED)
    entry = _by_step(summary["changes"], "Note")
    assert entry["kind"] == "removed"
    assert entry["after"] is None
    assert entry["before"]["arguments"]["arg_list"] == [
        {"name": "note", "value": "done"}]


def test_identical_collections_produce_no_changes():
    regressions, summary = _diff(_BEFORE, _BEFORE)
    assert regressions == []
    assert summary["changes"] == []
