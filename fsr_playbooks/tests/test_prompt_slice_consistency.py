"""The prompt the model sees must never name a tool absent from its slice.

Asserts the relationship (rendered prompt vs. the slice), not a hand list:
every strategy/intent slice is built the way production builds it, and every
registry tool the build surface offers that is NOT in the slice must be absent
from the prompt rendered for that slice.
"""
from __future__ import annotations

import re

import pytest

from fsr_playbooks.llm import intents
from fsr_playbooks.llm.tools import anthropic_tools

# Names that are also YAML step types the prompt legitimately teaches
# (`create_record` step vs the create_record tool).
_STEP_TYPE_NAMES = frozenset({"create_record", "update_record", "delete_record",
                              "find_record"})


def _slice(intent: str, strategy: str) -> set[str]:
    tools = intents.tools_for_intent(intent)
    if intent == "build":
        tools = intents.apply_create_strategy(tools, strategy)
    return {t["name"] for t in tools}


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])",
                     text) is not None


@pytest.mark.parametrize("intent,strategy", [
    ("build", "freeform"), ("build", "guided"),
    ("triage", "freeform"),
])
def test_rendered_prompt_names_only_tools_in_its_slice(intent, strategy):
    names = _slice(intent, strategy)
    text = intents.load_intent_prompt(intent, tool_names=names)
    # Candidate universe: tools the build surface can offer. Short generic
    # words (`find`, `search`) are only checked when backticked.
    universe = {t["name"] for t in intents.tools_for_intent("build")}
    stray = sorted(
        n for n in universe - names - _STEP_TYPE_NAMES
        if (("_" in n and _mentions(text, n)) or f"`{n}`" in text))
    assert not stray, f"{intent}/{strategy} prompt names absent tools: {stray}"


def test_guided_prompt_points_at_in_slice_equivalents():
    names = _slice("build", "guided")
    text = intents.load_intent_prompt("build", tool_names=names)
    assert "get_step_type" not in text
    assert "find(kind='step'" in text


def test_freeform_prompt_keeps_authoring_guidance():
    names = _slice("build", "freeform")
    text = intents.load_intent_prompt("build", tool_names=names)
    assert "get_step_type" in text and "edit_playbook" in text


def test_unsliced_load_is_the_full_prompt():
    full = intents.load_intent_prompt("build")
    assert "<!--" not in full and "get_step_type" in full


def test_registry_is_nonempty():  # guards the parametrized test against vacuity
    assert anthropic_tools()
