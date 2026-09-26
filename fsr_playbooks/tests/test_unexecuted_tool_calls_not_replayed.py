"""A tool call that never ran must not be replayed in history.

A round that stops on anything but a tool-call finish -- `length` /
`max_tokens` above all, where the output cap cuts a call off mid-arguments --
takes the terminal branch, so its calls are never executed. The providers still
appended them to history, and when a guard nudge or self-repair round sent the
next request, both OpenAI and Anthropic rejected it:

    An assistant message with 'tool_calls' must be followed by tool messages
    responding to each 'tool_call_id'.

Found live: a gpt-5.4-mini build round spent the whole 16384-token cap and
stopped mid-call; the build-progress nudge's follow-up died with that 400.

Each test drives the real provider loop through a truncated round into a
follow-up request and checks EVERY request it sent, so a pass means the
follow-up actually happened and was well-formed.
"""
from __future__ import annotations

import asyncio
import copy
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from test_anthropic_enhance_delivery_forced import _FakeStream as _AnthropicStream
from test_anthropic_enhance_delivery_forced import _text_block, _tool_use_block, _usage
from test_openai_build_progress_forced import (
    _BUILD_TOOLS,
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.lmstudio_provider import LMStudioProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, ToolUseEvent

# Does not compile, so self-repair sends a follow-up request.
_BROKEN_YAML_TEXT = "Here it is:\n```yaml\nplaybooks: [\n```\n"
# The call the output cap cut off mid-arguments.
_CUT_ARGS = '{"card_type": "playbook_offer", "payload": {"yaml": "playbooks:\\n  - na'


async def _drain(gen):
    return [ev async for ev in gen]


def _openai_unanswered(messages: list[dict[str, Any]]) -> list[str]:
    """tool_call ids with no `role: tool` reply before the next assistant turn."""
    missing: list[str] = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant" or not m.get("tool_calls"):
            continue
        answered: set[str] = set()
        for later in messages[i + 1:]:
            if later.get("role") == "assistant":
                break
            if later.get("role") == "tool":
                answered.add(later.get("tool_call_id"))
        missing += [tc["id"] for tc in m["tool_calls"] if tc["id"] not in answered]
    return missing


def _snapshotting(streams) -> tuple[AsyncMock, list[list[Any]]]:
    """A fake `create`/`stream` that records each request's messages AS SENT.

    The provider mutates one history list in place, so `call_args_list` would
    show every request with the final history -- and check nothing."""
    sent: list[list[Any]] = []
    queue = list(streams)

    def _call(*_a, **kw):
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)
    return _call, sent


def _openai_provider(cls, create):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    if cls is LMStudioProvider:
        return LMStudioProvider(model="m", client=client)
    return OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                          api_key="x", client=client)


def _truncated_round(*, text: str | None):
    chunks = []
    if text:
        chunks.append(_delta_chunk(content=text))
    chunks += [
        _delta_chunk(tool_calls=[_tc(index=0, id="c_cut", name="emit_card",
                                     args=_CUT_ARGS)]),
        _delta_chunk(finish="length"), _usage_chunk(),
    ]
    return chunks


def _close_round():
    return [_delta_chunk(content="Done."), _delta_chunk(finish="stop"), _usage_chunk()]


def _run_openai_like(cls, rounds, tools):
    call, sent = _snapshotting([_FakeStream(r) for r in rounds])
    create = AsyncMock(side_effect=call)
    p = _openai_provider(cls, create)
    mod = ("fsr_playbooks.llm.lmstudio_provider" if cls is LMStudioProvider
           else "fsr_playbooks.llm.openai_provider")
    with patch(f"{mod}.dispatch", MagicMock(return_value={"ok": True})) as disp, \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=tools, tags={})))
    return sent, disp, events


def test_openai_self_repair_after_a_truncated_call_is_well_formed():
    requests, disp, _ = _run_openai_like(
        OpenAIProvider, [_truncated_round(text=_BROKEN_YAML_TEXT), _close_round()],
        _BUILD_TOOLS)
    assert len(requests) == 2, "self-repair never sent its follow-up request"
    for msgs in requests:
        assert _openai_unanswered(msgs) == []
    assert not any(c.args[0] == "emit_card" for c in disp.call_args_list), (
        "a call cut off mid-arguments was executed")


def test_openai_nudge_after_a_textless_truncated_call_is_well_formed():
    """The live shape: research, then a round that is ONLY a cut-off call."""
    research = [
        _delta_chunk(tool_calls=[_tc(index=0, id="c1", name="get_step_type",
                                     args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    requests, _, events = _run_openai_like(
        OpenAIProvider,
        [research, _truncated_round(text=None), _close_round(), _close_round()],
        _BUILD_TOOLS)
    assert len(requests) >= 3, "no follow-up request after the truncated round"
    for msgs in requests:
        assert _openai_unanswered(msgs) == []
    # The model is told why nothing ran, in the slot the call occupied.
    followup = requests[2]
    stand_in = [m for m in followup if m.get("role") == "assistant"][-1]
    assert "emit_card" in stand_in["content"] and "length" in stand_in["content"]
    assert "emit_card" not in [e.name for e in events if isinstance(e, ToolUseEvent)]


def test_lmstudio_self_repair_after_a_truncated_call_is_well_formed():
    requests, disp, _ = _run_openai_like(
        LMStudioProvider, [_truncated_round(text=_BROKEN_YAML_TEXT), _close_round()],
        _BUILD_TOOLS)
    assert len(requests) == 2, "self-repair never sent its follow-up request"
    for msgs in requests:
        assert _openai_unanswered(msgs) == []
    assert not any(c.args[0] == "emit_card" for c in disp.call_args_list)


def _anthropic_unanswered(messages: list[Any]) -> list[str]:
    def blocks(m):
        content = m["content"] if isinstance(m, dict) else m.content
        return content if isinstance(content, list) else []

    def field(b, k):
        return b.get(k) if isinstance(b, dict) else getattr(b, k, None)

    def role(m):
        return m["role"] if isinstance(m, dict) else m.role

    missing: list[str] = []
    for i, m in enumerate(messages):
        if role(m) != "assistant":
            continue
        uses = [field(b, "id") for b in blocks(m) if field(b, "type") == "tool_use"]
        if not uses:
            continue
        nxt = messages[i + 1] if i + 1 < len(messages) else None
        answered = ({field(b, "tool_use_id") for b in blocks(nxt)
                     if field(b, "type") == "tool_result"} if nxt else set())
        missing += [u for u in uses if u not in answered]
    return missing


def test_anthropic_self_repair_after_a_truncated_call_is_well_formed():
    truncated = _AnthropicStream([_BROKEN_YAML_TEXT], MagicMock(
        content=[_text_block(_BROKEN_YAML_TEXT),
                 _tool_use_block("c_cut", "emit_card", {"card_type": "playbook_offer"})],
        stop_reason="max_tokens", usage=_usage()))
    close = _AnthropicStream(["Done."], MagicMock(
        content=[_text_block("Done.")], stop_reason="end_turn", usage=_usage()))
    client = MagicMock()
    client.messages = MagicMock()
    stream_call, requests = _snapshotting([truncated, close])
    client.messages.stream = MagicMock(side_effect=stream_call)
    client.messages.create = AsyncMock()
    p = AnthropicProvider(model="claude-haiku-4-5-20251001", base_url="http://x",
                          api_key="x", client=client)
    tools = [{"name": "emit_card", "description": "emit a card",
              "input_schema": {"type": "object", "properties": {}}}]
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch",
               MagicMock(return_value={"ok": True})) as disp:
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=tools, tags={})))

    assert not client.messages.create.called, "unexpected forced round"
    assert len(requests) >= 2, "self-repair never sent its follow-up request"
    for msgs in requests:
        assert _anthropic_unanswered(msgs) == [], json.dumps(msgs, default=str)[:800]
    assert not disp.called, "a call cut off mid-input was executed"
