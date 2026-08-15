"""A tool call with unreadable arguments must bounce, not run as `{}`.

Both streaming providers parsed the model's function-call arguments and, on
any failure, substituted an empty dict and dispatched the tool anyway. `{}` is
a DIFFERENT call from the one the model made:

  - it wastes the turn. Observed on `contain_block_ip_direct`
    (calibrate run 20260815T153152Z): three consecutive `run_op({})`
    dispatches, a third of the fixture's budget, and the turn ended with no
    approval card staged at all.
  - it weakens the gate. `_resolve_tier` reads `connector`/`op` out of the
    args, so a tier-4 containment whose args don't parse resolves as tier 3.
    Unknowns escalate, so nothing runs ungated -- but the step-up requirement
    that separates tier 4 from tier 3 is silently lost.

The correct handling is to hand the parse failure back to the model as a tool
result so it re-emits, which is what these pin.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from test_openai_provider import (  # noqa: F401 -- shared fake wire helpers
    _delta_chunk,
    _drain,
    _provider,
    _tool_call_delta,
    _usage_chunk,
)

from fsr_playbooks.llm.openai_provider import _BAD_ARGS_KEY
from fsr_playbooks.llm.provider import Message, ToolResultEvent

_RUN_OP_TOOLS = [{
    "type": "function",
    "function": {"name": "run_op", "description": "Run a connector operation",
                 "parameters": {"type": "object", "properties": {}}},
}]


@pytest.mark.parametrize("raw_args", [
    '{"connector": "fortigate-firewall", "op":',   # truncated mid-stream
    "not json at all",
    '["connector", "op"]',                          # valid JSON, wrong type
])
def test_openai_never_dispatches_unparseable_args(raw_args: str) -> None:
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="c1",
                                                  name="run_op", args=raw_args)]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="ok"), _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider([turn1, turn2])
    with patch("fsr_playbooks.llm.openai_provider.dispatch") as mock_dispatch:
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="block it")],
            tools=_RUN_OP_TOOLS, tags={})))

    assert not mock_dispatch.called, (
        "the tool ran with silently-emptied arguments")
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert results, "the model got no feedback at all -- it cannot re-emit"
    err = results[0].result
    assert err.get("code") == "bad_tool_arguments", err
    # The message has to be actionable, not just a rejection.
    assert "run_op" in err["message"] and "JSON object" in err["message"]


def test_openai_sentinel_does_not_leak_into_a_real_call() -> None:
    """A well-formed call is unaffected -- the guard is keyed, not heuristic."""
    good = '{"connector": "fortigate-firewall", "op": "get_blocked_ip"}'
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="c1",
                                                  name="run_op", args=good)]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    turn2 = [_delta_chunk(content="ok"), _delta_chunk(finish="stop"), _usage_chunk()]
    p = _provider([turn1, turn2])
    with patch("fsr_playbooks.llm.openai_provider.dispatch",
               return_value={"ok": True}) as mock_dispatch:
        asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="x")],
            tools=_RUN_OP_TOOLS, tags={})))
    assert mock_dispatch.called
    sent = mock_dispatch.call_args[0][1]
    assert _BAD_ARGS_KEY not in sent
    assert sent["op"] == "get_blocked_ip"


def test_emptied_args_would_have_downgraded_the_tier() -> None:
    """Why this is a gating bug and not only a wasted-call bug."""
    from fsr_playbooks.llm.tools import _resolve_tier
    real = {"connector": "fortigate-firewall", "op": "block_ip_new"}
    if _resolve_tier("run_op", real) != 4:
        pytest.skip("reference store does not classify this op as tier 4")
    assert _resolve_tier("run_op", {}) < 4, (
        "if emptied args no longer downgrade the tier, this rationale is "
        "stale -- but the bounce is still correct")
