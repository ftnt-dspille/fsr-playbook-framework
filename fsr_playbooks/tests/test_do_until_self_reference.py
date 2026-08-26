"""A `do_until` condition reading its own step is a poll, not a mistake.

`vars.steps.<self>.data` is normally a real error: the step's result does not
exist while its own arguments are being rendered. Two places are evaluated
AFTER the step runs and are therefore exempt -- `step_variables`, which was
already handled, and `do_until.condition`, which was not.

A poll is a self-reference BY CONSTRUCTION. The only thing worth re-testing is
what the step just returned, so warning here means warning on every poll anyone
writes -- which trains people to ignore the diagnostic that would have caught a
real typo. Live-verified on 8.0.0 that such a condition loops and exits.
"""
from fsr_playbooks.compiler.parser import parse_yaml
from fsr_playbooks.compiler.typed_walker import walk_playbook

CODE = "missing_field_on_step_output"


def _diags(yaml_text):
    coll, _ = parse_yaml(yaml_text)
    res = walk_playbook(coll, None)
    return [d for b in res.branches for d in b.diagnostics if d.code == CODE]


_POLL = """
name: C
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: Await Collection
      - name: Await Collection
        type: connector
        connector: generic-http
        operation: http_get
        params: {rest_api: /api/v1/fleet/hosts/1}
        retry:
          times: 5
          delay: 2
          until: "{{ vars.steps.Await_Collection.data.body.host.refetch_requested == false }}"
"""

_BODY = """
name: C
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: Await Collection
      - name: Await Collection
        type: connector
        connector: generic-http
        operation: http_get
        params:
          rest_api: "/api/v1/fleet/{{ vars.steps.Await_Collection.data.body.id }}"
"""


def test_do_until_condition_may_read_its_own_step():
    assert _diags(_POLL) == []


def test_the_same_path_outside_do_until_is_still_flagged():
    """The exemption is scoped to the loop test, not to the whole step.

    Without this, the fix would be indistinguishable from deleting the check:
    a step whose *params* read its own unrendered result is the real bug the
    diagnostic exists for, and it has to keep firing.
    """
    hits = _diags(_BODY)
    assert len(hits) == 1
    assert "self-reference" in hits[0].message
