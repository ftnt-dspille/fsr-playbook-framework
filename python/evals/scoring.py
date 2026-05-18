"""Score a candidate playbook YAML on three confidence tiers + an
example-match check + agent-behavior gates.

Confidence tiers (what a human means by "is this playbook good?"):

  draft        — YAML parses + compiles to FSR JSON. "It would import
                 without an error." Says nothing about whether it works.
  verified     — Statically sound: references resolve, branches
                 reachable, connectors/ops exist, picklists valid.
                 Equivalent to `verify_playbook.ready_to_push=True`.
                 "I would ship this without testing it manually."
  live_tested  — Actually executes on a real FSR (dry-run passes).
                 Strongest signal short of pushing. Skipped offline.

Orthogonal:

  matches_example — byte-equal compile output to the hand-curated
                    reference YAML in /examples/. Only meaningful for
                    tasks that have a reference; says nothing about
                    novel playbooks.

Agent-behavior gates (apply only when a tool-use `trace` is supplied):

  verify_called_before_submit
  verify_iterations_until_ready   (record only — not pass/fail)
  final_verify_ready_to_push
  tool_budget
  no_spiral
  adherence                       (final text included a YAML block)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

_YAML_BLOCK_RE = re.compile(r"```ya?ml\s*\n", re.IGNORECASE)


def _verify(yaml_text: str, *, live: bool) -> dict[str, Any]:
    from mcp_server import verify_playbook
    return verify_playbook(yaml_text=yaml_text, live_probe=live)


def _compile_obj(yaml_text: str) -> dict[str, Any]:
    from mcp_server import compile_yaml
    return compile_yaml(yaml_text, verbose=True)


_VOLATILE_KEYS = frozenset({"lastModifyDate"})


def _strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


# Agentic gate thresholds. Sourced from docs/AGENT_TOOL_USAGE.md p95s —
# raise via env if a model is intentionally chatty.
TOOL_BUDGET_MAX = int(os.environ.get("EVAL_TOOL_BUDGET_MAX", "20"))
NO_SPIRAL_MAX_CONSECUTIVE = int(
    os.environ.get("EVAL_NO_SPIRAL_MAX_CONSECUTIVE", "4"))


def _verify_metrics(trace: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Three metrics about the agent's use of `verify_playbook` from
    the call trace. Distinct from the `verified` confidence tier —
    these measure agent *behavior*, not playbook quality. The agent
    can technically ship a YAML it never ran through verify; this gate
    catches that."""
    verifies = [t for t in trace if t.get("name") == "verify_playbook"]
    called = len(verifies) >= 1
    last_ready = bool(verifies[-1].get("verify", {}).get("ready_to_push")) if verifies else False
    iters = len(verifies)
    for i, v in enumerate(verifies, start=1):
        if v.get("verify", {}).get("ready_to_push"):
            iters = i
            break
    return {
        "verify_called_before_submit": {
            "passed": called, "skipped": False,
            "detail": (f"{len(verifies)} verify_playbook call(s)" if called
                       else "agent never called verify_playbook"),
        },
        "verify_iterations_until_ready": {
            "passed": called, "skipped": False,
            "iterations": iters if called else 0,
            "detail": (f"{iters} verify cycle(s) until ready"
                       if called and last_ready
                       else "never reached ready_to_push=True"
                       if called else "no verify calls"),
        },
        "final_verify_ready_to_push": {
            "passed": last_ready, "skipped": False,
            "detail": ("last verify returned ready_to_push=True" if last_ready
                       else "last verify did NOT return ready_to_push=True"),
        },
    }


def _score_agentic(*, trace: list[dict[str, Any]],
                   text: str) -> dict[str, dict[str, Any]]:
    """tool_budget / no_spiral / adherence + verify-behavior metrics."""
    n = len(trace)
    longest = 0
    cur_name = None
    cur_run = 0
    longest_name = ""
    for call in trace:
        name = call.get("name", "")
        if name == cur_name:
            cur_run += 1
        else:
            cur_name = name
            cur_run = 1
        if cur_run > longest:
            longest = cur_run
            longest_name = name

    has_yaml = bool(_YAML_BLOCK_RE.search(text or ""))
    return {
        **_verify_metrics(trace),
        "tool_budget": {
            "passed": n <= TOOL_BUDGET_MAX, "skipped": False,
            "calls": n, "limit": TOOL_BUDGET_MAX,
        },
        "no_spiral": {
            "passed": longest <= NO_SPIRAL_MAX_CONSECUTIVE, "skipped": False,
            "longest_run": longest, "tool": longest_name,
            "limit": NO_SPIRAL_MAX_CONSECUTIVE,
        },
        "adherence": {
            "passed": has_yaml, "skipped": False,
            "detail": ("yaml block present" if has_yaml
                       else "no fenced ```yaml block in final text"),
        },
    }


def score(
    yaml_text: str,
    *,
    gold_json: dict[str, Any] | None = None,
    live: bool = False,
    dry_run_kwargs: dict[str, Any] | None = None,
    trace: list[dict[str, Any]] | None = None,
    final_text: str | None = None,
) -> dict[str, Any]:
    """Score a candidate YAML across confidence tiers + agent gates."""
    out: dict[str, Any] = {"levels": {}}

    # ----------------- confidence tier 1: draft (compile clean) ------------
    comp = _compile_obj(yaml_text)
    draft_ok = bool(comp.get("ok"))
    out["levels"]["draft"] = {
        "passed": draft_ok,
        "skipped": False,
        "detail": ("compiles" if draft_ok else "compile failed"),
        "errors": comp.get("errors", []) if not draft_ok else [],
    }

    # ----------------- confidence tier 2: verified -------------------------
    # Runs the same fan-out the agent is supposed to call: compile +
    # typed walk + per-step schema checks. live_probe follows the eval
    # mode so offline runs stay deterministic.
    verify = _verify(yaml_text, live=live)
    verified_ok = bool(verify.get("ready_to_push"))
    out["levels"]["verified"] = {
        "passed": verified_ok,
        "skipped": False,
        "required_fix_count": len(verify.get("required_fixes") or []),
        "warning_count": len(verify.get("warnings") or []),
        "detail": ("verify_playbook ready_to_push=True" if verified_ok
                   else f"{len(verify.get('required_fixes') or [])} required fix(es)"),
    }

    # ----------------- confidence tier 3: live_tested ----------------------
    if live:
        try:
            from mcp_server import dry_run_playbook  # noqa: PLC0415
            kw = dict(dry_run_kwargs or {})
            dr = dry_run_playbook(yaml_text, **kw) if kw else None
            if dr is None:
                dr = {"ok": False, "code": "no_dry_run_target",
                      "message": "dry_run_kwargs missing `playbook` name"}
            out["levels"]["live_tested"] = {
                "passed": bool(dr.get("ok")),
                "skipped": False,
                "code": dr.get("code"),
                "summary": dr.get("status") or dr.get("message"),
            }
        except Exception as exc:  # noqa: BLE001
            out["levels"]["live_tested"] = {
                "passed": False, "skipped": False,
                "detail": f"dry-run raised: {exc!r}",
            }
    else:
        out["levels"]["live_tested"] = {"passed": False, "skipped": True}

    # ----------------- example check (orthogonal) --------------------------
    if gold_json is not None:
        if comp.get("ok"):
            try:
                got = json.loads(comp["json"])
            except Exception:  # noqa: BLE001
                got = {}
            a = _strip_volatile(got)
            b = _strip_volatile(gold_json)
            out["levels"]["matches_example"] = {
                "passed": a == b, "skipped": False,
                "detail": ("match" if a == b
                           else "compiled JSON differs from the reference example"),
            }
        else:
            out["levels"]["matches_example"] = {
                "passed": False, "skipped": False,
                "detail": "compile failed — see draft errors",
            }
    else:
        out["levels"]["matches_example"] = {"passed": False, "skipped": True}

    # ----------------- agent-behavior gates --------------------------------
    if trace is not None:
        out["levels"].update(_score_agentic(trace=trace, text=final_text or ""))
    else:
        for k in ("tool_budget", "no_spiral", "adherence",
                  "verify_called_before_submit",
                  "verify_iterations_until_ready",
                  "final_verify_ready_to_push"):
            out["levels"][k] = {"passed": False, "skipped": True}

    # `verify_iterations_until_ready` is informational, not a gate —
    # exclude from the pass/fail aggregate. Same logic as the old
    # `skipped` flag, but here we mark it `passed=True` if it ran at
    # all so it doesn't drag the fraction.
    iters_lv = out["levels"].get("verify_iterations_until_ready", {})
    if not iters_lv.get("skipped"):
        # not counted toward fraction
        iters_lv["informational"] = True

    counted = [v for k, v in out["levels"].items()
               if not v.get("skipped") and not v.get("informational")]
    out["score"] = sum(1 for v in counted if v["passed"])
    out["max"] = len(counted)
    out["fraction"] = (out["score"] / out["max"]) if out["max"] else 0.0
    return out
