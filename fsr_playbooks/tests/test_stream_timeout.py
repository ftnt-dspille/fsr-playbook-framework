"""§2.2 -- stream timeout in AnthropicProvider.

Verifies that a hung Anthropic stream is cancelled after STREAM_TIMEOUT_SECS
and surfaces a clean ErrorEvent instead of blocking forever.

No wall-clock waits: the hung stream blocks on a gate that is never set, the
timeout is 0.05s, and the assertions are on ordering (stream entered, then
cancelled by the idle timeout, then ErrorEvent yielded), not on elapsed time.
The outer `wait_for` is only a safety net against a regression hanging the run.
"""
from __future__ import annotations

import asyncio
import threading

from fsr_playbooks.llm import agent_loop
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import DoneEvent, ErrorEvent, Message

TIMEOUT_SECS = 0.05
SAFETY_NET_SECS = 10


class _Probe:
    """Ordered record of what the hung stream did, shared with the test."""

    def __init__(self):
        self.order: list[str] = []
        self.entered = threading.Event()
        self.cancelled = threading.Event()

    def mark(self, label: str) -> None:
        self.order.append(label)


class _HangingStreamCtx:
    """Stream context manager that never completes until cancelled."""

    def __init__(self, probe: _Probe):
        self._probe = probe
        self._gate = asyncio.Event()  # never set: the stream hangs until cancelled

    async def _block(self):
        self._probe.entered.set()
        self._probe.mark("entered")
        try:
            await self._gate.wait()
        except asyncio.CancelledError:
            self._probe.cancelled.set()
            self._probe.mark("cancelled")
            raise

    async def _hang(self):
        await self._block()
        if False:
            yield None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._hang()

    async def get_final_message(self):
        await self._block()


class _HangingClient:
    def __init__(self, probe: _Probe):
        class messages:  # noqa: N801 -- mirrors the SDK attribute path
            @staticmethod
            def stream(**kwargs):
                return _HangingStreamCtx(probe)

        self.messages = messages


async def _collect(provider, messages, probe: _Probe):
    events = []
    async for ev in provider.stream(system="sys", messages=messages, tools=[]):
        events.append(ev)
        probe.mark(type(ev).__name__)
    return events


def _make_provider(probe: _Probe):
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._client = _HangingClient(probe)
    provider.model = "claude-haiku-4-5-20251001"
    return provider


def test_stream_timeout_yields_error_event(monkeypatch):
    monkeypatch.setattr(agent_loop, "STREAM_TIMEOUT_SECS", TIMEOUT_SECS)
    probe = _Probe()
    provider = _make_provider(probe)
    messages: list[Message] = [Message(role="user", content="ping")]

    events = asyncio.run(
        asyncio.wait_for(_collect(provider, messages, probe), timeout=SAFETY_NET_SECS)
    )

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert error_events, "expected an ErrorEvent on stream timeout"
    assert "timed out" in error_events[0].message.lower()
    # Stream exits via return after ErrorEvent -- no DoneEvent, consistent with
    # other error paths (APIConnectionError, AuthenticationError, etc.).
    assert not [e for e in events if isinstance(e, DoneEvent)]


def test_stream_timeout_cancels_the_hung_stream(monkeypatch):
    """The hung stream is entered, then cancelled rather than left running.

    Ordering is only "entered before the ErrorEvent": the idle timeout yields the
    ErrorEvent while the pump task's cancellation is delivered asynchronously, so
    the stream's cancel handler may run after the ErrorEvent.
    """
    monkeypatch.setattr(agent_loop, "STREAM_TIMEOUT_SECS", TIMEOUT_SECS)
    probe = _Probe()
    provider = _make_provider(probe)
    messages: list[Message] = [Message(role="user", content="ping")]

    asyncio.run(
        asyncio.wait_for(_collect(provider, messages, probe), timeout=SAFETY_NET_SECS)
    )

    assert probe.entered.is_set() and probe.cancelled.is_set()
    assert probe.order.index("entered") < probe.order.index("ErrorEvent"), probe.order
