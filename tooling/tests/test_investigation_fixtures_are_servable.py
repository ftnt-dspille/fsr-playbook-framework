"""Can an investigation fixture's required tools even be CALLED here?

`investigation_recall` matches a fixture's `required_facts` against the tool
trace, and `_fact_matches` looks at the tool NAME -- never at whether that
tool exists. A fixture whose facts name tools this repo does not register can
therefore only ever fail, and it fails looking exactly like a weak agent.

That is the state of five of the seven `investigation` fixtures:
`get_record` and `search_module_records` are injected by the CONNECTOR
(`fsr_soc_triage.registry.register_triage_tools()`), which is not importable
from this repo. `intents.py` says so itself -- "Framework-standalone (no
connector) keeps just the two base names".

The recall gate is 0.8; those rows top out at 0.33 and one at 0.0. They fail
deterministically, offline or live. Auto-memory's note that a degrading box
makes investigation scores "slide" describes runs from the connector repo,
where the tools exist.

Measured: `invest_outbound_cleartext_c2` scored 3/7 with recall **0.00**,
not the arithmetic 0.33 -- the shortfall CASCADES. Its one servable fact
wants `run_op` carrying an IP the agent can only learn by reading the alert
record, so losing `get_record` loses that fact too. The agent researched
competently throughout and scored zero.

These tests exist so that stays a KNOWN quantity:

  - if the connector's tools become importable here, `_UNSERVABLE_TODAY`
    starts failing and the fixtures become real measurements;
  - if someone adds a new investigation fixture naming an unregistered tool,
    it shows up here rather than as a mystery zero.

They assert the CURRENT, measured shape -- not that it is desirable.
"""
from __future__ import annotations

import importlib

import pytest

tasks_mod = importlib.import_module("evals.tasks")

#: fixture -> the required-fact tools this repo cannot register.
#: Empty list = fully servable here.
_UNSERVABLE_TODAY = {
    "invest_outbound_cleartext_c2": ["get_record", "search_module_records"],
    "invest_excessive_mail_egress": ["get_record", "search_module_records"],
    "invest_disk_latency_no_ti": ["get_record"],
    "invest_intrusion_incident": ["get_record", "search_module_records"],
    "invest_defense_evasion_host": ["get_record", "search_module_records"],
    "contain_block_ip_direct": [],
    "contain_isolate_edr_host_direct": [],
}


def _registry() -> set:
    from fsr_playbooks.llm.tools import REGISTRY
    return set(REGISTRY)


#: With the connector importable (FSR_CONNECTOR_REPO set, or it is already on
#: the path) the whole premise of this module is gone -- and that is the goal,
#: not a failure. Skip rather than assert the framework-only shape, so a
#: developer with both repos wired up does not see a red suite for succeeding.
_connector_present = pytest.mark.skipif(
    "get_record" in _registry(),
    reason="connector triage tools are registered -- these fixtures are "
           "servable here, which is the outcome this module wants")


def _unservable(task) -> list:
    reg = _registry()
    return sorted({f.get("tool") for f in (task.required_facts or [])
                   if f.get("tool") and f.get("tool") not in reg})


def _investigation_tasks() -> dict:
    return {t.name: t for t in tasks_mod.load_tasks()
            if t.mode == "investigation"}


@_connector_present
def test_the_unservable_set_is_exactly_what_we_measured():
    got = {name: _unservable(t) for name, t in _investigation_tasks().items()}
    assert got == _UNSERVABLE_TODAY, (
        "investigation fixture servability changed. If the connector's triage "
        "tools are now importable, delete the entries that are empty now -- "
        "those rows became real measurements. If a NEW fixture appears here, "
        "it names a tool nothing registers and can only score zero.")


@_connector_present
def test_the_record_tools_really_are_absent():
    # The root cause, asserted directly so the table above cannot drift from
    # its explanation.
    reg = _registry()
    assert "get_record" not in reg
    assert "search_module_records" not in reg
    # ...while the containment side genuinely is present, which is why the
    # two `contain_*` rows are servable.
    assert "run_op" in reg
    assert "emit_action_card" in reg


@_connector_present
def test_no_intent_slice_offers_a_record_tool():
    # Not an intent-filtering artifact: the tools are absent from the
    # registry itself, so no slice can advertise them.
    from fsr_playbooks.llm.intents import tools_for_intent
    for intent in ("triage", "build"):
        names = {t["name"] for t in tools_for_intent(intent)}
        assert not {n for n in names if "record" in n} - {"build_playbook_from_trace"}, intent


@_connector_present
def test_an_unservable_fixture_cannot_clear_the_recall_gate():
    # The arithmetic that makes this a deterministic failure rather than a
    # hard row: even a PERFECT agent, calling every tool it is offered, tops
    # out below the gate.
    from evals.scoring import INVESTIGATION_RECALL_GATE
    for name, missing in _UNSERVABLE_TODAY.items():
        if not missing:
            continue
        t = _investigation_tasks()[name]
        best = 1.0 - (len(missing) / len(t.required_facts))
        assert best < INVESTIGATION_RECALL_GATE, (
            f"{name}: best possible recall {best:.2f} -- if this ever reaches "
            f"the gate the fixture is no longer structurally dead")
