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
from typing import Any

from ._shared import mcp, REPO_ROOT, DB_PATH, _err, _db
from fsr_playbooks.compiler.record_op_checks import (
    check_connector_config,
    check_op_params,
    check_record_module,
    check_required_record_fields,
    check_unknown_record_fields,
)


# ---------------------------------------------------------------------------
# Check toggles — let a caller (e.g. pyfsr) skip groups of compiler checks.
# `verify_playbook(disable_checks=[...])` accepts either a GROUP name from this
# map or an individual diagnostic `code`. Disabled diagnostics are removed from
# `required_fixes`/`warnings` (so they no longer block `ready_to_push`) and
# echoed under `evidence.suppressed` for transparency — skipping is never
# silent. Codes that several checks share (notably `bad_value`) can only be
# toggled as a coarse group; distinct codes toggle precisely.
# ---------------------------------------------------------------------------
CHECK_GROUPS: dict[str, frozenset[str]] = {
    "jinja": frozenset({
        "jinja_syntax_error", "unknown_jinja_filter", "bad_jinja_filter_chain"}),
    "shape": frozenset({
        "missing_field_on_step_output", "unknown_shape_downstream_reference",
        "non_list_indexed"}),
    "type": frozenset({"type_mismatch"}),
    "record": frozenset({
        "required_record_field_missing", "unknown_module",
        "unknown_record_field"}),
    "op": frozenset({
        "op_param_unknown", "op_param_unknown_name", "required_op_param_missing",
        "unknown_operation", "unknown_param"}),
    "connector": frozenset({
        "unknown_connector", "connector_config_missing",
        "connector_config_no_default", "unknown_connector_config"}),
    "graph": frozenset({
        "unknown_step_reference", "unreachable_step_reference",
        "branch_target_missing", "unknown_next_step",
        "workflow_reference_unresolvable"}),
    "vars": frozenset({
        "var_read_before_definition", "var_defined_other_branch",
        "loop_var_outside_for_each", "set_var_reserved_key"}),
    # Coarse: `bad_value` is shared by picklist-drift, literal param-type,
    # code-snippet sandbox bans, and reserved-key coercion. Skipping "value"
    # turns off all of them.
    "value": frozenset({"bad_value"}),
    # Usually fatal structural problems; offered for completeness.
    "structure": frozenset({
        "parse_error", "missing_field", "unknown_step_type",
        "duplicate_step_id", "no_trigger", "internal"}),
}


import contextlib


@contextlib.contextmanager
def _db_override(db_path: str):
    """Temporarily point the catalog DB at `db_path` for the enclosed call.

    `_db()` (in `_shared`) and `compile_yaml` both read the DB path as a global
    at call time, so swapping it here lets a caller verify against a warmed
    catalog without the path being threaded through every helper. Restored on
    exit; the swap window is the single synchronous verify call."""
    from . import _shared
    global DB_PATH
    prev_shared, prev_local = _shared.DB_PATH, DB_PATH
    _shared.DB_PATH = str(db_path)
    DB_PATH = str(db_path)
    try:
        yield
    finally:
        _shared.DB_PATH = prev_shared
        DB_PATH = prev_local


def _resolve_disabled_codes(
    disable_checks: list[str] | None,
) -> tuple[frozenset[str], list[str]]:
    """Expand a `disable_checks` list (group names and/or codes) into the set
    of diagnostic codes to suppress. Returns (codes, unknown_tokens) — unknown
    tokens are surfaced to the caller, never fatal."""
    if not disable_checks:
        return frozenset(), []
    codes: set[str] = set()
    unknown: list[str] = []
    known_codes = {c for grp in CHECK_GROUPS.values() for c in grp}
    for tok in disable_checks:
        key = (tok or "").strip().lower()
        if not key:
            continue
        if key in CHECK_GROUPS:
            codes |= CHECK_GROUPS[key]
        elif key in known_codes:
            codes.add(key)
        else:
            # Accept an unrecognized token as a literal code (forward-compatible
            # with codes not yet in any group) but report it.
            codes.add(key)
            unknown.append(tok)
    return frozenset(codes), unknown


# ---------------------------------------------------------------------------
# Grounded output-shape oracle (pilot gap D). Shapes measured from real runs
# (tooling/ground_shapes.py, tooling/sweep_shapes.py) and persisted next to the
# packaged slim DB. Loaded once; used as the OFFLINE probe so `verify_playbook`
# checks `vars.steps.<op>.<path>` references against measured shapes even with
# no live FSR. Strictly additive: un-observed ops return None → walker falls
# back to inference, never worse than before.
# ---------------------------------------------------------------------------

_GROUNDED_STORE = None


def _grounded_store():
    global _GROUNDED_STORE
    if _GROUNDED_STORE is None:
        from fsr_playbooks._db import PACKAGED_SLIM_DB
        from fsr_playbooks.compiler.grounded_shapes import GroundedShapeStore
        path = PACKAGED_SLIM_DB.parent / "grounded_shapes.json"
        _GROUNDED_STORE = GroundedShapeStore.load(path)
    return _GROUNDED_STORE


def _combined_probe(live_probe_fn):
    """Probe that tries the live shape first, then the grounded oracle.

    With no live probe (offline verify) this is the grounded oracle alone.
    """
    from fsr_playbooks.compiler.grounded_shapes import grounded_probe
    grounded = grounded_probe(_grounded_store())
    if live_probe_fn is None:
        return grounded

    def _probe(connector, op, arguments):
        shape = live_probe_fn(connector, op, arguments)
        if shape is not None:
            return shape
        return grounded(connector, op, arguments)
    return _probe


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


def _param_type_fn():
    """Phase 4 target-type lookup: map a connector param's widget + observed
    type into the single tag the walker compares a source shape against.
    Mirrors the resolver's `_param_target_observed_type` so static and
    cross-step checks agree. Returns None for untyped/picklist params."""
    conn = _db()

    def lookup(connector: str, op: str, param: str):
        try:
            row = conn.execute(
                "SELECT type, observed_type FROM operation_params "
                "WHERE connector_name=? AND op_name=? AND param_name=? "
                "  AND parent_param_name IS NULL AND condition_value IS NULL",
                (connector, op, param),
            ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        if row is None:
            return None
        widget = (row[0] or "").lower()
        observed = row[1]
        if widget in {"integer", "intger"}:
            return "int"
        if widget in {"decimal", "numeric"}:
            return "float"
        if widget in {"checkbox", "boolean"}:
            return "bool"
        if widget in {"json", "object"}:
            return "json_object"
        if widget in {"text", "textarea", "richtext"}:
            return observed  # ipv4/url/json_array/… or None for unprobed
        return None  # select/multiselect/picklist → enum check handles it

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


def _nearest_op_names(connector: str, bad_op: str, n: int = 3) -> list[str]:
    """Top-N closest op names on `connector` by difflib ratio, so the
    `op_param_unknown` diagnostic can suggest concrete alternatives
    inline instead of asking the agent to run `find_operation`."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT op_name FROM operations WHERE connector_name=?",
            (connector,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    import difflib
    ops = [r[0] for r in rows]
    return difflib.get_close_matches(bad_op or "", ops, n=n, cutoff=0.3)


def _connector_exists(name: str) -> bool:
    conn = _db()
    try:
        return conn.execute(
            "SELECT 1 FROM connectors WHERE name=?", (name,),
        ).fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _known_modules() -> list[str]:
    """All module names in the catalog (empty when un-warmed)."""
    conn = _db()
    try:
        return [r[0] for r in conn.execute("SELECT name FROM modules").fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _module_required_fields(module: str) -> list[str]:
    """Required field_names for a module (F). Empty when un-warmed."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT field_name FROM module_fields "
            "WHERE module_name=? AND required=1",
            (module,),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _module_field_names(module: str) -> list[str]:
    """All field_names for a module (unknown-field check). Empty when un-warmed."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT field_name FROM module_fields WHERE module_name=?",
            (module,),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _op_declared_params(connector: str, op: str) -> list[str]:
    """All declared param names for a connector op (G unknown-name check),
    across any nesting/condition — conservative, to avoid flagging a valid
    nested/conditional param used at the top level."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT param_name FROM operation_params "
            "WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _op_required_params(connector: str, op: str) -> list[str]:
    """Top-level *unconditional* required params with no default (G missing-
    check). Excludes nested (parent_param_name) and conditional
    (condition_value) params — required only when a sibling is set — and params
    carrying a `default_value` (FSR supplies the default, so omitting them is
    not a failure). Flagging any of those would false-fire on valid playbooks."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT param_name FROM operation_params "
            "WHERE connector_name=? AND op_name=? AND required=1 "
            "  AND parent_param_name IS NULL AND condition_value IS NULL "
            "  AND (default_value IS NULL OR default_value='')",
            (connector, op),
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _connector_config_status(connector: str) -> tuple[bool, list[str], bool]:
    """(configs_known, config_names, has_default) for a connector.

    `configs_known` is False when the whole connector_configs table is empty
    (warm never ran) — the config check skips entirely in that case, so an
    un-warmed slim DB never false-flags a connector as un-configured."""
    conn = _db()
    try:
        any_rows = conn.execute(
            "SELECT 1 FROM connector_configs LIMIT 1"
        ).fetchone()
        if any_rows is None:
            return (False, [], False)
        rows = conn.execute(
            "SELECT config_name, is_default FROM connector_configs "
            "WHERE connector=?",
            (connector,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return (False, [], False)
    # `__default__` is a synthetic pointer row, not a user-visible config name.
    names = [r[0] for r in rows if r[0] and r[0] != "__default__"]
    has_default = any(bool(r[1]) for r in rows)
    return (True, names, has_default)


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

def _per_step_schema_checks(coll, *, live_probe: bool = False) -> list[dict[str, Any]]:
    fixes: list[dict[str, Any]] = []
    for pi, pb in enumerate(coll.playbooks):
        all_ids = {s.id for s in pb.steps}
        for si, s in enumerate(pb.steps):
            spath = f"playbooks[{pi}].steps[{si}]"
            t = s.type
            a = s.arguments

            # Jinja syntax + unknown-filter checks run in the compile stage
            # (validator._check_jinja_templates -> check_jinja) and are surfaced
            # here as compile findings, so they are not re-run per step.

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
                    near = _nearest_op_names(connector, op, n=3)
                    if near:
                        msg = (f"operation {op!r} not found on connector "
                               f"{connector!r}. Did you mean: "
                               f"{', '.join(repr(n) for n in near)}?")
                        sug = f"replace with {near[0]!r}"
                    else:
                        msg = (f"operation {op!r} not found on connector "
                               f"{connector!r}, and no close matches "
                               f"exist — connector may be installed but "
                               f"not yet probed, or the op name is wrong")
                        sug = ("call `find_operation` against this "
                               "connector to list real op names")
                    fixes.append({
                        "code": "op_param_unknown",
                        "message": msg,
                        "step": s.id, "path": spath,
                        "suggestion": sug,
                        "near": near,
                        "severity": "error",
                    })
                elif connector and op:
                    # Op exists — validate its params (G) and config bind.
                    fixes.extend(check_op_params(
                        connector=connector, operation=op,
                        params=a.get("params"),
                        declared_params=_op_declared_params(connector, op),
                        required_params=_op_required_params(connector, op),
                        step_id=s.id, path=spath,
                    ))
                # Connector-config existence is *instance-specific* (which
                # configs exist on THIS target), so it's a live-target preflight
                # — pyfsr D3's domain — not an offline-static fact. Running it
                # offline false-flags any playbook authored for a different box
                # (a connector not configured on the warm target). Gate on
                # live_probe so the default offline path never blocks on it.
                if connector and live_probe:
                    known, names, has_def = _connector_config_status(connector)
                    fixes.extend(check_connector_config(
                        connector=connector, config_value=a.get("config"),
                        configs_known=known, config_names=names,
                        has_default=has_def, step_id=s.id, path=spath,
                    ))

            elif t in {"create_record", "insert_record", "update_record"}:
                module = a.get("module")
                # Module existence applies to all record writes.
                fixes.extend(check_record_module(
                    module=module, known_modules=_known_modules(),
                    step_id=s.id, path=spath,
                ))
                # Required-field completeness is creation-only (update is a
                # partial patch — an absent required field is legal).
                if isinstance(module, str) and module:
                    # Unknown-field check applies to create + update (a bogus
                    # key is wrong either way); warning severity.
                    fixes.extend(check_unknown_record_fields(
                        module=module, resource=a.get("resource"),
                        known_fields=_module_field_names(module),
                        step_id=s.id, path=spath,
                    ))
                    if t != "update_record":
                        fixes.extend(check_required_record_fields(
                            module=module, resource=a.get("resource"),
                            required_fields=_module_required_fields(module),
                            step_id=s.id, path=spath,
                        ))

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
    disable_checks: list[str] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Single forcing-function pre-submit gate.

    Runs compile → typed walk → per-step schema checks (→ optional live
    probe). Returns one structured punch list. The agent must not show
    a playbook to the user until this returns `ready_to_push=True`.

    `disable_checks` (optional): skip groups or individual checks the caller
    doesn't want enforced. Each entry is a GROUP name or a diagnostic `code`.
    Disabled diagnostics move from `required_fixes`/`warnings` into
    `evidence.suppressed` (never silent) and stop blocking `ready_to_push`;
    `suppressed_count` reports how many. Groups:
      jinja | shape | type | record | op | connector | graph | vars |
      value (coarse: all `bad_value` — picklist/literal-type/snippet-ban) |
      structure (parse/missing-field/unknown-step-type/…)
    Example: `disable_checks=["jinja", "type_mismatch"]`.

    `db_path` (optional): verify against a specific reference catalog (e.g. a
    pyfsr per-install warmed cache) instead of the packaged slim one. The
    record/op/config checks only fire when the catalog carries those facts, so
    a warmed DB is what makes them meaningful.

    Required-fix codes (any present → ready_to_push=False):
      - unknown_step_reference
      - unreachable_step_reference
      - missing_field_on_step_output
      - non_list_indexed
      - type_mismatch                    (source→target type, Phase 4)
      - required_op_param_missing       (connector-op declared required param)
      - op_param_unknown
      - required_record_field_missing   (create_record missing a required field)
      - unknown_module                  (record write into a non-existent module)
      - connector_config_missing        (live_probe only — no config on target)
      - unknown_connector_config        (live_probe only — config: name unknown)
      - branch_target_missing
      - workflow_reference_unresolvable (error severity only)
      - jinja_syntax_error              (un-parseable Jinja template; emitted
                                         by the compile stage)

    Warning codes (do not block):
      - unknown_jinja_filter            (filter/test name outside the FSR catalog)
      - op_param_unknown_name           (unknown connector-op param name)
      - unknown_record_field            (resource key not a field of the module)
      - connector_config_no_default     (configs exist but none is default)
      - unknown_shape_downstream_reference
      - output_schema_stale
      - var_read_before_definition       (branch-scoped vars.<name>)
      - var_defined_other_branch         (branch-scoped vars.<name>)
      - loop_var_outside_for_each        (vars.item outside a for_each step)
    """
    # Optional catalog override: an SDK (pyfsr) compiles/verifies against a
    # warmed per-install catalog, not the packaged slim one. `_db()` and the
    # compile both read the module-level DB path at call time, so we swap it
    # for the duration and re-enter the body once (with db_path cleared) rather
    # than thread a path through every schema-check closure.
    if db_path is not None:
        with _db_override(db_path):
            return verify_playbook(
                yaml_text, playbook, simulated_inputs, live_probe,
                verbose, disable_checks, db_path=None)

    try:
        from fsr_playbooks.compiler import compile_yaml as _compile, parse_yaml
        from fsr_playbooks.compiler.typed_walker import walk_playbook
    except ImportError as exc:
        return _err("compiler_unavailable", str(exc))

    disabled_codes, unknown_tokens = _resolve_disabled_codes(disable_checks)
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
        result = _finalize(checks_run, required_fixes, warnings, evidence,
                           disabled_codes, unknown_tokens)
        _record_history(yaml_text, playbook, result["ready_to_push"],
                        result["required_fixes"], result["warnings"], live_probe)
        return result
    checks_run.append({"name": "compile", "ok": True,
                       "summary": "compile clean"})
    # Compile may have succeeded with non-blocking warnings (e.g. an unknown
    # Jinja filter name). These were previously dropped on the success path
    # because the per-step check_jinja re-run masked them; now that Jinja
    # checking lives in the compile stage, surface them here so they reach the
    # caller's `warnings`.
    for w in cres.warnings:
        warnings.append(w.to_dict())

    # 2. Two IR views:
    #  - `walk_coll` = the *resolved* IR (`cres.ir`): the resolver mutates
    #    Step objects in place, populating `step.branches` (decision routing)
    #    which the typed walker needs to enumerate every trigger→leaf path.
    #    A fresh parse leaves `branches={}` so enumeration would stop at the
    #    first decision (STATIC_TYPE_FLOW_PLAN.md Phase 0).
    #  - `coll` = a fresh parse (authoring shape): the per-step schema checks
    #    and Jinja-shape evidence are written against the friendly shape the
    #    author wrote. The resolver rewrites some steps in ways those checks
    #    don't expect — e.g. an `options:`-based manual_input becomes
    #    `type: InputBased` with `response_mapping` and no `inputVariables`,
    #    which would false-trigger the "InputBased needs inputs[]" check.
    coll, parse_errs = parse_yaml(yaml_text)
    if coll is None:
        # Should not happen — compile_yaml above succeeded.
        return _err("parse_inconsistency",
                    "compile succeeded but parse_yaml returned no IR")
    walk_coll = cres.ir if cres.ir is not None else coll

    # 3. Typed walk
    probe_cache: dict = {}
    probe_latencies: list[dict] = []
    walk = walk_playbook(
        walk_coll,
        playbook_name=playbook,
        probe=_combined_probe(
            _live_probe_factory(simulated_inputs, probe_cache, probe_latencies)
            if live_probe else None),
        module_fields_fn=_module_fields_fn(),
        op_safety_fn=_op_safety_fn(),
        param_type_fn=_param_type_fn(),
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
    schema_issues = _per_step_schema_checks(coll, live_probe=live_probe)
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
    # When live_probe=False the caller has explicitly opted into static
    # shape inference; we no longer emit a blanket warning for that. If
    # individual references actually resolve through unknown shapes they
    # surface as `unknown_shape_downstream_reference` (specific, useful).

    # Phase 5 — persist the type trace (best-effort) and surface its path.
    trace_path = _write_type_trace(yaml_text, playbook, walk)
    if trace_path:
        evidence["type_trace_path"] = trace_path

    # Evidence
    if verbose:
        evidence["typed_walk"] = walk.to_dict()
        # Folded-in trace: per-branch type decisions (source→target→verdict).
        evidence["type_trace"] = [
            {"name": b.name, "step_ids": b.step_ids,
             "type_decisions": b.type_decisions}
            for b in walk.branches
        ]
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

    result = _finalize(checks_run, required_fixes, warnings, evidence,
                       disabled_codes, unknown_tokens)
    _record_history(yaml_text, playbook, result["ready_to_push"],
                    result["required_fixes"], result["warnings"], live_probe)
    return result


def _write_type_trace(yaml_text: str, playbook: str | None, walk) -> str | None:
    """Phase 5 — persist a per-branch, per-step type trace to
    store/verify_traces/<yaml_sha>.json for troubleshooting. Best-effort;
    never raises. Returns the path written (str) or None."""
    try:
        import hashlib
        sha = hashlib.sha1((yaml_text or "").encode("utf-8")).hexdigest()[:16]
        out_dir = REPO_ROOT / "data" / "verify_traces"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{sha}.json"
        payload = {
            "yaml_sha": sha,
            "playbook": playbook,
            "branches": [
                {
                    "name": b.name,
                    "step_ids": b.step_ids,
                    "var_env": b.var_env,
                    "type_decisions": b.type_decisions,
                    "diagnostics": [d.to_dict() for d in b.diagnostics],
                }
                for b in walk.branches
            ],
        }
        path.write_text(json.dumps(payload, indent=2, default=str))
        return str(path)
    except Exception:  # noqa: BLE001
        return None


def _record_history(yaml_text: str, playbook: str | None, ready: bool,
                    required_fixes: list, warnings: list,
                    live_probe: bool) -> None:
    """Best-effort telemetry write to history.db (verify_runs table).
    Resolves open-Q #3 from VERIFY_PLAYBOOK_PLAN: enables the
    'agent submitted without verifying' detector + 2-week regression
    measurement. Never raises."""
    try:
        import hashlib
        sys.path.insert(0, str(REPO_ROOT / "web"))
        from backend import history as history_db  # noqa: PLC0415
        sha = hashlib.sha1((yaml_text or "").encode("utf-8")).hexdigest()[:16]
        codes = [f.get("code", "?") for f in required_fixes]
        history_db.record_verify_run(
            yaml_sha=sha, playbook_name=playbook,
            ready_to_push=ready, required_fix_codes=codes,
            warning_count=len(warnings), live_probe=live_probe,
        )
    except Exception:
        pass


def _finalize(checks_run, required_fixes, warnings, evidence,
              disabled_codes: frozenset[str] = frozenset(),
              unknown_tokens: list[str] | None = None) -> dict[str, Any]:
    # Apply check toggles: pull any disabled-code diagnostics out of the
    # blocking/​warning lists into `suppressed` so they never block — but stay
    # visible. `ready_to_push` is computed on what remains.
    suppressed: list[dict[str, Any]] = []
    if disabled_codes:
        kept_fixes, kept_warnings = [], []
        for fx in required_fixes:
            (suppressed if fx.get("code") in disabled_codes
             else kept_fixes).append(fx)
        for w in warnings:
            (suppressed if w.get("code") in disabled_codes
             else kept_warnings).append(w)
        required_fixes, warnings = kept_fixes, kept_warnings
        evidence["suppressed"] = suppressed
        evidence["disabled_checks"] = {
            "codes": sorted(disabled_codes),
            "suppressed_count": len(suppressed),
            "unknown_tokens": unknown_tokens or [],
        }
    ready = not required_fixes
    # Build a tiny ordered next-actions list so the agent doesn't have
    # to choose which fix to start with.
    next_actions: list[str] = []
    seen_codes: set[str] = set()
    # Priority: compile errors first, then schema, then walker.
    priority_codes = (
        "parse_error", "missing_field", "unknown_step_type",
        "jinja_syntax_error",
        "required_op_param_missing", "op_param_unknown",
        "required_record_field_missing", "connector_config_missing",
        "unknown_module", "unknown_connector_config",
        "branch_target_missing", "unknown_connector", "unknown_operation",
        "unknown_step_reference", "unreachable_step_reference",
        "missing_field_on_step_output",
        "non_list_indexed",
        "type_mismatch",
        "bad_jinja_filter_chain",
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
        "suppressed_count": len(suppressed),
        "checks_run": checks_run,
        "evidence": evidence,
        "next_actions": next_actions,
    }
