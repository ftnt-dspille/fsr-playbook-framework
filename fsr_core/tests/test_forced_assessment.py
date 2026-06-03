"""P1 — forced written assessment.

When a turn runs tools but the final assistant block carries no text (only
tool_use / emitted cards), the provider must force ONE extra no-tools round so
the analyst always gets a written close. Conversely, a turn whose final block
already has text must NOT trigger an extra call (no double-summarize), and a
pure-conversation turn that never ran tools is left alone.

Drives `AnthropicProvider` with the same mocked-client pattern as
test_parallel_dispatch.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fsr_core.llm import anthropic_provider as ap
from fsr_core.llm.anthropic_provider import AnthropicProvider
from fsr_core.llm.provider import Message, TextEvent, UsageEvent


class _FinalMessage:
    def __init__(self, content, stop_reason=None):
        self.content = content
        self.usage = SimpleNamespace(
            input_tokens=10, output_tokens=5,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        )
        if stop_reason is not None:
            self.stop_reason = stop_reason
        else:
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
        final = self._final

        async def _gen():
            for b in final.content:
                if getattr(b, "type", "") == "text":
                    yield SimpleNamespace(
                        type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text=b.text),
                    )
        return _gen()

    async def get_final_message(self):
        return self._final


class _Messages:
    def __init__(self, turns):
        self._turns = list(turns)
        self._i = 0
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
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
    events = []
    async for ev in provider.stream(system="sys", messages=messages, tools=[]):
        events.append(ev)
    return events


def _patch_dispatch(monkeypatch):
    monkeypatch.setattr(ap, "dispatch", lambda name, args: {"ok": True, "echo": args})
    monkeypatch.setattr(ap, "_tier_for", lambda name, args: 1)


def test_tools_only_final_forces_assessment(monkeypatch):
    _patch_dispatch(monkeypatch)
    turns = [
        # Round 1: a tool call.
        _FinalMessage([_tool_use("c1", "get_record", {"id": 1})]),
        # Round 2: end_turn with NO text — only the model deciding to stop.
        _FinalMessage([], stop_reason="end_turn"),
        # Round 3: the forced no-tools assessment.
        _FinalMessage([_text("Found C2 beacon. Severity: high. Next: isolate host.")]),
    ]
    client = _FakeClient(turns)
    provider = AnthropicProvider(model="fake", client=client)

    events = asyncio.run(_drain(provider, [Message(role="user", content="triage")]))

    texts = [e.text for e in events if isinstance(e, TextEvent)]
    assert any("Severity" in t for t in texts), f"no forced assessment text: {texts}"
    # The forced round was a no-tools call.
    assert "tools" not in client.messages.calls[-1] or not client.messages.calls[-1].get("tools")
    reasons = [e.stop_reason for e in events if isinstance(e, UsageEvent)]
    assert "assessment_forced" in reasons
    assert "assessment_summary" in reasons


def test_final_with_text_does_not_force(monkeypatch):
    _patch_dispatch(monkeypatch)
    turns = [
        _FinalMessage([_tool_use("c1", "get_record", {"id": 1})]),
        # Round 2 already carries a written close — no extra call wanted.
        _FinalMessage([_text("Done — clean, low severity.")], stop_reason="end_turn"),
    ]
    client = _FakeClient(turns)
    provider = AnthropicProvider(model="fake", client=client)

    asyncio.run(_drain(provider, [Message(role="user", content="triage")]))
    # Exactly two model round-trips — no forced third.
    assert len(client.messages.calls) == 2


def test_pure_text_turn_not_forced(monkeypatch):
    _patch_dispatch(monkeypatch)
    # No tools ever run; the turn is conversational. Empty-ish final must not
    # trigger the assessment guarantee (it only applies after tools).
    turns = [_FinalMessage([_text("Hi, how can I help?")], stop_reason="end_turn")]
    client = _FakeClient(turns)
    provider = AnthropicProvider(model="fake", client=client)

    asyncio.run(_drain(provider, [Message(role="user", content="hi")]))
    assert len(client.messages.calls) == 1
