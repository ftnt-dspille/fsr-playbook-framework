"""Each step recipe must compile clean when wrapped in a minimal playbook.

The recipes ship as `steps_yaml` blocks with placeholder tokens like
`<NEXT_STEP_NAME>` or `<POLICY_NAME>` that the agent fills in. We wrap
every recipe in a playbook scaffold that satisfies its `next:` targets,
substitute placeholders with concrete values, and run the compiler.

This guards against schema drift in the reference store — if a
connector op's param visibility rules change, the recipe should fail
this test before it lands in front of an agent.
"""
from __future__ import annotations

import re

import pytest

from fsr_core.compiler import compile_yaml
from recipes import step_lookup


# Generic placeholder fills; recipe-specific ones added per-recipe below.
_PLACEHOLDERS = {
    "<NEXT_STEP_NAME>": "End",
    "<APPROVE_STEP>": "End",
    "<REJECT_STEP>": "End",
    "<POLICY_NAME>": "FortiSOAR_Blocked_Policy",
    "<ADDRESS_GROUP>": "Blocked_IPs",
    "<ID_FIELD>": "target_value",
    "<LABEL>": "Target Value",
}


def _fill(text: str) -> str:
    for k, v in _PLACEHOLDERS.items():
        text = text.replace(k, v)
    return text


def _wrap(steps_yaml: str, recipe_name: str) -> str:
    """Wrap a recipe's steps block in a tiny playbook with start + end.

    The recipe's first step name is auto-discovered and wired as the
    `start.next`. We prepend a `Collect Input` manual_input step (named
    so its jinja-key becomes `Collect_Input`) so recipes that reference
    `vars.steps.Collect_Input.input.target_value` resolve cleanly. The
    `manual_input_trigger` recipe IS that step, so we skip the prepend
    for it to avoid a duplicate name.
    """
    first_name_match = re.search(r"^\s*-\s*type:\s*\S+\s*\n\s*name:\s*(\S.*)\s*$",
                                 steps_yaml, re.MULTILINE)
    first_name = first_name_match.group(1).strip() if first_name_match else "Step1"
    indented = "\n".join("      " + line if line else line
                         for line in steps_yaml.splitlines())
    needs_collect = recipe_name != "manual_input_trigger"
    collect_block = (
        "      - type: manual_input\n"
        "        name: Collect Input\n"
        "        arguments:\n"
        "          title: Collect Input\n"
        "          description: Collect input.\n"
        "          inputs:\n"
        "            - name: target_value\n"
        "              kind: text\n"
        "              label: Target\n"
        "              required: true\n"
        f"        options:\n"
        f"          - display: Continue\n"
        f"            primary: true\n"
        f"            next: {first_name}\n"
    ) if needs_collect else ""
    start_next = "Collect Input" if needs_collect else first_name
    return (
        "collection: T\n"
        "playbooks:\n"
        "  - name: T\n"
        "    steps:\n"
        f"      - type: start\n"
        f"        name: Start\n"
        f"        next: {start_next}\n"
        f"{collect_block}"
        f"{indented}\n"
        f"      - type: end\n"
        f"        name: End\n"
    )


@pytest.mark.parametrize("recipe", step_lookup.load_all(),
                         ids=lambda r: r.name)
def test_recipe_compiles_clean(recipe, db_path):
    yaml_text = _wrap(_fill(recipe.steps_yaml), recipe.name)
    result = compile_yaml(yaml_text, db_path)
    assert result.ok, (
        f"recipe {recipe.name!r} failed to compile: "
        + "; ".join(str(e) for e in result.errors)
    )
    # No visibility-cascade warnings — recipes must ship a coherent set.
    bad_warnings = [
        w for w in result.warnings
        if w.code.value == "bad_value"
        and ("only valid when" in w.message
             or "param-set conflict" in w.message)
    ]
    assert not bad_warnings, (
        f"recipe {recipe.name!r} has visibility warnings: "
        + "; ".join(w.message for w in bad_warnings)
    )


def test_find_returns_fortigate_recipes_for_block_intent():
    matches = step_lookup.find("block ip", connector="fortigate-firewall")
    names = {r.name for r in matches}
    assert "fortigate_block_ip_policy" in names
    assert "fortigate_block_ip_quarantine" in names


def test_find_returns_manual_trigger_for_user_prompt_intent():
    matches = step_lookup.find("manual trigger that prompts the user")
    assert any(r.name == "manual_input_trigger" for r in matches)


def test_find_filters_by_step_type():
    matches = step_lookup.find("record action",
                               step_type="set_variable")
    assert any(r.name == "set_variable_log" for r in matches)
    # Other step types shouldn't sneak in via this filter.
    for r in matches:
        assert "set_variable" in r.step_types
