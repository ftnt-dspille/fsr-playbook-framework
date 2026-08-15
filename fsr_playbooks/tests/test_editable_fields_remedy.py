"""The approval card's own error must not send the model in a circle.

`emit_action_card` rejects an `editable_fields` entry that has no value in
`args`, and used to prescribe one remedy for every case: "add it to args with
\"\" for blank". For a SELECT parameter that value is exactly what the param
validator refuses, so the two errors chase each other:

    add vdom+ngfw_mode to args   -> bad_params (ngfw_mode='' not in options)
    drop them from args          -> editable_fields_not_in_args
    add them back                -> bad_params ...

Measured on `contain_block_ip_direct` (calibrate run 20260815T152033Z): every
one of five repeats bounced off this at least once and one spent FIVE of its
ten budgeted tool calls staging a single card. The card is the P2 approval
gate, so the cost lands on the one step that must always be reachable.

The handling is therefore split by what the operation actually accepts:

  optional free-form -> HEAL it (prefill blank and render the card). Listing
                        the field already stated the intent; asking the model
                        to restate it is a toll on the approval gate, paid
                        once per card on every containment.
  select             -> error naming the real options, or drop the field
  required           -> error; a blank cannot stand in for a real value
  not a param at all -> error; adding it to args can only fail
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server.tools_emit import emit_action_card

CONNECTOR, OP = "fortigate-firewall", "block_ip_new"
# A valid, complete call -- so every failure below is the editable_fields
# remedy under test and not an unrelated missing-required-param bounce.
BASE_ARGS = {"method": "Quarantine Based", "ip_addresses": "1.2.3.4",
             "time_to_live": "Never"}
_fn = getattr(emit_action_card, "fn", emit_action_card)


def _emit(editable, args):
    return _fn(id="c1", connector=CONNECTOR, operation=OP,
               summary="block the C2", args=args, editable_fields=editable)


@pytest.fixture(autouse=True)
def _needs_catalogued_op():
    from fsr_playbooks.mcp_server._shared import op_param_facts
    opts = op_param_facts(CONNECTOR, OP)
    if not opts or "ngfw_mode" not in opts:
        pytest.skip("reference store has no params for this op")


def test_select_field_is_not_told_to_prefill_blank() -> None:
    """The livelock in one assertion: '' is what the select rejects."""
    out = _emit(["ngfw_mode"], dict(BASE_ARGS))
    assert out["ok"] is False
    msg = out["message"]
    assert "ngfw_mode" in msg and "select" in msg
    # It must name the real options instead of prescribing a blank.
    assert "Profile Based" in msg and "Policy Based" in msg
    assert 'prefilled ("" for blank)' not in msg.split("select")[1], (
        f"still advising a blank for a select: {msg}")


def test_unknown_field_is_told_to_drop_not_add() -> None:
    out = _emit(["not_a_real_param"], dict(BASE_ARGS))
    assert out["ok"] is False
    msg = out["message"]
    assert "not_a_real_param" in msg
    assert "remove" in msg, f"adding an unknown param can only fail: {msg}"


def test_optional_free_form_field_is_healed_not_bounced() -> None:
    """The one case with a single sensible outcome must not cost a round trip.

    Listing a field in editable_fields already says "let the analyst supply
    this". For an optional free-form param, prefilling blank IS that intent,
    so asking the model to restate it is a toll paid once per card on every
    containment -- measured as exactly one wasted call per carding run.
    """
    out = _emit(["vdom"], dict(BASE_ARGS))
    assert out["ok"] is True, out
    assert out["card"]["args"]["vdom"] == ""
    assert "vdom" in out["card"]["editable_fields"]


def test_healing_does_not_mutate_the_caller_s_args() -> None:
    caller_args = dict(BASE_ARGS)
    _emit(["vdom"], caller_args)
    assert "vdom" not in caller_args


def test_a_mixed_card_reports_only_what_the_model_must_fix() -> None:
    """Heal the blanks, ask about the rest -- and don't re-list the healed."""
    out = _emit(["vdom", "ngfw_mode"], dict(BASE_ARGS))
    assert out["ok"] is False
    assert "ngfw_mode" in out["message"]
    assert "vdom" not in out["message"], (
        f"re-asking about a field it could have filled: {out['message']}")


def test_the_remedy_actually_terminates() -> None:
    """Follow the message's own instruction; the next call must pass.

    A message that is merely more specific is worth nothing if applying it
    still bounces -- that was the whole defect.
    """
    first = _emit(["vdom", "ngfw_mode"], dict(BASE_ARGS))
    assert first["ok"] is False
    # ngfw_mode: drop it (one of the two offered remedies). vdom then heals.
    out = _emit(["vdom"], dict(BASE_ARGS))
    assert out["ok"] is True, out
