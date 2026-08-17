"""Approved tier-3 dispatch must run OFF the event loop on resume.

Live MCP tools open their own event loop internally (``asyncio.run`` inside
``_CrudhubMCP._session_call``). The main provider loop dispatches tools via
``asyncio.to_thread`` so that works; the resume path used to call ``dispatch``
inline inside the running loop, so every approved live-MCP action died with
``RuntimeError: asyncio.run() cannot be called from a running event loop`` --
the analyst saw "Approved -- but the action did not run" (live-verified on a
lab appliance, 2026-08-17).

These tests pin, for all three providers:
  * an approved tool whose fn calls ``asyncio.run`` internally executes and
    surfaces its real result;
  * the result is preceded by a NAMED synthetic ToolUseEvent (without it the
    widget renders a nameless "Used skill tool" chip on every resume);
  * resume re-enters the loop with the suspended turn's tool slice, and
    tolerates old pickled sessions that predate the ``tools`` field.
"""
from __future__ import annotations

import asyncio

import pytest

from fsr_playbooks.llm import approvals as A
from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.fortiai_proxy_provider import FortiAIProxyProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import ToolResultEvent, ToolUseEvent

_TOOL = "loopy_block_for_test"
_SLICE = [{"name": _TOOL, "description": "d", "input_schema": {}}]


def _loopy_tool() -> dict:
    # Mirrors a live MCP tool: spins up its own loop for the transport.
    asyncio.run(asyncio.sleep(0))
    return {"ok": True, "code": "ran"}


@pytest.fixture()
def _registered(monkeypatch):
    monkeypatch.setitem(
        T.REGISTRY,
        _TOOL,
        T.ToolSpec(
            name=_TOOL, description="test tool that owns its own loop",
            input_schema={"type": "object", "properties": {}},
            fn=_loopy_tool, tier=3,
        ),
    )


def _session(**over) -> A.SuspendedSession:
    base = dict(
        approval_id="ap-loop", session_id="s-loop", tool=_TOOL,
        tool_use_id="tu-loop", args={}, tier=3,
        history_snapshot=[], prior_tool_result_blocks=[],
        remaining_tool_calls=[], system="sys", tags={}, tools=list(_SLICE),
    )
    base.update(over)
    s = A.SuspendedSession(**base)
    A.bind(s)
    return s


def _resume_prefix(provider, suspended=None):
    """Drive resume() through the approved call's ToolUse+ToolResult pair,
    then stop -- the dispatch happens before the first yield, so the fake
    client is never asked to stream a model reply. Returns (use, result,
    captured_stream_tools)."""
    captured: dict = {}
    orig_stream = provider.stream

    async def _capture_stream(*, tools=None, **kw):
        captured["tools"] = tools
        return
        yield  # pragma: no cover -- makes this an async generator

    provider.stream = _capture_stream

    async def _go():
        events = []
        agen = provider.resume(
            suspended=suspended or _session(), decision="approve")
        try:
            # Consume fully: the stubbed stream() yields nothing, so the
            # generator terminates right after capturing the tool slice.
            async for ev in agen:
                events.append(ev)
        finally:
            provider.stream = orig_stream
        return events

    events = asyncio.run(_go())
    uses = [e for e in events if isinstance(e, ToolUseEvent)]
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert uses and results, events
    return uses[0], results[0], captured


_PROVIDERS = [
    lambda: AnthropicProvider(model="fake", client=object()),
    lambda: OpenAIProvider(model="fake", client=object()),
    lambda: FortiAIProxyProvider(model="fake", base_url="http://x", api_key="k"),
]


@pytest.mark.parametrize("mk", _PROVIDERS)
def test_resume_runs_loop_owning_tool_and_names_it(mk, _registered):
    use, result, _ = _resume_prefix(mk())
    assert result.result == {"ok": True, "code": "ran"}
    assert use.name == _TOOL and use.synthetic and use.call_id == "tu-loop"


@pytest.mark.parametrize("mk", _PROVIDERS)
def test_resume_reenters_with_suspended_tool_slice(mk, _registered):
    _, _, captured = _resume_prefix(mk())
    assert captured.get("tools") == _SLICE


@pytest.mark.parametrize("mk", _PROVIDERS)
def test_resume_tolerates_prefield_pickled_session(mk, _registered):
    # Old pickled sessions restore without the `tools` attr entirely.
    s = _session()
    del s.__dict__["tools"]
    _, result, captured = _resume_prefix(mk(), suspended=s)
    assert result.result == {"ok": True, "code": "ran"}
    assert captured.get("tools") == []
