"""End-to-end: a triage turn on the LIVE tool surface is forced into a verdict.

Live on .159 (0.6.46), "Investigate this alert end to end" ran get_record and
siem_search x3 and ended in prose: 0 verdict cards across every session. Two
defects kept VerdictDeliveryGuard dead in production while its unit tests
passed on hand-built triage slices:

  * triage and build advertise the same 41 tools, so "the slice has
    verify_playbook" read every live turn as a build;
  * its evidence list held pre-consolidation names, so `siem_search` counted
    as nothing.

This drives the real OpenAI loop with that full surface.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from test_openai_build_progress_forced import (
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, ToolUseEvent

_FULL_SURFACE = ("get_record", "siem_search", "faz_search", "run_op", "emit_card",
                 "find", "verify_playbook", "push_playbook", "verify_enhancement",
                 "validate_yaml", "compile_yaml", "build_playbook_from_trace")
_TOOLS = [{"type": "function", "function": {
    "name": n, "description": n,
    "parameters": {"type": "object", "properties": {}}}} for n in _FULL_SURFACE]


async def _drain(gen):
    return [ev async for ev in gen]


def _forced_verdict_response(disposition="true_positive"):
    fn = MagicMock()
    fn.name = "emit_card"
    fn.arguments = json.dumps({"card_type": "verdict", "payload": {
        "disposition": disposition, "severity": "high", "confidence": 0.8,
        "findings": [{"claim": "host beacons to a known C2", "evidence": ["c2"]}],
        "unknowns": []}})
    call = MagicMock(id="c_forced", function=fn)
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[call]))])


def _run(rounds):
    streams = [_FakeStream(r) for r in rounds]

    async def _create(*_a, **kw):
        return streams.pop(0) if kw.get("stream") else _forced_verdict_response()

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(return_value={"ok": True})) as disp, \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="investigate this alert")],
            tools=_TOOLS, tags={})))
    return events, disp


def _hunt_round():
    return [_delta_chunk(tool_calls=[
                _tc(index=0, id="c1", name="get_record", args='{"record": "a"}'),
                _tc(index=1, id="c2", name="siem_search", args='{"q": "10.0.0.5"}')]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _prose():
    return [_delta_chunk(content="This looks like a real C2 beacon."),
            _delta_chunk(finish="stop"), _usage_chunk()]


def test_triage_on_the_full_surface_ends_with_a_verdict():
    events, disp = _run([_hunt_round(), _prose()])
    verdicts = [c for c in disp.call_args_list
                if c.args[0] == "emit_card" and c.args[1].get("card_type") == "verdict"]
    assert verdicts, "no verdict was forced -- the guard is dead on the live surface"
    assert "emit_card" in [e.name for e in events if isinstance(e, ToolUseEvent)]


def test_a_build_turn_on_the_same_surface_is_not_forced_into_a_verdict():
    build = [_delta_chunk(tool_calls=[
                 _tc(index=0, id="c1", name="get_record", args='{"record": "a"}'),
                 _tc(index=1, id="c2", name="validate_yaml", args='{"yaml": "x"}')]),
             _delta_chunk(finish="tool_calls"), _usage_chunk()]
    _, disp = _run([build, _prose(), _prose()])
    assert not any(c.args[1].get("card_type") == "verdict"
                   for c in disp.call_args_list if c.args[0] == "emit_card")


def test_anthropic_triage_on_the_full_surface_ends_with_a_verdict():
    """The Anthropic loop had no verdict guard at all."""
    from test_anthropic_enhance_delivery_forced import _FakeStream as _AStream
    from test_anthropic_enhance_delivery_forced import (
        _text_block,
        _tool_use_block,
        _usage,
    )

    from fsr_playbooks.llm.anthropic_provider import AnthropicProvider

    hunt = _AStream([], MagicMock(content=[
        _tool_use_block("c1", "get_record", {"record": "a"}),
        _tool_use_block("c2", "siem_search", {"q": "10.0.0.5"})],
        stop_reason="tool_use", usage=_usage()))
    prose = _AStream(["Looks like a real C2 beacon."], MagicMock(
        content=[_text_block("Looks like a real C2 beacon.")],
        stop_reason="end_turn", usage=_usage()))
    forced = MagicMock(content=[_tool_use_block("c_forced", "emit_card", {
        "card_type": "verdict", "payload": {
            "disposition": "true_positive", "severity": "high", "confidence": 0.8,
            "findings": [{"claim": "beacons to C2", "evidence": ["c2"]}],
            "unknowns": []}})])
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=[hunt, prose])
    client.messages.create = AsyncMock(return_value=forced)
    p = AnthropicProvider(model="claude-sonnet-5", base_url="http://x", api_key="x",
                          client=client)
    tools = [{"name": n, "description": n,
              "input_schema": {"type": "object", "properties": {}}}
             for n in _FULL_SURFACE]
    with patch("fsr_playbooks.llm.anthropic_provider.dispatch",
               MagicMock(return_value={"ok": True})) as disp, \
         patch("fsr_playbooks.llm.anthropic_provider._tier_for", return_value=0):
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="investigate")],
            tools=tools, tags={})))
    assert any(c.args[0] == "emit_card" and c.args[1].get("card_type") == "verdict"
               for c in disp.call_args_list), "Anthropic never forced a verdict"
    forced_call = client.messages.create.call_args
    assert forced_call.kwargs["tool_choice"] == {"type": "tool", "name": "emit_card"}


def test_the_directive_states_the_validators_own_vocabulary():
    from fsr_playbooks.llm._loop_helpers import verdict_directive
    from fsr_playbooks.mcp_server.tools_emit import (
        VERDICT_DISPOSITIONS,
        VERDICT_SEVERITIES,
    )
    d = verdict_directive(["c1"])
    for word in VERDICT_DISPOSITIONS + VERDICT_SEVERITIES:
        assert word in d, word
    assert "needs_more_info" in d and "c1" in d


def _run_with_forced(responses, dispatch_results):
    """Hunt round + prose, then forced verdict rounds answered in order."""
    streams = [_FakeStream(_hunt_round()), _FakeStream(_prose())]
    forced = list(responses)
    sent: list = []

    async def _create(*_a, **kw):
        if kw.get("stream"):
            return streams.pop(0)
        sent.append([dict(m) for m in kw["messages"]])
        return forced.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    results = iter(dispatch_results)

    def _dispatch(name, args):
        return next(results) if name == "emit_card" else {"ok": True}

    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=_dispatch)) as disp, \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="investigate")],
            tools=_TOOLS, tags={})))
    return sent, disp


_REFUSED = {"ok": False, "code": "bad_disposition",
            "message": "disposition must be one of: ... (got 'inconclusive')"}


def test_a_refused_forced_verdict_gets_one_repair_attempt():
    # The live refusal: `inconclusive` is not in the vocabulary. The repair
    # sends a corrected payload (an identical retry is blocked upstream by the
    # repeated-call guard, as it should be).
    sent, disp = _run_with_forced(
        [_forced_verdict_response("inconclusive"),
         _forced_verdict_response("needs_more_info")],
        [_REFUSED, {"ok": True}])
    assert len(sent) == 2, "no repair attempt after the refusal"
    repair = sent[1][-1]["content"]
    assert "refused" in repair and "inconclusive" in repair
    assert sum(1 for c in disp.call_args_list if c.args[0] == "emit_card") == 2


def test_repair_is_attempted_once_not_forever():
    sent, _ = _run_with_forced(
        [_forced_verdict_response("inconclusive"), _forced_verdict_response("unsure")],
        [_REFUSED, _REFUSED])
    assert len(sent) == 2


def test_an_accepted_forced_verdict_is_not_repaired():
    sent, _ = _run_with_forced([_forced_verdict_response()], [{"ok": True}])
    assert len(sent) == 1
