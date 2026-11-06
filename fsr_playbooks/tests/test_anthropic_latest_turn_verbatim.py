"""The latest assistant turn goes back to Anthropic exactly as it came out.

With adaptive thinking on (Sonnet 5 family) the API refuses a request whose
latest assistant message differs from the response that produced it:
`400 messages.N.content.2: thinking or redacted_thinking blocks in the latest
assistant message cannot be modified`. `_parse` rebuilt the message from only
text / thinking / tool_use blocks, so a round that also carried server-side
blocks (the deferred-tool search: `server_tool_use` + `tool_search_tool_result`)
lost them, and the thinking block after them moved. Haiku never searched (it is
outside the tool-search family), which is why only the Sonnet config failed.

These use real SDK response objects, not mocks, so the block shapes are the
ones the live API returns.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import Message as SdkMessage
from test_anthropic_enhance_delivery_forced import _FakeStream
from test_anthropic_thinking_replayed import assert_preserved_thinking_contract

from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import Message

_TOOLS = [{"name": "get_record", "description": "read a record",
           "input_schema": {"type": "object", "properties": {}}}]

_SEARCH_ROUND = [
    {"type": "thinking", "thinking": "Need the SIEM tool.", "signature": "sig-1"},
    {"type": "text", "text": "Looking for the right tool."},
    {"type": "server_tool_use", "id": "srvtoolu_1", "name": "tool_search_tool_bm25",
     "input": {"query": "incident"}},
    {"type": "tool_search_tool_result", "tool_use_id": "srvtoolu_1",
     "content": {"type": "tool_search_tool_search_result",
                 "tool_references": [{"type": "tool_reference",
                                      "tool_name": "get_record"}]}},
    {"type": "thinking", "thinking": "Found it; read the record.", "signature": "sig-2"},
    {"type": "tool_use", "id": "toolu_1", "name": "get_record", "input": {"id": 7}},
]


def _final(content: list[dict[str, Any]], stop: str) -> SdkMessage:
    return SdkMessage.model_validate({
        "id": "msg", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
        "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "content": content})


def _run(rounds: list[_FakeStream]) -> list[list[Any]]:
    sent: list[list[Any]] = []
    queue = list(rounds)

    def _call(*_a, **kw):
        assert_preserved_thinking_contract(kw["messages"])
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)

    client = MagicMock()
    client.messages.stream = MagicMock(side_effect=_call)
    client.beta.messages.stream = MagicMock(side_effect=_call)
    client.messages.create = AsyncMock()
    p = AnthropicProvider(model="claude-sonnet-5", base_url="http://x",
                          api_key="x", client=client)
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(return_value={"ok": True})), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        async def _drain():
            return [ev async for ev in p.stream(
                system="s", messages=[Message(role="user", content="what happened?")],
                tools=_TOOLS, tags={})]
        asyncio.run(_drain())
    return sent


def _strip_cache(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in b.items() if k != "cache_control"} for b in blocks]


def test_latest_assistant_turn_is_replayed_byte_identical():
    sent = _run([
        _FakeStream([], _final(_SEARCH_ROUND, "tool_use")),
        _FakeStream(["Benign."], _final([{"type": "text", "text": "Benign."}], "end_turn")),
    ])
    assert len(sent) == 2, "the loop never sent its second round"
    latest = [m for m in sent[1] if m["role"] == "assistant"][-1]
    # Same blocks, same order, same thinking text and signatures.
    assert _strip_cache(latest["content"]) == _SEARCH_ROUND
    assert latest["content"][4]["signature"] == "sig-2"


def test_server_blocks_survive_into_an_earlier_turn_without_thinking():
    second = [
        {"type": "thinking", "thinking": "One more read.", "signature": "sig-3"},
        {"type": "tool_use", "id": "toolu_2", "name": "get_record", "input": {"id": 8}},
    ]
    sent = _run([
        _FakeStream([], _final(_SEARCH_ROUND, "tool_use")),
        _FakeStream([], _final(second, "tool_use")),
        _FakeStream(["done"], _final([{"type": "text", "text": "done"}], "end_turn")),
    ])
    assert len(sent) == 3
    asst = [m for m in sent[2] if m["role"] == "assistant"]
    # The earlier turn drops only its thinking; the search pair stays paired.
    assert [b["type"] for b in asst[0]["content"]] == [
        "text", "server_tool_use", "tool_search_tool_result", "tool_use"]
    assert _strip_cache(asst[-1]["content"]) == second
