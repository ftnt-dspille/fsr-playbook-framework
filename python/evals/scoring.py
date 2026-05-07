"""Score a candidate playbook YAML against the success-ladder gates.

Each level is a hard pass/fail with the structured tool result kept
inline so the eval matrix can show *why* a model failed without
re-running anything.

Levels:
  L1 — compiles clean (validate_yaml ok)
  L2 — live prechecks pass (resolve_yaml ok); skipped when no live FSR
  L3 — variable references reachable (subset of L1 — broken out so
       agent-driven authoring shows up specifically here)
  L4 — dry-run executes on the live FSR; skipped offline
  gold — optional byte-equal compile output match against a fixture
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

_YAML_BLOCK_RE = re.compile(r"```ya?ml\s*\n", re.IGNORECASE)


def _validate(yaml_text: str) -> dict[str, Any]:
    from mcp_server import validate_yaml
    return validate_yaml(yaml_text)


def _compile_warnings(yaml_text: str) -> list[dict[str, Any]]:
    """Return the compiler's `warnings` list (UNKNOWN_PARAM, corpus
    drift, lint hints). validate_yaml swallows these because
    CompileResult.ok already excludes them — we re-run via the
    library to surface them for the L1.5 gate."""
    from pathlib import Path as _P
    from compiler import compile_yaml as _compile
    db_path = _P(__file__).resolve().parents[2] / "store" / "fsr_reference.db"
    result = _compile(yaml_text, db_path)
    return [
        {"code": w.code.value, "path": w.path, "message": w.message}
        for w in result.warnings
    ]


def _resolve(yaml_text: str) -> dict[str, Any]:
    from mcp_server import resolve_yaml
    return resolve_yaml(yaml_text)


def _compile_obj(yaml_text: str) -> dict[str, Any]:
    from mcp_server import compile_yaml
    return compile_yaml(yaml_text, verbose=True)


_VOLATILE_KEYS = frozenset({"lastModifyDate"})


def _strip_volatile(obj: Any) -> Any:
    """Recursively drop fields that are time-stamped (wf-engine
    bookkeeping) so byte-equality comparisons aren't second-bound."""
    if isinstance(obj, dict):
        return {
            k: _strip_volatile(v)
            for k, v in obj.items() if k not in _VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def _has_var_reachability_error(validate_out: dict[str, Any]) -> bool:
    """The validator emits BAD_VALUE with a message phrase for both
    Jinja-step-not-found and not-reachable cases. Match on phrase so
    we can keep L3 as its own gate without a new error code."""
    for e in validate_out.get("errors") or []:
        msg = (e.get("message") or "").lower()
        if "no step with jinja-key" in msg or "cannot run before" in msg:
            return True
    return False


# Agentic gate thresholds. Sourced from docs/AGENT_TOOL_USAGE.md p95s —
# raise via env if a model is intentionally chatty.
TOOL_BUDGET_MAX = int(os.environ.get("EVAL_TOOL_BUDGET_MAX", "20"))
NO_SPIRAL_MAX_CONSECUTIVE = int(
    os.environ.get("EVAL_NO_SPIRAL_MAX_CONSECUTIVE", "4"))


def _score_agentic(
    *, trace: list[dict[str, Any]], text: str,
) -> dict[str, dict[str, Any]]:
    """Three gates over the agentic provider's trace.

    - tool_budget: total tool calls <= TOOL_BUDGET_MAX (default 20).
    - no_spiral: no tool called > NO_SPIRAL_MAX_CONSECUTIVE times in a
      row (caught the validate→validate×23 spiral in session
      60743f70). Default 4.
    - adherence: final assistant text contains a fenced ```yaml block —
      proxies "agent ended with a deliverable, not just chatter".
    """
    n = len(trace)
    # consecutive run length
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
    """Run all available scoring gates and return a result row.

    Returns a dict with per-level `{passed: bool, skipped: bool,
    detail: ...}` plus a flat `score` (passed gates / non-skipped
    gates) and `passed_levels` (highest contiguous level passed).
    """
    out: dict[str, Any] = {"levels": {}}

    # L1 — validate
    val = _validate(yaml_text)
    out["levels"]["L1"] = {
        "passed": bool(val.get("ok")),
        "skipped": False,
        "code": val.get("code"),
        "errors": val.get("errors", []),
    }

    # L1.5 — strict-whitelist (no UNKNOWN_PARAM / corpus-drift warnings)
    if val.get("ok"):
        warnings = _compile_warnings(yaml_text)
        out["levels"]["L1.5"] = {
            "passed": not warnings,
            "skipped": False,
            "warnings": warnings,
        }
    else:
        # Don't double-penalize: if L1 fails, the warning gate is meaningless.
        out["levels"]["L1.5"] = {"passed": False, "skipped": True}

    # L3 — variable reachability (computable even when L1 fails)
    has_var_err = _has_var_reachability_error(val)
    out["levels"]["L3"] = {
        "passed": (not has_var_err) and bool(val.get("ok")),
        "skipped": False,
        "detail": ("var-reachability error present" if has_var_err
                   else "ok"),
    }

    # L2 — live resolve (connector + picklist prechecks)
    if live:
        res = _resolve(yaml_text)
        # resolve_yaml returns {ok, structural, prechecks, summary}
        out["levels"]["L2"] = {
            "passed": bool(res.get("ok")),
            "skipped": False,
            "summary": res.get("summary"),
        }
    else:
        out["levels"]["L2"] = {"passed": False, "skipped": True}

    # L4 — dry-run
    if live:
        try:
            from mcp_server import dry_run_playbook  # noqa: PLC0415
            kw = dict(dry_run_kwargs or {})
            dr = dry_run_playbook(yaml_text, **kw) if kw else None
            # dry_run_playbook requires a `playbook` arg; if the caller
            # didn't supply one, fall back to "first playbook" by name.
            if dr is None:
                dr = {"ok": False, "code": "no_dry_run_target",
                      "message": "dry_run_kwargs missing `playbook` name"}
            out["levels"]["L4"] = {
                "passed": bool(dr.get("ok")),
                "skipped": False,
                "code": dr.get("code"),
                "summary": dr.get("status") or dr.get("message"),
            }
        except Exception as exc:  # noqa: BLE001
            out["levels"]["L4"] = {
                "passed": False, "skipped": False,
                "detail": f"dry-run raised: {exc!r}",
            }
    else:
        out["levels"]["L4"] = {"passed": False, "skipped": True}

    # gold-fixture byte-equality (against the compiled FSR JSON)
    if gold_json is not None:
        comp = _compile_obj(yaml_text)
        if comp.get("ok"):
            try:
                got = json.loads(comp["json"])
            except Exception:  # noqa: BLE001
                got = {}
            # `lastModifyDate` is `int(datetime.now().timestamp())` written
            # by emitter.py — it ticks per second so two compiles spanning
            # a second boundary produce different output. Strip it on both
            # sides of the gold comparison; the field is wf-engine
            # bookkeeping, not part of the playbook semantics.
            a = _strip_volatile(got)
            b = _strip_volatile(gold_json)
            out["levels"]["gold"] = {
                "passed": a == b,
                "skipped": False,
                "detail": ("match" if a == b
                           else "compiled JSON differs from gold"),
            }
        else:
            out["levels"]["gold"] = {
                "passed": False, "skipped": False,
                "detail": "compile failed — see L1 errors",
            }
    else:
        out["levels"]["gold"] = {"passed": False, "skipped": True}

    # Agentic gates — only when the provider returned a tool-use trace.
    # Skipped (not failing) for non-agentic providers so their score
    # max stays comparable to historical runs.
    if trace is not None:
        out["levels"].update(_score_agentic(
            trace=trace, text=final_text or ""))
    else:
        for k in ("tool_budget", "no_spiral", "adherence"):
            out["levels"][k] = {"passed": False, "skipped": True}

    # Aggregate: passed-non-skipped / total-non-skipped
    counted = [v for v in out["levels"].values() if not v["skipped"]]
    out["score"] = sum(1 for v in counted if v["passed"])
    out["max"] = len(counted)
    out["fraction"] = (out["score"] / out["max"]) if out["max"] else 0.0
    return out
