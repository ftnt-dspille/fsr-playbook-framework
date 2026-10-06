"""A citable tool result shows its own id, the value a verdict must cite.

The triage prompt says each finding cites "a tool_call_id from this turn (shown
in tool results)", but an OpenAI tool message carried the id only in its
envelope. Live on the box model nearly every first verdict cited prose ("get_record
on alert X showed ...") and was refused for invalid evidence ids, learning the
real ids only from the refusal -- a wasted round on every triage.
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
from test_verdict_forced_on_full_surface import _TOOLS, _prose

from fsr_playbooks.llm._loop_helpers import evidence_id_line
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message


def test_only_a_successful_evidence_call_is_labelled():
    assert evidence_id_line("call_1", "get_record", {}, True) == "[evidence id: call_1]\n"
    assert evidence_id_line("call_1", "get_record", {}, False) == ""
    assert evidence_id_line(None, "get_record", {}, True) == ""
    # A card is not evidence.
    assert evidence_id_line("call_1", "emit_card", {"card_type": "verdict"}, True) == ""


def _round(call_id, name, args):
    return [_delta_chunk(tool_calls=[_tc(index=0, id=call_id, name=name,
                                         args=json.dumps(args))]),
            _delta_chunk(finish="tool_calls"), _usage_chunk()]


def _tool_messages(results):
    rounds = [_round("call_rec", "get_record", {"module": "alerts", "uuid": "u1"}),
              _prose()]
    streams = [_FakeStream(r) for r in rounds]
    sent: list = []

    async def _create(*_a, **kw):
        sent.append([dict(m) for m in kw["messages"]])
        return streams.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)

    async def _drain(gen):
        return [ev async for ev in gen]

    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(return_value=results)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="triage this")],
            tools=_TOOLS)))
    return [m for m in sent[-1] if m.get("role") == "tool"]


def test_the_loop_shows_the_id_the_verdict_must_cite():
    msgs = _tool_messages({"ok": True, "record": {"name": "alert"}})
    assert msgs and msgs[0]["tool_call_id"] == "call_rec"
    assert msgs[0]["content"].startswith("[evidence id: call_rec]\n")


def test_a_failed_read_is_not_offered_as_evidence():
    msgs = _tool_messages({"ok": False, "error": "not found"})
    assert msgs and not msgs[0]["content"].startswith("[evidence id:")


def test_the_card_brief_says_evidence_holds_ids_not_sentences():
    # The brief read `evidence* [string]` and the box model wrote sentences.
    from fsr_playbooks.llm.tools import TOOL_SCHEMA_OVERRIDES
    brief = TOOL_SCHEMA_OVERRIDES["emit_card"]["properties"]["payload"]["description"]
    verdict = next(ln for ln in brief.splitlines() if ln.startswith("verdict:"))
    assert "evidence* [evidence id" in verdict
