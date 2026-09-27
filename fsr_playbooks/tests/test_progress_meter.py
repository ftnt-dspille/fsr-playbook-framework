"""A turn ends when it stops learning, not at a fixed count.

The 16-round cap fired 5 times over 362 sweep turns and every one was
productive (28-33 calls, all distinct) -- it cut builds off mid-authoring while
never meeting an actual runaway. ProgressMeter replaces it as the runaway
guard; MAX_TOOL_TURNS stays only as a cost ceiling.
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

from test_anthropic_enhance_delivery_forced import _FakeStream as _AnthropicStream
from test_anthropic_enhance_delivery_forced import _text_block, _tool_use_block, _usage
from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm._loop_helpers import (
    MAX_TOOL_TURNS,
    STALL_ERROR_ROUNDS,
    STALL_REPEAT_ROUNDS,
    ProgressMeter,
)
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolUseEvent

OK, ERR = {"ok": True}, {"ok": False, "code": "not_found"}


def _round(m, calls):
    for name, args, res in calls:
        m.note_result(name, args, res)
    return m.end_round()


def test_distinct_calls_never_stall_however_many():
    m = ProgressMeter()
    for i in range(MAX_TOOL_TURNS):
        assert _round(m, [("find", {"q": i}, OK)]) is None


def test_repeating_the_same_calls_stalls():
    m = ProgressMeter()
    assert _round(m, [("get_record", {"id": 1}, OK)]) is None   # new
    got = [_round(m, [("get_record", {"id": 1}, OK)]) for _ in range(STALL_REPEAT_ROUNDS)]
    assert got[-1] == "repeat" and all(g is None for g in got[:-1])


def test_an_error_then_a_corrected_call_is_progress():
    # A refused card re-sent with the fix: exactly how the model corrects.
    m = ProgressMeter()
    for i in range(STALL_ERROR_ROUNDS * 2):
        res = ERR if i % 2 == 0 else OK
        assert _round(m, [("emit_card", {"try": i}, res)]) is None


def test_sustained_failure_stalls():
    # Live: seven module names guessed in a row, each a 404.
    m = ProgressMeter()
    got = [_round(m, [("search_module_records", {"module": f"m{i}"}, ERR)])
           for i in range(STALL_ERROR_ROUNDS)]
    assert got[-1] == "flail" and all(g is None for g in got[:-1])


def test_one_new_call_in_a_round_resets_the_repeat_count():
    m = ProgressMeter()
    _round(m, [("a", {}, OK)])
    _round(m, [("a", {}, OK)])
    _round(m, [("a", {}, OK), ("b", {}, OK)])
    assert _round(m, [("a", {}, OK)]) is None


def test_guard_steering_is_not_failure():
    m = ProgressMeter()
    steer = {"ok": False, "kind": "guard_redirect"}
    for i in range(STALL_ERROR_ROUNDS + 1):
        assert _round(m, [("x", {"i": i}, steer)]) is None


def test_the_ceiling_is_a_cost_net_not_the_runaway_guard():
    assert MAX_TOOL_TURNS >= 32


# --- through the real loops -------------------------------------------------
_NAMES = ("get_record",)


def _dispatch(name, args):
    return {"ok": True, "record": {"name": "t"}}


def _call(cid):
    return [_delta_chunk(tool_calls=[_tc(index=0, id=cid, name="get_record",
                                         args=json.dumps({"uuid": "u"}))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


async def _drain(gen):
    return [ev async for ev in gen]


def test_openai_repeat_loop_ends_with_an_answer_round():
    rounds = [_call(f"c{i}") for i in range(STALL_REPEAT_ROUNDS + 1)]
    rounds.append([_delta_chunk(content="Here is what I found."),
                   _delta_chunk(finish="stop"), _usage_chunk()])
    sent: list = []
    queue = [_FakeStream(r) for r in rounds]

    def _create(*_a, **kw):
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="look it up")],
            tools=[{"type": "function", "function": {
                "name": "get_record", "description": "d",
                "parameters": {"type": "object", "properties": {}}}}], tags={})))
    assert sum(isinstance(e, ToolUseEvent) for e in events) == STALL_REPEAT_ROUNDS + 1
    assert isinstance(events[-1], DoneEvent)
    assert any("repeated calls" in str(m.get("content")) for m in sent[-1])


def test_anthropic_repeat_loop_ends_with_an_answer_round():
    def turn(blocks, stop):
        return _AnthropicStream([], MagicMock(content=blocks, stop_reason=stop,
                                              usage=_usage()))
    # More repeats scripted than the stall allows: without the meter the loop
    # would run all of them.
    streams = [turn([_tool_use_block(f"c{i}", "get_record", {"uuid": "u"})], "tool_use")
               for i in range(STALL_REPEAT_ROUNDS + 4)]
    streams.append(turn([_text_block("Here is what I found.")], "end_turn"))
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=streams)
    client.messages.create = AsyncMock(return_value=MagicMock(
        content=[_text_block("Here is what I found.")], stop_reason="end_turn",
        usage=_usage()))
    p = AnthropicProvider(model="claude-haiku-4-5-20251001", base_url="http://x",
                          api_key="x", client=client)
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.anthropic_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="look it up")],
            tools=[{"name": "get_record", "description": "d",
                    "input_schema": {"type": "object", "properties": {}}}], tags={})))
    assert sum(isinstance(e, ToolUseEvent) for e in events) == STALL_REPEAT_ROUNDS + 1
    assert isinstance(events[-1], DoneEvent)
    sent = json.dumps(client.messages.stream.call_args_list[-1].kwargs, default=str)
    assert "repeated calls" in sent
