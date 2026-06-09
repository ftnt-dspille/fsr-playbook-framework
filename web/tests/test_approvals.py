"""Tests for the HITL approval flow (HITL_GUARDRAILS_PLAN Phase 1).

Covers the building blocks:
- `approvals.stash/pop` single-use semantics + TTL.
- `tools.dispatch` honors `_approved=True` to bypass the gate.
- `POST /api/approvals/{id}` deny path returns user_denied without
  dispatching the underlying tool.
- `POST /api/approvals/{id}` approve path re-dispatches with the
  bypass sentinel.

The provider's suspend behavior (where the loop emits an
ApprovalRequestEvent and stops) is exercised indirectly: we stash a
SuspendedSession directly and verify the resume endpoint drives a
FakeProvider's `resume()` method with the right shape.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from fsr_core.llm import approvals as _approvals
from fsr_core.llm import factory
from fsr_core.llm.fake_provider import FakeProvider
from fsr_core.llm.provider import (
    DoneEvent,
    Event,
    Message,
    TextEvent,
    ToolResultEvent,
    UsageEvent,
)
from fsr_core.llm.tools import AUDIT_LOG, dispatch


@pytest.fixture(autouse=True)
def _clear_state():
    _approvals.clear()
    AUDIT_LOG.clear()
    yield
    _approvals.clear()


# --- tools.dispatch -------------------------------------------------------

def test_dispatch_approved_sentinel_bypasses_gate():
    # Unknown connector/op = tier 3 by default. Without _approved it
    # returns pending_approval. With _approved=True it falls through to
    # the underlying function (which itself errors because the op is
    # bogus — but importantly NOT with pending_approval).
    out = dispatch(
        "run_op",
        {"connector": "__nope__", "op": "__nope__", "_approved": True},
    )
    assert isinstance(out, dict)
    assert "pending_approval" not in out
    # Underlying tool was invoked (and predictably failed): we should
    # have an error or an ok=False rather than the gate envelope.


def test_dispatch_records_approval_audit_row():
    # Gate hit
    dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    pending_rows = [r for r in AUDIT_LOG if r["decision"] == "pending"]
    assert pending_rows, "gate should leave a pending audit row"
    # Now bypass
    dispatch("run_op", {"connector": "__x__", "op": "__y__", "_approved": True})
    approved_rows = [r for r in AUDIT_LOG if r["decision"] == "approved"]
    assert approved_rows, "bypass should leave an approved audit row"


# --- approvals store -------------------------------------------------------

def _mk_session(approval_id: str = "abc123") -> _approvals.SuspendedSession:
    return _approvals.SuspendedSession(
        approval_id=approval_id,
        session_id="sess",
        tool="run_op",
        tool_use_id="tu_1",
        args={"connector": "fortigate", "op": "block_ip", "params": {"ip": "8.8.8.8"}},
        tier=3,
        history_snapshot=[
            {"role": "user", "content": "block 8.8.8.8"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu_1", "name": "run_op",
                 "input": {"connector": "fortigate", "op": "block_ip"}},
            ]},
        ],
        prior_tool_result_blocks=[],
        remaining_tool_calls=[],
        system="sys",
        tags={},
        summary="Block 8.8.8.8 on FortiGate",
    )


def test_stash_pop_single_use():
    s = _mk_session()
    _approvals.stash(s)
    got = _approvals.pop(s.approval_id)
    assert got is not None and got.approval_id == s.approval_id
    # Second pop returns None — single-use.
    assert _approvals.pop(s.approval_id) is None


def test_stash_pop_expired_returns_none(monkeypatch):
    s = _mk_session()
    s.created_at = time.time() - 99999
    _approvals.stash(s)
    assert _approvals.pop(s.approval_id) is None


# --- /api/approvals endpoint ----------------------------------------------

class _ResumeRecordingProvider(FakeProvider):
    """Records resume() inputs and emits a scripted resume stream."""

    name = "anthropic"

    def __init__(self, resume_events: list[Event]):
        super().__init__()
        self.resume_calls: list[tuple[_approvals.SuspendedSession, str]] = []
        self._resume_events = resume_events

    async def resume(
        self, *, suspended: _approvals.SuspendedSession, decision: str
    ) -> AsyncIterator[Event]:
        self.resume_calls.append((suspended, decision))
        for ev in self._resume_events:
            yield ev


@pytest.fixture
def client():
    return TestClient(app)


def _register_resume_provider(events: list[Event]) -> _ResumeRecordingProvider:
    p = _ResumeRecordingProvider(events)
    factory.register("anthropic", lambda: p)
    return p


def _terminal_events(session_id: str = "sess") -> list[Event]:
    return [
        TextEvent(text="ok"),
        UsageEvent(
            session_id=session_id, turn=1, model="fake-1",
            input_tokens=1, output_tokens=1,
            cache_read=0, cache_write=0,
            history_chars=10, stop_reason="end_turn",
        ),
        DoneEvent(stop_reason="end_turn"),
    ]


def test_resolve_approval_missing_returns_404_envelope(client):
    r = client.post("/api/approvals/does_not_exist", json={"decision": "approve"})
    assert r.status_code == 200
    body = r.text
    assert "approval not found" in body
    assert "done" in body


def test_resolve_approval_bad_decision(client):
    s = _mk_session("bad1")
    _approvals.stash(s)
    r = client.post(f"/api/approvals/{s.approval_id}", json={"decision": "maybe"})
    assert r.status_code == 200
    assert "approve or deny" in r.text
    # Session NOT consumed on bad input — user can retry with a valid
    # decision.
    assert _approvals.peek(s.approval_id) is not None


def test_resolve_approval_approve_invokes_resume_with_approve(client):
    s = _mk_session("good1")
    _approvals.stash(s)
    p = _register_resume_provider(_terminal_events())
    r = client.post(f"/api/approvals/{s.approval_id}", json={"decision": "approve"})
    assert r.status_code == 200
    assert len(p.resume_calls) == 1
    suspended, decision = p.resume_calls[0]
    assert decision == "approve"
    assert suspended.approval_id == s.approval_id
    # Session is single-use: consumed by the resume.
    assert _approvals.peek(s.approval_id) is None


def test_resolve_approval_deny_invokes_resume_with_deny(client):
    s = _mk_session("deny1")
    _approvals.stash(s)
    p = _register_resume_provider(_terminal_events())
    r = client.post(f"/api/approvals/{s.approval_id}", json={"decision": "deny"})
    assert r.status_code == 200
    assert len(p.resume_calls) == 1
    suspended, decision = p.resume_calls[0]
    assert decision == "deny"
    assert suspended.approval_id == s.approval_id


# --- Phase 4: server-side step-up ----------------------------------------

def _mk_tier4_session(approval_id: str = "tier4_1") -> _approvals.SuspendedSession:
    s = _mk_session(approval_id)
    s.tier = 4
    return s


def test_step_up_missing_confirmed_target_400s(client):
    s = _mk_tier4_session("su1")
    _approvals.stash(s)
    p = _register_resume_provider(_terminal_events())
    r = client.post(f"/api/approvals/{s.approval_id}", json={"decision": "approve"})
    assert r.status_code == 200
    assert "Type the target" in r.text
    assert "step_up_required" in r.text
    # Session NOT consumed: user can retype.
    assert _approvals.peek(s.approval_id) is not None
    # Underlying resume NOT invoked.
    assert p.resume_calls == []


def test_step_up_wrong_confirmed_target_400s(client):
    s = _mk_tier4_session("su2")
    _approvals.stash(s)
    p = _register_resume_provider(_terminal_events())
    r = client.post(
        f"/api/approvals/{s.approval_id}",
        json={"decision": "approve", "confirmed_target": "9.9.9.9"},
    )
    assert "step_up_required" in r.text
    assert _approvals.peek(s.approval_id) is not None
    assert p.resume_calls == []


def test_step_up_correct_target_allows_approve(client):
    s = _mk_tier4_session("su3")
    _approvals.stash(s)
    p = _register_resume_provider(_terminal_events())
    r = client.post(
        f"/api/approvals/{s.approval_id}",
        json={"decision": "approve", "confirmed_target": "8.8.8.8"},
    )
    assert r.status_code == 200
    assert "step_up_required" not in r.text
    assert len(p.resume_calls) == 1
    assert p.resume_calls[0][1] == "approve"


def test_step_up_not_required_on_deny(client):
    # Deny should not require confirmed_target even at tier 4 — the
    # user is opting out, not committing to anything.
    s = _mk_tier4_session("su4")
    _approvals.stash(s)
    p = _register_resume_provider(_terminal_events())
    r = client.post(f"/api/approvals/{s.approval_id}", json={"decision": "deny"})
    assert "step_up_required" not in r.text
    assert len(p.resume_calls) == 1
    assert p.resume_calls[0][1] == "deny"


def test_resolve_approval_streams_serialized_events(client):
    s = _mk_session("stream1")
    _approvals.stash(s)
    _register_resume_provider([
        ToolResultEvent(call_id="tu_1", result={"ok": True}),
        UsageEvent(
            session_id="sess", turn=1, model="fake-1",
            input_tokens=1, output_tokens=1,
            cache_read=0, cache_write=0,
            history_chars=10, stop_reason="end_turn",
        ),
        DoneEvent(stop_reason="end_turn"),
    ])
    r = client.post(f"/api/approvals/{s.approval_id}", json={"decision": "approve"})
    body = r.text
    # SSE frames for each event type the resume emitted.
    assert "tool_result" in body
    assert "usage" in body
    assert "done" in body
