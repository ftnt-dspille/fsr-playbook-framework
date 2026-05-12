"""mcp_server.suggest_fix_for_diagnostic — translates a render-path
diagnostic into a structured patch proposal."""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import mcp_server  # noqa: E402


def test_missing_key_with_close_match_returns_high_confidence_swap():
    diag = {
        "kind": "missing_key",
        "severity": "error",
        "step_id": "emit",
        "path": "vars.steps.Fetch.data.statuss",
        "location": "arguments.arg_list[0].value",
        "message": "key 'statuss' not in 'Fetch's output",
        "suggestion": "did you mean 'status'?",
        "actual": "statuss",
        "expected": ["data", "status", "summary"],
    }
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["ok"] is True
    assert r["kind"] == "missing_key"
    assert r["before"] == "statuss"
    assert r["after"] == "status"
    assert r["confidence"] == "high"
    assert r["location"] == "arguments.arg_list[0].value"


def test_missing_key_without_suggestion_returns_no_proposal():
    diag = {
        "kind": "missing_key",
        "severity": "error",
        "step_id": "emit",
        "path": "vars.steps.Fetch.bogus",
        "location": "arguments.x",
        "suggestion": "",  # no close key
        "actual": "bogus",
        "expected": ["data"],
    }
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["ok"] is False
    assert "expected" in r["reason"] or "expected=" in r["reason"]


def test_picklist_drift_proposes_first_close_match():
    diag = {
        "kind": "picklist_drift",
        "severity": "error",
        "step_id": "emit",
        "path": "AlertStatus:In Progress",
        "location": "arguments.arg_list[0].value",
        "actual": "In Progress",
        "expected": ["Investigating", "Open", "Pending"],
        "suggestion": "close matches: Investigating, Open, Pending",
    }
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["ok"] is True
    assert r["after"] == "Investigating"
    assert r["confidence"] == "medium"  # multiple matches


def test_picklist_drift_single_match_is_high_confidence():
    diag = {
        "kind": "picklist_drift",
        "step_id": "x",
        "location": "arguments.x",
        "actual": "wrong",
        "expected": ["Right"],
    }
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["confidence"] == "high"


def test_unreachable_var_path_returns_no_auto_fix_with_actionable_reason():
    diag = {
        "kind": "unreachable_var_path",
        "step_id": "emit",
        "path": "vars.steps.bogus.id",
        "location": "arguments.arg_list[0].value",
        "extra": {"missing_step": "bogus"},
    }
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["ok"] is False
    assert "bogus" in r["reason"]


def test_required_arg_empty_proposes_todo_scaffold():
    diag = {
        "kind": "required_arg_empty",
        "step_id": "rc",
        "path": "module",
        "location": "arguments.module",
        "actual": "",
    }
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["ok"] is True
    assert r["after"].startswith("TODO_")
    assert r["confidence"] == "low"


def test_unknown_kind_returns_explanatory_no_fix():
    diag = {"kind": "some_future_check", "step_id": "x"}
    r = mcp_server.suggest_fix_for_diagnostic(diag)
    assert r["ok"] is False
    assert "some_future_check" in r["reason"]
