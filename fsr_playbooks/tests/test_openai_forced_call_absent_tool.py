"""A forced call for a tool this turn does not carry makes no request.

`_OpenAITurn.forced_call` used to send `tools=[None]` when the name was
absent from the turn's tool set. The Chat Completions API rejects that with a
400, and the loop's callers treat `None` as "no forced call", so the guard
belongs before the request.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from fsr_playbooks.llm.openai_provider import OpenAIProvider, _OpenAITurn


def _turn(create: AsyncMock, tool_name: str) -> _OpenAITurn:
    client = MagicMock()
    client.chat.completions.create = create
    provider = OpenAIProvider(model="gpt-4o", base_url="http://x/v1", api_key="x",
                              client=client)
    return _OpenAITurn(provider, "sys", [], [
        {"type": "function", "function": {"name": tool_name, "parameters": {}}},
    ])


def test_forced_call_for_absent_tool_returns_none_without_a_request():
    create = AsyncMock()
    turn = _turn(create, "get_record")

    assert asyncio.run(turn.forced_call("emit_card")) is None
    create.assert_not_called()


def test_forced_call_for_present_tool_still_sends_it():
    create = AsyncMock(side_effect=RuntimeError("stop after the request"))
    turn = _turn(create, "emit_card")

    try:
        asyncio.run(turn.forced_call("emit_card"))
    except RuntimeError:
        pass

    create.assert_awaited_once()
    sent = create.await_args.kwargs["tools"]
    assert [t["function"]["name"] for t in sent] == ["emit_card"]
