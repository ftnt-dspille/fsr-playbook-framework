"""LM Studio provider — tool-call delta accumulation, terminal turn,
self-repair, error mapping. The OpenAI client is mocked so tests don't
need an LM Studio instance.

These tests target the wire-format translation layer, not the agent
loop semantics (those are covered by test_llm_factory's protocol tests
via FakeProvider).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.llm.lmstudio_provider import LMStudioProvider, _to_openai_messages
from backend.llm.provider import (
    DoneEvent,
    ErrorEvent,
    Message,
    TextEvent,
    ToolResultEvent,
    ToolUseEvent,
    UsageEvent,
)


# ---- Helpers ----------------------------------------------------

def _delta_chunk(*, content=None, tool_calls=None, finish=None):
    """Build a ChatCompletionChunk-shaped MagicMock the way the OpenAI
    SDK delivers them mid-stream."""
    delta = MagicMock(content=content, tool_calls=tool_calls)
    choice = MagicMock(delta=delta, finish_reason=finish)
    return MagicMock(choices=[choice], usage=None)


def _usage_chunk(prompt=10, completion=5):
    """The final 'choices=[]' chunk that carries usage tokens when
    stream_options.include_usage=True."""
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=prompt,
                                                 completion_tokens=completion))


def _tool_call_delta(*, index, id=None, name=None, args=None):
    fn = MagicMock(name=name, arguments=args)
    # MagicMock(name=...) collides with the spec arg; set explicitly.
    fn.name = name
    fn.arguments = args
    return MagicMock(index=index, id=id, function=fn)


class _FakeStream:
    """async iterator over a fixed list of chunks. Models the OpenAI
    streaming response so we can replay deterministic transcripts."""
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


def _provider_with_chunks(
    chunks: list[Any] | list[list[Any]], *, model="fake-model"
) -> LMStudioProvider:
    """Build a provider whose client returns chunks on each create() call.

    `chunks` may be a flat list (single turn) or a list-of-lists (one
    list per expected turn — handed out in order via side_effect)."""
    if chunks and isinstance(chunks[0], list):
        streams = [_FakeStream(c) for c in chunks]
        create = AsyncMock(side_effect=streams)
    else:
        create = AsyncMock(return_value=_FakeStream(chunks))
    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock(create=create)
    return LMStudioProvider(model=model, base_url="http://x/v1",
                            api_key="x", client=fake_client)


async def _drain(provider, **kw):
    out = []
    async for ev in provider.stream(**kw):
        out.append(ev)
    return out


# ---- Translation: protocol Messages → OpenAI shape --------------

def test_to_openai_messages_prepends_system():
    out = _to_openai_messages("you are X", [Message(role="user", content="hi")])
    assert out[0] == {"role": "system", "content": "you are X"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_to_openai_messages_passes_through_block_lists():
    """Internal turns we appended during the loop are already in
    OpenAI shape (assistant w/ tool_calls, tool result messages).
    Translation must not re-wrap them."""
    blocks = [{"role": "assistant", "content": None,
               "tool_calls": [{"id": "c1"}]}]
    out = _to_openai_messages("sys", [Message(role="assistant", content=blocks)])
    assert out[1] == blocks[0]


# ---- Streaming text ---------------------------------------------

def test_streams_text_chunks_as_text_events():
    chunks = [
        _delta_chunk(content="Hello "),
        _delta_chunk(content="world."),
        _delta_chunk(finish="stop"),
        _usage_chunk(prompt=20, completion=2),
    ]
    p = _provider_with_chunks(chunks)
    events = asyncio.run(_drain(p, system="s",
                                messages=[Message(role="user", content="hi")],
                                tools=[], tags={}))
    text_events = [e for e in events if isinstance(e, TextEvent)]
    assert "".join(e.text for e in text_events) == "Hello world."
    assert any(isinstance(e, DoneEvent) for e in events)


def test_emits_usage_event_with_prompt_and_completion_tokens():
    chunks = [_delta_chunk(content="hi"),
              _delta_chunk(finish="stop"),
              _usage_chunk(prompt=42, completion=7)]
    p = _provider_with_chunks(chunks)
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.input_tokens == 42
    assert usage.output_tokens == 7
    # Cache fields are zero locally — LM Studio doesn't have prompt cache.
    assert usage.cache_read == 0 and usage.cache_write == 0


# ---- Tool call delta accumulation ------------------------------

def test_accumulates_tool_call_args_across_deltas():
    """The wire delivers tool_call.function.arguments as fragmented
    JSON-string chunks. The provider must concatenate them, then
    json.loads exactly once before dispatching."""
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="call_1",
                                                  name="find_connector",
                                                  args='{"q":')]),
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, args='"virus')]),
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, args='total"}')]),
        _delta_chunk(finish="tool_calls"),
        _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="done"),
             _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider_with_chunks([turn1, turn2])
    with patch("backend.llm.lmstudio_provider.dispatch",
               return_value={"matches": []}) as mock_dispatch:
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    # The dispatch call must have received reassembled args
    mock_dispatch.assert_called_once()
    name, args = mock_dispatch.call_args[0]
    assert name == "find_connector"
    assert args == {"q": "virustotal"}
    # And the loop must have surfaced both ToolUse + ToolResult events
    assert any(isinstance(e, ToolUseEvent) for e in events)
    assert any(isinstance(e, ToolResultEvent) for e in events)


def test_malformed_tool_args_become_empty_dict_not_crash():
    """A model that emits non-JSON in arguments shouldn't kill the loop —
    surface the failure as a bad-args tool result and keep going."""
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="c",
                                                  name="find_connector",
                                                  args="not-json{{")]),
        _delta_chunk(finish="tool_calls"),
        _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="ok"),
             _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider_with_chunks([turn1, turn2])
    with patch("backend.llm.lmstudio_provider.dispatch",
               return_value={"matches": []}) as mock_dispatch:
        events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    mock_dispatch.assert_called_once()
    assert mock_dispatch.call_args[0][1] == {}


def test_parallel_tool_calls_keyed_by_index():
    """OpenAI delivers parallel tool calls under different `index`
    values. The accumulator must keep them separate."""
    turn1 = [
        _delta_chunk(tool_calls=[
            _tool_call_delta(index=0, id="c0", name="find_connector", args='{"q":"a"}'),
            _tool_call_delta(index=1, id="c1", name="get_step_type", args='{"name":"x"}'),
        ]),
        _delta_chunk(finish="tool_calls"),
        _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="ok"),
             _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider_with_chunks([turn1, turn2])
    with patch("backend.llm.lmstudio_provider.dispatch",
               return_value={}) as mock_dispatch:
        asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    assert mock_dispatch.call_count == 2
    names = sorted(c.args[0] for c in mock_dispatch.call_args_list)
    assert names == ["find_connector", "get_step_type"]


# ---- Error / config gates ---------------------------------------

def test_no_model_emits_error_event_without_calling_api():
    """If the user hasn't picked a model, fail fast with a clear
    message rather than an HTTP 400 from the endpoint."""
    p = LMStudioProvider(model="", base_url="http://x/v1", api_key="x",
                         client=MagicMock())
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    err = next(e for e in events if isinstance(e, ErrorEvent))
    assert "model" in err.message.lower()


def test_connection_error_surfaces_friendly_hint():
    """APIConnectionError → 'is LM Studio running?' instead of raw stack."""
    from openai import APIConnectionError
    create = AsyncMock(side_effect=APIConnectionError(request=MagicMock()))
    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock(create=create)
    p = LMStudioProvider(model="m", base_url="http://x:1234/v1",
                         api_key="x", client=fake_client)
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    err = next(e for e in events if isinstance(e, ErrorEvent))
    assert "lm studio" in err.message.lower() or "reach" in err.message.lower()


# ---- Self-repair -------------------------------------------------

def test_self_repair_kicks_in_on_broken_yaml():
    """A terminal text turn that contains a broken yaml block should
    trigger one extra round-trip with the compiler errors fed back as
    a synthetic user message."""
    bad_yaml_msg = "Here you go:\n```yaml\ncollection: T\nplaybooks: []\n```"
    turn1 = [_delta_chunk(content=bad_yaml_msg),
             _delta_chunk(finish="stop"), _usage_chunk()]
    turn2 = [_delta_chunk(content="(fixed)"),
             _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider_with_chunks([turn1, turn2])
    events = asyncio.run(_drain(p, system="", messages=[], tools=[], tags={}))
    # Should have gotten TWO usage events (initial turn + repair turn),
    # and the repair-turn flag should be incremented on the second.
    usages = [e for e in events if isinstance(e, UsageEvent)]
    assert len(usages) == 2
    repair_flags = [u.self_repair_turn for u in usages]
    assert repair_flags == [0, 1]
