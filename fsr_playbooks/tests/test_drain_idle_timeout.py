"""§2.2 — `drain_with_idle_timeout`: the shared live-streaming scaffolding.

Each provider's `stream()` pumps SDK deltas through this helper so text
reaches the connector's chat_poll feed AS IT ARRIVES (not buffered to turn
end). These tests pin the four behaviors providers rely on: live in-order
passthrough, clean completion, error re-raise into the caller's mapping, and
a per-item inactivity timeout that cancels a stalled producer.
"""
from __future__ import annotations

import asyncio

from fsr_playbooks.llm._loop_helpers import drain_with_idle_timeout


async def _drain(pump, timeout):
    out = []
    async for item in drain_with_idle_timeout(pump, timeout=timeout):
        out.append(item)
    return out


def test_passthrough_in_order():
    async def _pump():
        for i in range(3):
            yield ("text", str(i))
        yield ("final", "done")

    out = asyncio.run(_drain(_pump(), timeout=5))
    assert out == [("text", "0"), ("text", "1"), ("text", "2"), ("final", "done")]


def test_yields_live_before_producer_finishes():
    """A consumer must see an early item before the producer has emitted its
    last — i.e. items are surfaced as produced, not collected then replayed."""
    seen_first = asyncio.Event()

    async def _pump():
        yield ("text", "first")
        # Block until the consumer has already received "first".
        await asyncio.wait_for(seen_first.wait(), timeout=5)
        yield ("final", None)

    async def _run():
        out = []
        async for item in drain_with_idle_timeout(_pump(), timeout=5):
            out.append(item)
            if item == ("text", "first"):
                seen_first.set()
        return out

    out = asyncio.run(_run())
    assert out == [("text", "first"), ("final", None)]


def test_producer_error_reraised():
    class Boom(Exception):
        pass

    async def _pump():
        yield ("text", "a")
        raise Boom("upstream blew up")

    async def _run():
        out = []
        try:
            async for item in drain_with_idle_timeout(_pump(), timeout=5):
                out.append(item)
        except Boom as e:
            return out, str(e)
        return out, None

    out, err = asyncio.run(_run())
    assert out == [("text", "a")]
    assert err == "upstream blew up"


def test_idle_timeout_raises_and_cancels():
    started = asyncio.Event()
    cancelled = {"v": False}

    async def _pump():
        started.set()
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            cancelled["v"] = True
            raise
        yield ("final", None)  # never reached

    async def _run():
        try:
            await asyncio.wait_for(_drain(_pump(), timeout=0.1), timeout=3)
        except asyncio.TimeoutError:
            # Give the cancelled pump task a tick to observe cancellation.
            await asyncio.sleep(0.05)
            return "timed_out"
        return "completed"

    assert asyncio.run(_run()) == "timed_out"
    assert cancelled["v"], "stalled producer should be cancelled on idle timeout"
