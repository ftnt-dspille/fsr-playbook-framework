"""A parallel tool batch streams each result as its call finishes.

Why. The round used to `gather` its batch and yield results only after the
slowest call, so a 0.5 s lookup's chip sat pending behind a 6 s one. Results
now yield in completion order, while the history the next round replays keeps
the model's call order (the provider requires every tool_use answered, and the
replay pairs by id; order is what the model reads back).

Driven through the real AnthropicProvider loop with a fake client, the same
pattern as test_guard_sites_are_recorded.py.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from fsr_playbooks.llm import agent_loop
from fsr_playbooks.llm.anthropic_provider import AnthropicProvider
from fsr_playbooks.llm.provider import Message, ToolResultEvent


class _Final:
    def __init__(self, content):
        self.content = content
        self.usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                                     cache_read_input_tokens=0,
                                     cache_creation_input_tokens=0)
        self.stop_reason = "tool_use" if any(
            getattr(b, "type", "") == "tool_use" for b in content) else "end_turn"


class _Stream:
    def __init__(self, final):
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def _gen():
            for b in self._final.content:
                if getattr(b, "type", "") == "text":
                    yield SimpleNamespace(
                        type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text=b.text))
        return _gen()

    async def get_final_message(self):
        return self._final


class _Client:
    def __init__(self, turns):
        self._turns, self._i = list(turns), 0
        self.calls: list[dict] = []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        final = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return _Stream(final)


def _use(cid, name, args):
    return SimpleNamespace(type="tool_use", id=cid, name=name, input=args)


def _say(text):
    return SimpleNamespace(type="text", text=text)


_SLICE = [{"name": "run_op", "description": "", "input_schema": {"type": "object"}}]


def test_fast_sibling_result_yields_before_slow_one(monkeypatch):
    def dispatch(name, args, **_kw):
        if args.get("which") == "slow":
            time.sleep(0.6)
        return {"ok": True, "which": args.get("which")}

    monkeypatch.setattr(agent_loop, "dispatch", dispatch)
    monkeypatch.setattr(agent_loop, "_tier_for", lambda n, a: 1)
    client = _Client([
        _Final([_use("slow1", "run_op", {"which": "slow"}),
                _use("fast1", "run_op", {"which": "fast"})]),
        _Final([_say("done")]),
    ])
    provider = AnthropicProvider(model="fake", client=client)

    async def go():
        return [e async for e in provider.stream(
            system="sys", messages=[Message(role="user", content="hi")],
            tools=_SLICE, tags=None)]

    events = asyncio.run(go())
    order = [e.call_id for e in events if isinstance(e, ToolResultEvent)]
    assert order == ["fast1", "slow1"], (
        f"results must stream as each finishes, got {order}")


def test_next_round_replays_results_in_call_order(monkeypatch):
    def dispatch(name, args, **_kw):
        if args.get("which") == "slow":
            time.sleep(0.6)
        return {"ok": True, "which": args.get("which")}

    monkeypatch.setattr(agent_loop, "dispatch", dispatch)
    monkeypatch.setattr(agent_loop, "_tier_for", lambda n, a: 1)
    client = _Client([
        _Final([_use("slow1", "run_op", {"which": "slow"}),
                _use("fast1", "run_op", {"which": "fast"})]),
        _Final([_say("done")]),
    ])
    provider = AnthropicProvider(model="fake", client=client)

    async def go():
        return [e async for e in provider.stream(
            system="sys", messages=[Message(role="user", content="hi")],
            tools=_SLICE, tags=None)]

    asyncio.run(go())
    second = client.calls[1]["messages"]
    answered = [b["tool_use_id"] for m in second if m["role"] == "user"
                and isinstance(m["content"], list)
                for b in m["content"] if b.get("type") == "tool_result"]
    assert answered == ["slow1", "fast1"], (
        f"history must keep the model's call order, got {answered}")
