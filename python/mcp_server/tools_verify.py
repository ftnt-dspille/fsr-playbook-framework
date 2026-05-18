"""verify_playbook — the forcing-function MCP tool.

Single gate the agent calls before showing YAML to the user. Plan:
VERIFY_PLAYBOOK_PLAN.md §"The `verify_playbook` MCP tool".

Fan-out (sequential; hard failure at any gate sets ready_to_push=False
but later gates still run so the agent gets a complete punch list in
one round-trip):

  1. compile_yaml          (any severity=error → blocks)
  2. typed DAG walk        (per-branch Jinja path validation)
  3. per-step schema check (connector_op: connector + op exist in store)
  4. live safe-op probe    (only when live_probe=True AND live FSR
                            configured; degrades to warning otherwise)

`verbose=True` also returns `evidence.per_step_jinja_shapes` keyed by
jinja-key (step name with spaces→underscores). The Render-Jinja
preview UI uses this to build stub contexts for `render_jinja` so
cross-step refs resolve deterministically offline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ._shared import mcp, REPO_ROOT, DB_PATH, _err, _db


# ---------------------------------------------------------------------------
# Resolver-callback factories (DB lookups). Built once per call so the
# typed walker stays offline-pure.
# ---------------------------------------------------------------------------

def _module_fields_fn():
    conn = _db()

    def lookup(module: str) -> list[str]:
        try:
            rows = conn.execute(
                "SELECT field_name FROM module_fields WHERE module_name=?",
                (module,),
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:  # noqa: BLE001
            return []

    return lookup


def _op_safety_fn():
    conn = _db()
    # Cached at call time — fine, table is tiny.
    try:
        rows = conn.execute(
            "SELECT connector_name, op_name, safety FROM op_safety"
        ).fetchall()
        cache = {(r[0], r[1]): r[2] for r in rows}
    except Exception:  # noqa: BLE001
        cache = {}

    def lookup(connector: str, op: str) -> str:
        return cache.get((connector, op), "unknown")

    return lookup


def _connector_op_exists(connector: str, op: str) -> bool:
    conn = _db()
    try:
        row = conn.execute(
            "SELECT 1 FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def _connector_exists(name: str) -> bool:
    conn = _db()
    try:
        return conn.execute(
            "SELECT 1 FROM connectors WHERE name=?", (name,),
        ).fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _live_probe_factory(simulated_inputs: dict | None,
                        cache: dict, latencies: list):
    """Build a probe callback that calls `run_op` for safe ops. Caches
    per (connector, op, sorted-params-hash) so repeat verifies don't
    re-call. Returns None and records latency_ms when probe times out
    or errors."""
    import time
    try:
        from . import tools_execution
    except ImportError:
        tools_execution = None  # type: ignore[assignment]

    def probe(connector: str, op: str, args: dict[str, Any]):
        if tools_execution is None:
            return None
        key = (connector, op, json.dumps(args, sort_keys=True, default=str))
        if key in cache:
            return cache[key]
        # `run_op` is the canonical live caller; let it do safety
        # classification internally (we already chose only safety='safe'
        # ops at the walker layer).
        t0 = time.time()
        try:
            res = tools_execution.run_op(
                connector=connector, op=op, params=args, confirm=False,
            )
        except Exception:  # noqa: BLE001
            latencies.append({"connector": connector, "op": op,
                              "ms": int((time.time() - t0) * 1000),
                              "error": "probe_raised"})
            return None
        latencies.append({"connector": connector, "op": op,
                          "ms": int((time.time() - t0) * 1000)})
        if not isinstance(res, dict) or not res.get("ok"):
            return None
        shape = res.get("output_shape")
        if shape is None:
            return None
        cache[key] = shape
        return shape

    return probe


# ---------------------------------------------------------------------------
# Per-step schema checks. Run inline after the walk so we can attach the
# step id directly to each diagnostic.
# ---------------------------------------------------------------------------

def _per_step_schema_checks(coll) -> list[dict[str, Any]]:
    fixes: list[dict[str, Any]] = []
    for pi, pb in enumerate(coll.playbooks):
        all_ids = {s.id for s in pb.steps}
        for si, s in enumerate(pb.steps):
            spath = f"playbooks[{pi}].steps[{si}]"
            t = s.type
            a = s.arguments

            if t in {"connector", "connector_op"}:
                connector = a.get("connector") or a.get("connector_name")
                op = a.get("operation") or a.get("op_name") or a.get("op")
                if connector and not _connector_exists(connector):
                    fixes.append({
                        "code": "required_op_param_missing",
                        "message": f"connector {connector!r} not found in store",
                        "step": s.id, "path": spath,
                        "suggestion": "run `fsrpb probe connectors` or use `find_connector`",
                        "severity": "error",
                    })
                elif connector and op and not _connector_op_exists(connector, op):
                    fixes.append({
                        "code": "op_param_unknown",
                        "message": (f"operation {op!r} not found on connector "
                                    f"{connector!r}"),
                        "step": s.id, "path": spath,
                        "suggestion": "use `find_operation` to discover valid op names",
                        "severity": "error",
                    })

            elif t == "manual_input":
                # InputBased manual_input must declare at least one input.
                if (a.get("type") or "").lower() == "inputbased":
                    iv = a.get("inputVariables") or a.get("inputs") or []
                    if not iv:
                        fixes.append({
                            "code": "required_op_param_missing",
                            "message": ("manual_input type=InputBased requires "
                                        "at least one `inputs[]` entry"),
                            "step": s.id, "path": spath,
                            "severity": "error",
                        })

            elif t == "decision":
                for label, target in (s.branches or {}).items():
                    if target and target not in all_ids:
                        fixes.append({
                            "code": "branch_target_missing",
                            "message": (f"decision branch {label!r} targets "
                                        f"step {target!r} which does not exist"),
                            "step": s.id, "path": spath,
                            "severity": "error",
                        })

            elif t == "workflow_reference":
                # Cross-playbook resolution is left to the runtime; we
                # only flag the explicitly-missing case (intra-collection).
                target = a.get("playbook") or a.get("playbook_name")
                if target:
                    if not any(p.name == target for p in coll.playbooks):
                        # not a hard error — target may live in another
                        # collection on the FSR — warning only.
                        fixes.append({
                            "code": "workflow_reference_unresolvable",
                            "message": (f"workflow_reference target {target!r} "
                                        "not in this collection"),
                            "step": s.id, "path": spath,
                            "severity": "warning",
                        })
    return fixes


# ---------------------------------------------------------------------------
# Tool entry point
# ---------------------------------------------------------------------------

@mcp.tool()
def verify_playbook(
    yaml_text: str,
    playbook: str | None = None,
    simulated_inputs: dict | None = None,
    live_probe: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Single forcing-function pre-submit gate.

    Runs compile → typed walk → per-step schema checks (→ optional live
    probe). Returns one structured punch list. The agent must not show
    a playbook to the user until this returns `ready_to_push=True`.

    Required-fix codes (any present → ready_to_push=False):
      - unreachable_step_reference
      - missing_field_on_step_output
      - non_list_indexed
      - required_op_param_missing
      - op_param_unknown
      - branch_target_missing
      - workflow_reference_unresolvable (error severity only)

    Warning codes (do not block):
      - unknown_shape_downstream_reference
      - live_probe_skipped_unsafe
      - output_schema_stale
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from compiler import compile_yaml as _compile, parse_yaml
        from compiler.typed_walker import walk_playbook
    except ImportError as exc:
        return _err("compiler_unavailable", str(exc))

    checks_run: list[dict[str, Any]] = []
    required_fixes: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}

    # 1. Compile
    cres = _compile(yaml_text, DB_PATH)
    if not cres.ok:
        compile_errors = [
            {"code": e.code.value, "message": e.message, "path": e.path,
             "suggestion": e.suggestion, "severity": e.severity}
            for e in cres.errors
        ]
        # Promote compile errors directly into required_fixes — caller
        # gets one shape regardless of which gate failed.
        for ce in compile_errors:
            if ce["severity"] == "error":
                required_fixes.append(ce)
            else:
                warnings.append(ce)
        checks_run.append({"name": "compile", "ok": False,
                           "summary": f"{len(compile_errors)} compiler issues"})
        evidence["compile"] = {"errors": compile_errors}
        return _finalize(checks_run, required_fixes, warnings, evidence)
    checks_run.append({"name": "compile", "ok": True,
                       "summary": "compile clean"})

    # 2. Parse to IR for the walker (the resolver in compile already
    # ran; reparse just gives us the IR object).
    coll, parse_errs = parse_yaml(yaml_text)
    if coll is None:
        # Should not happen — compile_yaml above succeeded.
        return _err("parse_inconsistency",
                    "compile succeeded but parse_yaml returned no IR")

    # 3. Typed walk
    probe_cache: dict = {}
    probe_latencies: list[dict] = []
    walk = walk_playbook(
        coll,
        playbook_name=playbook,
        probe=(_live_probe_factory(simulated_inputs, probe_cache, probe_latencies)
               if live_probe else None),
        module_fields_fn=_module_fields_fn(),
        op_safety_fn=_op_safety_fn(),
    )
    for d in walk.diagnostics:
        bucket = required_fixes if d.severity == "error" else warnings
        bucket.append(d.to_dict())
    checks_run.append({
        "name": "typed_walk", "ok": not any(d.severity == "error" for d in walk.diagnostics),
        "summary": f"{len(walk.branches)} branch(es); "
                   f"{sum(1 for d in walk.diagnostics if d.severity == 'error')} required fix(es)",
    })

    # 4. Per-step schema check
    schema_issues = _per_step_schema_checks(coll)
    for issue in schema_issues:
        bucket = required_fixes if issue["severity"] == "error" else warnings
        bucket.append(issue)
    checks_run.append({
        "name": "per_step_schema",
        "ok": not any(i["severity"] == "error" for i in schema_issues),
        "summary": f"{len(schema_issues)} schema issue(s)",
    })

    # 5. Live probe summary
    if live_probe:
        checks_run.append({
            "name": "live_probe", "ok": True,
            "summary": f"{len(probe_latencies)} live op(s); "
                       f"{sum(1 for x in probe_latencies if 'error' in x)} failed",
        })
        evidence["live_probes"] = probe_latencies
    else:
        warnings.append({
            "code": "live_probe_skipped_unsafe",
            "message": ("live_probe=False; safe-op output shapes degrade to "
                        "static schema and downstream refs may be over-permissive"),
            "severity": "warning",
        })

    # Evidence
    if verbose:
        evidence["typed_walk"] = walk.to_dict()
        evidence["per_step_shapes"] = walk.per_step_shapes
        # Per-step shapes re-keyed by jinja-key (step name with spaces→
        # underscores), which is what `vars.steps.<key>` actually
        # resolves against at runtime. Lets the Jinja-preview UI build
        # a stub context directly from this map without rerouting
        # through step ids.
        jinja_shapes: dict[str, Any] = {}
        for pb in coll.playbooks:
            for s in pb.steps:
                jkey = (s.name or s.id or "").strip().replace(" ", "_")
                if jkey and s.id in walk.per_step_shapes:
                    jinja_shapes[jkey] = walk.per_step_shapes[s.id]
        evidence["per_step_jinja_shapes"] = jinja_shapes
    else:
        evidence["typed_walk"] = {
            "branches": [{"name": b.name, "step_ids": b.step_ids,
                          "diagnostic_count": len(b.diagnostics)}
                         for b in walk.branches],
        }

    return _finalize(checks_run, required_fixes, warnings, evidence)


def _finalize(checks_run, required_fixes, warnings, evidence) -> dict[str, Any]:
    ready = not required_fixes
    # Build a tiny ordered next-actions list so the agent doesn't have
    # to choose which fix to start with.
    next_actions: list[str] = []
    seen_codes: set[str] = set()
    # Priority: compile errors first, then schema, then walker.
    priority_codes = (
        "parse_error", "missing_field", "unknown_step_type",
        "required_op_param_missing", "op_param_unknown",
        "branch_target_missing", "unknown_connector", "unknown_operation",
        "unreachable_step_reference", "missing_field_on_step_output",
        "non_list_indexed",
    )
    for code in priority_codes:
        for fx in required_fixes:
            if fx.get("code") == code and code not in seen_codes:
                next_actions.append(f"{code}: {fx.get('message', '')[:120]}")
                seen_codes.add(code)
                break
        if len(next_actions) >= 3:
            break
    # Fall back to first-N-required-fixes when none matched the priority
    # codes (e.g. compiler emitted only `bad_value` or similar).
    if not next_actions and required_fixes:
        for fx in required_fixes[:3]:
            next_actions.append(
                f"{fx.get('code', 'error')}: {fx.get('message', '')[:120]}"
            )

    return {
        "ok": ready,
        "ready_to_push": ready,
        "required_fixes": required_fixes,
        "warnings": warnings,
        "checks_run": checks_run,
        "evidence": evidence,
        "next_actions": next_actions,
    }
