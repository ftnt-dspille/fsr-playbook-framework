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
