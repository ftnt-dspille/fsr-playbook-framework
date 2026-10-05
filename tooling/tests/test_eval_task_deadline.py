"""A task over its wall-clock budget is recorded and abandoned, not waited on.

A Frank baseline hung after task 34/49 and was killed at the 2h tool limit with
nothing saved. The HTTP timeout bounds one request, not a task.
"""
from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from evals import harness  # noqa: E402
from evals.providers import TaskCancelled, _check_cancel  # noqa: E402


def test_a_task_in_budget_returns_its_value():
    assert harness._call_with_deadline(lambda: {"text": "ok"}, 5) == {"text": "ok"}


def test_a_task_error_is_raised_in_the_caller():
    def boom():
        raise ValueError("provider broke")
    with pytest.raises(ValueError, match="provider broke"):
        harness._call_with_deadline(boom, 5)


def test_an_overrun_times_out_and_the_abandoned_loop_stops():
    stopped = threading.Event()

    def looping_agent():
        try:
            while True:            # an agentic loop: checks between tool calls
                _check_cancel()
                time.sleep(0.01)
        except TaskCancelled:
            stopped.set()
            raise

    t0 = time.time()
    with pytest.raises(harness.TaskTimeout):
        harness._call_with_deadline(looping_agent, 0.2)
    assert time.time() - t0 < 2
    # The thread cannot be killed; it must notice the cancel and stop, or it
    # keeps dispatching into the next task's audit log.
    assert stopped.wait(2)


def test_cancel_is_per_task():
    """A fresh task is not cancelled by an earlier task's timeout."""
    with pytest.raises(harness.TaskTimeout):
        harness._call_with_deadline(lambda: time.sleep(0.5), 0.05)

    def checks():
        _check_cancel()
        return "ran"
    assert harness._call_with_deadline(checks, 5) == "ran"


def test_timeout_row_reads_timeout_not_err(capsys):
    harness._progress("m", 1, 1, "t", {"error": "x", "timeout": True,
                                       "score": 0, "max": 0})
    assert "TIMEOUT" in capsys.readouterr().err
