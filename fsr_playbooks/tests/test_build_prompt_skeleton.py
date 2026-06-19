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
