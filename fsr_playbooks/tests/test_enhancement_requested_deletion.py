"""A deletion the analyst ASKED for is not a dropped step.

`step_dropped` fired unconditionally at error severity, so an analyst who
typed "delete the 'Dead End' step" got their own request back as a blocking
regression. Live probe A3 caught it end to end on 8.0: EVERY check passed --
compile clean, typed_walk clean, per_step_schema clean -- and this was the
only finding, so `ready_to_push` went false, and the model responded by
narrating a refusal and asking how to proceed rather than delivering the edit.
That is the behaviour filed as #132 ("model narrates instead of calling
emit_patch_proposal"); the model was not being lazy, it was being told its
edit was broken. The change only reached the box because the connector's
salvage fabricated a `patch_proposal` around the failed verification.

This is the exemption `step_renamed_as_requested` already had, applied to the
sibling branch that never got it -- see [[parallel_name_lists_drift_bug_class]]:
three branches in one function, two intent-aware, one left behind.

The exemption must be narrow in BOTH directions, which is what these pin:
mentioning a step is not permission to delete it, and a delete verb aimed at
one step is not permission to drop another.

The write is still guarded. `prewrite.check_prewrite` refuses a save that drops
a step unless the caller acknowledges it -- and unlike this gate it HAS an
acknowledgement path. Two fail-closed gates in series with no way through is
what made a deletion impossible to perform at all.
"""
from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.mcp_server.tools_enhancement import _diff_collections

_BEFORE = """
collection: Deletion Fixtures
description: before/after fixture for the requested-deletion exemption.

playbooks:
  - name: Suspicious IP Response
    description: fixture.
    steps:
      - name: start
        type: start
        next: Enrich IP
      - name: Enrich IP
        type: set_variable
        next: Dead End
        vars:
          reputation: unknown
      - name: Dead End
        type: set_variable
        next: Note It
        vars:
          noop: true
      - name: Note It
        type: set_variable
        vars:
          note: done
"""

# "Dead End" removed and the flow rewired around it, as a real edit would.
_DELETED = """
collection: Deletion Fixtures
description: before/after fixture for the requested-deletion exemption.

playbooks:
  - name: Suspicious IP Response
    description: fixture.
    steps:
      - name: start
        type: start
        next: Enrich IP
      - name: Enrich IP
        type: set_variable
        next: Note It
        vars:
          reputation: unknown
      - name: Note It
        type: set_variable
        vars:
          note: done
"""


def _regressions(after: str, user_message):
    before_coll, _ = parse_yaml(_BEFORE)
    after_coll, _ = parse_yaml(after)
    regs, _ = _diff_collections(before_coll, after_coll, user_message)
    return {r["kind"]: r for r in regs}


def test_a_requested_deletion_is_a_warning_not_a_blocker():
    """THE A3 defect, in the words the probe actually used."""
    regs = _regressions(_DELETED, "Delete the step named 'Dead End'. "
                                  "Keep every other step exactly as it is.")
    assert "step_dropped" not in regs, (
        "the analyst's own deletion came back as a blocking regression"
    )
    r = regs["step_deleted_as_requested"]
    assert r["severity"] == "warning"
    assert r["step"] == "Dead End"


def test_no_error_severity_regression_survives_a_requested_deletion():
    """`ready_to_push` keys off error severity, so this is the property that
    actually decides whether the turn can deliver."""
    regs = _regressions(_DELETED, "delete the Dead End step")
    blocking = [k for k, r in regs.items() if r["severity"] == "error"]
    assert not blocking, f"still blocking on {blocking}"


def test_the_consequence_still_reaches_the_analyst():
    """Demoting it must not hide it -- deleting a step breaks anything reading
    vars.steps.<slug>.* off it, and that has to be readable even when asked
    for. Same contract as the requested-rename warning."""
    regs = _regressions(_DELETED, "delete the Dead End step")
    assert "vars.steps" in regs["step_deleted_as_requested"]["message"]


def test_the_removal_is_still_reported_in_the_diff():
    """The exemption changes severity, not visibility."""
    before_coll, _ = parse_yaml(_BEFORE)
    after_coll, _ = parse_yaml(_DELETED)
    _, summary = _diff_collections(before_coll, after_coll,
                                   "delete the Dead End step")
    assert "Dead End" in summary["steps_removed"]
    assert any(c["step"] == "Dead End" and c["kind"] == "removed"
               for c in summary["changes"])


def test_naming_a_step_is_not_permission_to_delete_it():
    """The narrowing that keeps this from being a licence to drop steps. The
    step IS named, so `referenced` contains it, but nothing in the ask is a
    deletion -- so the old error stands."""
    regs = _regressions(_DELETED,
                        "add a note to the Dead End step explaining the flow")
    assert regs["step_dropped"]["severity"] == "error"
    assert "step_deleted_as_requested" not in regs


def test_a_delete_verb_aimed_elsewhere_does_not_exempt_this_step():
    """A delete verb in the message is not a blanket licence: the step must
    ALSO be the one the analyst named."""
    regs = _regressions(_DELETED, "delete the Note It step")
    assert regs["step_dropped"]["severity"] == "error", (
        "a deletion the analyst asked for on a DIFFERENT step exempted this one"
    )


def test_without_a_user_message_a_drop_is_still_an_error():
    """No chat context (eval harness / direct agent call) means no intent to
    read, and the safe reading of a vanished step is that nobody asked."""
    regs = _regressions(_DELETED, None)
    assert regs["step_dropped"]["severity"] == "error"


def test_other_phrasings_of_the_same_request_are_honoured():
    """The verb list is literal by design, but it has to cover how analysts
    actually ask -- a missed phrasing shows up as their request being called
    an error."""
    for msg in ("remove the Dead End step",
                "get rid of the Dead End step",
                "take out Dead End",
                "we no longer need the Dead End step"):
        regs = _regressions(_DELETED, msg)
        assert "step_deleted_as_requested" in regs, f"not honoured: {msg!r}"
        assert regs["step_deleted_as_requested"]["severity"] == "warning"


# --------------------------------------------------------------------------- #
# The intent has to REACH the gate.
#
# Every exemption above reads `user_message`, which is an OPTIONAL tool
# argument -- and live on 8.0 the box model called
# `verify_enhancement(before_yaml, after_yaml)` with no `user_message` at all.
# So the analyst typed "Delete the step named 'Dead End'", the gate never saw
# it, and the exemption was dead code that passed its own unit tests.
#
# Same finding as tracker #60 (`requested_by` declared on 0 of 4 live calls):
# derive the intent, never depend on the model to pass it. These pin the
# derivation, because the fix above is worthless without it.
# --------------------------------------------------------------------------- #

import pytest

from fsr_playbooks.mcp_server._shared import (
    reset_turn_user_message,
    set_turn_user_message,
)
from fsr_playbooks.mcp_server.tools_enhancement import verify_enhancement


@pytest.fixture
def turn_message():
    """Bind a turn's user message the way the chat loop does."""
    tokens = []

    def _bind(text):
        tokens.append(set_turn_user_message(text))

    yield _bind
    for t in reversed(tokens):
        reset_turn_user_message(t)


def _severities(result):
    return {r["kind"]: r["severity"] for r in result.get("regressions") or []}


def test_the_gate_reads_the_turns_message_when_the_model_omits_it(turn_message):
    """THE live shape: two positional args, no user_message."""
    turn_message("Delete the step named 'Dead End' and wire the rest straight "
                 "through. Change nothing else.")

    result = verify_enhancement(_BEFORE, _DELETED)

    sev = _severities(result)
    assert "step_dropped" not in sev, (
        "the analyst's deletion was still called an error -- the turn's message "
        "never reached the gate"
    )
    assert sev.get("step_deleted_as_requested") == "warning"


def test_deriving_the_message_unblocks_ready_to_push(turn_message):
    """The property the model actually acts on. `ready_to_push: False` is what
    made it narrate a refusal instead of delivering the edit."""
    turn_message("delete the Dead End step")
    assert verify_enhancement(_BEFORE, _DELETED)["ready_to_push"] is True


def test_without_a_bound_message_the_drop_still_blocks():
    """No turn context = no intent to read. Fails closed."""
    result = verify_enhancement(_BEFORE, _DELETED)
    assert _severities(result).get("step_dropped") == "error"
    assert result["ready_to_push"] is False


def test_an_explicit_argument_still_wins_over_the_bound_message(turn_message):
    """Eval harnesses and direct agent calls pass it explicitly; that must keep
    working, and must not be silently overridden by ambient turn state."""
    turn_message("delete the Dead End step")
    result = verify_enhancement(_BEFORE, _DELETED,
                                user_message="add a logging step")
    assert _severities(result).get("step_dropped") == "error", (
        "the ambient turn message overrode the caller's explicit argument"
    )
