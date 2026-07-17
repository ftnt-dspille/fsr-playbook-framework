"""The build system prompt's canonical skeleton must match what validate_yaml
accepts. It previously instructed `id:` on every step — which is a hard
validation error — and omitted `next:` wiring, forcing two wasted validate
round-trips on every build (see session yq8nhcix). Pin the corrected shape.
"""
from __future__ import annotations

from pathlib import Path

_PROMPT = (Path(__file__).resolve().parents[1]
           / "agent" / "system_prompt_build.md").read_text()


def test_skeleton_does_not_use_step_id():
    # `- id:` step keys are rejected by the parser ("step.id is not allowed").
    assert "- id:" not in _PROMPT


def test_skeleton_identifies_steps_by_name_and_wires_with_next():
    assert "- name: Start" in _PROMPT
    assert "next: Set Inputs" in _PROMPT


# --- Quick-action modes (Track C1) -------------------------------------
# The 5 build quick-action chips each route to a distinct toolset via a
# `quick_action` key the connector threads onto the turn. The prompt must
# document every mode so the connector's `# Active quick-action` marker has a
# branch to land on. See PLAN_demoable_three_pillars.md (Track C / C1).

_QUICK_ACTION_MODES = [
    "explain",
    "add_step",
    "find_issues",
    "add_error_handling",
    "optimize",
]


# --- Native steps vs connector ops (D2 ③) ------------------------------
# A real build ("create a playbook to block an ip and create an alert")
# derailed because the model searched connectors for a `create_alert`
# operation (there is none — creating a record is a native `create_record`
# step) and hallucinated. The prompt must disambiguate native steps from
# connector ops.

def test_native_steps_section_present():
    assert "# Native step types vs connector operations" in _PROMPT


def test_prompt_teaches_create_record_is_native_not_a_connector_op():
    assert "create_record" in _PROMPT
    assert "update_record" in _PROMPT
    # It must explicitly say record CRUD is NOT a connector operation and steer
    # the model away from find_operation for it.
    assert "no `create_alert`" in _PROMPT or "not a connector" in _PROMPT.lower() \
        or "native `create_record`" in _PROMPT


def test_prompt_warns_against_faking_a_record_with_set_variable():
    # The observed hallucination: a "Create Alert" step that only set a message
    # string. The prompt must call that out.
    low = _PROMPT.lower()
    assert "set_variable" in low and "message string" in low


def test_quick_action_modes_section_present():
    assert "# Quick-action modes" in _PROMPT
    assert "# Active quick-action" in _PROMPT  # referenced marker name


def test_every_quick_action_mode_documented():
    for key in _QUICK_ACTION_MODES:
        # Each mode is a bolded **`key`** bullet.
        assert f"**`{key}`**" in _PROMPT, f"missing quick-action mode: {key}"


# --- P4: the prompt may only promise tools the build persona actually has -----
#
# The failure this pins is not hypothetical and not a typo — it is a whole class,
# and it cost this plan a live eval to find. S2 ran the designer persona against
# a real box: 0/4 runs, every one dead-ending in `analyze_playbook` with nothing
# to pass it. The cause was one sentence in this prompt —
#
#     "the open playbook's IRI is in the entity block, so call `analyze_playbook`
#      on it rather than asking the analyst to paste YAML"
#
# — instructing an action the tool cannot perform: `analyze_playbook` requires
# `yaml_text` and has no IRI parameter, and NOTHING in the build slice reads a
# live playbook. The assistant was not wrong; it was obeying a prompt that
# promised a capability that did not exist. Auditing the prompt against the real
# slice then found a second one already shipped: `suggest_fix_for_diagnostic`,
# instructed by the `add_error_handling` mode, is exposed to no intent at all.
#
# Prose cannot be trusted to stay true to a toolset that moves underneath it
# (C5's triage-only scoping silently removed `get_record` from build). So check
# it mechanically, against the same registry the agent is handed.

import re

import pytest

# Prose assertions must survive a re-wrap: this prompt is hand-wrapped at ~78
# cols, so any phrase long enough to be worth pinning is liable to straddle a
# newline. Flatten runs of whitespace to a single space and match against that,
# never against the raw text.
_FLAT = re.sub(r"\s+", " ", _PROMPT).lower()

# Backticked identifiers that are deliberately NOT tools. Each needs a reason —
# if you add one, say why, because the default answer is "then don't name it".
_NOT_TOOLS = {
    # Quick-action chip keys (`# Active quick-action` markers), not callables.
    "explain", "add_step", "find_issues", "add_error_handling", "optimize",
    "quick_action",
    # The prompt's own example of a GUESSED op that does not exist. Naming it is
    # the point — it teaches the model not to invent it.
    "get_api_response",
    # Native step types, resolved via get_step_type. Not tools.
    "create_record", "update_record", "set_variable", "decision", "start", "end",
    "connector",
    # YAML keys / fields the prompt teaches.
    "playbooks", "templates", "type", "stepType", "next", "name", "id",
    "parameters", "module", "yaml_text", "before_yaml", "after_yaml",
    # Widget/connector ops the analyst's buttons call — deliberately NOT in the
    # agent's slice (the Save button calls update_playbook; the agent must not).
    "update_playbook",
}

# Shapes that read as a tool name. Kept as prefixes rather than a bare
# snake_case match so ordinary prose words never trip the check.
_TOOLISH = re.compile(
    r"^(find_|get_|emit_|verify_|validate_|compile_|push_|dry_run_|"
    r"build_playbook|analyze_|step_through_|diagnose_|suggest_|list_|"
    r"picklist_|resolve_|propose_|healthcheck_|search_|run_playbook)")


def _build_slice_names() -> set[str]:
    from fsr_playbooks.llm.intents import tools_for_intent
    out = set()
    for t in tools_for_intent("build"):
        name = t["name"] if isinstance(t, dict) else getattr(t, "name", None)
        if name:
            out.add(name)
    return out


def _prompt_tool_mentions() -> set[str]:
    named = set(re.findall(r"`([a-z_][a-z0-9_]*)`", _PROMPT))
    return {n for n in named if _TOOLISH.match(n) and n not in _NOT_TOOLS}


def test_prompt_only_names_tools_the_build_persona_actually_has():
    missing = sorted(_prompt_tool_mentions() - _build_slice_names())
    assert not missing, (
        "the build prompt instructs tools that are not in tools_for_intent('build'): "
        f"{missing}. The persona cannot call them, so the instruction is a "
        "dead-end (this is exactly how S2 scored 0/4). Either expose the tool to "
        "the build intent, or stop naming it."
    )


def test_the_mentions_check_actually_sees_the_prompts_tools():
    # Guard the guard: if the regex or the allowlist ever swallowed everything,
    # the test above would pass vacuously — an oracle that only ever passes is
    # the bug this plan exists to catch, one level up.
    mentions = _prompt_tool_mentions()
    assert len(mentions) >= 10, f"suspiciously few tool mentions parsed: {mentions}"
    assert {"analyze_playbook", "verify_playbook", "get_step_type"} <= mentions


def test_prompt_does_not_claim_a_playbook_can_be_analyzed_by_iri():
    # The exact regression: no tool in the slice takes a playbook IRI/uuid, so
    # any instruction to analyze/read "by IRI" is uncallable by construction.
    low = _FLAT
    assert "call `analyze_playbook` on it" not in low
    for tool in ("analyze_playbook", "step_through_playbook", "verify_playbook"):
        for prop in ("workflow_iri", "workflow_uuid"):
            assert f"{tool}({prop}" not in low


@pytest.mark.parametrize("tool", ["analyze_playbook", "verify_playbook",
                                  "validate_yaml", "compile_yaml",
                                  "step_through_playbook"])
def test_the_analysis_tools_really_do_require_yaml_text(tool):
    # The claim the prompt now makes ("every analysis tool takes yaml_text, not a
    # record") must stay true of the actual schemas, or the prompt is lying again
    # in the other direction.
    by_name = {}
    from fsr_playbooks.llm.intents import tools_for_intent
    for t in tools_for_intent("build"):
        n = t["name"] if isinstance(t, dict) else getattr(t, "name", None)
        by_name[n] = t
    spec = by_name[tool]
    schema = spec["input_schema"] if isinstance(spec, dict) else spec.input_schema
    assert "yaml_text" in (schema.get("required") or []), (
        f"{tool} no longer requires yaml_text — the prompt's 'pass the OPEN "
        f"PLAYBOOK YAML as yaml_text' instruction needs revisiting")


def test_prompt_grounds_the_designer_in_the_open_playbook_block():
    # The block name is a contract with the connector's _entity_context_block
    # (operations.py): the prompt tells the model to look for "OPEN PLAYBOOK",
    # so the connector must keep emitting that exact header.
    assert "OPEN PLAYBOOK" in _PROMPT
    assert "never ask the analyst to paste" in _FLAT


def test_prompt_warns_that_the_last_yaml_fence_wins():
    # The widget takes the LAST ```yaml fence as the playbook to save and Save
    # compiles it back over the open record, so a trailing snippet silently
    # deletes every step it omits (view.controller.js, _extract fence loop).
    assert "last ```yaml fence" in _FLAT
    assert "complete revised playbook" in _FLAT


def test_prompt_does_not_offer_a_duplicate_when_a_playbook_is_open():
    # emit_playbook_offer's accept path PUSHES (creates) a new playbook. Offering
    # one while the analyst has a playbook open saves a duplicate and leaves the
    # open record untouched, so the terminal rule has to be conditional.
    assert "do not call `emit_playbook_offer` here" in _FLAT
    assert "duplicate" in _FLAT
