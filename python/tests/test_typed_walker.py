"""Hermetic tests for compiler.typed_walker.

Synthetic IR — no DB, no parser, no live calls. Each test builds a
Collection in Python and asserts on the walk result.
"""
from __future__ import annotations

from compiler.ir import Collection, Playbook, Step
from compiler.typed_walker import (
    BranchResult,
    walk_playbook,
)


def _coll(*steps: Step, trigger_id: str | None = None) -> Collection:
    pb = Playbook(
        name="pb1",
        trigger_step_id=trigger_id or steps[0].id,
        steps=list(steps),
    )
    return Collection(name="c", playbooks=[pb])


def test_linear_set_variable_chain_resolves():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="set"),
        Step(id="set", type="set_variable", name="set vars",
             arguments={"arg_list": [{"key": "foo", "value": "bar"}]},
             next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "echoed",
                                       "value": "{{ vars.steps.set_vars.foo }}"}]}),
    )
    res = walk_playbook(coll)
    assert len(res.branches) == 1
    assert res.diagnostics == []


def test_unreachable_step_reference():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="a"),
        # `b` is not on this branch.
        Step(id="a", type="set_variable", name="a",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.b.foo }}"}]}),
        Step(id="b", type="set_variable", name="b",
             arguments={"arg_list": [{"key": "foo", "value": "1"}]}),
    )
    res = walk_playbook(coll)
    codes = {d.code for d in res.diagnostics}
    assert "unreachable_step_reference" in codes


def test_case_or_punct_mismatch_emits_unknown_with_did_you_mean():
    """Regression: agent typed `Re_fetch_Ticket` but the step's display
    name produces jinja_key `Re-fetch_Ticket` (hyphen preserved). Should
    surface as `unknown_step_reference` with a did-you-mean, NOT as the
    misleading `unreachable_step_reference`."""
    coll = _coll(
        Step(id="start", type="start", name="Start", next="refetch"),
        Step(id="refetch", type="set_variable", name="Re-fetch Ticket",
             arguments={"arg_list": [{"key": "foo", "value": "1"}]},
             next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                      "value": "{{ vars.steps.Re_fetch_Ticket.foo }}"}]}),
    )
    res = walk_playbook(coll)
    diags = [d for d in res.diagnostics
             if d.code in ("unknown_step_reference",
                           "unreachable_step_reference")]
    assert len(diags) == 1
    assert diags[0].code == "unknown_step_reference"
    assert "Re-fetch_Ticket" in diags[0].message  # the suggested correct key


def test_unknown_step_reference_when_step_doesnt_exist():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="a"),
        Step(id="a", type="set_variable", name="a",
             arguments={"arg_list": [{"key": "x",
                                      "value": "{{ vars.steps.nonexistent.foo }}"}]}),
    )
    res = walk_playbook(coll)
    codes = {d.code for d in res.diagnostics}
    assert "unknown_step_reference" in codes
    assert "unreachable_step_reference" not in codes


def test_missing_field_on_set_variable_output():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="set"),
        Step(id="set", type="set_variable", name="set",
             arguments={"arg_list": [{"key": "known", "value": "1"}]},
             next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.set.missing }}"}]}),
    )
    res = walk_playbook(coll)
    codes = [d.code for d in res.diagnostics]
    assert "missing_field_on_step_output" in codes


def test_decision_forks_into_two_branches():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="d"),
        Step(id="d", type="decision", name="d",
             branches={"yes": "a", "no": "b"}),
        Step(id="a", type="set_variable", name="a",
             arguments={"arg_list": [{"key": "ax", "value": "1"}]}),
        Step(id="b", type="set_variable", name="b",
             arguments={"arg_list": [{"key": "bx", "value": "1"}]}),
    )
    res = walk_playbook(coll)
    assert len(res.branches) == 2
    labels = sorted(b.name for b in res.branches)
    assert any("yes" in l for l in labels)
    assert any("no" in l for l in labels)


def test_manual_input_branches_and_input_shape():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="mi"),
        Step(id="mi", type="manual_input", name="mi",
             arguments={
                 "inputVariables": [
                     {"name": "reason", "kind": "text"},
                     {"name": "count", "kind": "integer"},
                 ],
                 "options": [
                     {"label": "approve", "next": "ok"},
                     {"label": "deny", "next": "bad"},
                 ],
             }),
        Step(id="ok", type="set_variable", name="ok",
             arguments={"arg_list": [{"key": "r",
                                       "value": "{{ vars.steps.mi.input.reason }}"}]}),
        Step(id="bad", type="set_variable", name="bad",
             arguments={"arg_list": [{"key": "r",
                                       "value": "{{ vars.steps.mi.input.nonexistent }}"}]}),
    )
    res = walk_playbook(coll)
    # Two branches.
    assert len(res.branches) == 2
    # Approve branch has no diag; deny branch has missing_field.
    by_name = {b.name: b for b in res.branches}
    approve = next(b for k, b in by_name.items() if "approve" in k)
    deny = next(b for k, b in by_name.items() if "deny" in k)
    assert approve.diagnostics == []
    assert any(d.code == "missing_field_on_step_output" for d in deny.diagnostics)


def test_cycle_does_not_infinite_loop():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="a"),
        Step(id="a", type="set_variable", name="a",
             arguments={"arg_list": []}, next="b"),
        Step(id="b", type="set_variable", name="b",
             arguments={"arg_list": []}, next="a"),  # cycle
    )
    res = walk_playbook(coll)
    # Should complete and produce at least one branch.
    assert len(res.branches) >= 1


def test_connector_unsafe_yields_unknown_warning():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="op"),
        Step(id="op", type="connector_op", name="op",
             arguments={"connector": "fortigate", "operation": "block_ip"},
             next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.op.result_id }}"}]}),
    )
    res = walk_playbook(coll, op_safety_fn=lambda c, o: "unsafe")
    # Downstream of unknown shape → warning, not error.
    warns = [d for d in res.diagnostics if d.severity == "warning"]
    assert any(d.code == "unknown_shape_downstream_reference" for d in warns)


def test_connector_safe_with_probe_callback():
    def probe(c, o, args):
        return {"kind": "object", "keys": {
            "ip": {"kind": "scalar", "type": "string"},
            "blocked": {"kind": "scalar", "type": "boolean"},
        }}

    coll = _coll(
        Step(id="start", type="start", name="Start", next="op"),
        Step(id="op", type="connector_op", name="op",
             arguments={"connector": "fortigate", "operation": "get_status"},
             next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.op.ip }}"}]}),
    )
    res = walk_playbook(
        coll,
        op_safety_fn=lambda c, o: "safe",
        probe=probe,
    )
    assert res.diagnostics == []


def test_self_reference_universal_key_ok():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="s"),
        Step(id="s", type="set_variable", name="s",
             arguments={"arg_list": [
                 {"key": "self_status", "value": "{{ vars.steps.s.status }}"},
             ]}),
    )
    res = walk_playbook(coll)
    assert res.diagnostics == []


def test_self_reference_non_universal_key_fails():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="s"),
        Step(id="s", type="set_variable", name="s",
             arguments={"arg_list": [
                 {"key": "self_x", "value": "{{ vars.steps.s.self_x }}"},
             ]}),
    )
    res = walk_playbook(coll)
    assert any(d.code == "missing_field_on_step_output" for d in res.diagnostics)


def test_find_record_shape_is_list_with_module_fields():
    def module_fields(m):
        return ["id", "name", "severity"] if m == "alerts" else []

    coll = _coll(
        Step(id="start", type="start", name="Start", next="find"),
        Step(id="find", type="find_record", name="find",
             arguments={"module": "alerts"}, next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.find[0].severity }}"}]}),
    )
    res = walk_playbook(coll, module_fields_fn=module_fields)
    assert res.diagnostics == []


def test_find_record_missing_field_is_error():
    def module_fields(m):
        return ["id", "name"]

    coll = _coll(
        Step(id="start", type="start", name="Start", next="find"),
        Step(id="find", type="find_record", name="find",
             arguments={"module": "alerts"}, next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.find[0].nope }}"}]}),
    )
    res = walk_playbook(coll, module_fields_fn=module_fields)
    assert any(d.code == "missing_field_on_step_output"
               for d in res.diagnostics)


def test_non_list_indexed_is_error():
    coll = _coll(
        Step(id="start", type="start", name="Start", next="set"),
        Step(id="set", type="set_variable", name="set",
             arguments={"arg_list": [{"key": "scalar", "value": "1"}]},
             next="use"),
        Step(id="use", type="set_variable", name="use",
             arguments={"arg_list": [{"key": "x",
                                       "value": "{{ vars.steps.set.scalar[0] }}"}]}),
    )
    res = walk_playbook(coll)
    assert any(d.code == "non_list_indexed" for d in res.diagnostics)
