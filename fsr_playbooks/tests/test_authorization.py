"""One decision for whether a tool call runs: `authorization.authorize`.

The loop and the batch collector used to split rounds on a hardcoded
`tier >= 3` while dispatch honoured the read-only switch. With the switch off
(every tier 1+ call gated), a tier-1 call ran in the parallel batch, dispatch
returned its approval envelope, and the envelope went back to the model as an
ordinary tool result: no card, no suspension.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import patch

import pytest

from fsr_playbooks.llm import agent_loop, approvals, authorization
from fsr_playbooks.llm import tools as T
from fsr_playbooks.llm.approvals import InMemoryApprovalGateway
from fsr_playbooks.llm.authorization import authorize, needs_approval
from fsr_playbooks.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    Message,
    ToolResultEvent,
)
from fsr_playbooks.tests.test_openai_provider import (
    _delta_chunk,
    _drain,
    _provider,
    _tool_call_delta,
    _usage_chunk,
)


@pytest.fixture(autouse=True)
def _defaults():
    T.set_readonly_auto_approve(None)
    T.set_eval_policy(None)
    yield
    T.set_readonly_auto_approve(None)
    T.set_eval_policy(None)


def test_floor_follows_the_read_only_switch():
    assert not needs_approval(2) and needs_approval(3)
    T.set_readonly_auto_approve(False)
    assert not needs_approval(0) and needs_approval(1)


def test_outcomes_in_order():
    assert authorize("x", {}, tier=1).outcome == "run"
    assert authorize("x", {}, tier=3).outcome == "card"
    d = authorize("x", {}, tier=3, approved_by="system:autonomy")
    assert (d.outcome, d.label, d.actor) == ("run", "approved", "system:autonomy")


def test_a_once_grant_decides_one_call():
    T.grant_tool_approval("s1", "run_op", op_key="fg:block_ip", mode="once")
    args = {"connector": "fg", "op": "block_ip"}
    d = authorize("run_op", args, tier=3, session_id="s1")
    assert (d.outcome, d.label) == ("run", "auto_allow_grant")
    assert authorize("run_op", args, tier=3, session_id="s1").outcome == "card"


def test_eval_policy_denies_with_a_reason():
    T.set_eval_policy("deny")
    d = authorize("x", {}, tier=3)
    assert d.outcome == "deny" and "tier-3" in d.reason


def test_audit_names_who_approved():
    T.clear_audit_log()
    with patch.object(T, "_invoke", return_value={"ok": True}), \
         patch.object(T, "_finalize_tool_output", side_effect=lambda n, r: r):
        T.dispatch("find_connector", {"q": "fortigate", "_approved": True},
                   _internal=True, approved_by="system:autonomy")
    row = T.snapshot_audit_log()[-1]
    assert row["decision"] == "approved" and row["actor"] == "system:autonomy"


def test_no_threshold_outside_authorization():
    for mod in (agent_loop, approvals):
        src = inspect.getsource(mod)
        assert ">= 3" not in src.replace("tier >= 3 slice", ""), mod.__name__


_GET_RECORD_TOOLS = [{
    "type": "function",
    "function": {"name": "get_record", "description": "Read a record",
                 "parameters": {"type": "object",
                                "properties": {"iri": {"type": "string"}}}},
}]


def test_paranoid_mode_cards_a_tier_one_call():
    T.set_readonly_auto_approve(False)
    turn1 = [
        _delta_chunk(tool_calls=[_tool_call_delta(index=0, id="c1",
                                                  name="get_record", args='{"iri":"/x"}')]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]
    envelope = {"pending_approval": True, "approval_id": "appr_r", "tier": 1,
                "tool": "get_record", "preview": {}, "args_hash": "h",
                "summary": "Read", "requires_step_up": False}
    gw = InMemoryApprovalGateway()
    p = _provider(turn1, gateway=gw)
    with patch("fsr_playbooks.llm.agent_loop.dispatch", return_value=envelope), \
         patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=1):
        events = asyncio.run(_drain(p.stream(
            system="s", messages=[Message(role="user", content="read it")],
            tools=_GET_RECORD_TOOLS, tags={})))
    assert any(isinstance(e, ApprovalRequestEvent) for e in events)
    assert not any(isinstance(e, ToolResultEvent) and isinstance(e.result, dict)
                   and e.result.get("pending_approval") for e in events)
    assert next(e for e in events if isinstance(e, DoneEvent)).stop_reason == "pending_approval"


def test_tools_reexports_the_same_state():
    assert T.grant_tool_approval is authorization.grant_tool_approval
    assert T.AUDIT_LOG is authorization.AUDIT_LOG
