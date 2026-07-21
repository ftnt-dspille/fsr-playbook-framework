"""Declared playbook parameters must survive the round-trip.

A playbook's input form is built from the TRIGGER step's
`arguments.inputVariables[]`. The decompiler used to read declarations only
from the workflow's top-level `parameters` field — but on real appliance
content the two sources disagree:

  * most stock playbooks have `parameters: []` and declare everything on the
    trigger, and
  * some have a NON-EMPTY `parameters` that still omits names the trigger
    declares.

Either way the decompiled YAML came back referencing `vars.input.params.X`
with nothing declaring X, so the compiler rejected the decompiler's own
output. Found by pulling 400 stock playbooks from a live appliance: this one
bug accounted for 42 of the 122 hard compile failures, and fixing it moved the
corpus from 142/400 to 178/400 compiling clean.

Why it is worse than a normal fidelity gap — same reason as the dropped
`for_each`: the widget saves the agent's LAST ```yaml fence back OVER the open
record. So pull a playbook -> ask for any one-field edit -> save silently
stripped its entire manual-trigger input form, with no error and no diff the
analyst would think to re-check.
"""
from __future__ import annotations

import yaml

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler.decompiler import decompile_to_yaml

TRIGGER_UUID = "e77eec41-6212-468a-9128-63a2cead869c"


def _wf(top_level_params, input_var_names):
    """A minimal two-step workflow whose trigger declares `input_var_names`."""
    return {
        "name": "Action - Domain - Unblock",
        "description": "",
        "isActive": True,
        "parameters": top_level_params,
        "triggerStep": f"/api/3/workflow_steps/{TRIGGER_UUID}",
        "steps": [
            {
                "uuid": TRIGGER_UUID,
                "name": "Start",
                "stepType": "/api/3/workflow_step_types/"
                            "f4ca4d1c-8b1c-4a2a-9b53-9d0a2a5a1a11",
                "arguments": {
                    "route": "177547a1-b3cb-47ca-a186-743a675a79c4",
                    "title": "Action - Domain - Unblock",
                    "resources": ["indicators"],
                    "inputVariables": [
                        {"name": n, "type": "string", "label": n}
                        for n in input_var_names
                    ],
                },
            },
            {
                "uuid": "5f8ddf88-42e8-4b69-aff4-9fc07775a234",
                "name": "Add note",
                "stepType": "/api/3/workflow_step_types/"
                            "f4ca4d1c-8b1c-4a2a-9b53-9d0a2a5a1a22",
                "arguments": {},
            },
        ],
        "routes": [],
    }


def _parameters_of(wf: dict) -> list[str]:
    env = {"data": [{"name": "C", "description": "", "visible": True,
                     "workflows": [wf]}]}
    doc = yaml.safe_load(decompile_to_yaml(env, PACKAGED_SLIM_DB))
    return list(doc["playbooks"][0].get("parameters") or [])


def test_trigger_input_variables_are_recovered_when_top_level_is_empty():
    """The common stock shape: `parameters: []`, everything on the trigger."""
    params = _parameters_of(_wf([], ["actionReason", "inputIndicatorValue"]))
    assert "actionReason" in params, (
        "trigger-declared parameter was dropped — the playbook's input form "
        "does not survive a pull")
    assert "inputIndicatorValue" in params


def test_trigger_declarations_are_UNIONED_with_a_nonempty_top_level_list():
    """The shape that a fallback (rather than a union) would still lose.

    This playbook declares three parameters at the top level AND a fourth on
    the trigger only. An `if not params:` fallback never fires here, so the
    fourth stayed lost — which is exactly what the live corpus showed.
    """
    wf = _wf(["inputIndicatorRecordIRI", "inputIndicatorValue",
              "inputActionReasons"], ["actionReason"])
    params = _parameters_of(wf)
    assert "actionReason" in params, (
        "a trigger-only declaration was lost because the top-level list was "
        "non-empty — the two sources must be unioned, not preferred")
    # …without losing the ones that were already there.
    for p in ("inputIndicatorRecordIRI", "inputIndicatorValue",
              "inputActionReasons"):
        assert p in params


def test_no_duplicates_when_both_sources_declare_the_same_parameter():
    params = _parameters_of(_wf(["actionReason"], ["actionReason"]))
    assert params.count("actionReason") == 1


def test_declaration_order_is_stable_top_level_first():
    """Order is part of the form layout, so pin it rather than sorting."""
    params = _parameters_of(_wf(["alpha"], ["beta", "gamma"]))
    assert params == ["alpha", "beta", "gamma"]


def test_a_trigger_with_no_input_variables_yields_no_parameters():
    """The guard must not invent parameters for playbooks that declare none."""
    assert _parameters_of(_wf([], [])) == []
