"""The model's reasoning goes back to it inside the tool loop.

`_parse` kept only text and tool_use blocks, so a thinking block never reached
history: each round of a 17-round investigation started without the reasoning
that chose the previous call, and the long silent rounds at the end of a live
triage turn were the model re-deriving it. The thinking also never reached the
audit row, which is why that latency could only be inferred from token counts.

These drive the real provider loop and check what each request SENT.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from test_anthropic_enhance_delivery_forced import (
    _FakeStream,
    _text_block,
    _tool_use_block,
    _usage,
)

from fsr_playbooks.llm.anthropic_provider import AnthropicProvider, _without_thinking
from fsr_playbooks.llm.provider import Message, UsageEvent

_TOOLS = [{"name": "get_record", "description": "read a record",
           "input_schema": {"type": "object", "properties": {}}}]


def _thinking_block(text: str, sig: str) -> MagicMock:
    return MagicMock(type="thinking", thinking=text, signature=sig)


def assert_preserved_thinking_contract(messages: list[Any]) -> None:
    """Enforce, OFFLINE, the server-side rule that bites preserved-thinking
    models (Haiku 5.5, Sonnet 5.5, Opus 5.x, Fable 5.x): a request may carry
    thinking/redacted_thinking blocks ONLY on the LATEST assistant turn. Resending
    an earlier turn's thinking is a live `400 ... thinking or redacted_thinking
    blocks in the latest assistant message cannot be modified`.

    This is the backstop that records-vs-validates: the loop tests send real
    request bodies through it, so ANY future regression that replays old thinking
    fails here for free, not months later on a live box."""
    asst_idx = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    for i in asst_idx[:-1]:  # every assistant turn except the last
        c = messages[i].get("content")
        if isinstance(c, list) and any(
                isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking")
                for b in c):
            raise AssertionError(
                f"preserved-thinking contract violated: assistant turn at "
                f"messages[{i}] (not the latest) still carries a thinking block -- "
                f"a live preserved-thinking model would 400 on this request.")


def _run(rounds: list[_FakeStream]) -> tuple[list[list[Any]], list[Any]]:
    sent: list[list[Any]] = []
    queue = list(rounds)

    def _call(*_a, **kw):
        # Validate every outgoing request against the live contract, not just
        # record it -- a mock that only records is how this class of bug ships.
        assert_preserved_thinking_contract(kw["messages"])
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=_call)
    client.messages.create = AsyncMock()
    p = AnthropicProvider(model="claude-sonnet-4-6", base_url="http://x",
                          api_key="x", client=client)
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(return_value={"ok": True})), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        async def _drain():
            return [ev async for ev in p.stream(
                system="s", messages=[Message(role="user", content="what happened?")],
                tools=_TOOLS, tags={})]
        events = asyncio.run(_drain())
    return sent, events


def _research_then_answer():
    research = _FakeStream([], MagicMock(
        content=[_thinking_block("The host is the pivot; read the record first.", "sig-1"),
                 _tool_use_block("c1", "get_record", {})],
        stop_reason="tool_use", usage=_usage()))
    answer = _FakeStream(["Benign."], MagicMock(
        content=[_thinking_block("Nothing on the host.", "sig-2"), _text_block("Benign.")],
        stop_reason="end_turn", usage=_usage()))
    return [research, answer]


def test_the_next_request_carries_the_rounds_thinking_verbatim():
    sent, _ = _run(_research_then_answer())
    assert len(sent) == 2, "the loop never sent its second round"
    assistant = [m for m in sent[1] if m["role"] == "assistant"][-1]
    blocks = assistant["content"]
    # Order matters: the reasoning precedes the call it chose.
    assert [b["type"] for b in blocks] == ["thinking", "tool_use"]
    assert blocks[0]["thinking"] == "The host is the pivot; read the record first."
    assert blocks[0]["signature"] == "sig-1"
    assert "cache_control" not in blocks[0]


def test_each_rounds_thinking_rides_its_usage_event():
    _, events = _run(_research_then_answer())
    usage = [e for e in events if isinstance(e, UsageEvent)]
    assert [u.thinking for u in usage] == [
        "The host is the pivot; read the record first.", "Nothing on the host."]


def _two_tools_then_answer():
    # Two tool rounds, then an answer: mirrors the live "list connectors ->
    # look up connector -> continue" turn that hit the 400.
    r1 = _FakeStream([], MagicMock(
        content=[_thinking_block("Reason one.", "sig-1"),
                 _tool_use_block("c1", "get_record", {})],
        stop_reason="tool_use", usage=_usage()))
    r2 = _FakeStream([], MagicMock(
        content=[_thinking_block("Reason two.", "sig-2"),
                 _tool_use_block("c2", "get_record", {})],
        stop_reason="tool_use", usage=_usage()))
    answer = _FakeStream(["done"], MagicMock(
        content=[_text_block("done")], stop_reason="end_turn", usage=_usage()))
    return [r1, r2, answer]


def test_only_the_latest_assistant_turn_keeps_its_thinking():
    # The preserved-thinking guard: resending an EARLIER turn's thinking block is
    # a 400 (`... blocks in the latest assistant message cannot be modified`).
    # The 3rd request must carry the FIRST assistant turn WITHOUT thinking and the
    # SECOND (latest) assistant turn WITH it.
    sent, _ = _run(_two_tools_then_answer())
    assert len(sent) == 3, "the loop did not reach the third request"
    third = sent[2]
    assistants = [m for m in third if m["role"] == "assistant"]
    assert len(assistants) == 2
    first_types = [b["type"] for b in assistants[0]["content"]]
    last_types = [b["type"] for b in assistants[-1]["content"]]
    assert "thinking" not in first_types, (
        "earlier assistant turn still carries thinking -- this is the 400 trigger")
    assert first_types == ["tool_use"]
    assert last_types == ["thinking", "tool_use"], "latest turn must keep its reasoning"
    assert assistants[-1]["content"][0]["signature"] == "sig-2"


def test_the_contract_validator_catches_a_stale_thinking_block():
    # Prove the backstop bites: an earlier assistant turn carrying thinking must
    # raise, and a clean history must pass.
    import pytest
    bad = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "old", "signature": "s1"},
            {"type": "tool_use", "id": "c1", "name": "get_record", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{}"}]},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "new", "signature": "s2"},
            {"type": "tool_use", "id": "c2", "name": "get_record", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c2", "content": "{}"}]},
    ]
    with pytest.raises(AssertionError, match="preserved-thinking contract"):
        assert_preserved_thinking_contract(bad)
    # The latest assistant turn keeping thinking is fine.
    ok = [bad[0], {"role": "assistant", "content": bad[1]["content"]}, bad[2]]
    assert_preserved_thinking_contract(ok)  # no raise


def test_redacted_thinking_is_kept_too():
    research = _FakeStream([], MagicMock(
        content=[MagicMock(type="redacted_thinking", data="opaque"),
                 _tool_use_block("c1", "get_record", {})],
        stop_reason="tool_use", usage=_usage()))
    answer = _FakeStream(["ok"], MagicMock(
        content=[_text_block("ok")], stop_reason="end_turn", usage=_usage()))
    sent, _ = _run([research, answer])
    assistant = [m for m in sent[1] if m["role"] == "assistant"][-1]
    assert assistant["content"][0] == {"type": "redacted_thinking", "data": "opaque"}


def test_side_requests_go_out_without_thinking():
    msgs = [{"role": "user", "content": "q"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "t", "signature": "s"},
                {"type": "tool_use", "id": "c1", "name": "get_record", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c1", "content": "{}"}]}]
    out = _without_thinking(msgs)
    assert [b["type"] for b in out[1]["content"]] == ["tool_use"]
    assert msgs[1]["content"][0]["type"] == "thinking", "the history itself was mutated"
