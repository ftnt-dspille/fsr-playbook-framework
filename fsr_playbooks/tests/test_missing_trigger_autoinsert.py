"""A playbook with steps but no trigger step has no entry point and cannot
compile. The model routinely omits the required `start` on a connector-less
loop/decision playbook (localized live on for_each_loop): the whole compile
failed on NO_TRIGGER and bounced the agent loop back to re-author a playbook
that was otherwise complete.

When the entry is unambiguous -- exactly one step is the target of no other
step's next/branch/unlabeled route -- the parser prepends a manual `start`
routed to it and warns. A manual start only fills a TOTAL absence; it never
flips an existing trigger, so it cannot corrupt intent. Ambiguous (no single
entry) stays the honest NO_TRIGGER error.

RED without the fix: `_insert_missing_trigger` does not exist / is not called,
so the single-entry playbook fails to compile with NO_TRIGGER.
"""
from __future__ import annotations

from pathlib import Path

from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.pipeline import compile_yaml

_DB = Path(__file__).resolve().parents[1] / "_data" / "fsr_reference.db"

_NO_TRIGGER_LINEAR = """playbooks:
  - name: For Each Create
    steps:
      - name: Build alerts
        type: set_variable
        next: Create alert per item
        vars:
          alerts_to_create:
            - name: "A"
              severity: High
      - name: Create alert per item
        type: create_record
        for_each:
          item: "{{ vars.steps.Build_alerts.alerts_to_create }}"
        module: alerts
        operation: Replace
        fields:
          severity: "{{ vars.item.severity }}"
"""

# Two steps, neither routes to the other -> two entry points -> ambiguous.
_NO_TRIGGER_AMBIGUOUS = """playbooks:
  - name: Two Roots
    steps:
      - name: First
        type: set_variable
        vars: {a: "1"}
      - name: Second
        type: set_variable
        vars: {b: "2"}
"""

_HAS_TRIGGER = """playbooks:
  - name: Already Triggered
    steps:
      - name: trigger
        type: start
        next: Note
      - name: Note
        type: set_variable
        vars: {a: "1"}
"""


def _blockers(result):
    return [e for e in result.errors if e.severity != "warning"]


def test_single_entry_gets_a_manual_start_and_a_warning():
    result = compile_yaml(_NO_TRIGGER_LINEAR, _DB)
    assert not any(e.code == ErrorCode.NO_TRIGGER for e in _blockers(result)), \
        "a single-entry playbook should have had a start step inserted"
    warns = [e for e in result.errors if e.severity == "warning"]
    assert any(e.code == ErrorCode.NO_TRIGGER and "manual" in e.message
               for e in warns), "the inserted trigger must be surfaced, not silent"
    # The inserted start routes to the real entry step.
    pb = result.ir.playbooks[0]
    starts = [s for s in pb.steps if s.type == "start"]
    assert len(starts) == 1
    assert starts[0].next == pb.steps[1].id


def test_ambiguous_entry_stays_an_honest_no_trigger_error():
    result = compile_yaml(_NO_TRIGGER_AMBIGUOUS, _DB)
    assert any(e.code == ErrorCode.NO_TRIGGER for e in _blockers(result)), \
        "two entry points are ambiguous; must not guess a trigger"


def test_existing_trigger_is_untouched():
    result = compile_yaml(_HAS_TRIGGER, _DB)
    assert not any(e.severity == "warning" and e.code == ErrorCode.NO_TRIGGER
                   for e in result.errors)
    pb = result.ir.playbooks[0]
    assert len([s for s in pb.steps if s.type == "start"]) == 1
