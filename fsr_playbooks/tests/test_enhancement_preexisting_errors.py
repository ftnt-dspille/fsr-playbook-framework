"""A problem the open playbook already had does not block an unrelated edit.

Live on 8.0: a playbook that referenced an undeclared `vars.input.params.rec`
could not take a one-step addition. The edit carried the old error forward, the
gate called it the edit's, edit_playbook refused four times, and the turn ended
with no offer. Orphan steps were already grandfathered; every other required
fix was not.

The exemption must stay narrow: an error the edit INTRODUCES still blocks.
"""
from fsr_playbooks.mcp_server.tools_enhancement import verify_enhancement

_BEFORE = """
collection: C
description: d
playbooks:
  - name: P
    description: d
    steps:
      - name: start
        type: start
        next: Note It
      - name: Note It
        type: set_variable
        vars:
          note: "{{ vars.input.params.rec }}"
"""

_ADD_STEP = _BEFORE + """        next: Mark Reviewed
      - name: Mark Reviewed
        type: set_variable
        vars:
          reviewed: true
"""

_ADD_BROKEN_STEP = _BEFORE + """        next: Mark Reviewed
      - name: Mark Reviewed
        type: set_variable
        vars:
          reviewed: "{{ vars.input.params.other }}"
"""


def test_an_error_the_playbook_already_had_does_not_block_the_edit():
    r = verify_enhancement(_BEFORE, _ADD_STEP)
    assert r["ready_to_push"] is True
    assert r["required_fixes"] == []
    assert r["verified_id"]
    old = [w for w in r["warnings"] if w.get("pre_existing")]
    assert old and "params.rec" in old[0]["message"]
    # The card folds it under "existing issues", not the edit's own warnings.
    assert old[0]["in_change"] is False and old[0]["step_name"] == "Note It"


def test_an_error_the_edit_introduces_still_blocks():
    r = verify_enhancement(_BEFORE, _ADD_BROKEN_STEP)
    assert r["ready_to_push"] is False
    assert r["verified_id"] is None
    blocking = [f["message"] for f in r["required_fixes"]]
    assert any("params.other" in m for m in blocking)
    assert not any("params.rec" in m for m in blocking)


# The exemption must not cover a HALF-FIX. Live (sweep repair row): the edit
# fixed `vars.steps.gate_step` in one step and left the identical broken
# reference in the next; grandfathered as pre-existing, the half-fix was
# offered as verified.
_TWO_BAD_REFS = """
collection: C
description: d
playbooks:
  - name: P
    description: d
    steps:
      - name: start
        type: start
        next: Gate Step
      - name: Gate Step
        type: set_variable
        vars:
          ip: "1.2.3.4"
        next: Use One
      - name: Use One
        type: set_variable
        vars:
          a: "{{ vars.steps.gate_step.ip }}"
        next: Use Two
      - name: Use Two
        type: set_variable
        vars:
          b: "{{ vars.steps.gate_step.ip }}"
"""


def test_fixing_one_instance_of_a_defect_makes_the_other_instances_block():
    half = _TWO_BAD_REFS.replace(
        'a: "{{ vars.steps.gate_step.ip }}"', 'a: "{{ vars.steps.Gate_Step.ip }}"')
    r = verify_enhancement(_TWO_BAD_REFS, half)
    assert r["ready_to_push"] is False
    (left,) = r["required_fixes"]
    assert "use_two" in left["message"] and "fix every instance" in left["message"]
    assert not [w for w in r["warnings"] if w.get("pre_existing")
                and "gate_step" in w.get("message", "")]


def test_fixing_every_instance_passes():
    whole = _TWO_BAD_REFS.replace("vars.steps.gate_step.ip", "vars.steps.Gate_Step.ip")
    assert verify_enhancement(_TWO_BAD_REFS, whole)["ready_to_push"] is True


def test_an_unrelated_edit_still_grandfathers_both():
    add = _TWO_BAD_REFS + """        next: Mark
      - name: Mark
        type: set_variable
        vars:
          done: true
"""
    r = verify_enhancement(_TWO_BAD_REFS, add)
    assert r["ready_to_push"] is True
