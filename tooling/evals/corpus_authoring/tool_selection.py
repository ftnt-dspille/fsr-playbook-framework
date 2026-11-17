"""Tool-selection discipline: did the agent reach for the right tool?

A toolkit is only as good as the agent's willingness to use it. A live finding:
given a BROKEN run, the agent tends to brute-force the fix by re-compiling in a
loop and never calls debug_run -- so debug_run's diagnosis (and now its grounded
fix path) never reaches the model. This grader makes that a first-class,
repeatable metric instead of a one-off observation.

For each drive we know the SITUATION and the tool the toolkit intends for it:

  * runtime_output_dependency -- a reference renders empty at run time. debug_run
    is the one tool that can see it (it re-renders Jinja against the run's vars
    and now names the resolvable paths). The RIGHT move is to call it; compiling
    again cannot catch a silent-empty render, so a compile-only loop is a miss.

The grade is per drive and aggregated: selection rate (reached for the right
tool), brute-force rate (iterated compile/verify without the diagnostic tool),
and a histogram of every tool actually called. Pure bookkeeping over a tool list
-- no box, no model -- so the test pins it with known tool lists."""
from __future__ import annotations

from collections import Counter
from typing import Any

# situation -> the tool the toolkit intends as the right diagnostic for it.
_RIGHT_TOOL: dict[str, str] = {
    "runtime_output_dependency": "debug_run",
}
# tools that only re-check well-formedness; looping on these without the
# diagnostic tool is the brute-force pattern we want to measure.
_STATIC_LOOP = frozenset({"compile_playbook_yaml", "verify_playbook",
                          "analyze_playbook", "decompile_playbook"})


def _base(name: str) -> str:
    """Strip an MCP prefix (mcp__<server>__debug_run -> debug_run)."""
    return name.rsplit("__", 1)[-1] if name else name


def grade_tool_selection(tools: list[str] | None, situation: str) -> dict[str, Any]:
    """Score one drive's tool selection against the situation's right tool."""
    called = [_base(t) for t in (tools or [])]
    called_set = set(called)
    want = _RIGHT_TOOL.get(situation)
    selected_right = (want in called_set) if want else None
    # brute-forced: wanted a diagnostic, didn't call it, but did loop on static
    # checks -- the exact pattern where the toolkit's diagnosis never reaches it.
    brute_forced = bool(
        want and want not in called_set and (called_set & _STATIC_LOOP))
    return {
        "situation": situation,
        "expected": want,
        "called": called,
        "selected_right": selected_right,
        "brute_forced": brute_forced,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-drive grades into selection / brute-force rates and a histogram."""
    graded = [r for r in rows if r.get("selected_right") is not None]
    hist: Counter = Counter()
    for r in rows:
        hist.update(r.get("called") or [])

    def rate(pred) -> str:
        return (f"{sum(1 for r in graded if pred(r))}/{len(graded)}"
                if graded else "0/0")

    return {
        "selected_right": rate(lambda r: r["selected_right"]),
        "brute_forced": rate(lambda r: r["brute_forced"]),
        "tool_histogram": dict(hist.most_common()),
    }
