"""A3 guard — every *gating* key emitted by `scoring.score(...)` must resolve
to a real prompt lever (Chat Intelligence Plan, Track A3).

`calibrate_investigation` and `chat_drive` annotate each failing, counted gate
with `levers.lever_for(key)` so a red eval points at the exact prompt section to
edit. If a new gate lands without a lever, the verdict prints
"unmapped — inspect trace". This test drives `score()` across the modes the
tuning loop uses, harvests every key that counts toward the pass/fail aggregate
(not skipped, not informational), and fails loudly if any has no mapped lever.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT / "tooling", REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evals import scoring  # noqa: E402
from evals.levers import LEVER_MAP, lever_for  # noqa: E402

_FALLBACK = lever_for("__definitely_not_a_real_gate__")

# A trace that exercises the agentic gates (consecutive run_op -> no_spiral,
# an enrichment deliverable path) plus enough variety that nothing is skipped.
_TRACE = [
    {"name": "get_record", "args": {}, "ok": True},
    {"name": "search_module_records", "args": {}, "ok": True},
    {"name": "run_op", "args": {"a": 1}, "ok": True},
    {"name": "run_op", "args": {"b": 2}, "ok": True},
    {"name": "find_containment_actions", "args": {}, "ok": True},
]


def _counted_keys(out: dict) -> set[str]:
    return {
        k for k, v in out["levels"].items()
        if not v.get("skipped") and not v.get("informational")
    }


def _harvest() -> set[str]:
    keys: set[str] = set()
    # Build mode (default): authoring tiers + agent-behavior gates.
    keys |= _counted_keys(scoring.score(
        "workflows: []", trace=_TRACE, final_text="```yaml\n```"))
    # Investigation mode: recall + investigation_* quality gates.
    keys |= _counted_keys(scoring.score(
        "workflows: []", mode="investigation", trace=_TRACE,
        required_facts=[{"any": ["x"]}], forbidden_facts=[]))
    return keys


def test_every_counted_gate_has_a_lever():
    unmapped = sorted(
        k for k in _harvest() if lever_for(k) == _FALLBACK)
    assert not unmapped, (
        f"gates with no prompt lever (add to levers.LEVER_MAP): {unmapped}")


def test_forbidden_pivot_marker_has_a_lever():
    # Synthetic marker the recall scorer raises; not a `levels` key but the
    # verdict annotates it, so it must be mapped too.
    assert lever_for("<forbidden>") != _FALLBACK


def test_lever_map_keys_are_strings():
    assert all(isinstance(k, str) and isinstance(v, str)
               for k, v in LEVER_MAP.items())
