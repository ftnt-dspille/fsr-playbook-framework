"""Does the free lane predict the paid one? (B3, row 11)

The whole testing strategy rests on one unmeasured assumption: that screening
a change on the free, offline lane tells you what the paid lane on a live box
would have said. Until this module there was no number for it -- only the
habit of trusting the cheap run.

An agreement report is deliberately NOT a delta. `delta_vs` refuses to diff
two runs whose substrates disagree, because a cell that moved may have moved
because the world did. Here the worlds are SUPPOSED to disagree -- that is the
comparison. So the comparability contract is inverted:

  * the two runs must name DIFFERENT lanes (two screen runs measure
    repeatability, not agreement, and calling that 100% would be a lie),
  * they must cover the SAME tasks, and
  * they must have been scored by the SAME `scorer_version` -- otherwise the
    verdicts differ because the ruler changed.

Anything else is refused with the field that differs, in the same spirit as
the differ: a number nobody can read is worse than no number.

What comes out is per-task: did each lane's verdict agree? The disagreements
are the only tasks that ever need a paid run again. Everything else is
screened free forever, and re-running this whenever either model changes is
the only honest justification for spending tokens on the paid lane at all.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.harness import RUNS_DIR, _new_run_id
from evals.scoring import SCORER_VERSION

#: A repeat run's archive filename. Kept beside `matrix.json` rather than in
#: it: a screen is N matrices plus the verdict rule applied across them, and
#: flattening it into one matrix would lose the per-repeat spread that is the
#: entire reason for repeating.
SCREEN_FILE = "screen.json"


class AgreementError(ValueError):
    """Two runs that cannot honestly be compared, with the reason."""


def save_screen(screen: dict[str, Any], run_id: str | None = None) -> Path:
    """Archive a `--repeat N` run so it can be compared later.

    Before this, `--repeat` returned a verdict to the terminal and dropped
    everything -- `--save` was silently ignored on that path, so the one kind
    of run whose result is trustworthy enough to publish was the one kind that
    could not be. An agreement report needs both sides on disk, so this is a
    prerequisite for row 11 rather than a convenience.
    """
    run_id = run_id or _new_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # The comparability key rides on the screen itself, lifted from the first
    # underlying matrix -- every repeat ran the same way by construction.
    first = (screen.get("runs") or [{}])[0]
    payload = {
        **{k: v for k, v in screen.items() if k != "runs"},
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "lane": first.get("lane", "adhoc"),
        "offline": first.get("offline"),
        "tool_substrate": first.get("tool_substrate"),
        "record_substrate": first.get("record_substrate"),
        "scorer_version": first.get("scorer_version", SCORER_VERSION),
        # The per-repeat matrices, kept whole: a disagreement is usually read
        # by going back to the traces behind it.
        "runs": screen.get("runs") or [],
    }
    (run_dir / SCREEN_FILE).write_text(json.dumps(payload, indent=2, default=str))
    return run_dir


def load_screen(run_id: str) -> dict[str, Any]:
    p = RUNS_DIR / run_id / SCREEN_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"no screen run {run_id!r} at {p}. Only `--repeat N` runs archive "
            f"a screen; a single run archives matrix.json instead."
        )
    return json.loads(p.read_text())


def list_screens() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted(p.name for p in RUNS_DIR.iterdir()
                  if (p / SCREEN_FILE).exists())


def task_verdict(cell: dict[str, Any]) -> str:
    """One task's verdict from its repeat spread.

    `pass` / `fail` are MAJORITY verdicts, not unanimity: agreement asks what
    each lane would have told you, and what a lane tells you on a flaky task
    is whichever way it fell most often. The spread is not thrown away --
    `mixed` is reported separately below so a 2/3 never quietly counts as a
    clean pass.

    A cell whose provider raised on every repeat is `error`, never `fail`: a
    dead gateway agreeing with a dead box is not agreement (auto-memory:
    `substrate_failure_scored_as_behavior`).
    """
    of = int(cell.get("of") or 0)
    if not of:
        return "error"
    if int(cell.get("errors") or 0) == of:
        return "error"
    passes = int(cell.get("passes") or 0)
    return "pass" if passes * 2 > of else "fail"


def _cells(screen: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-task cells, collapsed across models.

    A lane names ONE model, so its screen has one model column; collapsing is
    a no-op for a lane run and a refusal for anything else -- comparing a
    two-model screen against a one-model one would silently pick a column.
    """
    models = list(screen.get("models") or [])
    if len(models) != 1:
        raise AgreementError(
            f"run {screen.get('run_id','?')!r} screened {len(models)} models "
            f"({', '.join(models) or 'none'}). Agreement is between two LANES, "
            f"each of which names exactly one model."
        )
    return dict(screen["cells"][models[0]])


def agree(screen: dict[str, Any], confirm: dict[str, Any]) -> dict[str, Any]:
    """Per-task agreement between a screen run and a confirm run.

    Raises `AgreementError` rather than returning a number nobody can read.
    """
    for side, run in (("screen", screen), ("confirm", confirm)):
        if not run.get("cells"):
            raise AgreementError(f"the {side} run has no screened cells")
    a_lane = screen.get("lane", "adhoc")
    b_lane = confirm.get("lane", "adhoc")
    if a_lane == b_lane:
        raise AgreementError(
            f"both runs are lane {a_lane!r}. Two runs of the SAME lane measure "
            f"repeatability, not agreement -- publishing that as an agreement "
            f"number would overstate exactly the thing being tested."
        )
    if "adhoc" in (a_lane, b_lane):
        raise AgreementError(
            f"an unlabeled run cannot be shown to be a lane "
            f"(screen={a_lane!r}, confirm={b_lane!r}). Run it through "
            f"`make matrix LANE=…` so the lane is stamped in."
        )
    a_sv, b_sv = screen.get("scorer_version"), confirm.get("scorer_version")
    if a_sv != b_sv or a_sv is None:
        raise AgreementError(
            f"scorer_version differs ({a_sv} vs {b_sv}): the verdicts would "
            f"disagree because the RULER changed, not because the lanes did."
        )
    a_cells, b_cells = _cells(screen), _cells(confirm)
    only_a = sorted(set(a_cells) - set(b_cells))
    only_b = sorted(set(b_cells) - set(a_cells))
    if only_a or only_b:
        raise AgreementError(
            "the two runs did not cover the same tasks; agreement over an "
            "intersection would be a different (and flattering) number. "
            f"screen-only: {only_a or '-'}  confirm-only: {only_b or '-'}"
        )

    tasks = []
    for name in sorted(a_cells):
        a, b = a_cells[name], b_cells[name]
        av, bv = task_verdict(a), task_verdict(b)
        tasks.append({
            "task": name,
            "screen": av, "confirm": bv,
            "screen_rate": f"{a.get('passes', 0)}/{a.get('of', 0)}",
            "confirm_rate": f"{b.get('passes', 0)}/{b.get('of', 0)}",
            # An `error` on either side is unscoreable, not a disagreement.
            "status": ("unscoreable" if "error" in (av, bv)
                       else "agree" if av == bv else "DISAGREE"),
            # Flagged even when the verdicts agree: a task both lanes only
            # sometimes pass agrees today by coin flip.
            "flaky": (0 < int(a.get("passes", 0)) < int(a.get("of", 0))
                      or 0 < int(b.get("passes", 0)) < int(b.get("of", 0))),
        })
    scored = [t for t in tasks if t["status"] != "unscoreable"]
    agreed = [t for t in scored if t["status"] == "agree"]
    return {
        "screen_run": screen.get("run_id"),
        "confirm_run": confirm.get("run_id"),
        "screen_lane": a_lane, "confirm_lane": b_lane,
        "scorer_version": a_sv,
        "repeats": {"screen": screen.get("repeats"),
                    "confirm": confirm.get("repeats")},
        "tasks": tasks,
        "scored": len(scored),
        "agreed": len(agreed),
        "unscoreable": len(tasks) - len(scored),
        # None, not 0.0, when nothing was scoreable -- a 0% agreement number
        # for a run that never scored anything is the same lie as a green gate
        # over an empty slice.
        "agreement": (len(agreed) / len(scored)) if scored else None,
        "disagreements": [t["task"] for t in scored if t["status"] == "DISAGREE"],
    }


def render_agreement(rep: dict[str, Any]) -> str:
    lines = [
        f"Lane agreement -- {rep['screen_lane']} {rep['screen_run']} vs "
        f"{rep['confirm_lane']} {rep['confirm_run']}",
        f"  scorer {rep['scorer_version']}   repeats "
        f"screen={rep['repeats']['screen']} confirm={rep['repeats']['confirm']}",
        "",
    ]
    width = max([len(t["task"]) for t in rep["tasks"]] + [8])
    header = (f"{'fixture':<{width}}  {'screen':>10}  {'confirm':>10}  status")
    lines += [header, "-" * len(header)]
    for t in rep["tasks"]:
        flag = " ~flaky" if t["flaky"] else ""
        lines.append(
            f"{t['task']:<{width}}  "
            f"{t['screen'] + ' ' + t['screen_rate']:>10}  "
            f"{t['confirm'] + ' ' + t['confirm_rate']:>10}  "
            f"{t['status']}{flag}")
    lines.append("")
    if rep["agreement"] is None:
        lines += [
            "NO AGREEMENT NUMBER -- nothing was scoreable on both lanes.",
            "An unscoreable cell is a dead provider or a dead box, not a",
            "verdict; fix the substrate before reading anything here.",
        ]
        return "\n".join(lines)
    lines.append(f"Agreement: {rep['agreed']}/{rep['scored']} "
                 f"({rep['agreement']:.0%})"
                 + (f"   unscoreable: {rep['unscoreable']}"
                    if rep["unscoreable"] else ""))
    if rep["disagreements"]:
        lines += [
            "",
            "These are the only tasks that ever need a paid run again:",
        ]
        lines += [f"  {t}" for t in rep["disagreements"]]
    else:
        lines += ["", "No disagreements: the free lane predicted the paid one "
                      "on every scoreable task."]
    return "\n".join(lines)
