"""The live triage trace must compile -- driven through the SHIPPING path.

Captured from `.159` (8.0.0) on 2026-08-02, live-integration `trace_recorded`:
the agent enriched an IP, then ran `fortigate-firewall.block_ip_new` twice from
approved action cards. The recorded call carries both branches of two nested
selects -- method='Quarantine Based' with the Policy-Based-only
`ip_block_policy`/`ip_type`, and time_to_live='1 Day' with `duration` (valid
only under 'Custom Time').

This exists because `test_prune_hidden_params.py` drives `compile_trace`
DIRECTLY and was green through two releases that did not fix the bug.
`compile_and_verify` -- the function `build_playbook_from_trace` actually calls
-- re-emits every step from `call.resolved_inputs` AFTER compile_trace has
pruned, which threw the prune away. Unit tests one layer below the shipping
path proved nothing about the shipping path.

So: assert at the layer the connector calls, on the shape a real box produced.
"""
from fsr_playbooks.agent.skill_trace import SkillCall, SkillTrace
from fsr_playbooks.compiler.skill_verify import compile_and_verify

# The two-branch containment call exactly as the appliance recorded it.
_BLOCK_IP_NEW = {
    "connector": "fortigate-firewall",
    "operation": "block_ip_new",
    "method": "Quarantine Based",
    "ip_block_policy": "default_policy",
    "ip_group_name": "default_group",
    "ip_addresses": "198.51.100.7",
    "duration": 1440,
    "ip_type": "IPv4",
    "ip": "198.51.100.7",
    "time_to_live": "1 Day",
}

# Params the catalog says FSR hides given the chosen discriminators. FSR does
# not transmit these, so a playbook that names them cannot run.
_HIDDEN = {"ip_block_policy", "ip_type", "ip", "duration", "ip_group_name"}


def _live_trace() -> SkillTrace:
    trace = SkillTrace()
    trace.calls.append(SkillCall(
        skill_id="run_connector_action", step_name="Ioc Search",
        resolved_inputs={"connector": "fortinet-fortiguard-ioc",
                         "operation": "ioc_search", "indicator": "198.51.100.7"},
    ))
    trace.calls.append(SkillCall(
        skill_id="run_connector_action", step_name="Block Ip New",
        resolved_inputs=dict(_BLOCK_IP_NEW),
    ))
    return trace


def test_the_live_trace_emits_no_hidden_params():
    """The regression: compile_and_verify must not resurrect pruned params."""
    compiled = compile_and_verify(_live_trace())
    block = next(s for s in compiled["steps"] if s.get("name") == "Block Ip New")
    leaked = _HIDDEN & set(block)
    assert not leaked, (
        f"{sorted(leaked)} survived into the emitted step; FSR hides these at "
        f"runtime, so the compiled playbook cannot run"
    )
    # The chosen branch must survive intact -- pruning is fidelity, not deletion.
    assert block["method"] == "Quarantine Based"
    assert block["ip_addresses"] == "198.51.100.7"
    assert block["time_to_live"] == "1 Day"


def test_the_prune_is_reported_on_the_shipping_path():
    """`pruned` is the analyst-facing signal; it must survive the re-emit."""
    compiled = compile_and_verify(_live_trace())
    assert set(compiled.get("pruned", {}).get("Block Ip New", [])) >= {
        "duration", "ip_block_policy", "ip_type",
    }
