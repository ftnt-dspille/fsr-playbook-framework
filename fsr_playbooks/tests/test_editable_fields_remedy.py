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

The remedy therefore has to be split by what the operation actually accepts:
free-form param -> prefill blank; select -> name the options or drop the
field; unknown name -> drop the field (adding it can only fail).
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
    from fsr_playbooks.mcp_server._shared import op_param_options
    opts = op_param_options(CONNECTOR, OP)
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


def test_free_form_field_still_gets_the_blank_prefill_remedy() -> None:
    """The original advice is correct here and must survive."""
    out = _emit(["vdom"], dict(BASE_ARGS))
    assert out["ok"] is False
    assert "vdom" in out["message"]
    assert '"" for blank' in out["message"]


def test_the_remedy_actually_terminates() -> None:
    """Follow the message's own instruction; the next call must pass.

    A message that is merely more specific is worth nothing if applying it
    still bounces -- that was the whole defect.
    """
    args = dict(BASE_ARGS)
    first = _emit(["vdom", "ngfw_mode"], args)
    assert first["ok"] is False
    # vdom: prefill blank.  ngfw_mode: drop it (the other offered remedy).
    out = _emit(["vdom"], {**args, "vdom": ""})
    assert out["ok"] is True, out
