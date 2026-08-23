"""Two runs are diffable only if they measured the same thing.

The harness has recorded `tool_substrate` / `record_substrate` / `offline`
since the registry seam landed, and `_substrate_delta` compared them -- but
`render_delta` printed the cell table anyway, under a banner. That does not
work: the eye goes to the grid, and "not comparable" has never stopped anyone
reading a red cell as a regression. Five separate times a dead box or gateway
was recorded as agent regression.

Two changes, both asserted here:

  1. `scorer_version` joins the comparability key. A scorer change moves every
     cell without the agent doing anything -- and that is not hypothetical:
     the pinned pre-#127 tool-gate baseline was scored on
     `terminal_tool_reached` alone and gives every row 1.0, so any honest
     composite-scored run diffs as a wall of regressions.
  2. the differ WITHHOLDS the table when the key does not match, instead of
     captioning it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.harness import _substrate_delta, delta_vs, render_delta  # noqa: E402
from evals.scoring import SCORER_VERSION  # noqa: E402


def _run(**over):
    base = {
        "run_id": "20260101T000000Z",
        "offline": True,
        "tool_substrate": "framework+connector",
        "record_substrate": "soc_invest_surface",
        "scorer_version": SCORER_VERSION,
        # The lane names provider+model+substrate in one word (evals/
        # lanes.py) and joins the key too -- see test_eval_lanes.py.
        "lane": "screen",
        "tasks": ["select_run_playbook"],
        "models": ["agentic_frank"],
        "rows": [{"model": "agentic_frank", "task": "select_run_playbook",
                  "fraction": 1.0}],
        "summary": {"agentic_frank": {"score": 1.0}},
    }
    base.update(over)
    return base


def test_identical_substrate_is_comparable() -> None:
    d = _substrate_delta(_run(), _run(run_id="b"))
    assert d["comparable"] is True


def test_scorer_version_change_breaks_comparability() -> None:
    """THE known case: the pinned baseline predates the composite score."""
    d = _substrate_delta(_run(scorer_version=1), _run(scorer_version=2))
    assert d["comparable"] is False
    moved = [f for f in d["fields"] if not f["match"]]
    assert [f["field"] for f in moved] == ["scorer_version"]


def test_missing_scorer_version_is_a_mismatch_not_a_pass() -> None:
    """An unstamped run -- every baseline saved before this change -- is
    exactly the case that cannot be shown comparable, so it must not pass."""
    prior = _run()
    del prior["scorer_version"]
    assert _substrate_delta(prior, _run())["comparable"] is False


def test_substrate_change_still_breaks_comparability() -> None:
    assert _substrate_delta(_run(), _run(offline=False))["comparable"] is False
    assert _substrate_delta(
        _run(), _run(record_substrate="empty"))["comparable"] is False


def test_incomparable_diff_withholds_the_table() -> None:
    """The cells must NOT be rendered -- a captioned grid still gets read."""
    d = delta_vs(_run(scorer_version=1), _run(scorer_version=2))
    out = render_delta(d)
    assert "NOT COMPARABLE" in out
    assert "refusing to diff" in out
    # the per-cell table and its headers are gone
    assert "before" not in out and "after" not in out
    assert "select_run_playbook" not in out
    # ...but it says how to fix it
    assert "re-baseline" in out.lower()


def test_comparable_diff_still_renders_the_table() -> None:
    """The refusal must not swallow the normal path."""
    prior = _run()
    prior["rows"] = [{"model": "agentic_frank",
                      "task": "select_run_playbook", "fraction": 0.5}]
    prior["summary"] = {"agentic_frank": {"score": 0.5}}
    out = render_delta(delta_vs(prior, _run()))
    assert "NOT COMPARABLE" not in out
    assert "select_run_playbook" in out
    assert "improved" in out
