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
  select, required   -> STAGE it, left out of args: the card carries the
                        field schema, the widget renders the select with its
                        options and keeps Approve disabled until it is filled.
                        Refusing it sent the model to ask in prose live ("I
                        need duration and time_to_live"), and the analyst's
                        answer then re-ran the whole hunt.
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


def test_a_select_is_left_for_the_analyst_on_the_card() -> None:
    """No blank (the select refuses ""), no error: the analyst picks it."""
    out = _emit(["ngfw_mode"], dict(BASE_ARGS))
    assert out["ok"] is True, out
    assert "ngfw_mode" in out["card"]["editable_fields"]
    assert "ngfw_mode" not in out["card"]["args"]


def test_a_required_field_is_left_for_the_analyst_on_the_card() -> None:
    args = {k: v for k, v in BASE_ARGS.items() if k != "time_to_live"}
    out = _emit(["time_to_live"], args)
    assert out["ok"] is True, out
    assert "time_to_live" in out["card"]["editable_fields"]
    assert "time_to_live" not in out["card"]["args"]


def test_a_required_field_not_offered_on_the_card_is_still_refused() -> None:
    args = {k: v for k, v in BASE_ARGS.items() if k != "time_to_live"}
    out = _emit([], args)
    assert out["ok"] is False


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


def test_a_mixed_card_heals_the_blank_and_leaves_the_select() -> None:
    out = _emit(["vdom", "ngfw_mode"], dict(BASE_ARGS))
    assert out["ok"] is True, out
    assert out["card"]["args"]["vdom"] == ""
    assert "ngfw_mode" not in out["card"]["args"]


def test_an_unknown_field_mixed_in_names_only_that_field() -> None:
    out = _emit(["vdom", "ngfw_mode", "not_a_real_param"], dict(BASE_ARGS))
    assert out["ok"] is False
    assert "not_a_real_param" in out["message"]
    assert "vdom" not in out["message"] and "ngfw_mode" not in out["message"]


def test_editable_fields_written_as_args_paths_mean_the_args_keys() -> None:
    """Live, an unattended containment named its editable fields as paths
    ("args.method", "args.ip"), was told twice the op has no such parameter,
    and the turn ended with nothing staged."""
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    args = dict(BASE_ARGS)
    out = emit_card(card_type="action", payload={
        "id": "c1", "connector": CONNECTOR, "operation": OP,
        "summary": "block the C2", "args": args,
        "editable_fields": [f"args.{k}" for k in args]})
    assert out.get("ok") is not False, out
    card = out.get("card") or out
    assert card["editable_fields"] == list(args)
