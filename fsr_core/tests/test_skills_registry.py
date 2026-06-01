"""Phase 1 — skill descriptor registry (SKILL_BASED_PLAYBOOK_PLAN §1).

Pure-registry tests: the four demo-core skills exist, obey the 1:1
step-type rule, and each `compile()` hook emits a YAML source-form step
that the real `parser.parse_yaml` accepts without error.
"""
from __future__ import annotations

import yaml

from fsr_core.compiler import skills
from fsr_core.compiler.parser import parse_yaml


DEMO_CORE = {"run_connector_action", "set_variable", "manual_input", "decision"}


def test_demo_core_skills_registered():
    reg = skills.all_skills()
    assert DEMO_CORE <= set(reg), f"missing demo-core skills: {DEMO_CORE - set(reg)}"


def test_one_to_one_step_type_rule():
    # Each demo-core skill maps to a distinct FSR step type.
    seen = {}
    for sid in DEMO_CORE:
        s = skills.get_skill(sid)
        assert s is not None
        assert s.step_type, f"{sid} has no step_type"
        seen.setdefault(s.step_type, sid)
    assert len(seen) == len(DEMO_CORE), "step types must be 1:1 across demo-core"


def test_register_rejects_missing_step_type():
    try:
        skills.register(skills.Skill(id="bad", step_type="", compile=lambda *_: {}))
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("register should reject empty step_type")


def _compile_all_into_playbook():
    run = skills.get_skill("run_connector_action").compile(
        {"connector": "fortiedr", "operation": "isolate_host", "host": "1.2.3.4"},
        {},
        "Isolate Host",
    )
    setv = skills.get_skill("set_variable").compile(
        {"verdict": "malicious"}, {}, "Stage Verdict",
    )
    manual = skills.get_skill("manual_input").compile(
        {"message": "Block this host?",
         "options": [{"display": "Yes", "next": "Decide"},
                     {"display": "No", "next": "Notify"}]},
        {},
        "Confirm Block",
    )
    decide = skills.get_skill("decision").compile(
        {"conditions": [{"display": "Malicious",
                         "when": "{{ vars.steps.Stage_Verdict.verdict == 'malicious' }}",
                         "next": "Isolate Host"}],
         "default": "Notify"},
        {},
        "Decide",
    )
    return [run, setv, manual, decide]


def test_compiled_steps_parse_clean():
    steps = _compile_all_into_playbook()
    doc = {
        "collection": "00 - FSR Studio",
        "playbooks": [{
            "name": "Skill Compile Smoke",
            "trigger": "start",
            "steps": [{"type": "start", "name": "Start", "next": "Isolate Host"}] + steps,
        }],
    }
    text = yaml.safe_dump(doc, sort_keys=False)
    collection, errors = parse_yaml(text)
    hard = [e for e in errors if getattr(e, "severity", "error") != "warning"]
    assert not hard, f"compiled skill steps failed to parse: {hard}"
    assert collection is not None


def test_run_connector_action_wiring_overrides_literal():
    step = skills.get_skill("run_connector_action").compile(
        {"connector": "fortiedr", "operation": "isolate_host", "host": "1.2.3.4"},
        {"host": "{{ vars.steps.Enrich.ip }}"},
        "Isolate Host",
    )
    assert step["arguments"]["host"] == "{{ vars.steps.Enrich.ip }}"
    assert step["arguments"]["connector"] == "fortiedr"


def test_set_variable_emits_top_level_vars_not_arguments():
    step = skills.get_skill("set_variable").compile({"x": 1}, {}, "S")
    assert step["type"] == "set_variable"
    assert step["vars"] == {"x": 1}
    assert "arguments" not in step
