"""The emitter writes at most one route per (source, target) step pair.

The playbook designer refuses a second connection between the same two steps
("Duplicate routes are not allowed") and stops adding routes there, so a pasted
playbook silently loses every route after the duplicate. The API import takes
both, which is why this went unnoticed.

Found pasting the all-step-types example into the designer: its manual_input
has `next: Wait briefly` AND an `approve` option to Wait briefly, and the
emitter wrote an unlabelled route for `next:` beside the labelled option route.
"""
from __future__ import annotations

from collections import Counter

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml

_YAML = """
collection: dup routes
playbooks:
  - name: wf
    steps:
      - name: trigger
        type: start
        next: Approve
      - name: Approve
        type: manual_input
        next: {next}
        title: Approve?
        options:
          - {{display: approve, primary: true, next: Approved}}
          - {{display: reject, next: Rejected}}
      - name: Approved
        type: set_variable
        vars: {{verdict: approved}}
      - name: Rejected
        type: set_variable
        vars: {{verdict: rejected}}
      - name: Elsewhere
        type: set_variable
        vars: {{verdict: elsewhere}}
"""


def _routes(next_target: str) -> list[tuple[str, str, str | None]]:
    res = compile_yaml(_YAML.format(next=next_target), PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]
    names = {f"/api/3/workflow_steps/{s['uuid']}": s["name"] for s in wf["steps"]}
    return [(names[r["sourceStep"]], names[r["targetStep"]], r.get("label")) for r in wf["routes"]]


def test_next_matching_an_option_target_leaves_only_the_labelled_route():
    routes = _routes("Approved")
    assert Counter((s, t) for s, t, _ in routes).most_common(1)[0][1] == 1
    assert ("Approve", "Approved", "approve") in routes
    assert ("Approve", "Rejected", "reject") in routes


def test_next_to_a_step_no_option_reaches_is_still_emitted():
    assert ("Approve", "Elsewhere", None) in _routes("Elsewhere")


def test_decision_next_matching_a_condition_target_leaves_only_the_labelled_route():
    """A decision with a default row AND a `next:` that is also a condition's
    target (seen in a connector's bundled playbook): the emitter only folds
    `next:` into an Else row when there is no default, so it used to emit an
    unlabelled route beside the labelled one."""
    res = compile_yaml("""
collection: dup decision routes
playbooks:
  - name: wf
    steps:
      - name: trigger
        type: start
        next: Check
      - name: Check
        type: decision
        next: Rotate
        conditions:
          - display: Invalid - rotate
            when: "{{ vars.valid | default(false) != true }}"
            next: Rotate
          - display: Valid
            default: true
            next: Healthy
      - name: Rotate
        type: set_variable
        vars: {outcome: rotated}
      - name: Healthy
        type: set_variable
        vars: {outcome: healthy}
""", PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    wf = res.fsr_json["data"][0]["workflows"][0]
    names = {f"/api/3/workflow_steps/{s['uuid']}": s["name"] for s in wf["steps"]}
    routes = [(names[r["sourceStep"]], names[r["targetStep"]], r.get("label")) for r in wf["routes"]
              if names[r["sourceStep"]] == "Check"]
    assert sorted(routes) == [("Check", "Healthy", "Valid"), ("Check", "Rotate", "Invalid - rotate")]
