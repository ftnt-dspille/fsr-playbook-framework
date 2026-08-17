"""Approved tier-3 dispatch must run OFF the event loop on resume.

Live MCP tools open their own event loop internally (``asyncio.run`` inside
``_CrudhubMCP._session_call``). The main provider loop dispatches tools via
``asyncio.to_thread`` so that works; the resume path used to call ``dispatch``
inline inside the running loop, so every approved live-MCP action died with
``RuntimeError: asyncio.run() cannot be called from a running event loop`` --
the analyst saw "Approved -- but the action did not run" (live-verified on a
lab appliance, 2026-08-17).

These tests pin the fix for both providers: an approved tool whose fn calls
``asyncio.run`` internally must execute and surface its real result in the
first ``ToolResultEvent``.
"""
from __future__ import annotations

import asyncio

import pytest

from fsr_playbooks.llm import approvals as A
from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import ToolResultEvent

_TOOL = "loopy_block_for_test"


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


def _session() -> A.SuspendedSession:
    s = A.SuspendedSession(
        approval_id="ap-loop", session_id="s-loop", tool=_TOOL,
        tool_use_id="tu-loop", args={}, tier=3,
        history_snapshot=[], prior_tool_result_blocks=[],
        remaining_tool_calls=[], system="sys", tags={},
    )
    A.bind(s)
    return s


def _first_tool_result(provider) -> dict:
    """Drive resume() until the approved call's ToolResultEvent, then stop.

    The dispatch happens before the first yield; stopping there keeps the
    fake client from ever being asked to stream a model reply.
    """
    async def _go():
        agen = provider.resume(suspended=_session(), decision="approve")
        try:
            async for ev in agen:
                if isinstance(ev, ToolResultEvent):
                    return ev.result
                raise AssertionError(f"unexpected event before result: {ev!r}")
        finally:
            await agen.aclose()
        raise AssertionError("resume yielded no ToolResultEvent")

    return asyncio.run(_go())


def test_anthropic_resume_runs_loop_owning_tool(_registered):
    result = _first_tool_result(AnthropicProvider(model="fake", client=object()))
    assert result == {"ok": True, "code": "ran"}


def test_openai_resume_runs_loop_owning_tool(_registered):
    result = _first_tool_result(OpenAIProvider(model="fake", client=object()))
    assert result == {"ok": True, "code": "ran"}
