"""End-to-end: a build turn that drafts a playbook the checks still reject must
not end on bare prose. The loop delivers a `choice` card naming what is left,
so the analyst is never dead-ended (the "never dead-end" house rule, E4b).

Mirrors test_openai_create_delivery_forced: drive the real OpenAIProvider loop
with a fake stream. Here verify_playbook comes back NOT ready, with
required_fixes, then the model narrates and stops.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolUseEvent

DRAFT_YAML = ("playbooks:\n  - name: Block IP\n    steps:\n"
    "      - {name: Start, type: start, next: Block}\n"
    "      - {name: Block, type: connector, connector: x, operation: block}\n")


def _delta(*, content=None, tool_calls=None, finish=None):
    return MagicMock(choices=[MagicMock(
        delta=MagicMock(content=content, tool_calls=tool_calls),
        finish_reason=finish)], usage=None)


def _usage(p=10, c=5):
    return MagicMock(choices=[], usage=MagicMock(prompt_tokens=p, completion_tokens=c))


def _tc(*, index, id=None, name=None, args=None):
    fn = MagicMock(); fn.name = name; fn.arguments = args
    return MagicMock(index=index, id=id, function=fn)


class _Stream:
    def __init__(self, chunks): self._c = chunks
    def __aiter__(self):
        async def g():
            for c in self._c: yield c
        return g()


_TOOLS = [
    {"type": "function", "function": {"name": "verify_playbook",
        "parameters": {"type": "object", "properties": {"yaml_text": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "emit_card",
        "parameters": {"type": "object", "properties": {
            "card_type": {"type": "string"}, "payload": {"type": "object"}}}}},
]


def _dispatch(name, args):
    if name == "verify_playbook":
        return {"ok": True, "ready_to_push": False,
                "required_fixes": [{"message": "connector 'x' is not configured"},
                                   {"message": "step 'Block' is unreachable"}]}
    if name == "emit_card":
        return {"ok": True, "card": {"type": args.get("card_type")}}
    return {"ok": True}


async def _drain(gen):
    return [ev async for ev in gen]


def _provider(create):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=create)
    return OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1",
                          api_key="x", client=client)


def _turns():
    t1 = [_delta(tool_calls=[_tc(index=0, id="c1", name="verify_playbook",
              args=json.dumps({"yaml_text": DRAFT_YAML}))]),
          _delta(finish="tool_calls"), _usage()]
    t2 = [_delta(content="The playbook still has a couple of problems to sort out."),
          _delta(finish="stop"), _usage()]
    return t1, t2


def test_unfinished_build_ends_on_a_choice_card_not_prose():
    t1, t2 = _turns()
    create = AsyncMock(side_effect=[_Stream(t1), _Stream(t2)])
    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        events = asyncio.run(_drain(_provider(create).stream(
            system="s", messages=[Message(role="user", content="build a block-ip playbook")],
            tools=_TOOLS, tags={})))
    emits = [e for e in events if isinstance(e, ToolUseEvent) and e.name == "emit_card"]
    assert len(emits) == 1, "loop did not deliver a terminal card"
    assert emits[0].arguments.get("card_type") == "choice"
    prompt = emits[0].arguments["payload"]["prompt"]
    assert "not ready" in prompt and "not configured" in prompt
    # No extra model round was spent on the card.
    assert create.await_count == 2
    assert isinstance(events[-1], DoneEvent)
