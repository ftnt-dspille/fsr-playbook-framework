"""Ladder evaluator for the chat loop.

Maps a YAML draft to the five L1→L5 success-ladder rungs that the eval
harness uses (`evals/scoring.py`). The chat route emits one
``LadderEvent`` per turn so the UI can render progress live.

Live-FSR rungs (L2 prechecks, L4 dry-run, L5 outcome assertion) are
expensive — they can be added later behind a flag. For now we score
what's free:

  L1 compile        — `compile_yaml(text).ok` excluding warnings
  L2 prechecks      — skipped offline (placeholder)
  L3 reachability   — checks compile errors for the var-reachability
                      phrasing that scoring.py already uses as a gate
  L4 dry_run        — skipped offline
  L5 outcome        — skipped offline

The emitter is deliberately pure: takes YAML text, returns the rungs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .provider import LadderEvent, LadderRung


_REPO = Path(__file__).resolve().parents[3]
_DB = _REPO / "store" / "fsr_reference.db"


def _has_var_reachability(errs: list[Any]) -> bool:
    for e in errs:
        msg = (getattr(e, "message", "") or "").lower()
        if "no step with jinja-key" in msg or "cannot run before" in msg:
            return True
    return False


def evaluate(yaml_text: str) -> LadderEvent:
    """Run a fast offline scoring pass against the current YAML."""
    try:
        from compiler import compile_yaml as _cy  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return LadderEvent(
            rungs=[
                LadderRung(
                    id="compile", label="Compile",
                    state="failed",
                    summary=f"compiler unavailable: {exc}"
                )
            ],
            error_count=1,
            warning_count=0,
            achieved=0,
        )

    res = _cy(yaml_text, _DB)
    blocking = [e for e in res.errors if getattr(e, "severity", "error") != "warning"]
    warnings = [e for e in res.errors if getattr(e, "severity", "") == "warning"]
    err_count = len(blocking)
    warn_count = len(warnings)

    # L1 — compile
    if res.ok:
        l1 = LadderRung(
            id="compile", label="Compile", state="passed",
            summary="Compiles clean" + (
                f" · {warn_count} warning{'s' if warn_count != 1 else ''}"
                if warn_count else ""
            ),
        )
        achieved = 1
    else:
        first = blocking[0] if blocking else None
        l1 = LadderRung(
            id="compile", label="Compile", state="failed",
            summary=(
                f"{err_count} error{'s' if err_count != 1 else ''}"
                + (f" · {first.code.value if hasattr(first.code, 'value') else first.code}"
                   if first else "")
            ),
        )
        achieved = 0

    # L2 — live prechecks (offline = skipped). Placeholder so the rung
    # renders; flip to a real check once the chat route knows the FSR
    # is reachable.
    l2 = LadderRung(
        id="prechecks", label="Prechecks", state="skipped",
        summary="needs live FSR",
    )

    # L3 — variable reachability. Counts as failed only when there's a
    # specific reachability-class diagnostic; a generic compile failure
    # leaves L3 pending so the UI doesn't double-flag.
    if _has_var_reachability(res.errors):
        l3 = LadderRung(
            id="reachability", label="Reachability",
            state="failed",
            summary="references a step that can't run first",
        )
    elif res.ok:
        l3 = LadderRung(
            id="reachability", label="Reachability",
            state="passed", summary="all jinja paths reachable",
        )
        achieved = 3
    else:
        l3 = LadderRung(
            id="reachability", label="Reachability",
            state="pending", summary="blocked by L1",
        )

    # L4, L5 — live-only.
    l4 = LadderRung(
        id="dry_run", label="Dry run", state="skipped",
        summary="needs live FSR",
    )
    l5 = LadderRung(
        id="outcome", label="Outcome", state="skipped",
        summary="needs assertions",
    )

    return LadderEvent(
        rungs=[l1, l2, l3, l4, l5],
        error_count=err_count,
        warning_count=warn_count,
        achieved=achieved,
    )
