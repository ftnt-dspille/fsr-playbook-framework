"""Per-session approval grants: 'once' and 'always' modes.

After a human approves a tool/action, the approval grant store enables future
calls to the same tool (optionally scoped to the same connector+op for run_op)
to auto-run without another approval card, either:
  - 'once': consume the grant on the next matching call, then require approval again.
  - 'always': persist the grant for the session, auto-run all matching calls.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import tools as tools_mod
from fsr_playbooks.llm.tools import (
    REGISTRY,
    ToolSpec,
    _consume_grant,
    clear_session_grants,
    dispatch,
    grant_tool_approval,
)


@pytest.fixture
def tier3_tool(monkeypatch):
    """Register a throwaway tier-3 tool whose fn records if it ran."""
    calls: list[dict] = []

    def _fn(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "did_run": True}

    spec = ToolSpec(
        name="_grant_probe",
        description="test-only tier-3 tool for grant testing",
        input_schema={"type": "object", "properties": {}},
        fn=_fn,
        tier=3,
    )
    monkeypatch.setitem(REGISTRY, "_grant_probe", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "_grant_probe", 3)
    # Neutralize any ambient eval policy so tier-3 falls through to the
    # real pending_approval / grant path rather than a short-circuit.
    monkeypatch.delenv("EVAL_APPROVAL_POLICY", raising=False)
    yield calls
    # Cleanup
    tools_mod._APPROVAL_GRANTS.clear()


@pytest.fixture
def session_id():
    """Return a test session ID."""
    return "test-session-uuid-12345"


def test_grant_once_consumes_grant_on_next_call(tier3_tool, session_id):
    """A 'once' grant auto-runs exactly one call, then is consumed."""
    grant_tool_approval(session_id, "_grant_probe", mode="once")

    # First call: grant exists, auto-runs, grant is consumed.
    result1 = dispatch("_grant_probe", {}, session_id=session_id)
    assert result1.get("ok") is True
    assert result1.get("did_run") is True
    assert len(tier3_tool) == 1, "fn must run on first call with 'once' grant"

    # Second call: grant is gone, should return pending_approval.
    result2 = dispatch("_grant_probe", {}, session_id=session_id)
    assert result2.get("pending_approval") is True
    assert len(tier3_tool) == 1, "fn must NOT run without grant (still 1 call)"


def test_grant_always_persists_across_calls(tier3_tool, session_id):
    """An 'always' grant auto-runs all matching calls for the session."""
    grant_tool_approval(session_id, "_grant_probe", mode="always")

    # Multiple calls should all succeed.
    for i in range(3):
        result = dispatch("_grant_probe", {}, session_id=session_id)
        assert result.get("ok") is True
        assert result.get("did_run") is True

    assert len(tier3_tool) == 3, "fn must run all 3 times with 'always' grant"


def test_grant_audited_as_auto_allow_grant(tier3_tool, session_id):
    """Dispatches using grants are audited with 'auto_allow_grant' decision."""
    grant_tool_approval(session_id, "_grant_probe", mode="once")
    before = len(tools_mod.AUDIT_LOG)

    dispatch("_grant_probe", {}, session_id=session_id)

    assert len(tools_mod.AUDIT_LOG) > before
    row = tools_mod.AUDIT_LOG[-1]
    assert row["tool"] == "_grant_probe"
    assert row["decision"] == "auto_allow_grant"
    assert row["tier"] == 3


def test_grant_with_wrong_tool_does_not_leak(tier3_tool, session_id, monkeypatch):
    """A grant for tool A does not apply to tool B."""
    grant_tool_approval(session_id, "_grant_probe", mode="once")

    # Call a different tool (find_connector is tier 0, won't be gated).
    # Register a second tier-3 tool to test the isolation.
    calls2: list[dict] = []

    def _fn2(**kwargs):
        calls2.append(kwargs)
        return {"ok": True}

    spec = ToolSpec(
        name="_grant_probe_2",
        description="second test tool",
        input_schema={"type": "object", "properties": {}},
        fn=_fn2,
        tier=3,
    )
    monkeypatch.setitem(REGISTRY, "_grant_probe_2", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "_grant_probe_2", 3)

    # Call _grant_probe_2: grant is for _grant_probe, not this tool.
    result = dispatch("_grant_probe_2", {}, session_id=session_id)
    assert result.get("pending_approval") is True
    assert len(calls2) == 0, "grant for _grant_probe must NOT apply to _grant_probe_2"


def test_grant_with_wrong_session_does_not_leak(tier3_tool, session_id):
    """A grant for session A does not apply to session B."""
    grant_tool_approval(session_id, "_grant_probe", mode="once")

    # Call with a different session_id: grant won't match.
    other_session = "different-session-uuid"
    result = dispatch("_grant_probe", {}, session_id=other_session)
    assert result.get("pending_approval") is True
    assert len(tier3_tool) == 0, "grant for one session must NOT apply to another"


def test_run_op_grant_scoped_by_op_key(monkeypatch, session_id):
    """For run_op, grants are scoped to (connector, op) pairs via op_key."""
    calls: list[dict] = []

    def _fn(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    spec = ToolSpec(
        name="run_op",
        description="test run_op",
        input_schema={"type": "object", "properties": {}},
        fn=_fn,
        tier=-1,  # Dynamic tier, resolved at call time
    )
    monkeypatch.setitem(REGISTRY, "run_op", spec)
    monkeypatch.setitem(tools_mod.TOOL_TIERS, "run_op", -1)
    monkeypatch.delenv("EVAL_APPROVAL_POLICY", raising=False)

    # Mock _resolve_tier to return a predictable tier.
    original_resolve_tier = tools_mod._resolve_tier

    def mock_resolve_tier(name, args):
        if name == "run_op":
            return 3  # Force tier-3 to trigger gating
        return original_resolve_tier(name, args)

    monkeypatch.setattr(tools_mod, "_resolve_tier", mock_resolve_tier)

    # Grant for fortigate:block_ip
    grant_tool_approval(
        session_id, "run_op", op_key="fortigate:block_ip", mode="once"
    )

    # Call with matching op_key: should auto-run.
    result1 = dispatch(
        "run_op",
        {"connector": "fortigate", "op": "block_ip", "params": {}},
        session_id=session_id,
    )
    assert result1.get("ok") is True
    assert len(calls) == 1

    # Call with different op_key: should require approval.
    result2 = dispatch(
        "run_op",
        {"connector": "fortigate", "op": "unblock_ip", "params": {}},
        session_id=session_id,
    )
    assert result2.get("pending_approval") is True
    assert len(calls) == 1, "grant for block_ip must NOT apply to unblock_ip"


def test_clear_session_grants_removes_all_grants_for_session(session_id):
    """clear_session_grants removes both 'once' and 'always' grants for a session."""
    grant_tool_approval(session_id, "_grant_probe", mode="once")
    grant_tool_approval(session_id, "_grant_probe", op_key="op:key", mode="always")

    other_session = "other-session"
    grant_tool_approval(other_session, "_grant_probe", mode="once")

    # Before clear: 3 grants total.
    assert len(tools_mod._APPROVAL_GRANTS) == 3

    # Clear only session_id's grants.
    clear_session_grants(session_id)

    # After clear: only other_session's grant remains.
    assert len(tools_mod._APPROVAL_GRANTS) == 1
    remaining_key = list(tools_mod._APPROVAL_GRANTS.keys())[0]
    assert remaining_key[0] == other_session


def test_no_session_id_no_grant_check(tier3_tool, monkeypatch):
    """If session_id is not passed, grants are not checked (backward compatible)."""
    grant_tool_approval("some-session", "_grant_probe", mode="once")
    monkeypatch.delenv("EVAL_APPROVAL_POLICY", raising=False)

    # Call without session_id: grant exists but won't be checked, returns pending_approval.
    result = dispatch("_grant_probe", {})
    assert result.get("pending_approval") is True
    assert len(tier3_tool) == 0


def test_consume_grant_internal_helper():
    """Test the internal _consume_grant helper directly."""
    session_id = "session-1"

    # Grant doesn't exist: returns False.
    assert _consume_grant(session_id, "tool_a") is False

    # Grant 'once': first consume returns True and removes it.
    grant_tool_approval(session_id, "tool_a", mode="once")
    assert _consume_grant(session_id, "tool_a") is True
    assert _consume_grant(session_id, "tool_a") is False  # Now gone

    # Grant 'always': consume returns True but doesn't remove it.
    grant_tool_approval(session_id, "tool_b", mode="always")
    assert _consume_grant(session_id, "tool_b") is True
    assert _consume_grant(session_id, "tool_b") is True  # Still there


def test_invalid_grant_mode_raises_error():
    """Passing an invalid mode to grant_tool_approval raises ValueError."""
    with pytest.raises(ValueError, match="Invalid grant mode"):
        grant_tool_approval("session", "tool", mode="invalid")
