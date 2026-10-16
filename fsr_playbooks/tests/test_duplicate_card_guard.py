"""The same card is not emitted twice in one turn (tracker #170).

Live (offline sweep, boundary_absent_connector): one model emitted the SAME
capability_gap card, same id, five times in a single turn. A gap card is the
turn's answer, so any second gap is refused; any other card is refused only
when its (card_type, id) is already on screen. A failed emit is not "on
screen", so the model may fix and resend it.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, ToolResultEvent


def _delta_chunk(*, content=None, tool_calls=None, finish=None):
    delta = MagicMock(content=content, tool_calls=tool_calls)
    return MagicMock(choices=[MagicMock(delta=delta, finish_reason=finish)], usage=None)


def _usage_chunk():
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=10, completion_tokens=5))


def _tc(*, index, id=None, name=None, args=None):
    fn = MagicMock()
    fn.name = name
    fn.arguments = args
    return MagicMock(index=index, id=id, function=fn)


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


async def _drain(gen):
    return [ev async for ev in gen]

_TOOLS = [{"type": "function", "function": {
    "name": "emit_card", "description": "card",
    "parameters": {"type": "object", "properties": {
        "card_type": {"type": "string"}, "payload": {"type": "object"}}}}}]


def _emit(index, card_type, cid, **extra):
    payload = {"id": cid, **extra} if cid else dict(extra)
    return _tc(index=index, id=f"t{index}", name="emit_card",
               args=json.dumps({"card_type": card_type, "payload": payload}))


def _run(calls, dispatch):
    rounds = [_FakeStream([_delta_chunk(tool_calls=calls),
                           _delta_chunk(finish="tool_calls"), _usage_chunk()]),
              _FakeStream([_delta_chunk(content="done"),
                           _delta_chunk(finish="stop"), _usage_chunk()])]
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=rounds))
    p = OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1", api_key="x", client=client)
    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(side_effect=dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="isolate with crowdstrike")],
            tools=_TOOLS, tags={})))
    return [e.result for e in events if isinstance(e, ToolResultEvent)]


def _ok(name, args):
    return {"ok": True, "card": {"type": (args or {}).get("card_type")}}


def _codes(results):
    return [r.get("code") if r.get("ok") is not True else "ok" for r in results]


def test_the_same_gap_card_five_times_renders_once():
    calls = [_emit(i, "capability_gap", "gap_crowdstrike", summary="s") for i in range(5)]
    assert _codes(_run(calls, _ok)) == ["ok"] + ["duplicate_card"] * 4


def test_a_second_gap_card_with_a_new_id_is_refused_too():
    calls = [_emit(0, "capability_gap", "gap_a"), _emit(1, "capability_gap", "gap_b"),
             _emit(2, "capability_gap", "")]
    assert _codes(_run(calls, _ok)) == ["ok", "duplicate_card", "duplicate_card"]


def test_distinct_cards_are_not_blocked():
    calls = [_emit(0, "action", "block_ip"), _emit(1, "action", "isolate_host"),
             _emit(2, "choice", "pick"), _emit(3, "action", "block_ip")]
    assert _codes(_run(calls, _ok)) == ["ok", "ok", "ok", "duplicate_card"]


def test_a_failed_emit_can_be_fixed_and_resent():
    seen = []

    def dispatch(name, args):
        seen.append(args)
        if len(seen) == 1:
            return {"ok": False, "code": "bad_payload", "message": "summary required"}
        return _ok(name, args)

    calls = [_emit(0, "capability_gap", "gap_a"),
             _emit(1, "capability_gap", "gap_a", summary="fixed")]
    assert _codes(_run(calls, dispatch)) == ["bad_payload", "ok"]
