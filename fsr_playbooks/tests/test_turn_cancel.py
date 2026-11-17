"""C6: a Stop from the analyst ends the agent turn on the host side.

The loop checks `cancel_check` (carried on the turn's TurnRequest) before each
model round and before each tool dispatch. After Stop: no further model call,
no tool dispatch, and the turn ends with stop_reason `stopped_by_analyst`.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.provider import Message
from fsr_playbooks.llm.run_turn import run_agent_turn

_SPEC = importlib.util.spec_from_file_location(
    "_create_delivery_fixtures",
    Path(__file__).with_name("test_openai_create_delivery_forced.py"))
fx = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(fx)


def _run(create, cancel_check, dispatch):
    provider = fx._provider(create)
    with patch("fsr_playbooks.llm.agent_loop.dispatch", MagicMock(side_effect=dispatch)), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
        return asyncio.run(run_agent_turn(
            provider=provider,
            system="s",
            messages=[Message(role="user", content="build a phishing playbook")],
            tools=fx._BUILD_TOOLS,
            tags={},
            cancel_check=cancel_check,
        ))


def test_stop_before_the_first_round_makes_no_model_call():
    turn1, _ = fx._narrated_turns()
    create = AsyncMock(side_effect=[fx._FakeStream(turn1)])
    dispatch = MagicMock(side_effect=fx._fake_dispatch)
    result = _run(create, lambda: True, dispatch)
    assert create.await_count == 0
    assert dispatch.call_count == 0
    assert result.stop_reason == "stopped_by_analyst"


def test_stop_during_a_round_runs_no_tool_and_no_further_round():
    """The model asks for a tool; the analyst stops while that round is in
    flight. The tool must not dispatch and no second round may start."""
    turn1, turn2 = fx._narrated_turns()
    seen = {"rounds": 0}

    async def create(**_kwargs):
        seen["rounds"] += 1
        return fx._FakeStream(turn1 if seen["rounds"] == 1 else turn2)

    create_mock = AsyncMock(side_effect=create)
    dispatch = MagicMock(side_effect=fx._fake_dispatch)
    result = _run(create_mock, lambda: seen["rounds"] >= 1, dispatch)
    assert create_mock.await_count == 1
    assert dispatch.call_count == 0, "a tool ran after Stop"
    assert result.stop_reason == "stopped_by_analyst"


def test_a_turn_nobody_stopped_runs_to_its_normal_end():
    turn1, turn2 = fx._narrated_turns()
    create = AsyncMock(side_effect=[fx._FakeStream(turn1), fx._FakeStream(turn2),
                                    fx._forced_response()])
    dispatch = MagicMock(side_effect=fx._fake_dispatch)
    result = _run(create, lambda: False, dispatch)
    assert dispatch.call_count >= 1
    assert result.stop_reason != "stopped_by_analyst"


def test_a_broken_stop_probe_does_not_kill_the_turn():
    turn1, turn2 = fx._narrated_turns()
    create = AsyncMock(side_effect=[fx._FakeStream(turn1), fx._FakeStream(turn2),
                                    fx._forced_response()])

    def boom():
        raise RuntimeError("store unreachable")

    result = _run(create, boom, MagicMock(side_effect=fx._fake_dispatch))
    assert result.stop_reason != "stopped_by_analyst"
