"""Tests for the read-only auto-approve policy flag.

Read-only actions (tier 1-2) auto-run without an approval card by default.
`FSR_AUTO_APPROVE_READONLY=0` turns on paranoid mode: every tier>=1 action is
gated, only tier-0 local tools auto-run. This makes the previously-implicit
`tier >= 3` gate an explicit, operator-toggleable policy.
"""
from __future__ import annotations

import os

import pytest

from fsr_playbooks.llm import tools as _tools
from fsr_playbooks.llm.tools import ToolSpec


# --- helpers: flag + floor resolution -------------------------------------

@pytest.fixture(autouse=True)
def _reset_state():
    _tools.set_readonly_auto_approve(None)
    os.environ.pop("FSR_AUTO_APPROVE_READONLY", None)
    _tools.clear_audit_log()
    yield
    _tools.set_readonly_auto_approve(None)
    os.environ.pop("FSR_AUTO_APPROVE_READONLY", None)
    _tools.clear_audit_log()


def test_default_is_auto_approve_on():
    assert _tools._readonly_auto_approve() is True
    assert _tools._approval_floor() == 3


@pytest.mark.parametrize("val", ["0", "false", "False", "no", "off", ""])
def test_env_disables(val):
    os.environ["FSR_AUTO_APPROVE_READONLY"] = val
    assert _tools._readonly_auto_approve() is False
    assert _tools._approval_floor() == 1


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "anything"])
def test_env_enables(val):
    os.environ["FSR_AUTO_APPROVE_READONLY"] = val
    assert _tools._readonly_auto_approve() is True
    assert _tools._approval_floor() == 3


def test_override_takes_precedence_over_env():
    os.environ["FSR_AUTO_APPROVE_READONLY"] = "1"
    _tools.set_readonly_auto_approve(False)
    assert _tools._readonly_auto_approve() is False
    _tools.set_readonly_auto_approve(True)
    os.environ["FSR_AUTO_APPROVE_READONLY"] = "0"
    assert _tools._readonly_auto_approve() is True


# --- dispatch integration: a synthetic tier-2 read-only tool --------------

_FAKE = "__fake_readonly_tool__"


@pytest.fixture
def fake_tier2_tool():
    """Register a tier-2 tool with a fn that records it ran, so we can tell
    auto-run (fn invoked) from suspend (fn NOT invoked) without touching the
    reference DB or live FSR."""
    calls: list[dict] = []

    def _fn(**kw):
        calls.append(kw)
        return {"ok": True, "ran": True}

    spec = ToolSpec(name=_FAKE, description="", input_schema={}, fn=_fn, tier=2)
    _tools.REGISTRY[_FAKE] = spec
    _tools.TOOL_TIERS[_FAKE] = 2
    try:
        yield calls
    finally:
        _tools.REGISTRY.pop(_FAKE, None)
        _tools.TOOL_TIERS.pop(_FAKE, None)


def test_readonly_autoruns_by_default(fake_tier2_tool):
    out = _tools.dispatch(_FAKE, {"x": 1})
    assert "pending_approval" not in out
    assert out == {"ok": True, "ran": True}
    assert fake_tier2_tool == [{"x": 1}]  # fn actually ran
    assert _tools.snapshot_audit_log()[-1]["decision"] == "auto_allow"


def test_readonly_gated_when_disabled(fake_tier2_tool):
    _tools.set_readonly_auto_approve(False)
    out = _tools.dispatch(_FAKE, {"x": 1})
    assert out.get("pending_approval") is True
    assert out["tier"] == 2
    assert fake_tier2_tool == []  # fn must NOT have run
    assert _tools.snapshot_audit_log()[-1]["decision"] == "pending"


def test_disabled_still_lets_approved_calls_through(fake_tier2_tool):
    _tools.set_readonly_auto_approve(False)
    out = _tools.dispatch(_FAKE, {"x": 1, "_approved": True})
    assert "pending_approval" not in out
    assert out == {"ok": True, "ran": True}
    assert fake_tier2_tool == [{"x": 1}]


def test_disabled_does_not_gate_tier0(fake_tier2_tool):
    """Local tier-0 tools stay auto-run even in paranoid mode."""
    _tools.set_readonly_auto_approve(False)
    # analyze_playbook is a static tier-0 tool; missing args make it error,
    # but the point is it dispatches (no pending_approval), not the result.
    out = _tools.dispatch("compile_yaml", {})
    assert "pending_approval" not in out
