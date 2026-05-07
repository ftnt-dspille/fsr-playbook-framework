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
from typing import Any


def _validate(yaml_text: str) -> dict[str, Any]:
    from mcp_server import validate_yaml
    return validate_yaml(yaml_text)


def _resolve(yaml_text: str) -> dict[str, Any]:
    from mcp_server import resolve_yaml
    return resolve_yaml(yaml_text)


def _compile_obj(yaml_text: str) -> dict[str, Any]:
    from mcp_server import compile_yaml
    return compile_yaml(yaml_text)


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


def score(
    yaml_text: str,
    *,
    gold_json: dict[str, Any] | None = None,
    live: bool = False,
    dry_run_kwargs: dict[str, Any] | None = None,
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

    # Aggregate: passed-non-skipped / total-non-skipped
    counted = [v for v in out["levels"].values() if not v["skipped"]]
    out["score"] = sum(1 for v in counted if v["passed"])
    out["max"] = len(counted)
    out["fraction"] = (out["score"] / out["max"]) if out["max"] else 0.0
    return out
