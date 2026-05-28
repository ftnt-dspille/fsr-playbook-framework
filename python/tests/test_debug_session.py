"""Stateful debug-session tools (VISUAL_EDITOR_PLAN.md Phase 5.3-5.7).

Covers: step-by-step advance, continue-until-breakpoint,
continue-until-step-id, branch_choice override mid-run,
stop cleanup, unknown-session error, expiry eviction.
"""
from __future__ import annotations

import textwrap
import time

import pytest

pytest.importorskip("mcp.server.fastmcp",
                    reason="mcp package not installed")

import mcp_server  # noqa: E402
import mcp_server._shared  # noqa: E402, F401
from mcp_server import debug_session as _ds  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_fsr(monkeypatch):
    monkeypatch.setattr(mcp_server._shared, "_live_client", lambda: None)


@pytest.fixture(autouse=True)
def _clean_store():
    # Reset the singleton between tests to keep them independent.
    _ds._STORE._sessions.clear()  # noqa: SLF001
    yield
    _ds._STORE._sessions.clear()  # noqa: SLF001


def _linear_yaml() -> str:
    return textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: a
              - id: a
                type: set_variable
                name: A
                arguments:
                  arg_list:
                    - name: x
                      value: 1
                next: b
              - id: b
                type: set_variable
                name: B
                arguments:
                  arg_list:
                    - name: y
                      value: 2
                next: c
              - id: c
                type: set_variable
                name: C
                arguments:
                  arg_list:
                    - name: z
                      value: 3
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)


def test_start_returns_session_paused_at_start():
    r = mcp_server.start_debug_session(_linear_yaml())
    assert r["ok"] is True
    s = r["status"]
    assert s["session_id"]
    assert s["paused_at"] == "t"
    assert s["done"] is False
    assert s["trace_len"] == 0


def test_step_advances_one_at_a_time():
    sid = mcp_server.start_debug_session(_linear_yaml())["status"]["session_id"]
    r1 = mcp_server.step_debug_session(sid)
    assert r1["status"]["paused_at"] == "a"
    assert r1["status"]["last_step"]["step_id"] == "t"
    r2 = mcp_server.step_debug_session(sid)
    assert r2["status"]["paused_at"] == "b"
    assert r2["status"]["last_step"]["step_id"] == "a"


def test_continue_runs_to_done():
    sid = mcp_server.start_debug_session(_linear_yaml())["status"]["session_id"]
    r = mcp_server.continue_debug_session(sid)
    assert r["status"]["done"] is True
    assert r["stop_reason"] == "done"
    assert r["status"]["trace_len"] >= 4  # t, a, b, c (stop is terminal)


def test_continue_stops_at_breakpoint():
    sid = mcp_server.start_debug_session(
        _linear_yaml(), breakpoints=["b"])["status"]["session_id"]
    r = mcp_server.continue_debug_session(sid)
    assert r["stop_reason"] == "breakpoint"
    assert r["status"]["paused_at"] == "b"
    # Breakpoint pauses BEFORE the bp step runs.
    assert r["status"]["last_step"]["step_id"] == "a"


def test_continue_until_step_id():
    sid = mcp_server.start_debug_session(
        _linear_yaml())["status"]["session_id"]
    r = mcp_server.continue_debug_session(sid, until_step_id="c")
    assert r["stop_reason"] == "until_step"
    assert r["status"]["paused_at"] == "c"


def test_add_breakpoints_merges_into_session():
    sid = mcp_server.start_debug_session(
        _linear_yaml())["status"]["session_id"]
    r = mcp_server.continue_debug_session(
        sid, add_breakpoints=["b", "c"])
    assert r["stop_reason"] == "breakpoint"
    # 'b' hits first since it comes earlier on the path.
    assert r["status"]["paused_at"] == "b"
    assert set(r["status"]["breakpoints"]) == {"b", "c"}


def test_stop_releases_session():
    sid = mcp_server.start_debug_session(
        _linear_yaml())["status"]["session_id"]
    stop = mcp_server.stop_debug_session(sid)
    assert stop["ok"] is True
    # Trace is captured in the stop response even after drop.
    assert "trace" in stop["status"]
    # Second stop on the same id errors cleanly.
    again = mcp_server.stop_debug_session(sid)
    assert again["ok"] is False


def test_get_returns_full_trace_and_vars_keys():
    sid = mcp_server.start_debug_session(
        _linear_yaml())["status"]["session_id"]
    mcp_server.continue_debug_session(sid, until_step_id="c")
    r = mcp_server.get_debug_session(sid)
    assert r["ok"] is True
    assert "trace" in r["status"]
    assert "A" in r["status"]["vars_keys"]
    assert "B" in r["status"]["vars_keys"]


def test_unknown_session_errors_cleanly():
    for fn in (mcp_server.step_debug_session,
               mcp_server.continue_debug_session,
               mcp_server.stop_debug_session,
               mcp_server.get_debug_session):
        r = fn("not-a-real-id")
        assert r["ok"] is False
        assert "unknown session" in r["error"]


def test_branch_choice_override_per_step():
    yaml = textwrap.dedent("""\
        playbooks:
          - name: P
            steps:
              - id: t
                type: start
                name: T
                next: d
              - id: d
                type: decision
                name: D
                arguments:
                  conditions:
                    - display: "A"
                      when: "false"
                      next: a_branch
                    - display: "B"
                      default: true
                      next: b_branch
                branches:
                  A: a_branch
                  B: b_branch
              - id: a_branch
                type: set_variable
                name: ABranch
                arguments:
                  arg_list:
                    - name: which
                      value: a
                next: stop
              - id: b_branch
                type: set_variable
                name: BBranch
                arguments:
                  arg_list:
                    - name: which
                      value: b
                next: stop
              - id: stop
                type: stop
                name: Stop
        """)
    sid = mcp_server.start_debug_session(yaml)["status"]["session_id"]
    # Walk to the decision step.
    mcp_server.step_debug_session(sid)  # start (t) → now at d
    # Override the branch to force the A path even though `when` is false.
    r = mcp_server.step_debug_session(
        sid, branch_choice_override={"d": "A"})
    assert r["status"]["paused_at"] == "a_branch"


def test_session_expiry_evicts():
    store = _ds.SessionStore(ttl_seconds=0.0)
    sess, err = _ds.build_session(yaml_text=_linear_yaml())
    assert sess is not None and err is None
    sess.session_id = "test-id"
    store._sessions[sess.session_id] = sess  # noqa: SLF001
    time.sleep(0.01)
    assert store.get("test-id") is None
    assert len(store) == 0


def test_step_through_playbook_unchanged_after_refactor():
    """Regression guard: the one-shot tool must still return the same
    shape since analyzer / verify_playbook depend on it."""
    r = mcp_server.step_through_playbook(_linear_yaml())
    assert r["ok"] is True
    assert len(r["trace"]) >= 4
    assert r["trace"][0]["step_id"] == "t"
