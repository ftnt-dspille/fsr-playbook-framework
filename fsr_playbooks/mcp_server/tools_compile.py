"""MCP tools: Tools Compile"""
from __future__ import annotations
from . import _shared

import json
import re
from typing import Any

from ._shared import (
    mcp,
    _err,
    _serialize_compiler_error,
    load_yaml_text,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# ── Friendly-form authoring reference ──
# Single source of truth: `_FRIENDLY_FORMS` lives in `tools_discovery` (the
# richer, actively-maintained copy that `get_step_type` renders). Re-exported
# here so the compile-path consumers that import it from this module (and the
# package `__init__`) stay in lockstep -- no second copy to drift.
from .tools_discovery import _FRIENDLY_FORMS  # noqa: F401,E402 (re-export)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def validate_yaml(yaml_text: str) -> dict[str, Any]:
    """Validate a YAML playbook without producing output JSON.

    Runs the full compiler pipeline (parse → resolve → validate) and
    returns structured errors.  Each error has: code, path, message,
    suggestion (may be empty).

    Returns `{ok: true}` when the playbook compiles. When the playbook
    compiles but the graph linter raised non-blocking issues (e.g.
    unreachable step, missing default branch), the response is
    `{ok: true, warnings: [...]}`. Treat warnings as authoring bugs
    to fix before declaring done -- they don't block compile but they
    almost always mean the playbook won't behave correctly at runtime.
    """
    try:
        from fsr_playbooks.compiler import compile_yaml as _compile
    except ImportError as exc:
        return _err("compiler_unavailable", f"compiler not available: {exc}")

    result = _compile(yaml_text, _shared.DB_PATH)

    # §F: the compiler auto-corrects known foot-guns (set_variable
    # namespace refs, `vars.input.<p>` missing `.params.`, `stop`→`end`,
    # …) on its internal IR, but the agent only got a warning describing
    # each rewrite -- re-authoring the YAML by hand cost a full
    # validate→fix→validate round-trip per foot-gun in live sessions.
    # Hand back the corrected source text instead.
    corrected: dict[str, Any] = {}
    try:
        from fsr_playbooks.compiler.source_fixer import (
            apply_fixes as _apply_fixes, collect_fixes as _collect_fixes,
        )
        fixes = _collect_fixes(yaml_text)
        if fixes:
            fixed_text = _apply_fixes(yaml_text, fixes)
            if fixed_text != yaml_text:
                corrected = {
                    "corrected_yaml": fixed_text,
                    "auto_fixes": [
                        {"code": f.code, "line": f.line, "message": f.message}
                        for f in fixes
                    ],
                    "auto_fix_note": (
                        "Known foot-guns were auto-corrected in "
                        "`corrected_yaml` -- adopt it as your working copy "
                        "instead of re-applying each warning by hand. It "
                        "fixes only the listed items; any other errors "
                        "still need your attention."
                    ),
                }
    except Exception:  # noqa: BLE001 -- advisory affordance, never block validation
        corrected = {}

    if result.ok:
        warnings = [_serialize_compiler_error(w) for w in result.warnings]
        if warnings:
            return {
                "ok": True,
                "warnings": warnings,
                "next_fix": _pick_next_fix(warnings),
                **corrected,
            }
        return {"ok": True, **corrected}
    errs = [_serialize_compiler_error(e) for e in result.errors]
    return _err(
        "validation_failed",
        f"{len(result.errors)} compiler error(s); see `errors` for codes "
        "and suggestions",
        errors=errs,
        **corrected,
        # Single most-actionable next fix. Picks the first error of the
        # highest-priority code so the agent has a clear next move
        # instead of staring at a 9-error wall. Saves several
        # validate-fix-validate spirals (the recurring failure mode in
        # session cabdaf00).
        next_fix=_pick_next_fix(errs),
    )


# Order matters: structural problems (missing collection / unknown step
# type) must be fixed before semantic ones (jinja path doesn't resolve)
# can even be checked. Lower index = fix first.
_NEXT_FIX_PRIORITY = (
    "missing_field",
    "unknown_connector",
    "unknown_operation",
    "unknown_param",
    "bad_value",
)


def _pick_next_fix(errors: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the single most actionable error to fix first."""
    if not errors:
        return None
    only_errors = [e for e in errors if e.get("severity") != "warning"]
    pool = only_errors or errors
    for code in _NEXT_FIX_PRIORITY:
        for e in pool:
            if e.get("code") == code:
                return {
                    "code": e.get("code"),
                    "path": e.get("path"),
                    "message": e.get("message"),
                    "suggestion": e.get("suggestion") or e.get("near"),
                }
    e = pool[0]
    return {
        "code": e.get("code"),
        "path": e.get("path"),
        "message": e.get("message"),
        "suggestion": e.get("suggestion") or e.get("near"),
    }


# ---------------------------------------------------------------------------
# resolve_yaml -- static-resolve check + live prechecks
# ---------------------------------------------------------------------------

_PICKLIST_LITERAL = re.compile(
    r"\{\{\s*['\"]([^'\"]+)['\"]\s*\|\s*picklist\(\s*['\"]([^'\"]+)['\"]\s*\)",
)


def _walk_strings_iter(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings_iter(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings_iter(v)


def _extract_connectors_and_picklists(yaml_text: str) -> tuple[
    list[tuple[str, str | None]], list[tuple[str, str]]
]:
    """Parse YAML and return (connectors_used, picklist_literals).

    connectors_used: list of (name, version_or_None) from steps where
        type == 'connector'.
    picklist_literals: list of (picklist_name, value) from any string
        in the document matching `{{ 'PL' | picklist('value') }}`.
    """
    try:
        doc, _ = load_yaml_text(yaml_text)
    except Exception:  # noqa: BLE001
        return [], []

    connectors: dict[tuple[str, str | None], None] = {}
    picklists: dict[tuple[str, str], None] = {}

    playbooks = doc.get("playbooks") or []
    for pb in playbooks if isinstance(playbooks, list) else []:
        for step in (pb.get("steps") or []) if isinstance(pb, dict) else []:
            if not isinstance(step, dict):
                continue
            if step.get("type") == "connector":
                cn = step.get("connector")
                cv = step.get("version")
                if isinstance(cn, str) and cn:
                    connectors[(cn, cv if isinstance(cv, str) else None)] = None

    for s in _walk_strings_iter(doc):
        for m in _PICKLIST_LITERAL.finditer(s):
            pl_name, val = m.group(1), m.group(2)
            picklists[(pl_name, val)] = None

    return list(connectors.keys()), list(picklists.keys())

@mcp.tool()
def resolve_yaml(yaml_text: str) -> dict[str, Any]:
    """Static-resolve check: full whole-YAML resolvability check.

    Runs the structural validator (`validate_yaml` equivalent) and then,
    if a live FSR is configured, verifies that every connector the
    playbook uses is installed and every `{{ 'PL' | picklist('value') }}`
    literal resolves. Returns one consolidated report so the agent can
    fix everything in a single round-trip.

    Response shape:
      {
        ok: bool,
        structural: { ok, errors: [...] },        # from validate_yaml
        prechecks:  [ {ok, code, message, suggestions, ...}, ... ],
        summary:    { connectors_checked, picklists_checked, fails },
      }

    When no live FSR is configured the structural gate still runs and
    `prechecks` is reported as skipped -- failure here is not retroactively
    fatal (the agent can re-run when an FSR is reachable).
    """
    structural = validate_yaml(yaml_text)
    structural_ok = bool(structural.get("ok"))

    client = _shared._live_client()
    prechecks: list[dict[str, Any]] = []
    summary = {"connectors_checked": 0, "picklists_checked": 0,
               "fails": 0, "live_fsr": client is not None}
    if client is None:
        return {
            "ok": structural_ok,
            "structural": structural,
            "prechecks": [],
            "summary": {**summary, "note": "no live FSR; prechecks skipped"},
        }

    connectors, picklists = _extract_connectors_and_picklists(yaml_text)
    try:
        from recipes.prechecks import (
            check_connector_installed, check_picklist_value,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "structural": structural,
            "prechecks": [{"ok": False, "code": "precheck_import_failed",
                           "message": str(exc), "suggestions": []}],
            "summary": {**summary, "fails": 1},
        }

    installed_connectors: set[str] = set()
    for name, version in connectors:
        r = check_connector_installed(client, name, version)
        prechecks.append(r.to_dict())
        summary["connectors_checked"] += 1
        if r.ok:
            installed_connectors.add(name)
        else:
            summary["fails"] += 1

    for pl_name, val in picklists:
        r = check_picklist_value(client, pl_name, val)
        prechecks.append(r.to_dict())
        summary["picklists_checked"] += 1
        if not r.ok:
            summary["fails"] += 1

    overall_ok = structural_ok and summary["fails"] == 0
    return {
        "ok": overall_ok,
        "structural": structural,
        "prechecks": prechecks,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# compile_yaml
# ---------------------------------------------------------------------------

@mcp.tool()
def compile_yaml(yaml_text: str, verbose: bool = False) -> dict[str, Any]:
    """Compile a YAML playbook to FortiSOAR WorkflowCollection JSON.

    Returns `{ok: true, summary: {workflows, steps, uuid, name}}` by
    default -- the agent rarely needs the full JSON body, just a
    confirmation that compile succeeds. Pass `verbose=True` to also get
    the importable FSR JSON string under `json`.

    On failure: `{ok: false, errors: [...]}` with structured compiler
    errors regardless of verbose.
    """
    try:
        from fsr_playbooks.compiler import compile_yaml as _compile
    except ImportError as exc:
        return _err("compiler_unavailable", f"compiler not available: {exc}")

    result = _compile(yaml_text, _shared.DB_PATH)
    if not result.ok:
        return _err(
            "compile_failed",
            f"{len(result.errors)} compiler error(s); see `errors` for codes "
            "and suggestions",
            errors=[_serialize_compiler_error(e) for e in result.errors],
        )
    coll = (result.fsr_json.get("data") or [{}])[0]
    workflows = coll.get("workflows") or []
    summary = {
        "name": coll.get("name"),
        "uuid": coll.get("uuid"),
        "workflows": len(workflows),
        "steps": sum(len(w.get("steps") or []) for w in workflows),
    }
    out: dict[str, Any] = {"ok": True, "summary": summary}
    if verbose:
        out["json"] = json.dumps(result.fsr_json, indent=2)
    return out


@mcp.tool()
def build_playbook_from_trace(
    trace_json: str = "",
    name: str = "Triage Playbook",
    live: bool = False,
    module: str = "",
    guard_containment: bool = True,
) -> dict[str, Any]:
    """Compile a playbook from connector ops THIS SESSION ALREADY RAN, instead
    of hand-authoring YAML. Only useful after a triage session that actually
    executed connector ops -- it replays that recorded trace. If this session
    has run no ops (a plain "build me a playbook that…" request), there is no
    trace to compile and this returns nothing useful: author the YAML and gate
    it with `verify_playbook` instead. (SKILL_BASED_PLAYBOOK_PLAN §3-5.)

    This is the flag-gated trace-compiler entry point: the agent already
    ran the connector ops during triage, so their real outputs were
    captured as a `SkillTrace`. This tool replays that trace into candidate
    steps, wires each step's inputs to prior steps' captured outputs by
    deterministic value-match (no guessed jinja paths), verifies every wire
    resolves (and repairs the ones that don't back to a literal + a gap),
    then compiles the result to confirm it imports clean.

    Args:
      trace_json: the serialized `SkillTrace` (`SkillTrace.to_json()`).
        **Leave empty** in normal agent use -- the session's recorded trace
        is read from the active recorder automatically. Pass a value only
        to compile an externally-supplied trace (tests, batch tooling).
      name: the playbook display name.
      live: when True, verify wires against the live FSR Jinja engine
        (`render_jinja`) for runtime-identical evidence; offline (default)
        uses a strict local Jinja render.
      module: friendly module name (alerts, incidents, …) to bind the
        playbook's start trigger to, so it runs as a manual Execute-menu
        trigger on that module's record listing. **Leave empty** in normal
        agent use -- it's read from the trace's recorded triage module
        (stamped by the connector when it opened the session). Pass a value
        only to override or to compile an externally-supplied trace.

    Returns on success: `{ok, yaml, compile_summary, verified, gaps,
    repaired, static_errors}`. `gaps`/`repaired`/`static_errors` are the
    analyst-facing trust signals (a value that couldn't be auto-wired
    surfaces as a gap, never a dangling reference). Returns
    `{ok: false, ...}` with `empty_trace` when the trace has no recorded
    actions (caller should fall back to the hand-author path).
    """
    from fsr_playbooks.agent import skill_trace as _skill_trace
    from fsr_playbooks.agent.skill_trace import SkillTrace
    from fsr_playbooks.compiler import skill_compiler as sc
    from fsr_playbooks.compiler import skill_verify as sv

    if trace_json:
        try:
            trace = SkillTrace.from_json(trace_json)
        except Exception as exc:  # noqa: BLE001
            return _err("bad_trace_json", f"could not parse trace_json: {exc}")
    else:
        # Normal agent path: use the session's active recorder, installed by
        # the connector's per-turn trace scope.
        trace = _skill_trace.get_active_trace() or SkillTrace()
    if len(trace) == 0:
        return _err(
            "empty_trace",
            "no recorded actions in the trace -- nothing to compile",
            suggestions=["fall back to the hand-author build path"],
        )

    render_fn = None
    if live:
        try:
            from fsr_playbooks.mcp_server import render_jinja as _render
            render_fn = _render
        except Exception:  # noqa: BLE001
            render_fn = None  # offline fallback

    compiled = sv.compile_and_verify(trace, render_fn=render_fn)
    # Gate a containment op behind a malicious-verdict decision so a re-run never
    # blocks a clean indicator (safe-by-default; no-op when no verdict signal is
    # recognized in the enrichment outputs).
    if guard_containment:
        compiled = sc.insert_containment_guard(compiled, trace)
    # Explicit arg overrides; otherwise bind to the module recorded on the
    # trace (the triaged record's module, stamped by the connector). None →
    # bare `start` (a designer-only Referenced trigger).
    trigger_module = module or getattr(trace, "module", None) or None
    doc = sc.assemble_playbook(compiled, name=name, module=trigger_module)
    yaml_text = sc.to_yaml(doc)

    # Confirm the trace-built playbook imports clean (draft tier).
    try:
        from fsr_playbooks.compiler import compile_yaml as _compile
        result = _compile(yaml_text, _shared.DB_PATH)
        if result.ok:
            coll = (result.fsr_json.get("data") or [{}])[0]
            workflows = coll.get("workflows") or []
            compile_summary: dict[str, Any] = {
                "ok": True,
                "workflows": len(workflows),
                "steps": sum(len(w.get("steps") or []) for w in workflows),
            }
        else:
            compile_summary = {
                "ok": False,
                "errors": [_serialize_compiler_error(e) for e in result.errors],
            }
    except ImportError as exc:
        compile_summary = {"ok": False, "errors": [str(exc)]}

    return {
        "ok": True,
        "yaml": yaml_text,
        "compile_summary": compile_summary,
        "verified": compiled.get("verified", {}),
        "gaps": compiled.get("gaps", {}),
        "repaired": compiled.get("repaired", {}),
        "static_errors": compiled.get("static_errors", []),
    }


# ---------------------------------------------------------------------------
# push / run / dry-run -- closes the agent's authoring loop without dropping
# out to the CLI. All three mutate state on the live FSR instance.
# ---------------------------------------------------------------------------