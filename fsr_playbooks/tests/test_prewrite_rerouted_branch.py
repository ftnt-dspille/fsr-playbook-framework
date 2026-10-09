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


_PLACEHOLDER = """
collection: C
playbooks:
  - name: Child
    parameters: [ip]
    steps:
      - {name: Start, type: start, next: Note}
      - {name: Note, type: set_variable, vars: {ip: "{{ vars.input.params.ip }}"}}
  - name: Reputation Gate
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Block IP}
      - {name: Block IP, type: set_variable, vars: {pending_note: "wire the real block later"}, next: End}
      - {name: End, type: end}
"""


def _only(pb_name: str, text: str) -> dict:
    env = _compiled(text)
    data = env["data"][0] if "data" in env else env
    data["workflows"] = [w for w in data["workflows"] if w["name"] == pb_name]
    return env


def test_replacing_a_placeholder_with_a_different_step_type_is_an_edit():
    # Analyst sim: a set_variable placeholder "Block IP" became the reference
    # step "Block IP"; its set_variable arguments (pending_note, message) were
    # reported dropped and the Apply refused.
    real = _PLACEHOLDER.replace(
        '{name: Block IP, type: set_variable, vars: {pending_note: "wire the real block later"}, next: End}',
        '{name: Block IP, type: workflow_reference, target: Child, ip: "{{ vars.input.records[0].sourceIp }}", next: End}')
    verdict = check_prewrite(_only("Reputation Gate", _PLACEHOLDER), _only("Reputation Gate", real))
    assert verdict.ok, verdict.message


def test_same_type_step_losing_an_argument_is_still_refused():
    lost = _PLACEHOLDER.replace('vars: {pending_note: "wire the real block later"}', 'vars: {other: 1}')
    verdict = check_prewrite(_only("Reputation Gate", _PLACEHOLDER), _only("Reputation Gate", lost))
    assert not verdict.ok


def test_a_modified_step_token_covers_its_fields_and_routes_not_the_step():
    from fsr_playbooks.compiler.prewrite import _ack_matches
    tok = "Ping Team.*"
    assert _ack_matches(tok, "collection.workflows[w].routes[Ping Team->End:Dismiss]")
    assert _ack_matches(tok, "collection.workflows[w].steps[Ping Team].arguments.message.content")
    assert not _ack_matches(tok, "collection.workflows[w].steps[Ping Team]")
    assert not _ack_matches(tok, "collection.workflows[w].steps[Other].arguments.x")
    assert not _ack_matches(tok, "collection.workflows[w].routes[Other->Ping Team:x]")


def test_a_modified_step_token_matches_whole_segments_only():
    from fsr_playbooks.compiler.prewrite import _ack_matches
    assert not _ack_matches("A.*", "collection.workflows[w].steps[A2].arguments.x")
    assert not _ack_matches("A.*", "collection.workflows[w].routes[BA->C:x]")
