"""`edit_playbook`: a step renamed in the same batch as an update to that step.

Live: the analyst asked to replace a placeholder connector step. The batch was
update_step (new connector, new params) on "No Operation", rename_step "No
Operation" -> "Block IPv4 Addresses", and an update to the manual step that
routes to it. The verifier reported the placeholder as `step_dropped`, an error
that blocks the push, although nothing was deleted. It is a rename the analyst
asked for by name.

Cause: the structural diff pairs a dropped name with an added name only by
uuid or by projection (the step's content minus its name). An open playbook
without uuids pairs by projection, and the update in the same batch changed the
projection, so the rename was never paired. The rename op itself was the one
piece of evidence that said the two names were one step, and the pairing did
not use it.

The open playbook here is the raw text, with no uuids, as an authored or
exported playbook reads before a designer round trip.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from fsr_playbooks.mcp_server import _verified_yaml  # noqa: E402
from fsr_playbooks.mcp_server._shared import (  # noqa: E402
    reset_grounded_yaml,
    set_grounded_yaml,
)
from fsr_playbooks.mcp_server.tools_enhancement import edit_playbook  # noqa: E402

RAW_OPEN = """collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, module: alerts, next: No Operation}
      - {name: No Operation, type: connector, connector: cyops_utilities, operation: no_op, params: {}, next: Notify}
      - {name: Notify, type: set_variable, vars: {a: "1"}}
"""


@pytest.fixture(autouse=True)
def grounded():
    _verified_yaml.clear()
    tok = set_grounded_yaml(RAW_OPEN)
    yield
    reset_grounded_yaml(tok)
    _verified_yaml.clear()


def _kinds(out):
    return {r.get("kind"): r for r in (out.get("regressions") or [])}


def test_rename_with_an_update_to_the_same_step_is_not_a_dropped_step():
    """Red before the fix: the renamed step is reported `step_dropped`."""
    ops = [
        {"op": "update_step", "name": "No Operation",
         "set": {"connector": "fortigate-firewall", "operation": "block_ip_new",
                 "params": {"method": "Quarantine Based"}}},
        {"op": "rename_step", "name": "No Operation", "to": "Block IPv4 Addresses"},
    ]
    out = edit_playbook(ops, user_message=(
        "Replace the No Operation step with a real connector action that blocks "
        "the IPv4 addresses."))
    kinds = _kinds(out)
    assert "step_dropped" not in kinds, (
        f"a step renamed by the batch was reported dropped: {out.get('regressions')}")
    assert "step_renamed_as_requested" in kinds, (
        f"the requested rename was not paired with its step: {out.get('regressions')}")
    assert kinds["step_renamed_as_requested"]["before"] == "No Operation"
    assert kinds["step_renamed_as_requested"]["after"] == "Block IPv4 Addresses"


def test_rename_alone_is_still_paired():
    """Control: a rename with no other change pairs by projection, as before."""
    ops = [{"op": "rename_step", "name": "Notify", "to": "Tell the analyst"}]
    out = edit_playbook(ops, user_message="Rename the Notify step to Tell the analyst.")
    kinds = _kinds(out)
    assert "step_dropped" not in kinds
    assert "step_renamed_as_requested" in kinds


def test_a_step_that_is_really_gone_is_still_dropped():
    """The fix must not hide a real drop: no rename op names the removed step,
    so it stays an error."""
    ops = [
        {"op": "update_step", "name": "No Operation",
         "set": {"connector": "fortigate-firewall", "operation": "block_ip_new"}},
        {"op": "remove_step", "name": "Notify"},
    ]
    out = edit_playbook(ops, user_message="Replace the No Operation step.")
    kinds = _kinds(out)
    assert "step_dropped" in kinds, out.get("regressions")
    assert kinds["step_dropped"]["step"] == "Notify"
