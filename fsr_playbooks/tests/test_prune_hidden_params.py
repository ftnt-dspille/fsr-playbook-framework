"""A trace carrying two branches of a conditional must still compile.

The live shape (2026-08-01, live-integration `trace_recorded` on 8.0.0): the
agent ran `fortigate-firewall.block_ip_new` from an approved action card, and
the recorded call carried BOTH branches of two nested selects --
method='Quarantine Based' alongside the Policy-Based-only `ip_block_policy` and
`ip_type`, and time_to_live='1 Day' alongside `duration` (valid only under
'Custom Time'). The compiler rejects that as a param-set conflict, correctly:
FSR hides those fields and the call would not work as written.

The consequence was P4 failing on the exact op it exists to bottle -- the
containment step ran, the analyst approved it, and `build_playbook_from_trace`
produced nothing. The trace is not wrong to record what was sent; the BUILD is
wrong to emit fields FSR would never transmit. Pruning them is fidelity.

`prune_hidden_params` is driven with an explicit rules table here so the test
pins the logic rather than whatever the shipped catalog happens to contain.
"""
import pytest

from fsr_playbooks.compiler.skill_compiler import (
    _visible_params,
    prune_hidden_params,
)

# (param_name, parent_param_name, condition_value) -- the catalog's shape.
# Mirrors fortigate-firewall.block_ip_new's real nesting.
BLOCK_IP_NEW_RULES = [
    ("method", None, None),
    ("vdom", None, None),
    ("ip_block_policy", "method", "Policy Based"),
    ("ip_type", "method", "Policy Based"),
    ("ip", "method", "Policy Based"),
    ("ip_group_name", "method", "Policy Based"),
    ("ip_addresses", "method", "Quarantine Based"),
    ("time_to_live", "method", "Quarantine Based"),
    ("duration", "time_to_live", "Custom Time"),
]


def _rules_for(_connector, _operation):
    return BLOCK_IP_NEW_RULES


def _step(**params):
    return {"name": "Block IP", "type": "connector",
            "connector": "fortigate-firewall", "operation": "block_ip_new",
            "params": params}


def test_the_live_two_branch_trace_is_pruned_to_one_branch():
    """The regression itself, with the params exactly as recorded live."""
    step = _step(method="Quarantine Based", ip_block_policy="pol1",
                 ip_type="IPv4", ip="198.51.100.7", ip_addresses="198.51.100.7",
                 time_to_live="1 Day", duration=3600, vdom="root")
    dropped = prune_hidden_params(step, _rules_for)
    assert dropped == ["duration", "ip", "ip_block_policy", "ip_type"], dropped
    assert step["params"] == {
        "method": "Quarantine Based", "ip_addresses": "198.51.100.7",
        "time_to_live": "1 Day", "vdom": "root",
    }


def test_nested_gating_resolves_transitively():
    """`duration` is visible only when its parent chain is ALSO visible.

    A single pass over the rules keeps `duration` when time_to_live=='Custom
    Time' even if `method` rules time_to_live out entirely -- so the fixed
    point matters, not just a per-rule check.
    """
    keep = _step(method="Quarantine Based", time_to_live="Custom Time",
                 duration=3600)
    assert prune_hidden_params(keep, _rules_for) == []
    # Same time_to_live value, but the parent select excludes it: the whole
    # sub-branch goes, `duration` included.
    drop = _step(method="Policy Based", time_to_live="Custom Time",
                 duration=3600, ip_type="IPv4", ip="198.51.100.7")
    assert prune_hidden_params(drop, _rules_for) == ["duration", "time_to_live"]


def test_a_coherent_call_is_left_completely_alone():
    step = _step(method="Policy Based", ip_type="IPv4", ip="198.51.100.7",
                 ip_block_policy="pol1", vdom="root")
    before = dict(step["params"])
    assert prune_hidden_params(step, _rules_for) == []
    assert step["params"] == before


def test_ungated_and_unknown_keys_are_never_touched():
    """`vdom` has no gating parent; `config` isn't an operation param at all.

    Pruning anything the catalog doesn't list would strip step plumbing and
    silently break the emitted playbook.
    """
    step = _step(method="Quarantine Based", vdom="root")
    step["config"] = "fortigate-lab"
    assert prune_hidden_params(step, _rules_for) == []
    assert step["config"] == "fortigate-lab"
    assert step["params"]["vdom"] == "root"


def test_a_catalog_miss_leaves_the_step_unchanged():
    """No rules (unknown op, or no reference DB) must not mean "drop it all"."""
    step = _step(method="Quarantine Based", duration=3600)
    before = dict(step["params"])
    assert prune_hidden_params(step, lambda _c, _o: []) == []
    assert step["params"] == before


def test_a_raising_catalog_is_survived():
    def _boom(_c, _o):
        raise RuntimeError("db gone")

    step = _step(method="Quarantine Based", duration=3600)
    assert prune_hidden_params(step, _boom) == []
    assert step["params"]["duration"] == 3600


def test_non_connector_steps_are_ignored():
    step = {"name": "Set", "type": "set_variable", "vars": {"x": "1"}}
    assert prune_hidden_params(step, _rules_for) == []
    assert step["vars"] == {"x": "1"}


def test_visible_params_handles_a_param_with_several_rules():
    """Any ONE satisfied rule makes a param visible (rules are OR-ed)."""
    rules = [("mode", None, None),
             ("target", "mode", "A"),
             ("target", "mode", "B")]
    assert "target" in _visible_params(rules, {"mode": "B", "target": "t"})
    assert "target" not in _visible_params(rules, {"mode": "C", "target": "t"})


def test_connector_and_op_inside_arguments_still_prunes():
    """The shape that made this whole function a silent no-op on a live box.

    A trace whose recorded inputs carried an `arguments:` wrapper keeps
    `connector`/`operation` inside it rather than at step level. Reading only
    the step level meant prune_hidden_params returned [] before it ever
    consulted the catalog: the block_ip_new trace kept both branches, the
    compiler rejected the param-set conflict, and build_playbook_from_trace
    produced nothing -- the exact P4 failure this module exists to prevent,
    reappearing through a different step shape.
    """
    step = {"name": "Block IP", "type": "connector",
            "arguments": {"connector": "fortigate-firewall",
                          "operation": "block_ip_new",
                          "method": "Quarantine Based",
                          "ip_block_policy": "pol1", "ip_type": "IPv4",
                          "ip": "198.51.100.7", "ip_addresses": "198.51.100.7",
                          "time_to_live": "1 Day", "duration": 3600,
                          "vdom": "root"}}
    dropped = prune_hidden_params(step, _rules_for)
    assert dropped == ["duration", "ip", "ip_block_policy", "ip_type"], dropped
    # The routing keys are not op params and must survive the prune.
    assert step["arguments"]["connector"] == "fortigate-firewall"
    assert step["arguments"]["operation"] == "block_ip_new"
    assert step["arguments"]["method"] == "Quarantine Based"


def test_connector_in_the_arguments_wrapper_around_nested_params_still_prunes():
    """The shape that survived the FIRST fix and failed live a second time.

    When the `arguments:` wrapper also nests `params:`, the routing keys sit in
    the container BETWEEN the step and the params -- neither at step level (the
    original lookup) nor alongside the params (the first fix's lookup). The
    prune silently returned [] again, the block_ip_new trace kept both branches
    a second time, and P4 produced no playbook on a live box after a release
    that was supposed to have fixed exactly this.

    Hence the parametrised shapes below: pin every level, not the two that have
    burned us so far.
    """
    step = {"name": "Block IP", "type": "connector",
            "arguments": {"connector": "fortigate-firewall",
                          "operation": "block_ip_new",
                          "params": {"method": "Quarantine Based",
                                     "ip_block_policy": "pol1", "ip_type": "IPv4",
                                     "ip": "198.51.100.7",
                                     "ip_addresses": "198.51.100.7",
                                     "time_to_live": "1 Day", "duration": 3600,
                                     "vdom": "root"}}}
    dropped = prune_hidden_params(step, _rules_for)
    assert dropped == ["duration", "ip", "ip_block_policy", "ip_type"], dropped
    assert step["arguments"]["connector"] == "fortigate-firewall"
    assert step["arguments"]["params"]["method"] == "Quarantine Based"


@pytest.mark.parametrize("place_routing_keys", ["step", "container", "params"])
def test_routing_keys_are_found_at_every_level(place_routing_keys):
    """connector/operation appear at all three levels in real traces."""
    params = {"method": "Quarantine Based", "ip_block_policy": "pol1",
              "ip_type": "IPv4", "time_to_live": "1 Day", "duration": 3600}
    keys = {"connector": "fortigate-firewall", "operation": "block_ip_new"}
    step = {"name": "Block IP", "type": "connector", "arguments": {"params": params}}
    if place_routing_keys == "step":
        step.update(keys)
    elif place_routing_keys == "container":
        step["arguments"].update(keys)
    else:
        params.update(keys)

    assert prune_hidden_params(step, _rules_for) == ["duration", "ip_block_policy", "ip_type"]
