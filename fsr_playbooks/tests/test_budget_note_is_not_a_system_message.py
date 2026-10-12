"""The budget note rides in the conversation as a user message.

The loop tells the model how many tool rounds are left once the turn nears its
ceiling. It used to be appended as a `system` message in the middle of the
history. OpenAI-compatible gateways (Frank among them) reject any system
message that is not first, with a 400 "System message must be at the
beginning", so a long build turn died at the budget.

Anthropic already carries the note as a text block in a user message. Every
provider now uses the user role, and no provider takes a note role at all.
Each test drives the real OpenAI-shaped loop through a stream of fake rounds and
checks every request it sent.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from test_fenced_playbook_connector_gate import _reply_round
from test_openai_build_progress_forced import (
    _BUILD_TOOLS,
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)
from test_unexecuted_tool_calls_not_replayed import (
    _close_round,
    _drain,
    _openai_provider,
    _snapshotting,
)

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message


def _tool_round(call_id: str):
    return [
        _delta_chunk(tool_calls=[_tc(index=0, id=call_id, name="get_step_type", args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]


def _run(rounds, max_tool_turns: int):
    call, sent = _snapshotting([_FakeStream(r) for r in rounds])
    create = AsyncMock(side_effect=call)
    p = _openai_provider(OpenAIProvider, create)

    async def go():
        return await _drain(p.stream(
            system="s", messages=[Message(role="user", content="build a playbook")],
            tools=_BUILD_TOOLS, tags={}, max_tool_turns=max_tool_turns))

    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(return_value={"ok": True})), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        asyncio.run(go())
    return sent


def test_no_request_carries_a_system_message_after_the_first_position():
    """Red before the fix: the budget note is sent as a mid-history system
    message on the request that follows the soft-window round."""
    sent = _run([_tool_round("c1"), _tool_round("c2"), _tool_round("c3"),
                 _reply_round("Done."), _close_round()], max_tool_turns=4)
    assert len(sent) >= 2, "the loop never reached a second request"
    for n, msgs in enumerate(sent):
        late = [i for i, m in enumerate(msgs) if i > 0 and m.get("role") == "system"]
        assert late == [], f"request {n} has a system message at {late}"


def test_the_budget_note_is_still_delivered_as_a_user_message():
    """The note is not dropped: it arrives in a later request as user text."""
    sent = _run([_tool_round("c1"), _tool_round("c2"), _tool_round("c3"),
                 _reply_round("Done."), _close_round()], max_tool_turns=4)
    texts = [str(m.get("content")) for msgs in sent for m in msgs
             if m.get("role") == "user" and "[turn budget]" in str(m.get("content"))]
    assert texts, "no budget note reached the model"
