"""fsr_playbooks.harness: the LLM choice, transcript reading and turn classification
every chat-turn harness shares."""
from __future__ import annotations

import pytest

from fsr_playbooks.harness.classify import classify_turn
from fsr_playbooks.harness.frames import (
    assistant_summary,
    assistant_text,
    cards,
    pending_halt,
)
from fsr_playbooks.harness.llm import DEFAULT_FRANK_MODEL, LLMConfigError, resolve_llm

FRANK_ENV = {"FRANK_BASE_URL": "https://gw.example.com/v1", "FRANK_API_KEY": "k-frank",
             "OPENAI_API_KEY": "k-openai"}


def test_model_source_is_named():
    r = resolve_llm("frank", env=FRANK_ENV)
    assert (r.model, r.model_source, r.api_key) == (DEFAULT_FRANK_MODEL, "default", "k-frank")
    r = resolve_llm("frank", env={**FRANK_ENV, "FRANK_MODEL": "coding-b200/eco"})
    assert (r.model, r.model_source) == ("coding-b200/eco", "env:FRANK_MODEL")
    assert resolve_llm("frank", "m", env=FRANK_ENV).model_source == "arg"


def test_openai_takes_the_openai_key_first():
    assert resolve_llm("openai", env=FRANK_ENV).api_key == "k-openai"


def test_missing_endpoint_raises_instead_of_falling_back():
    with pytest.raises(LLMConfigError):
        resolve_llm("frank", env={"FRANK_API_KEY": "k"})
    with pytest.raises(LLMConfigError):
        resolve_llm("gpt", env=FRANK_ENV)


def test_connector_config_matches_local_turn():
    cfg = resolve_llm("frank", env=FRANK_ENV).connector_config()
    assert cfg == {"llm_provider": "openai", "openai_api_key": "k-frank",
                   "openai_base_url": "https://gw.example.com/v1",
                   "openai_model": DEFAULT_FRANK_MODEL, "persona_models": False}


@pytest.mark.parametrize("envelope,kind", [
    ({"ok": True, "stop_reason": "end_turn",
      "transcript": [{"type": "text", "text": "done"}]}, "answered"),
    # A provider failure the connector returns as a normal reply.
    ({"ok": True, "stop_reason": "error", "transcript": [
        {"type": "error", "message": "Could not reach the OpenAI endpoint at "
                                     "https://gw.example.com -- check network"}]},
     "transport_error"),
    ({"ok": True, "stop_reason": "error", "transcript": [
        {"type": "error", "message": "Error code: 400 - invalid tool arguments"}]},
     "provider_error"),
    ({"ok": True, "stop_reason": "max_tokens", "transcript": []}, "truncated"),
    ({"ok": True, "stop_reason": "pending_approval", "transcript": [
        {"type": "approval_request", "approval_id": "a1"}]}, "halted"),
    ("<html>502</html>", "transport_error"),
])
def test_classify_turn(envelope, kind):
    assert classify_turn(envelope).kind == kind


def test_an_approval_outranks_a_card():
    t = {"transcript": [{"type": "action_card", "id": "c1"},
                        {"type": "approval_request", "approval_id": "a1"}]}
    assert pending_halt(t) == {"key": "approval_id", "value": "a1", "kind": "approval"}
    assert pending_halt({"transcript": [{"type": "action_card", "id": "c1"}]})["key"] == "card_id"


def test_text_deltas_coalesce_and_history_keeps_tool_ids():
    t = [{"type": "text", "text": "Hel"}, {"type": "text", "text": "lo"},
         {"type": "tool_use", "id": "t1", "name": "get_record", "input": {}},
         {"type": "tool_result", "tool_use_id": "t1", "content": {"ok": True}}]
    assert assistant_text(t) == "Hello"
    assert [b["type"] for b in assistant_summary(t)] == ["text", "tool_use", "tool_result"]


def test_a_nested_card_without_its_own_type_takes_the_frame_type():
    """Connector frames sometimes wrap the card; the frame type names it when
    the card dict does not, so the halt still resumes on the right key."""
    t = {"transcript": [{"type": "choice_card", "card": {"id": "c-7"}}]}
    assert pending_halt(t) == {"key": "choice_id", "value": "c-7", "kind": "choice_card"}
    assert cards(t) == [{"id": "c-7"}]


def test_tool_results_keep_orphans_and_fall_back_to_output():
    """A result with no matching call is still a result (a card's execution
    arrives this way); `output` is read when `content` is absent."""
    from fsr_playbooks.harness.frames import tool_results
    t = [{"type": "tool_result", "tool_use_id": "cardexec_1", "content": {"ok": True}},
         {"type": "tool_result", "tool_use_id": "x", "output": '{"ok": false}'}]
    got = tool_results(t)
    assert [(r.tool_use_id, r.body) for r in got] == [
        ("cardexec_1", {"ok": True}), ("x", {"ok": False})]


def test_frames_of_filters_by_type_in_order():
    from fsr_playbooks.harness.frames import frame_types, frames_of
    t = [{"type": "text", "text": "a"}, {"type": "action_card", "id": "1"},
         {"type": "approval_request", "approval_id": "2"}, {"type": "action_card", "id": "3"}]
    assert [f.get("id", f.get("approval_id")) for f in frames_of(t, "action_card", "approval_request")] == ["1", "2", "3"]
    assert frame_types(t) == ["text", "action_card", "approval_request", "action_card"]


def test_tool_call_carries_tier_and_duration():
    t = [{"type": "tool_use", "id": "a", "name": "run_op", "input": {}, "tier": 3},
         {"type": "tool_result", "tool_use_id": "a", "content": {"ok": True}, "duration_ms": 41}]
    (c,) = tool_calls(t)
    assert (c.tier, c.duration_ms) == (3, 41)
