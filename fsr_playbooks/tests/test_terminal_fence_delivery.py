"""A build turn that ends on a compile-clean fence it never verified or offered.

The gap the two existing build guards leave: BuildProgressGuard's nudge is prose
(a model can author in prose again and ignore it), and CreateDeliveryGuard only
has bytes once a `verify_playbook` passed -- it never did. So a connector-less
playbook (loop / decision / set_variable) whose only research is `get_step_type`
gets authored in a trailing ```yaml fence and the turn ends with no Create
prompt. Localized live: for_each_loop on the production model delivered nothing
this way (0 of 2 live runs).

The fix verifies the terminal fence in the loop so the delivery guard can offer
it -- the same self-delivery as a validated clean draft, sourced from the fence.
`_fence_problem` (the compiler) is patched to None here so the test isolates the
delivery WIRING; the compile check itself is covered by the offer/compile tests.
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import DoneEvent, Message, ToolUseEvent

CLEAN_YAML = """playbooks:
  - name: Create Alerts From List
    trigger: {type: manual}
    steps:
      - id: loop
        type: connector
        connector: cyops_utilities
        operation: create_alert
"""
_NAMES = ("get_step_type", "compile_yaml", "validate_yaml", "verify_playbook",
          "emit_card", "run_playbook")
_OPENAI_TOOLS = [{"type": "function", "function": {
    "name": n, "description": n,
    "parameters": {"type": "object", "properties": {}}}} for n in _NAMES]


def _dispatch(name, args):
    if name == "verify_playbook":
        return {"ready_to_push": True, "summary": "Creates alerts from a list."}
    if name == "emit_card":
        return {"ok": True, "card": {"type": "playbook_offer"}}
    return {"ok": True}


async def _drain(gen):
    return [ev async for ev in gen]


def _call_round(cid, name, args):
    return [_delta_chunk(tool_calls=[_tc(index=0, id=cid, name=name,
                                         args=json.dumps(args))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _text_round(text):
    return [_delta_chunk(content=text), _delta_chunk(finish="stop"), _usage_chunk()]


_RESEARCH = _call_round("c1", "get_step_type", {"name": "set_variable"})
_STOP_WITH_FENCE = _text_round(
    "Here is the playbook:\n```yaml\n" + CLEAN_YAML + "```\n")


def _run(rounds):
    queue = [_FakeStream(r) for r in rounds]
    sent: list = []

    def _create(*_a, **kw):
        sent.append(copy.deepcopy(kw["messages"]))
        return queue.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    disp = MagicMock(side_effect=_dispatch)
    with patch("fsr_playbooks.llm.agent_loop.dispatch", disp), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0), \
         patch("fsr_playbooks.llm.agent_loop._fence_problem", return_value=None):
        events = asyncio.run(_drain(p.stream(
            system="s",
            messages=[Message(role="user", content="build a looping playbook")],
            tools=_OPENAI_TOOLS, tags={})))
    return events, sent, disp


def _names(events):
    return [e.name for e in events if isinstance(e, ToolUseEvent)]


def test_terminal_clean_fence_is_verified_and_offered_by_the_loop():
    # research, then the model gets the prose nudge and STILL answers with a
    # bare fence (never verifies, never offers). The loop must verify the fence
    # bytes itself and deliver the offer. RED without the fix: no emit_card.
    events, sent, disp = _run([_RESEARCH, _STOP_WITH_FENCE, _STOP_WITH_FENCE])
    names = _names(events)
    assert "verify_playbook" in names, "the loop never verified the terminal fence"
    assert "emit_card" in names, "verified fence was never delivered as an offer"
    assert names.index("verify_playbook") < names.index("emit_card")
    offer = next(c.args[1] for c in disp.call_args_list if c.args[0] == "emit_card")
    assert offer["card_type"] == "playbook_offer"
    assert offer["payload"]["yaml"] == CLEAN_YAML
    assert isinstance(events[-1], DoneEvent)


def test_a_failing_fence_is_not_offered():
    # The same shape, but the fence fails verify: nothing may be offered.
    def _disp(name, args):
        if name == "verify_playbook":
            return {"ok": False, "ready_to_push": False,
                    "required_fixes": [{"path": "steps[loop]", "fix": "add id"}]}
        return _dispatch(name, args)
    queue = [_FakeStream(r) for r in (_RESEARCH, _STOP_WITH_FENCE, _STOP_WITH_FENCE)]

    def _create(*_a, **kw):
        return queue.pop(0)
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-4.1-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(side_effect=_disp)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0), \
         patch("fsr_playbooks.llm.agent_loop._fence_problem", return_value=None):
        events = asyncio.run(_drain(p.stream(
            system="s",
            messages=[Message(role="user", content="build a looping playbook")],
            tools=_OPENAI_TOOLS, tags={})))
    # A failing fence must never be delivered as a playbook OFFER -- no broken
    # YAML is pushed. The unfinished-build behavior (exp/playbook-loop-e1-e3) may
    # still end the turn on a `choice` card that guides the analyst to a fix
    # instead of leaving bare prose; that is allowed. The invariant is only that
    # the failing fence is not OFFERED.
    offers = [e for e in events
              if getattr(e, "name", None) == "emit_card"
              and (getattr(e, "arguments", {}) or {}).get("card_type") == "playbook_offer"]
    assert not offers, "a failing fence was delivered as a playbook offer"
    assert isinstance(events[-1], DoneEvent)
