"""P4 — repeated-error guard.

If a tool call with the identical (name, args) shape already failed once this
turn, the provider must NOT re-run it; it returns a guard envelope so the model
adapts or reports the blocker instead of burning budget on the same 400.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fsr_core.llm import anthropic_provider as ap
from fsr_core.llm.anthropic_provider import AnthropicProvider
from fsr_core.llm.provider import Message, ToolResultEvent


class _FinalMessage:
    def __init__(self, content, stop_reason=None):
        self.content = content
        self.usage = SimpleNamespace(
            input_tokens=10, output_tokens=5,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        )
        self.stop_reason = stop_reason or ("tool_use" if any(
            getattr(b, "type", "") == "tool_use" for b in content
        ) else "end_turn")


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
                yield None
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


async def _drain(provider, messages):
    out = []
    async for ev in provider.stream(system="sys", messages=messages, tools=[]):
        out.append(ev)
    return out


def test_identical_failing_call_not_rerun(monkeypatch):
    calls = []

    def _dispatch(name, args):
        calls.append((name, dict(args)))
        return {"ok": False, "code": 400, "error": "bad incident id"}

    monkeypatch.setattr(ap, "dispatch", _dispatch)
    monkeypatch.setattr(ap, "_tier_for", lambda name, args: 1)

    args = {"incident_id": "563", "op": "siem_events_for_incident"}
    turns = [
        _FinalMessage([_tool_use("c1", "run_op", args)]),     # fails (real dispatch)
        _FinalMessage([_tool_use("c2", "run_op", dict(args))]),  # identical → guard
        _FinalMessage([_text("Blocked on SIEM id; reporting.")]),
    ]
    provider = AnthropicProvider(model="fake", client=_FakeClient(turns))
    events = asyncio.run(_drain(provider, [Message(role="user", content="triage")]))

    # dispatch ran exactly once — the second identical call was short-circuited.
    assert len(calls) == 1, f"expected 1 real dispatch, got {len(calls)}"

    results = [e.result for e in events if isinstance(e, ToolResultEvent)]
    guarded = [r for r in results if isinstance(r, dict) and r.get("repeated_call_guard")]
    assert guarded, f"no guard envelope emitted: {results}"


def test_different_args_not_guarded(monkeypatch):
    calls = []

    def _dispatch(name, args):
        calls.append((name, dict(args)))
        return {"ok": False, "code": 400, "error": "bad"}

    monkeypatch.setattr(ap, "dispatch", _dispatch)
    monkeypatch.setattr(ap, "_tier_for", lambda name, args: 1)

    turns = [
        _FinalMessage([_tool_use("c1", "run_op", {"incident_id": "563"})]),
        # Adapted: a DIFFERENT id — must actually run, not be guarded.
        _FinalMessage([_tool_use("c2", "run_op", {"incident_id": "11521"})]),
        _FinalMessage([_text("done")]),
    ]
    provider = AnthropicProvider(model="fake", client=_FakeClient(turns))
    asyncio.run(_drain(provider, [Message(role="user", content="triage")]))
    assert len(calls) == 2, "adapted call should run, not be guarded"
