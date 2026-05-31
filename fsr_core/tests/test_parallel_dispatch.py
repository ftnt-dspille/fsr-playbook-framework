"""§2.8 — parallel read-only tool dispatch in AnthropicProvider.

Drives the provider's tool loop with a mocked Anthropic client (a scripted
sequence of `messages.stream` round-trips) and a patched `dispatch` that
sleeps + records concurrency. Asserts:

  1. Independent read-only (tier ≤ 2) calls in one turn run *concurrently*
     (observed peak concurrency > 1; wall-clock ≈ slowest, not sum).
  2. `tool_result` blocks stay in `tool_use` order regardless of which
     call finished first.
  3. A mixed turn (read-only calls + a tier-3 call) runs the read-only
     ones in parallel, then suspends on the tier-3 call (pending_approval).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from fsr_core.llm import anthropic_provider as ap
from fsr_core.llm.anthropic_provider import AnthropicProvider
from fsr_core.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    Message,
    ToolResultEvent,
    ToolUseEvent,
)


# --- mock anthropic client -------------------------------------------------

class _FinalMessage:
    def __init__(self, content):
        self.content = content
        self.usage = SimpleNamespace(
            input_tokens=10, output_tokens=5,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        )
        self.stop_reason = "tool_use" if any(
            getattr(b, "type", "") == "tool_use" for b in content
        ) else "end_turn"


class _StreamCtx:
    def __init__(self, final):
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def _gen():
            if False:
                yield None  # no text-delta events needed
        return _gen()

    async def get_final_message(self):
        return self._final


class _Messages:
    def __init__(self, turns):
        self._turns = list(turns)
        self._i = 0

    def stream(self, **kwargs):
        final = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return _StreamCtx(final)


class _FakeClient:
    def __init__(self, turns):
        self.messages = _Messages(turns)


def _tool_use(call_id, name, args):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)


def _text(s):
    return SimpleNamespace(type="text", text=s)


# --- concurrency-recording dispatch ---------------------------------------

class _ConcurrencyRecorder:
    def __init__(self, sleep=0.1):
        self.sleep = sleep
        self.active = 0
        self.peak = 0
        self.lock = None  # threads → use a plain non-atomic counter; GIL-safe enough

    def __call__(self, name, args):
        # Runs inside asyncio.to_thread → a worker thread. Count overlap.
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.sleep)
            return {"ok": True, "tool": name, "echo": args}
        finally:
            self.active -= 1


async def _drain(provider, messages):
    events = []
    async for ev in provider.stream(system="sys", messages=messages, tools=[]):
        events.append(ev)
    return events


def test_independent_readonly_calls_run_concurrently(monkeypatch):
    rec = _ConcurrencyRecorder(sleep=0.15)
    monkeypatch.setattr(ap, "dispatch", rec)
    # All three are read-only (find_connector → tier 0/1).
    monkeypatch.setattr(ap, "_tier_for", lambda name, args: 1)

    turns = [
        _FinalMessage([
            _tool_use("c1", "find_connector", {"q": "a"}),
            _tool_use("c2", "find_connector", {"q": "b"}),
            _tool_use("c3", "find_connector", {"q": "c"}),
        ]),
        _FinalMessage([_text("done")]),
    ]
    provider = AnthropicProvider(model="fake", client=_FakeClient(turns))

    start = time.monotonic()
    events = asyncio.run(_drain(provider, [Message(role="user", content="hunt")]))
    elapsed = time.monotonic() - start

    # Concurrency actually happened.
    assert rec.peak >= 2, f"expected overlap, peak={rec.peak}"
    # Wall-clock ≈ slowest (0.15s), not sum (0.45s). Generous ceiling.
    assert elapsed < 0.4, f"calls did not overlap (elapsed={elapsed:.2f}s)"

    # tool_result order matches tool_use order.
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [r.call_id for r in results] == ["c1", "c2", "c3"]
    uses = [e for e in events if isinstance(e, ToolUseEvent)]
    assert [u.call_id for u in uses] == ["c1", "c2", "c3"]


def test_mixed_turn_parallelizes_readonly_then_suspends(monkeypatch):
    rec = _ConcurrencyRecorder(sleep=0.1)

    def _dispatch(name, args):
        if name == "run_op":
            return {"pending_approval": True, "approval_id": "ap1",
                    "tier": 3, "preview": {}, "args_hash": "h"}
        return rec(name, args)

    monkeypatch.setattr(ap, "dispatch", _dispatch)
    monkeypatch.setattr(
        ap, "_tier_for",
        lambda name, args: 3 if name == "run_op" else 1,
    )

    turns = [
        _FinalMessage([
            _tool_use("c1", "find_connector", {"q": "a"}),
            _tool_use("c2", "get_record", {"iri": "x"}),
            _tool_use("c3", "run_op", {"connector": "fg", "op": "block_ip"}),
            _tool_use("c4", "find_connector", {"q": "after"}),
        ]),
    ]
    provider = AnthropicProvider(model="fake", client=_FakeClient(turns))
    events = asyncio.run(_drain(provider, [Message(role="user", content="contain")]))

    # Two read-only calls ran (concurrently); the tier-3 call suspended.
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [r.call_id for r in results] == ["c1", "c2"]
    assert rec.peak >= 2

    approvals = [e for e in events if isinstance(e, ApprovalRequestEvent)]
    assert len(approvals) == 1
    assert approvals[0].approval_id == "ap1"
    assert approvals[0].tool == "run_op"

    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done and done[-1].stop_reason == "pending_approval"
