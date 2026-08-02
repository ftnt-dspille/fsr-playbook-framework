"""The positive control for guard-fire telemetry: a real fire reaches
`TurnResult.guards_fired`.

Both ENDS of this chain were already pinned -- `test_guard_fire_telemetry.py`
proves each guard calls `record_guard_fire` when it forces, and the connector's
`test_guard_fire_envelope.py` proves fires get copied onto the envelope tags.
Nothing pinned the MIDDLE: that a guard forcing inside the real provider loop
survives `run_agent_turn`'s clear-at-start / snapshot-at-end
(`run_turn.py:276` and `:412`) and lands on the result.

That gap matters right now because Phase 4.1 decides each guard's fate from
measured fire rates, and the headline outcome it is looking for is a ZERO. A
zero from a broken telemetry chain and a zero from a guard that never needed to
fire are the same number and opposite conclusions -- the same trap as a
pre-commit hook scoped to a directory that no longer exists, which looks
exactly like a passing gate. So: force a guard for real, and assert the number
is not zero.

Reuses the create-delivery fixtures rather than re-deriving them; that module
already reproduces the live widget failure (verified YAML, narrated, never
offered) chunk for chunk.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fsr_playbooks.llm.provider import Message
from fsr_playbooks.llm.run_turn import run_agent_turn

# `fsr_playbooks/tests` is not a package (no __init__.py), so load the fixture
# module by path rather than by import name.
_SPEC = importlib.util.spec_from_file_location(
    "_create_delivery_fixtures",
    Path(__file__).with_name("test_openai_create_delivery_forced.py"))
fx = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(fx)


def _run(create):
    provider = fx._provider(create)
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               MagicMock(side_effect=fx._fake_dispatch)), \
         patch("fsr_playbooks.llm.openai_provider._tier_for", return_value=0):
        return asyncio.run(run_agent_turn(
            provider=provider,
            system="s",
            messages=[Message(role="user",
                              content="build a phishing playbook")],
            tools=fx._BUILD_TOOLS,
            tags={},
        ))


def test_a_forced_guard_lands_on_the_turn_result():
    """The control. If this ever goes green-with-an-empty-list, every
    guard-fire rate measured anywhere is meaningless."""
    turn1, turn2 = fx._narrated_turns()
    result = _run(AsyncMock(side_effect=[
        fx._FakeStream(turn1), fx._FakeStream(turn2), fx._forced_response()]))
    assert result.guards_fired == ["CreateDeliveryGuard"], (
        "a guard forced inside the provider loop but the fire did not survive "
        "run_agent_turn -- clear/snapshot ordering, or the guard stopped "
        "calling mark_forced()")


def test_a_healthy_turn_reports_no_fires():
    """The other half of the control: the field is not simply always
    populated. Absent = healthy is the contract the connector relies on to
    keep `guards_fired` off the envelope entirely."""
    turn1, _ = fx._narrated_turns()
    # One round that ends without ever tripping a guard: the model narrates,
    # nothing is verified, so CreateDeliveryGuard is inert by design (there
    # are no verified bytes to deliver).
    result = _run(AsyncMock(side_effect=[fx._FakeStream(turn1)]))
    assert result.guards_fired == []
