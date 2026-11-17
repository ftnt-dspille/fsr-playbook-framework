"""The verdict's result tells the model the card is the write-up.

Live, a triage turn wrote its assessment in prose, then the same verdict as a
card, then a closing "bottom line": the conclusion three times and about 40
seconds of output. The prompt's "do not restate a card" sat thousands of
tokens back; the verdict's own result is the last thing the model reads before
it writes again, so the reminder rides there.
"""
from __future__ import annotations

import asyncio
import copy
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from test_anthropic_enhance_delivery_forced import (
    _FakeStream,
    _text_block,
    _tool_use_block,
    _usage,
)

from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import Message
from fsr_playbooks.mcp_server import emit_card
from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry,
    register_tool_result,
)
from fsr_playbooks.mcp_server.tools_emit import VERDICT_SHOWN_NOTE

_VERDICT = {"disposition": "suspicious", "severity": "high", "confidence": 0.5,
            "summary": "Shadow-copy deletion on one host.",
            "findings": [{"claim": "vssadmin ran", "evidence": ["c0"]}],
            "unknowns": ["Which user started the parent process."]}


def test_the_verdict_result_carries_the_note():
    clear_tool_registry()
    register_tool_result("c0", "get_record", True)
    r = emit_card("verdict", dict(_VERDICT))
    assert r["ok"] is True
    assert r["shown"] == VERDICT_SHOWN_NOTE
    assert "do not restate" in VERDICT_SHOWN_NOTE


def test_the_model_reads_the_note_on_its_next_request():
    clear_tool_registry()
    register_tool_result("c0", "get_record", True)
    sent: list[list[Any]] = []
    rounds = [
        _FakeStream([], MagicMock(
            content=[_tool_use_block("c0", "get_record", {})],
            stop_reason="tool_use", usage=_usage())),
        _FakeStream([], MagicMock(
            content=[_tool_use_block("c1", "emit_card",
                                     {"card_type": "verdict", "payload": dict(_VERDICT)})],
            stop_reason="tool_use", usage=_usage())),
        _FakeStream(["Isolate it next."], MagicMock(
            content=[_text_block("Isolate it next.")], stop_reason="end_turn",
            usage=_usage())),
    ]

    def _call(*_a, **kw):
        sent.append(copy.deepcopy(kw["messages"]))
        return rounds.pop(0)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=_call)
    client.messages.create = AsyncMock()
    p = AnthropicProvider(model="claude-sonnet-4-6", base_url="http://x",
                          api_key="x", client=client)
    tools = [{"name": "get_record", "description": "read a record",
              "input_schema": {"type": "object", "properties": {}}},
             {"name": "emit_card", "description": "emit a card",
              "input_schema": {"type": "object", "properties": {
                  "card_type": {"type": "string"}, "payload": {"type": "object"}}}}]

    def _dispatch(name, args):
        return emit_card(**args) if name == "emit_card" else {"ok": True}

    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        async def _drain():
            return [ev async for ev in p.stream(
                system="s", messages=[Message(role="user", content="how bad is it?")],
                tools=tools, tags={})]
        asyncio.run(_drain())

    assert len(sent) >= 3, "the loop never sent a request after the verdict"
    results = [b for m in sent[2] if m["role"] == "user" and isinstance(m["content"], list)
               for b in m["content"] if b.get("type") == "tool_result"]
    assert results, "no tool result followed the verdict"
    assert VERDICT_SHOWN_NOTE in json.dumps(results[-1]["content"])


def test_the_advertised_description_says_the_card_replaces_prose():
    """Live, with the rule only in the system prompt, the model still wrote a
    2,444-character assessment before the card. The tool description is what
    it reads when it decides to call the card."""
    from fsr_playbooks.llm.tools import REGISTRY
    desc = " ".join(REGISTRY["emit_card"].description.split())
    assert "IS the written assessment" in desc
    assert "instead of writing the findings out in prose" in desc
