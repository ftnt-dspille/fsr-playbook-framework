"""A second offer card in one turn is refused -- the offer card is its own
save prompt, so a model that re-emits the same playbook as a "save"/"confirm"
follow-up would put two identical cards in front of the analyst.

Reproduced from a live gate run: claude-haiku-5-5 on `select_build_offer`
built the playbook, called `emit_playbook_offer`, then called it again with the
SAME yaml under an id suffixed `_save` / `_confirm` (2 of 3 runs). The scorer's
never-offer-twice bar failed. This pins the guard that makes the second
emission a no-op refusal, so one card reaches the analyst regardless of model.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolResultEvent

YAML = "playbooks:\n  - name: Alert Source IP VirusTotal Severity\n"


def _delta_chunk(*, content=None, tool_calls=None, finish=None):
    delta = MagicMock(content=content, tool_calls=tool_calls)
    return MagicMock(choices=[MagicMock(delta=delta, finish_reason=finish)], usage=None)


def _usage_chunk():
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=10, completion_tokens=5))


def _tc(*, index, id=None, name=None, args=None):
    fn = MagicMock()
    fn.name = name
    fn.arguments = args
    return MagicMock(index=index, id=id, function=fn)


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


_TOOLS = [
    {"type": "function", "function": {
        "name": "emit_playbook_offer", "description": "offer",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "summary": {"type": "string"},
            "yaml": {"type": "string"}}}}},
]


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def _dispatch(name, args):
    if name == "emit_playbook_offer":
        return {"ok": True, "card": {"type": "playbook_offer"}}
    return {"ok": True}


def _provider(create):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    return OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                          api_key="x", client=client)


# ONE round with TWO offer calls -- the Haiku shape (both in a single assistant
# message), which the turn-end-on-offer guard cannot catch because both are
# dispatched before the round's turn-end check.
_TWO_OFFERS = [
    _delta_chunk(tool_calls=[
        _tc(index=0, id="o1", name="emit_playbook_offer",
            args=json.dumps({"id": "vt_sev", "summary": "s", "yaml": YAML})),
        _tc(index=1, id="o2", name="emit_playbook_offer",
            args=json.dumps({"id": "vt_sev_save", "summary": "s", "yaml": YAML})),
    ]),
    _delta_chunk(finish="tool_calls"), _usage_chunk(),
]


def _run_two_offers():
    create = AsyncMock(side_effect=[_FakeStream(_TWO_OFFERS)])
    p = _provider(create)
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        return asyncio.run(_drain(p.stream(
            system="s",
            messages=[Message(role="user", content="build a playbook and save it")],
            tools=_TOOLS, tags={})))


def test_second_offer_in_one_turn_is_refused():
    events = _run_two_offers()
    offer_results = [e for e in events if isinstance(e, ToolResultEvent)]
    # Both offer calls produce a result frame, but only the FIRST renders a card.
    delivered = [e for e in offer_results
                 if isinstance(e.result, dict) and e.result.get("ok") is True
                 and isinstance(e.result.get("card"), dict)]
    refused = [e for e in offer_results
               if isinstance(e.result, dict)
               and e.result.get("code") == "duplicate_offer"]
    assert len(delivered) == 1, (
        f"exactly one offer card should reach the analyst, got {len(delivered)}")
    assert len(refused) == 1, (
        f"the second offer should be refused as duplicate_offer, "
        f"got {len(refused)} refusals")
    assert isinstance(events[-1], DoneEvent)
