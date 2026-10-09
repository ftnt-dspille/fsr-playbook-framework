"""A decision branch re-pointed at a new step is an edit, not a loss.

Analyst sim (reputation gate): "now block it if VirusTotal says malicious,
otherwise set severity Low" re-points the decision's two existing branches at
two new steps. The guard keyed each condition by its whole dict -- label,
expression, target step -- so a changed target read as a deleted branch and
every Apply was refused would_drop_fields. Dropping a branch must still refuse.
"""
from __future__ import annotations

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.prewrite import check_prewrite

_V1 = """
collection: C
playbooks:
  - name: Reputation Gate
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Decide}
      - name: Decide
        type: decision
        conditions:
          - {display: Malicious, when: "{{ vars.input.records[0].severity == 'High' }}", next: Log Findings}
          - {display: Clean, default: true, next: End}
      - {name: Log Findings, type: set_variable, vars: {seen: true}, next: End}
      - {name: End, type: end}
"""

_V2 = """
collection: C
playbooks:
  - name: Reputation Gate
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Decide}
      - name: Decide
        type: decision
        conditions:
          - {display: Malicious, when: "{{ vars.input.records[0].severity == 'High' }}", next: Block}
          - {display: Clean, default: true, next: Set Low}
      - {name: Log Findings, type: set_variable, vars: {seen: true}, next: End}
      - {name: Block, type: set_variable, vars: {blocked: true}, next: Log Findings}
      - {name: Set Low, type: set_variable, vars: {low: true}, next: End}
      - {name: End, type: end}
"""


def _compiled(text: str) -> dict:
    res = compile_yaml(text, default_db_path())
    assert res.ok, [e.message for e in res.errors]
    return res.fsr_json


def test_rerouting_existing_branches_is_not_a_loss():
    verdict = check_prewrite(_compiled(_V1), _compiled(_V2))
    assert verdict.ok, verdict.message


def test_dropping_a_branch_is_still_refused():
    no_clean = _V1.replace(
        "          - {display: Clean, default: true, next: End}\n", "")
    verdict = check_prewrite(_compiled(_V1), _compiled(no_clean))
    assert not verdict.ok
    assert any("Clean" in p for p in verdict.dropped), verdict.dropped


def test_branches_sharing_a_label_still_report_a_dropped_one():
    # Keyed by label, two "Same" branches would merge and the loss of one
    # would vanish; the guard falls back to whole-value identity.
    from fsr_playbooks.compiler.prewrite import diff_losses
    live = {"data": [{"workflows": [{"name": "P", "steps": [{"name": "D", "arguments": {
        "conditions": [{"option": "Same", "step_name": "A"},
                       {"option": "Same", "step_name": "B"}]}}]}]}]}
    out = {"data": [{"workflows": [{"name": "P", "steps": [{"name": "D", "arguments": {
        "conditions": [{"option": "Same", "step_name": "A"}]}}]}]}]}
    assert diff_losses(live, out)
