"""Tests for the AI step-drafter.

The provider is faked end-to-end so these tests hit real prompt
construction + response parsing without making any LLM calls.
"""
from __future__ import annotations

import asyncio

import pytest

from fsr_playbooks.llm.factory import register, reset_registry
from fsr_playbooks.llm.fake_provider import FakeProvider
from fsr_playbooks.llm.provider import TextEvent
from backend.step_drafter import (
    build_system_prompt,
    draft_step_args,
    extract_json,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_extract_json_handles_fenced_block():
    raw = "Sure! Here you go:\n```json\n{\"a\": 1}\n```\nDone."
    assert extract_json(raw) == {"a": 1}


def test_extract_json_handles_bare_object():
    raw = '{"x": "y", "n": 2}'
    assert extract_json(raw) == {"x": "y", "n": 2}


def test_extract_json_handles_object_with_prose_around_it():
    raw = "Some prose first.\n{\"k\": [1, 2, 3]}\nthen more"
    assert extract_json(raw) == {"k": [1, 2, 3]}


def test_extract_json_returns_none_on_garbage():
    assert extract_json("nothing JSON-shaped here") is None
    assert extract_json("{not valid: json,}") is None


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def test_build_system_prompt_contains_intent_and_intro():
    prompt = build_system_prompt("decision", None,
                                 "branch on whether ip is null", None)
    assert "branch on whether ip is null" in prompt
    assert "Branches the playbook on Jinja predicates" in prompt
    assert "Output contract" in prompt


def test_build_system_prompt_includes_module_schema_when_module_set():
    # The DB might not exist in CI; the function falls back to a
    # short stub. Either way the module name must appear.
    prompt = build_system_prompt("find_record", "alerts",
                                 "find high severity alerts", None)
    assert "alerts" in prompt
    assert "Schema" in prompt or "module catalog unavailable" in prompt


def test_build_system_prompt_skips_schema_section_when_no_module():
    prompt = build_system_prompt("set_variable", None, "store the score", None)
    assert "## Schema" not in prompt


def test_build_system_prompt_includes_current_args_for_iteration():
    prompt = build_system_prompt("decision", None, "tighten the predicate",
                                 {"conditions": [{"option": "Yes"}]})
    assert "Current draft" in prompt
    assert '"option": "Yes"' in prompt


def test_unknown_step_type_falls_back_to_generic_intro():
    prompt = build_system_prompt("totally_made_up_type", None, "do a thing", None)
    assert "totally_made_up_type" in prompt
    assert "Output contract" in prompt


# ---------------------------------------------------------------------------
# Drafter end-to-end (with FakeProvider)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_provider():
    """Stand up a FakeProvider as the default and tear down afterward."""
    fake = FakeProvider(turns=[[
        TextEvent(text='```json\n{"conditions": [{"option": "Yes", '
                       '"condition": "{{ vars.x }}"}, '
                       '{"option": "No", "default": true}]}\n```')
    ]])
    register("fake", lambda **_: fake)
    yield fake
    reset_registry()


def test_draft_step_args_returns_parsed_json(fake_provider):
    out = asyncio.run(draft_step_args(
        step_type="decision",
        intent="branch on whether the score is over 50",
        provider_name="fake",
    ))
    assert out["ok"] is True
    proposed = out["proposed_args"]
    assert proposed["conditions"][0]["option"] == "Yes"
    assert proposed["conditions"][1]["default"] is True
    # Sanity: the prompt the fake saw included the user's intent.
    assert "score is over 50" in fake_provider.last_system


def test_draft_step_args_reports_parse_failure_gracefully():
    fake = FakeProvider(turns=[[TextEvent(text="I'm not going to give you JSON, sorry.")]])
    register("fake", lambda **_: fake)
    try:
        out = asyncio.run(draft_step_args(step_type="set_variable",
                                          intent="anything",
                                          provider_name="fake"))
        assert out["ok"] is False
        assert "did not return parseable JSON" in out["error"]
        assert out["raw_text"].startswith("I'm not going to")
    finally:
        reset_registry()


def test_draft_step_args_passes_module_through_to_prompt():
    fake = FakeProvider(turns=[[TextEvent(text='{"module": "alerts?$limit=30", "query": {"logic": "AND", "filters": []}}')]])
    register("fake", lambda **_: fake)
    try:
        out = asyncio.run(draft_step_args(
            step_type="find_record",
            intent="find all alerts",
            module="alerts",
            provider_name="fake",
        ))
        assert out["ok"] is True
        assert "alerts" in fake.last_system
        assert out["proposed_args"]["module"].startswith("alerts")
    finally:
        reset_registry()


def test_draft_step_args_tags_usage_with_step_type():
    fake = FakeProvider(turns=[[TextEvent(text='{"x": 1}')]])
    register("fake", lambda **_: fake)
    try:
        asyncio.run(draft_step_args(step_type="delay", intent="wait 5 seconds",
                                    provider_name="fake"))
        assert fake.last_tags == {"feature": "step_drafter", "step_type": "delay"}
    finally:
        reset_registry()


def test_draft_step_args_returns_diagnostics_field():
    """Successful drafts always carry a `diagnostics` array (possibly
    empty) so the inspector can render the validation badge without
    having to feature-detect the field."""
    fake = FakeProvider(turns=[[TextEvent(
        text='{"seconds": 5}'
    )]])
    register("fake", lambda **_: fake)
    try:
        out = asyncio.run(draft_step_args(
            step_type="delay",
            intent="wait 5 seconds",
            provider_name="fake",
        ))
        assert out["ok"] is True
        # The drafter calls the compiler under the hood. Whether it
        # finds errors or not depends on the local store, but the
        # field MUST be present so the modal can render the badge.
        assert "diagnostics" in out
        assert isinstance(out["diagnostics"], list)
    finally:
        reset_registry()
