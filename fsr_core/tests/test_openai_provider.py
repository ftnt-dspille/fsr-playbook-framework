"""OpenAIProvider — wire-format translation + HITL approval parity.

The OpenAI client is mocked so tests need no live endpoint. These cover
the bits that differ from / extend the LM Studio loop: tool-call delta
accumulation, and the tier-3+ approval suspend → resume round-trip that
the FortiSOAR connector depends on.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_core.llm.approvals import InMemoryApprovalGateway
from fsr_core.llm.openai_provider import OpenAIProvider
from fsr_core.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)


def _delta_chunk(*, content=None, tool_calls=None, finish=None):
    delta = MagicMock(content=content, tool_calls=tool_calls)
    choice = MagicMock(delta=delta, finish_reason=finish)
    return MagicMock(choices=[choice], usage=None)


def _usage_chunk(prompt=10, completion=5):
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=prompt,
                                                 completion_tokens=completion))


def _tool_call_delta(*, index, id=None, name=None, args=None):
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


def _provider(chunks, *, gateway=None, model="gpt-4o"):
    if chunks and isinstance(chunks[0], list):
        create = AsyncMock(side_effect=[_FakeStream(c) for c in chunks])
    else:
        create = AsyncMock(return_value=_FakeStream(chunks))
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    return OpenAIProvider(model=model, base_url="http://x/v1", api_key="x",
                          client=client, approval_gateway=gateway)


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


# Explicit tool schema so `block_ip` passes the intent-slice guard
# (allowed_names is derived from the advertised tools, not the registry).
_BLOCK_IP_TOOLS = [{
    "type": "function",
    "function": {"name": "block_ip", "description": "Block an IP",
                 "parameters": {"type": "object",
                                "properties": {"ip": {"type": "string"}}}},
}]


def test_streams_text_and_usage():
    chunks = [_delta_chunk(content="Hello "), _delta_chunk(content="world."),
              _delta_chunk(finish="stop"), _usage_chunk(prompt=20, completion=3)]
    p = _provider(chunks)
    events = asyncio.run(_drain(p.stream(
        system="s", messages=[Message(role="user", content="hi")],
        tools=[], tags={})))
    assert "".join(e.text for e in events if isinstance(e, TextEvent)) == "Hello world."
    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.input_tokens == 20 and usage.output_tokens == 3
    assert any(isinstance(e, DoneEvent) for e in events)


def test_accumulates_tool_call_args_across_deltas():
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="c1",
                                                  name="find_connector", args='{"q":')]),
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, args='"virus')]),
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, args='total"}')]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="done"), _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider([turn1, turn2])
    with patch("fsr_core.llm.openai_provider.dispatch",
               return_value={"matches": []}) as mock_dispatch, \
         patch("fsr_core.llm.openai_provider._tier_for", return_value=1):
        events = asyncio.run(_drain(p.stream(system="", messages=[], tools=[], tags={})))
    mock_dispatch.assert_called_once()
    name, args = mock_dispatch.call_args[0]
    assert name == "find_connector" and args == {"q": "virustotal"}
    assert any(isinstance(e, ToolUseEvent) for e in events)
    assert any(isinstance(e, ToolResultEvent) for e in events)


def test_tool_result_carries_duration_ms():
    """Every dispatched tool stamps server-side wall-time (ms) on its
    ToolResultEvent and the matching ToolCallUsage, so the widget can
    freeze a per-tool duration and the turn record can profile slowness."""
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="c1",
                                                  name="find_connector", args='{"q":"vt"}')]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="done"), _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider([turn1, turn2])
    with patch("fsr_core.llm.openai_provider.dispatch",
               return_value={"matches": []}), \
         patch("fsr_core.llm.openai_provider._tier_for", return_value=1):
        events = asyncio.run(_drain(p.stream(system="", messages=[], tools=[], tags={})))
    tr = next(e for e in events if isinstance(e, ToolResultEvent))
    assert isinstance(tr.duration_ms, int) and tr.duration_ms >= 0
    usage = next(e for e in events
                 if isinstance(e, UsageEvent) and e.tool_calls)
    assert usage.tool_calls[0].duration_ms == tr.duration_ms


def test_tier3_call_suspends_and_stashes_session():
    """A tier-3+ tool returning pending_approval must emit an
    ApprovalRequestEvent + DoneEvent(pending_approval) and stash the
    session in the injected gateway (connector-critical path)."""
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="call_x",
                                                  name="block_ip", args='{"ip":"1.2.3.4"}')]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    gw = InMemoryApprovalGateway()
    p = _provider(turn1, gateway=gw)
    envelope = {"pending_approval": True, "approval_id": "appr_1", "tier": 3,
                "tool": "block_ip", "preview": {"ip": "1.2.3.4"},
                "args_hash": "abc", "summary": "Block 1.2.3.4",
                "requires_step_up": False}
    with patch("fsr_core.llm.openai_provider.dispatch", return_value=envelope), \
         patch("fsr_core.llm.openai_provider._tier_for", return_value=3):
        events = asyncio.run(_drain(p.stream(system="sys", messages=[
            Message(role="user", content="block that ip")], tools=_BLOCK_IP_TOOLS, tags={})))
    appr = next(e for e in events if isinstance(e, ApprovalRequestEvent))
    assert appr.approval_id == "appr_1" and appr.tier == 3
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.stop_reason == "pending_approval"
    stashed = gw.peek("appr_1")
    assert stashed is not None
    assert stashed.tool == "block_ip" and stashed.tool_use_id == "call_x"
    # The assistant tool_calls turn is in the snapshot; system is NOT.
    assert all(m.get("role") != "system" for m in stashed.history_snapshot)
    assert any(m.get("role") == "assistant" and m.get("tool_calls")
               for m in stashed.history_snapshot)


def test_resume_approve_redispatches_and_continues():
    """Resuming an approved suspension re-dispatches the gated tool with
    _approved=True, emits its ToolResultEvent, and re-enters the loop to
    produce the model's closing turn."""
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="call_x",
                                                  name="block_ip", args='{"ip":"1.2.3.4"}')]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    post_resume = [_delta_chunk(content="Blocked."), _delta_chunk(finish="stop"), _usage_chunk()]
    gw = InMemoryApprovalGateway()
    p = _provider([turn1, post_resume], gateway=gw)

    envelope = {"pending_approval": True, "approval_id": "appr_2", "tier": 3,
                "tool": "block_ip", "preview": {}, "args_hash": "h",
                "requires_step_up": False}
    with patch("fsr_core.llm.openai_provider.dispatch", return_value=envelope), \
         patch("fsr_core.llm.openai_provider._tier_for", return_value=3):
        asyncio.run(_drain(p.stream(system="sys", messages=[
            Message(role="user", content="block it")], tools=_BLOCK_IP_TOOLS, tags={})))

    suspended = gw.pop("appr_2")
    assert suspended is not None

    with patch("fsr_core.llm.openai_provider.dispatch",
               return_value={"ok": True, "blocked": "1.2.3.4"}) as mock_dispatch:
        events = asyncio.run(_drain(p.resume(suspended=suspended, decision="approve")))

    # re-dispatched with the approval bypass sentinel
    assert mock_dispatch.call_args[0][0] == "block_ip"
    assert mock_dispatch.call_args[0][1].get("_approved") is True
    tr = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tr.call_id == "call_x" and tr.result.get("ok") is True
    # loop continued: closing text + terminal done
    assert "".join(e.text for e in events if isinstance(e, TextEvent)) == "Blocked."
    assert any(isinstance(e, DoneEvent) for e in events)


def test_resume_deny_synthesizes_denial_without_dispatch():
    gw = InMemoryApprovalGateway()
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="call_d",
                                                  name="block_ip", args='{"ip":"9.9.9.9"}')]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    post = [_delta_chunk(content="Understood, not blocking."),
            _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider([turn1, post], gateway=gw)
    envelope = {"pending_approval": True, "approval_id": "appr_3", "tier": 3,
                "tool": "block_ip", "preview": {}, "args_hash": "h"}
    with patch("fsr_core.llm.openai_provider.dispatch", return_value=envelope), \
         patch("fsr_core.llm.openai_provider._tier_for", return_value=3):
        asyncio.run(_drain(p.stream(system="sys", messages=[
            Message(role="user", content="block it")], tools=_BLOCK_IP_TOOLS, tags={})))
    suspended = gw.pop("appr_3")
    # On deny, dispatch must NOT be called for the gated tool.
    with patch("fsr_core.llm.openai_provider.dispatch") as mock_dispatch:
        events = asyncio.run(_drain(p.resume(suspended=suspended, decision="deny")))
    mock_dispatch.assert_not_called()
    tr = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tr.result.get("code") == "user_denied"
