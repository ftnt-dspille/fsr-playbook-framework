"""Ladder evaluator for the chat loop.

Maps a YAML draft to three success-ladder rungs that the UI renders
each turn:

  Compiles — YAML parses + compiles clean AND every {{ vars.* }}
             reference points at a step that runs before it.
             (Static; free.)
  Runs     — Executes against live FSR without error (live prechecks
             + dry-run roll up here). Skipped offline.
  Works    — Final state matches the task's expected assertions.
             Skipped when no assertions are available.

The emitter is deliberately pure: takes YAML text, returns the rungs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .provider import LadderEvent, LadderRung


_REPO = Path(__file__).resolve().parents[2]
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
        from fsr_core.compiler import compile_yaml as _cy  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return LadderEvent(
            rungs=[
                LadderRung(
                    id="compiles", label="Compiles",
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

    # Compiles — YAML compiles cleanly AND no variable-reachability
    # diagnostics. Reachability piggybacks here since it's the other
    # purely-static check; lumping them keeps the rung honest ("this
    # would import cleanly and the data flow is sound").
    has_reach_err = _has_var_reachability(res.errors)
    if res.ok and not has_reach_err:
        compiles = LadderRung(
            id="compiles", label="Compiles", state="passed",
            summary="compiles clean, vars reachable" + (
                f" · {warn_count} warning{'s' if warn_count != 1 else ''}"
                if warn_count else ""
            ),
        )
        achieved = 1
    else:
        if has_reach_err:
            summary = "references a step that can't run first"
        else:
            first = blocking[0] if blocking else None
            summary = (
                f"{err_count} error{'s' if err_count != 1 else ''}"
                + (f" · {first.code.value if hasattr(first.code, 'value') else first.code}"
                   if first else "")
            )
        compiles = LadderRung(
            id="compiles", label="Compiles", state="failed",
            summary=summary,
        )
        achieved = 0

    # Runs — live execution (prechecks + dry-run). Skipped offline.
    runs = LadderRung(
        id="runs", label="Runs", state="skipped",
        summary="needs live FSR",
    )

    # Works — assertions match. Live-only and only meaningful when the
    # task carries expected outcomes.
    works = LadderRung(
        id="works", label="Works", state="skipped",
        summary="needs assertions",
    )

    return LadderEvent(
        rungs=[compiles, runs, works],
        error_count=err_count,
        warning_count=warn_count,
        achieved=achieved,
    )
