"""Offline regression pin for the committed investigation golden traces.

`python/evals/golden_traces/*.json` are tool-call traces banked from a *live*,
known-good agent run (by `calibrate_investigation.py --capture` or
`chat_drive.py --capture-fixture`). They encode "this is what a good
investigation of fixture X looked like".

This test replays each FROZEN golden trace through the same scoring gates the
live calibration applies (`scoring._score_investigation` +
`_score_investigation_quality`) and asserts it still clears its fixture's
contract — recall ≥ gate, no forbidden pivot, every non-skipped quality gate
green.

SCOPE (deliberate, per Chat Intelligence Plan A4/A6 fast-vs-live split): this is
the FAST/STRUCTURE guard. It reddens when an edit to a fixture's
`required_facts`/`forbidden_facts`, or to the recall/forbidden scoring, breaks a
case that used to pass — i.e. it pins the *durable investigation contract*. It
does NOT re-drive the agent, so a *prompt* regression is caught by the live
`calibrate_investigation.py --baseline` capability gate, not here. Green here
means "the contract is intact", not "the prompts are fine".

What it hard-pins vs. warns on:
  * HARD FAIL — recall ≥ gate and zero forbidden pivots. These are invariants of
    a *good* investigation: the required pivots stay reachable, the off-limits
    ones stay off-limits. A fixture/scoring edit that breaks either is a real
    regression.
  * WARN ONLY — the quality gates (tool budget, param-flail, deliverable). On a
    FROZEN trace these are constants (the call count never changes), so pinning a
    historical capture to a later-tightened budget would redden CI for reasons
    unrelated to the trace. A drift here means the golden is STALE relative to
    today's quality bar and should be re-captured live (`calibrate … --capture`
    or `chat-drive … --capture-fixture`); it's surfaced loudly but not failed.
"""
from __future__ import annotations

import importlib
import json
import warnings
from pathlib import Path

import pytest

scoring = importlib.import_module("evals.scoring")
tasks_mod = importlib.import_module("evals.tasks")

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "evals" / "golden_traces"

# Baseline set committed today. Deleting/renaming a golden without intent should
# redden this test rather than silently shrink coverage.
_EXPECTED_MIN_GOLDENS = 5


def _golden_files() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*.json"))


def _tasks_by_name() -> dict:
    return {t.name: t for t in tasks_mod.load_tasks()}


def test_golden_dir_has_expected_baseline():
    files = _golden_files()
    assert len(files) >= _EXPECTED_MIN_GOLDENS, (
        f"expected ≥{_EXPECTED_MIN_GOLDENS} golden traces in {GOLDEN_DIR}, "
        f"found {len(files)}: {[f.name for f in files]}"
    )


@pytest.mark.parametrize("golden_path", _golden_files(),
                         ids=lambda p: p.stem)
def test_golden_trace_still_clears_its_fixture(golden_path: Path):
    golden = json.loads(golden_path.read_text())
    fixture_name = golden["fixture"]
    trace = golden["trace"]

    # 1) Every golden must map to a live task fixture (no orphans).
    task = _tasks_by_name().get(fixture_name)
    assert task is not None, (
        f"golden {golden_path.name} references unknown fixture {fixture_name!r} "
        "— add the fixture under python/evals/tasks/ or remove the golden"
    )
    assert task.mode == "investigation", (
        f"{fixture_name}: golden pin only applies to investigation fixtures"
    )

    # 2) Recall gate + no forbidden pivot, replayed over the frozen trace.
    rec = scoring._score_investigation(
        trace, task.required_facts, task.forbidden_facts)
    assert not rec["forbidden_hit"], (
        f"{fixture_name}: frozen golden now trips forbidden pivot(s) "
        f"{rec['forbidden_hit']} — fixture/scoring edit broke a known-good case"
    )
    assert rec["passed"], (
        f"{fixture_name}: frozen golden no longer clears recall "
        f"({rec['detail']}; missing={rec['missing']})"
    )

    # 3) Quality gates (budget / flail / deliverable) — WARN, don't fail. On a
    #    frozen trace these are constants; a miss means the golden is stale vs.
    #    today's quality bar and wants a live re-capture, not a red offline CI.
    quality = scoring._score_investigation_quality(
        trace, task.investigation_quality)
    drift = {k: v.get("detail") for k, v in quality.items()
             if not v.get("skipped") and not v.get("passed")}
    if drift:
        warnings.warn(
            f"STALE GOLDEN {fixture_name}: recall intact but quality drift "
            f"{drift} — re-capture live (calibrate --capture / "
            f"chat-drive --capture-fixture) to refresh the bar",
            stacklevel=2,
        )
