"""Guard-fire records for the NOC verdict checks (mcp_server/_noc_scaffold.py).

The checks run inside the verdict tool, outside the loop; their firings are
recorded here so each name stays a registered literal (guard_fires.MECHANISMS).
"""
from __future__ import annotations

from typing import Any

from .guard_fires import record_guard_fire


def record_review(rev: Any) -> None:
    """Record what a ``VerdictReview`` decided."""
    refusal = rev.refusal[0] if rev.refusal else ""
    if refusal == "diff_not_read":
        record_guard_fire("noc.diff_not_read")
    if refusal == "benign_over_blackhole":
        record_guard_fire("noc.benign_over_blackhole")
    if "noc.benign_capped" in rev.fired:
        record_guard_fire("noc.benign_capped")
    if "noc.install_task_attached" in rev.fired:
        record_guard_fire("noc.install_task_attached")
