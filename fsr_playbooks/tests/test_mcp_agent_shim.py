"""Offline round-trip for the MCP triage→build shim (tools_agent).

Drives `triage_build_turn` / `triage_build_resume` against a scripted fake
provider that suspends on a tier-3 action and, on resume(approve), emits a
playbook offer. Asserts the two tools round-trip a HITL approval through the
in-process session store with no live LLM and no FortiSOAR.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import factory
from fsr_playbooks.llm import approvals as _approvals
from fsr_playbooks.llm.approvals import SuspendedSession
from fsr_playbooks.llm.provider import (
    ApprovalRequestEvent,
    DoneEvent,
    TextEvent,
    ToolUseEvent,
    UsageEvent,
)
from fsr_playbooks.mcp_server import tools_agent as ta


def _usage(stop_reason: str) -> UsageEvent:
    return UsageEvent(
        session_id="sess", turn=1, model="fake-1",
        input_tokens=1, output_tokens=1, cache_read=0, cache_write=0,
        history_chars=0, stop_reason=stop_reason,
    )


class _SuspendingFakeProvider:
    """First stream() stages a tier-3 action and suspends; resume(approve)
    emits a playbook offer. The gateway is injected the same way the real
    providers receive it (`approval_gateway=` from the shim)."""

    name = "fake"

    def __init__(self, *, approval_gateway=None, **_):
        self.gateway = approval_gateway

    async def stream(self, *, system, messages, tools, tags=None):
        yield TextEvent(text="Found a malicious IP; staging a block.")
        # Stage the containment action (recorded into the active trace so it
        # surfaces in staged_actions) ...
        from fsr_playbooks.agent import skill_trace
        skill_trace.record_staged_action(
            connector="fortigate", op="block_ip",
            params={"ip": "1.2.3.4"}, step_name="Block IP")
        # ... then suspend on approval, exactly like a real provider.
        sid = (tags or {}).get("session_id", "sess")
        suspended = SuspendedSession(
            approval_id="appr-1", session_id=sid, tool="run_op",
            tool_use_id="tu-1", args={"connector": "fortigate",
                                       "operation": "block_ip"},
            tier=3, history_snapshot=[], prior_tool_result_blocks=[],
            remaining_tool_calls=[], system=system, tags=tags or {},
            summary="Block IP 1.2.3.4",
        )
        _approvals.bind(suspended)
        if self.gateway is not None:
            self.gateway.stash(suspended)
        yield ApprovalRequestEvent(
            approval_id="appr-1", tool_use_id="tu-1", tool="run_op",
            tier=3, preview={"ip": "1.2.3.4"}, args_hash="abc",
            summary="Block IP 1.2.3.4")
        yield _usage("pending_approval")
        yield DoneEvent(stop_reason="pending_approval")

    async def resume(self, *, suspended, decision):
        assert decision == "approve"
        yield TextEvent(text="Block executed. Here is a re-runnable playbook.")
        yield ToolUseEvent(name="emit_playbook_offer", call_id="po-1",
                           arguments={"collection": "Auto Block IP"}, tier=0)
        yield _usage("end_turn")
        yield DoneEvent(stop_reason="end_turn")


@pytest.fixture
def fake_provider_registered():
    saved = dict(factory._REGISTRY)
    factory.register("fake", _SuspendingFakeProvider)
    # Pin the shim's active provider to our fake.
    import os
    prev = os.environ.get("FSR_LLM_PROVIDER")
    os.environ["FSR_LLM_PROVIDER"] = "fake"
    ta._SESSIONS.clear()
    try:
        yield
    finally:
        factory._REGISTRY.clear()
        factory._REGISTRY.update(saved)
        if prev is None:
            os.environ.pop("FSR_LLM_PROVIDER", None)
        else:
            os.environ["FSR_LLM_PROVIDER"] = prev
        ta._SESSIONS.clear()


def test_turn_suspends_then_resume_yields_offer(fake_provider_registered):
    # Turn 1: investigate → stage → suspend on approval.
    r1 = ta.triage_build_turn(
        message="triage this incident and contain the threat",
        entity={"module": "incidents", "uuid": "INC-1",
                "fields": {"name": "Beaconing host"}})
    assert r1["ok"] is True
    assert r1["stop_reason"] == "pending_approval"
    assert r1["approval"] and r1["approval"]["approval_id"] == "appr-1"
    assert any(a["step_name"] == "Block IP" for a in r1["staged_actions"])
    sid = r1["session_id"]
    assert ta._SESSIONS[sid].pending_approval_id == "appr-1"

    # Resume: approve → playbook offer.
    r2 = ta.triage_build_resume(session_id=sid, decision="approve")
    assert r2["ok"] is True
    assert r2["stop_reason"] == "end_turn"
    assert r2["playbook_offer"] is not None
    assert r2["playbook_offer"]["args"]["collection"] == "Auto Block IP"
    # Approval consumed (single-use); store cleared.
    assert ta._SESSIONS[sid].pending_approval_id is None


def test_resume_without_pending_is_rejected(fake_provider_registered):
    ta.triage_build_turn(message="hello")
    # First turn suspends in this fake, so force a fresh clean session.
    sid_new = "no-pending-sess"
    ta._SESSIONS.pop(sid_new, None)
    ta._get_or_create(sid_new)
    r = ta.triage_build_resume(session_id=sid_new, decision="approve")
    assert r["ok"] is False
    assert "no pending approval" in (r.get("message") or "").lower()


def test_unknown_session_resume_errors(fake_provider_registered):
    r = ta.triage_build_resume(session_id="nope", decision="approve")
    assert r["ok"] is False
    assert "unknown session" in (r.get("message") or "").lower()
