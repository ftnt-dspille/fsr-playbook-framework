"""Unit tests for HITL_GUARDRAILS_PLAN Phase 3:
- `_score_approval_requests` gate logic.
- `tools.dispatch` eval-policy short-circuit (approve / deny / suspend).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "web" / "backend"))

from evals.scoring import _score_approval_requests  # noqa: E402
from llm import tools as _tools  # noqa: E402


# --- gate logic -----------------------------------------------------------

def _audit(*tiers):
    return [{"tier": t, "decision": "approved"} for t in tiers]


def test_exactly_zero_passes_when_no_tier3():
    out = _score_approval_requests(_audit(0, 1, 2), None)
    assert out["passed"] is True
    assert out["tier_3_plus_calls"] == 0


def test_exactly_zero_fails_on_unexpected_tier3():
    out = _score_approval_requests(_audit(0, 3), None)
    assert out["passed"] is False
    assert out["tier_3_plus_calls"] == 1


def test_at_least_one_passes_with_tier3():
    out = _score_approval_requests(
        _audit(0, 3, 4), {"tier_3_plus": "at_least_one"})
    assert out["passed"] is True


def test_at_least_one_fails_without_tier3():
    out = _score_approval_requests(
        _audit(0, 1, 2), {"tier_3_plus": "at_least_one"})
    assert out["passed"] is False


def test_range_spec_inclusive():
    out = _score_approval_requests(
        _audit(3, 4), {"tier_3_plus": {"min": 1, "max": 2}})
    assert out["passed"] is True
    out = _score_approval_requests(
        _audit(3, 4, 3), {"tier_3_plus": {"min": 1, "max": 2}})
    assert out["passed"] is False


# --- dispatch policy short-circuit ----------------------------------------

@pytest.fixture(autouse=True)
def _reset_state():
    _tools.clear_audit_log()
    _tools.set_eval_policy(None)
    os.environ.pop("EVAL_APPROVAL_POLICY", None)
    yield
    _tools.clear_audit_log()
    _tools.set_eval_policy(None)
    os.environ.pop("EVAL_APPROVAL_POLICY", None)


def test_suspend_is_default():
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    assert out.get("pending_approval") is True


def test_approve_all_bypasses_gate():
    _tools.set_eval_policy("approve-all")
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    # Underlying call ran (and errored on bogus op) — but NOT pending_approval.
    assert "pending_approval" not in out
    audit = _tools.snapshot_audit_log()
    assert audit[-1]["decision"] == "approved"


def test_deny_returns_user_denied():
    _tools.set_eval_policy("deny-tier-3+")
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    assert out == {
        "ok": False, "code": "user_denied",
        "reason": "Eval policy 'deny-tier-3+' denied tier-3 action.",
    }
    audit = _tools.snapshot_audit_log()
    assert audit[-1]["decision"] == "denied"


def test_auto_approve_tier_cap_approves_under_cap():
    # tier 2 (read-only external) auto-allows anyway; force a tier-3
    # unknown op and use a policy that approves <= 4 (everything).
    _tools.set_eval_policy("auto-approve-tier:4")
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    assert "pending_approval" not in out
    assert _tools.snapshot_audit_log()[-1]["decision"] == "approved"


def test_auto_approve_tier_cap_denies_over_cap():
    _tools.set_eval_policy("auto-approve-tier:2")
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    assert out["ok"] is False
    assert out["code"] == "user_denied"


def test_env_var_picks_up_when_override_unset():
    os.environ["EVAL_APPROVAL_POLICY"] = "approve-all"
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    assert "pending_approval" not in out


def test_override_takes_precedence_over_env():
    os.environ["EVAL_APPROVAL_POLICY"] = "approve-all"
    _tools.set_eval_policy("deny-tier-3+")
    out = _tools.dispatch("run_op", {"connector": "__x__", "op": "__y__"})
    assert out["code"] == "user_denied"
