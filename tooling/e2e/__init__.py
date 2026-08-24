"""End-to-end test harness: compile → push → trigger → poll → assert → cleanup."""

from .runner import RunResult, run_test  # noqa: F401
