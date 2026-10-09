"""A forced wrap-up must leave the analyst a reply.

Frank ZTPF sweep at RUNS=2: a turn ran six reads and closed with no text, so
the assessment wrap-up fired -- and it too came back empty, having spent all
512 of its output tokens (a reasoning model draws its reasoning from that
budget). The analyst saw nothing at all. Forced rounds now get the normal
output ceiling, and an empty wrap-up still says what happened.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from test_openai_build_progress_forced import _delta_chunk, _FakeStream, _usage_chunk
from test_promised_action_guard import _OPENAI_TOOLS, _call, _dispatch, _drain

from fsr_playbooks.llm._loop_helpers import DEFAULT_MAX_OUTPUT_TOKENS, EMPTY_WRAPUP_TEXT
from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message, TextEvent


def _empty():
    return [_delta_chunk(content=""), _delta_chunk(finish="stop"), _usage_chunk()]


def _run(rounds):
    kwargs_seen: list = []
    queue = [_FakeStream(r) for r in rounds]

    def _create(*_a, **kw):
        kwargs_seen.append({k: v for k, v in kw.items() if k != "messages"})
        return queue.pop(0)

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock(create=AsyncMock(side_effect=_create))
    p = OpenAIProvider(model="gpt-5.4-mini", base_url="http://x/v1", api_key="x",
                       client=client)
    tools = [t for t in _OPENAI_TOOLS if t["function"]["name"] != "emit_card"]
    with patch("fsr_playbooks.llm.agent_loop.dispatch",
               MagicMock(side_effect=_dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="summarize")],
            tools=tools, tags={})))
    return events, kwargs_seen


def test_an_empty_wrapup_still_tells_the_analyst_something():
    events, _ = _run([_call("c1", "get_record", {"uuid": "u"}), _empty(), _empty()])
    said = "".join(e.text for e in events if isinstance(e, TextEvent))
    assert EMPTY_WRAPUP_TEXT in said


def test_the_wrapup_gets_the_normal_output_ceiling():
    _, kwargs = _run([_call("c1", "get_record", {"uuid": "u"}), _empty(), _empty()])
    wrapup = kwargs[-1]
    cap = wrapup.get("max_completion_tokens") or wrapup.get("max_tokens")
    assert cap == DEFAULT_MAX_OUTPUT_TOKENS


def test_a_wrapup_that_answers_is_left_alone():
    answer = [_delta_chunk(content="The profile has 7 steps."),
              _delta_chunk(finish="stop"), _usage_chunk()]
    events, _ = _run([_call("c1", "get_record", {"uuid": "u"}), _empty(), answer])
    said = "".join(e.text for e in events if isinstance(e, TextEvent))
    assert "7 steps" in said and EMPTY_WRAPUP_TEXT not in said
