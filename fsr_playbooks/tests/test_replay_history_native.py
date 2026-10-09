"""Replayed history reaches each provider as native tool turns, never as
call-shaped text.

A history that shows `[called edit_playbook(...)]` as prose teaches the model
that writing that string is how a tool gets called. Replayed in the neutral
block form, an earlier call must reach an OpenAI-compatible endpoint as an
assistant `tool_calls` message answered by a `role: tool` message with the
same id -- and reach the text-only FortiAI proxy as prose that is not
call-shaped.
"""

from __future__ import annotations

import json

from fsr_playbooks.llm import openai_provider
from fsr_playbooks.llm.provider import Message
from fsr_playbooks.llm.replay import blocks_to_prose, is_block_content

_HISTORY = [
    Message(role="user", content="Build a playbook that notifies on high alerts"),
    Message(role="assistant", content=[
        {"type": "text", "text": "Checking the step type first."},
        {"type": "tool_use", "id": "hist1_1", "name": "get_step_type",
         "input": {"name": "decision"}},
    ]),
    Message(role="user", content=[
        {"type": "tool_result", "tool_use_id": "hist1_1",
         "content": '{"ok": true}'},
    ]),
    Message(role="assistant", content=[
        {"type": "text", "text": "Here is the draft."},
    ]),
    Message(role="user", content="Now add a step that sets the status"),
]


def test_block_content_is_told_apart_from_the_loops_own_carrier():
    assert is_block_content(_HISTORY[1].content)
    assert is_block_content(_HISTORY[2].content)
    assert not is_block_content("plain")
    assert not is_block_content([])
    # What the providers append to their own in-loop history: role-carrying.
    assert not is_block_content([{"role": "tool", "tool_call_id": "x",
                                  "content": "{}"}])


def _assert_native(out):
    assert out[0]["role"] == "system"
    roles = [m["role"] for m in out[1:]]
    assert roles == ["user", "assistant", "tool", "assistant", "user"]
    call_msg, tool_msg = out[2], out[3]
    (call,) = call_msg["tool_calls"]
    assert call["function"]["name"] == "get_step_type"
    assert json.loads(call["function"]["arguments"]) == {"name": "decision"}
    assert tool_msg["tool_call_id"] == call["id"] == "hist1_1"
    assert call_msg["content"] == "Checking the step type first."
    assert "[called" not in json.dumps(out)


def test_openai_provider_replays_calls_natively():
    _assert_native(openai_provider._to_openai_messages("sys", _HISTORY))


def test_openai_carrier_dicts_still_pass_through_untouched():
    carrier = [{"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": "find", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "{}"}]
    out = openai_provider._to_openai_messages(
        "sys", [Message(role="user", content="hi"),
                Message(role="assistant", content=carrier)])
    assert out[2:] == carrier


def test_text_only_transport_gets_prose_that_is_not_call_shaped():
    prose = blocks_to_prose("assistant", _HISTORY[1].content)
    assert "Checking the step type first." in prose
    assert "get_step_type" in prose
    assert "[called" not in prose and "(" + "{" not in prose
    # A results-only turn has nothing to say without its call.
    assert blocks_to_prose("user", _HISTORY[2].content) == ""
