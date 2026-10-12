"""A refused ```yaml fence is never the saveable reply, even after the repair cap.

The widget saves the LAST ```yaml fence of the turn's text over the open record
and has no other signal. The loop repairs a failing last fence up to
MAX_SELF_REPAIR_TURNS times. When the cap runs out the failing fence used to
stay in the delivered text, so a playbook that does not compile, or calls a
connector this box does not have, could still be saved.

The fix neutralises a failing fence in the delivered text: the fence becomes a
plain-language note naming what failed, and a passing fence is untouched. The
fence text is held back until the round ends, so a failing fence never streams.

Each test drives the real OpenAI-shaped provider loop with a scripted stream
(the same fake gateway the self-repair tests use) and checks what was DELIVERED
(the text events), not only the requests sent.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from test_fenced_playbook_connector_gate import (
    _FALCON_REPLY,
    _FORTIEDR_REPLY,
    _LISTING_NO_FALCON,
    _reply_round,
    _with_listing,
)
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
    _run_openai_like,
    _snapshotting,
)

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, TextEvent

# Compiles to an error, with no connector to check.
_BAD_COMPILE = "Here is the playbook.\n\n```yaml\nnot a playbook\n```\n"


def _delivered(events) -> str:
    return "".join(ev.text for ev in events if isinstance(ev, TextEvent))


def _compile_only_refuses_bad(text):
    """Stands in for the compiler: refuses the marker text, passes the rest."""
    return "- top level must be a mapping" if "not a playbook" in text else None


def _run_with_budget(rounds, max_tool_turns: int):
    """Like `_run_openai_like`, but with a tool-turn budget, so the loop reaches
    its wrap-up round (the other delivery path) after the budget runs out."""
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
        events = asyncio.run(go())
    return sent, events


def _tool_round():
    return [
        _delta_chunk(tool_calls=[_tc(index=0, id="c1", name="get_step_type", args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]


def test_a_fence_that_does_not_compile_is_not_delivered_after_the_cap():
    """Red before the fix: the third reply (cap spent) streams its bad fence."""
    with patch("fsr_playbooks.llm.agent_loop.compile_errors",
               side_effect=_compile_only_refuses_bad), \
         _with_listing(_LISTING_NO_FALCON):
        requests, _, events = _run_openai_like(
            OpenAIProvider,
            [_reply_round(_BAD_COMPILE)] * 3 + [_close_round()], _BUILD_TOOLS)
    assert len(requests) == 3, "the repair cap did not stop the loop at two repairs"
    text = _delivered(events)
    assert "```yaml" not in text, f"a failing fence was delivered: {text!r}"
    assert "not a playbook" not in text, f"the failing fence body was delivered: {text!r}"
    assert "did not pass its checks" in text, "the reply does not say what was refused"
    assert "Here is the playbook." in text, "the prose before the fence was lost"


def test_a_fence_calling_an_unconfigured_connector_is_not_delivered_after_the_cap():
    """Red before the fix: the connector check refuses, the cap runs out, and
    the bad fence is still the reply."""
    with _with_listing(_LISTING_NO_FALCON), \
         patch("fsr_playbooks.llm.agent_loop.compile_errors", return_value=None), \
         patch("fsr_playbooks.mcp_server.tools_emit._needs_configuration",
               return_value=True):
        requests, _, events = _run_openai_like(
            OpenAIProvider,
            [_reply_round(_FALCON_REPLY)] * 3 + [_close_round()], _BUILD_TOOLS)
    assert len(requests) == 3
    text = _delivered(events)
    assert "```yaml" not in text, f"a failing fence was delivered: {text!r}"
    assert "crowd-strike-falcon" in text and "not configured" in text, (
        f"the reply does not name the connector that failed: {text!r}")


def test_a_repaired_reply_delivers_only_the_good_fence():
    """The first fence fails, the repair fixes it: the failing draft is not
    shown, and the good fence is delivered unchanged."""
    with _with_listing(_LISTING_NO_FALCON), \
         patch("fsr_playbooks.llm.agent_loop.compile_errors",
               side_effect=_compile_only_refuses_bad), \
         patch("fsr_playbooks.mcp_server.tools_emit._needs_configuration",
               return_value=True):
        requests, _, events = _run_openai_like(
            OpenAIProvider,
            [_reply_round(_BAD_COMPILE), _reply_round(_FORTIEDR_REPLY)], _BUILD_TOOLS)
    assert len(requests) == 2
    text = _delivered(events)
    assert "not a playbook" not in text, f"the repaired-away draft was delivered: {text!r}"
    assert _FORTIEDR_REPLY in text, f"the good fence was not delivered: {text!r}"


def test_a_good_fence_is_delivered_unchanged():
    """Control: a passing fence is not touched, and the loop ends after one round."""
    with _with_listing(_LISTING_NO_FALCON), \
         patch("fsr_playbooks.llm.agent_loop.compile_errors", return_value=None), \
         patch("fsr_playbooks.mcp_server.tools_emit._needs_configuration",
               return_value=True):
        requests, _, events = _run_openai_like(
            OpenAIProvider, [_reply_round(_FORTIEDR_REPLY), _close_round()], _BUILD_TOOLS)
    assert len(requests) == 1
    assert _delivered(events) == _FORTIEDR_REPLY


def test_a_fence_split_across_stream_deltas_is_still_held():
    """The hold-back works on the stream, not on whole chunks: a fence that
    arrives one character at a time must not reach the analyst either."""
    chunks = [_delta_chunk(content=ch) for ch in _BAD_COMPILE]
    chunks += [_delta_chunk(finish="stop"), _usage_chunk()]
    with patch("fsr_playbooks.llm.agent_loop.compile_errors",
               side_effect=_compile_only_refuses_bad), \
         _with_listing(_LISTING_NO_FALCON):
        _, _, events = _run_openai_like(
            OpenAIProvider, [chunks] * 3 + [_close_round()], _BUILD_TOOLS)
    text = _delivered(events)
    assert "```" not in text and "not a playbook" not in text, repr(text)
    assert "did not pass its checks" in text


def test_the_budget_wrapup_round_is_held_to_the_same_rule():
    """The other delivery path: the tool budget runs out and the loop's wrap-up
    round delivers the reply. Its failing fence must not be the saveable one."""
    with patch("fsr_playbooks.llm.agent_loop.compile_errors",
               side_effect=_compile_only_refuses_bad), \
         _with_listing(_LISTING_NO_FALCON):
        requests, events = _run_with_budget(
            [_tool_round(), _tool_round(), _reply_round(_BAD_COMPILE)], max_tool_turns=2)
    text = _delivered(events)
    assert "```yaml" not in text, f"the wrap-up delivered a failing fence: {text!r}"
    assert "did not pass its checks" in text


def test_a_failing_fence_in_a_tool_round_is_not_the_saved_reply():
    """The widget saves the LAST fence of the whole turn. A tool round can
    print a fence too; if a later round prints none, that fence is what gets
    saved, so a failing one is neutralised as the round goes out."""
    tool_round_with_fence = [
        _delta_chunk(content=_BAD_COMPILE),
        _delta_chunk(tool_calls=[_tc(index=0, id="c1", name="get_step_type", args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    with patch("fsr_playbooks.llm.agent_loop.compile_errors",
               side_effect=_compile_only_refuses_bad), \
         _with_listing(_LISTING_NO_FALCON):
        _, _, events = _run_openai_like(
            OpenAIProvider, [tool_round_with_fence, _close_round()], _BUILD_TOOLS)
    text = _delivered(events)
    assert "not a playbook" not in text, f"a failing fence from a tool round was delivered: {text!r}"
    assert "did not pass its checks" in text
