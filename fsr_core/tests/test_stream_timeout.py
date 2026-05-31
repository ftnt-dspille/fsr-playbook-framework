"""§2.2 — stream timeout in AnthropicProvider.

Verifies that a hung Anthropic stream is cancelled after STREAM_TIMEOUT_SECS
and surfaces a clean ErrorEvent instead of blocking forever.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fsr_core.llm import anthropic_provider as ap
from fsr_core.llm.anthropic_provider import AnthropicProvider
from fsr_core.llm.provider import DoneEvent, ErrorEvent, Message


class _HangingStreamCtx:
    """Stream context manager that never completes."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def _hang():
            await asyncio.sleep(9999)
            if False:
                yield None
        return _hang()

    async def get_final_message(self):
        await asyncio.sleep(9999)


class _HangingClient:
    class messages:
        @staticmethod
        def stream(**kwargs):
            return _HangingStreamCtx()


async def _collect(provider, messages):
    events = []
    async for ev in provider.stream(system="sys", messages=messages, tools=[]):
        events.append(ev)
    return events


def _make_provider():
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._client = _HangingClient()
    provider.model = "claude-haiku-4-5-20251001"
    return provider


def test_stream_timeout_yields_error_event(monkeypatch):
    monkeypatch.setattr(ap, "STREAM_TIMEOUT_SECS", 1)
    provider = _make_provider()
    messages: list[Message] = [Message(role="user", content="ping")]

    events = asyncio.run(
        asyncio.wait_for(_collect(provider, messages), timeout=5)
    )

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    done_events = [e for e in events if isinstance(e, DoneEvent)]
    assert error_events, "expected an ErrorEvent on stream timeout"
    assert "timed out" in error_events[0].message.lower()
    # Stream exits via return after ErrorEvent — no DoneEvent, consistent with
    # other error paths (APIConnectionError, AuthenticationError, etc.).


def test_stream_timeout_does_not_block(monkeypatch):
    """Turn must resolve within 3× the timeout, not hang forever."""
    monkeypatch.setattr(ap, "STREAM_TIMEOUT_SECS", 1)
    provider = _make_provider()
    messages: list[Message] = [Message(role="user", content="ping")]

    # If the fix isn't working this wait_for will hit 3s and raise TimeoutError.
    asyncio.run(
        asyncio.wait_for(_collect(provider, messages), timeout=3)
    )
