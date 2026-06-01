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
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FRIENDLY_FORMS: dict[str, dict[str, Any]] = {
    "start": {
        "accepted_keys": ["module", "modules", "button_label",
                          "requires_record", "run_mode"],
        "note": (
            "Manual / designer trigger. With NO `module:` it's a pure "
            "designer trigger (cybersponse.abstract_trigger). With a "
            "`module:` set it becomes a record-context Execute action "
            "(cybersponse.action) — `button_label:` is what the user "
            "sees in the Execute menu (NOT the step name). "
            "`run_mode: per_record` (default) or `once_for_all`."
        ),
        "example": {
            "type": "start",
            "name": "Run",
            "arguments": {
                "module": "alerts",
                "button_label": "Enrich This Alert",
                "run_mode": "per_record",
            },
        },
    },
    "start_on_create": {
        "accepted_keys": ["module", "modules", "when"],
        "note": (
            "Auto-fires whenever a record is created in `module`. "
            "Optional `when:` filters by post-write field state."
        ),
        "when_shape": (
            "{logic: AND|OR, filters: [{field, op, value?}, ...]} — "
            "use string-typed fields or `op: changed` (changed only on "
            "start_on_update); LIKE against picklist fields will not match."
        ),
        "example": {
            "type": "start_on_create",
            "arguments": {
                "module": "alerts",
                "when": {
                    "logic": "AND",
                    "filters": [{"field": "name", "op": "contains",
                                 "value": "phish"}],
                },
            },
        },
    },
    "start_on_update": {
        "accepted_keys": ["module", "modules", "when"],
        "note": (
            "Auto-fires whenever a record in `module` is updated. "
            "`op: changed` lets you fire only when a specific field "
            "changed value (no `value:` needed)."
        ),
        "example": {
            "type": "start_on_update",
            "arguments": {
                "module": "alerts",
                "when": {
                    "logic": "AND",
                    "filters": [{"field": "status", "op": "changed"}],
                },
            },
        },
    },
    "set_variable": {
        "accepted_keys_step_level": ["vars", "message", "record"],
        "shape": (
            "Variables go under a step-level `vars:` mapping (not under "
            "`arguments:`). The parser hoists `vars:` into the wire-form "
            "`arg_list`. Optional `message:` posts a comment to the "
            "triggered record's collaboration panel; `record:` is only "
            "needed when the playbook has no triggered record."
        ),
        "example": {
            "type": "set_variable",
            "name": "Stash Inputs",
            "vars": {
                "source_ip": "{{ vars.input.records[0].sourceIp }}",
                "verdict": "pending",
            },
        },
        "do_not_use": [
            "set: / values: / variables: at step level — only `vars:` is "
            "the recognized sugar key",
            "putting variables under `arguments:` — use step-level `vars:`",
            "arg_list: [{name, value}, ...] at step level — legacy wire "
            "form, the parser writes it for you",
        ],
    },
    "decision": {
        "accepted_keys": ["conditions"],
        "shape": (
            "`conditions:` lives at the step level (sugar) or under "
            "`arguments:` (wire form). Each non-default entry has "
            "`display`, `when`, `next`. Exactly one entry must be the "
            "default (`default: true`, no `when`) and supply `next:` for "
            "the else branch. Do NOT use a step-level `branches:` dict — "
            "the parser hard-errors on it."
        ),
        "example": {
            "type": "decision",
            "name": "Score Check",
            "conditions": [
                {"display": "Critical",
                 "when": "{{ vars.score > 50 }}",
                 "next": "Set Critical"},
                {"display": "Else", "default": True, "next": "Set Low"},
            ],
        },
        "do_not_use": [
            "step-level `branches:` dict — write `next:` on each "
            "conditions[] entry instead",
            "bare step-level `next:` — declare an explicit `default: true` "
            "row in `conditions:` and put `next:` on it",
        ],
    },
    "connector": {
        "accepted_keys": ["connector", "operation", "config", "params",
                          "agent", "version", "pickFromTenant"],
        "note": (
            "Always look up the operation first via "
            "find_operation/get_op_schema — `params` keys are validated "
            "against the operation_params catalog. `config: \"\"` "
            "selects the default connector configuration."
        ),
        "step_outputs": (
            "Reference results as `vars.steps.<step_name>.<key>` where "
            "<step_name> is the step's display NAME with spaces → "
            "underscores (NOT the YAML id:)."
        ),
        "example": {
            "type": "connector",
            "name": "Query VirusTotal",
            "arguments": {
                "connector": "virustotal",
                "operation": "query_ip",
                "config": "",
                "params": {"ip": "{{ vars.input.params.ip }}"},
            },
        },
    },
    "stop": {
        "accepted_keys": [],
        "example": {"type": "stop", "name": "End"},
        "note": (
            "Compiles to the connector handler's no_op (cyops_utilities). "
            "Use as a decision-branch terminator instead of dangling "
            "steps or filler set_variable."
        ),
    },
    "end": {
        "accepted_keys": [],
        "example": {"type": "end", "name": "End"},
        "note": "Alias for stop.",
    },
    "find_record": {
        "accepted_keys": ["module", "query", "partial"],
        "note": (
            "Returns a hydra envelope. Records are at "
            "`vars.steps.<name>['hydra:member']`, NOT `.records`. "
            "`partial: true` returns first page only."
        ),
        "query_shape": (
            "{logic: AND|OR, filters: [{field, operator, value}, ...]}"
        ),
        "example": {
            "type": "find_record",
            "name": "find",
            "arguments": {
                "module": "indicators",
                "query": {
                    "logic": "AND",
                    "filters": [{"field": "value", "operator": "eq",
                                 "value": "{{ vars.input.params.indicator }}"}],
                },
                "partial": True,
            },
        },
    },
    "create_record": {
        "accepted_keys": ["module", "resource"],
        "note": (
            "`module:` is the friendly module name (alerts, incidents, "
            "indicators, ...) — compiler converts to the IRI form. "
            "`resource:` is a flat dict of {field: value}."
        ),
        "example": {
            "type": "create_record",
            "name": "Create alert",
            "arguments": {
                "module": "alerts",
                "resource": {
                    "name": "Phishing - {{ vars.input.params.subject }}",
                    "severity": "{{ 'High' | picklist('severity') }}",
                },
            },
        },
    },
    "insert_record": {
        "accepted_keys": ["module", "resource"],
        "note": "Alias for create_record (legacy short name).",
        "example": {
            "type": "create_record",
            "name": "Create alert",
            "arguments": {
                "module": "alerts",
                "resource": {"name": "Test alert"},
            },
        },
    },
    "update_record": {
        "accepted_keys": ["module", "collection", "resource"],
        "note": (
            "`module:` (or `collectionType:`) names the module being "
            "updated. `collection:` is the RECORD IRI to update — "
            "usually `\"{{ vars.input.records[0]['@id'] }}\"`. Don't "
            "confuse the two."
        ),
        "example": {
            "type": "update_record",
            "name": "Update alert severity",
            "arguments": {
                "module": "alerts",
                "resource": {
                    "severity": "{{ 'Critical' | picklist('severity') }}",
                },
            },
        },
    },
    "delay": {
        "accepted_keys": ["seconds", "minutes", "hours", "days"],
        "note": (
            "Provide one or more units; the compiler builds the canonical "
            "TimeBased rule with the instance-wide resume_playbook channel."
        ),
        "example": {
            "type": "delay",
            "name": "Wait",
            "arguments": {"minutes": 5},
        },
    },
    "manual_input": {
        "accepted_keys_arguments": ["title", "description", "inputs"],
        "accepted_keys_step_level": ["options"],
        "shape": (
            "Prompt body (title, description, inputs) goes under "
            "`arguments:`. Branch buttons go under a STEP-LEVEL `options:` "
            "list (NOT under `arguments:`). Each option carries its own "
            "`next:` — do not use a step-level `branches:` dict."
        ),
        "type_value": "InputBased (only valid value; omit to let compiler fill)",
        "options_shape": (
            "list of {display, next, primary?} dicts. The first option "
            "is treated as primary unless another carries `primary: true`."
        ),
        "inputs_shape": (
            "list of {name, kind, label?, tooltip?, required?, default?, "
            "options?} — kind is one of: text, textarea, richtext, email, "
            "url, password, ipv4, ipv6, domain, filehash, integer, "
            "checkbox, select, datetime, json, picklist, lookup. After "
            "the operator submits, fields are read at "
            "`vars.steps.<step_name>.input.<name>`. `kind: select` "
            "requires `options:` (list of strings or jinja that resolves "
            "to a list). Prefer the most specific kind for typed values "
            "(ipv4 over text for IP addresses, etc.)."
        ),
        "example": {
            "type": "manual_input",
            "name": "Triage Decision",
            "arguments": {
                "title": "Confirm triage",
                "description": "Review the alert details and approve.",
                "inputs": [
                    {"name": "comment", "kind": "textarea",
                     "label": "Analyst comment", "required": True},
                    {"name": "severity", "kind": "select",
                     "label": "Severity",
                     "options": ["Low", "Medium", "High"]},
                ],
            },
            "options": [
                {"display": "Approve", "primary": True, "next": "Act"},
                {"display": "Reject", "next": "Drop"},
            ],
        },
        "do_not_use": [
            "step-level `branches:` dict — put `next:` on each option",
            "`options:` nested under `arguments:` — it must be at the "
            "step level (the parser hard-errors on this)",
            "type: textarea / single-select / free-text (no such dispatch — "
            "use `inputs: [{kind: textarea, ...}]` for a textarea field)",
            "label, message (not valid keys — use title/description)",
            "timeout (FSR ignores it)",
            "vars.steps.<id>.input.choice (does not exist; the option's "
            "`next:` is what routes the playbook)",
        ],
    },
    "code_snippet": {
        "accepted_keys": ["code", "config"],
        "note": (
            "`code:` is the Python body. `config:` is an optional named "
            "code-snippet connector config; defaults to the default config."
        ),
        "example": {
            "type": "code_snippet",
            "name": "Compute",
            "arguments": {"code": "result = inputs['x'] * 2"},
        },
    },
    "workflow_reference": {
        "accepted_keys": ["target", "workflowReference", "arguments"],
        "note": (
            "Either `target: <playbook_name>` (resolved within the same "
            "collection) OR `workflowReference: /api/3/workflows/<uuid>` "
            "for cross-collection refs. `arguments:` keys must match the "
            "target's declared `parameters:` list. Child output is at "
            "`vars.steps.<call_step_name>.<key>` — does NOT auto-merge "
            "into parent vars."
        ),
        "example": {
            "type": "workflow_reference",
            "name": "Call Score Multiplier",
            "arguments": {
                "target": "FSRPB Score Multiplier",
                "arguments": {"score": "{{ vars.input.params.base_score }}"},
            },
        },
    },
    "approval": {
        "accepted_keys": "pass-through (canonical FSR Approval shape)",
        "note": (
            "No friendly form yet. Use the canonical Approval wire shape "
            "from `args_schema_json` / `examples`."
        ),
    },
}

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
    to fix before declaring done — they don't block compile but they
    almost always mean the playbook won't behave correctly at runtime.
    """
    try:
        from fsr_core.compiler import compile_yaml as _compile
    except ImportError as exc:
        return _err("compiler_unavailable", f"compiler not available: {exc}")

    result = _compile(yaml_text, _shared.DB_PATH)
    if result.ok:
        warnings = [_serialize_compiler_error(w) for w in result.warnings]
        if warnings:
            return {
                "ok": True,
                "warnings": warnings,
                "next_fix": _pick_next_fix(warnings),
            }
        return {"ok": True}
    errs = [_serialize_compiler_error(e) for e in result.errors]
    return _err(
        "validation_failed",
        f"{len(result.errors)} compiler error(s); see `errors` for codes "
        "and suggestions",
        errors=errs,
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
# resolve_yaml — static-resolve check + live prechecks
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
        import yaml as _yaml  # type: ignore
        doc = _yaml.safe_load(yaml_text) or {}
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
    `prechecks` is reported as skipped — failure here is not retroactively
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
    default — the agent rarely needs the full JSON body, just a
    confirmation that compile succeeds. Pass `verbose=True` to also get
    the importable FSR JSON string under `json`.

    On failure: `{ok: false, errors: [...]}` with structured compiler
    errors regardless of verbose.
    """
    try:
        from fsr_core.compiler import compile_yaml as _compile
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
) -> dict[str, Any]:
    """Compile a playbook from the session's typed action trace instead of
    hand-authoring YAML (SKILL_BASED_PLAYBOOK_PLAN §3–5).

    This is the flag-gated trace-compiler entry point: the agent already
    ran the connector ops during triage, so their real outputs were
    captured as a `SkillTrace`. This tool replays that trace into candidate
    steps, wires each step's inputs to prior steps' captured outputs by
    deterministic value-match (no guessed jinja paths), verifies every wire
    resolves (and repairs the ones that don't back to a literal + a gap),
    then compiles the result to confirm it imports clean.

    Args:
      trace_json: the serialized `SkillTrace` (`SkillTrace.to_json()`).
        **Leave empty** in normal agent use — the session's recorded trace
        is read from the active recorder automatically. Pass a value only
        to compile an externally-supplied trace (tests, batch tooling).
      name: the playbook display name.
      live: when True, verify wires against the live FSR Jinja engine
        (`render_jinja`) for runtime-identical evidence; offline (default)
        uses a strict local Jinja render.

    Returns on success: `{ok, yaml, compile_summary, verified, gaps,
    repaired, static_errors}`. `gaps`/`repaired`/`static_errors` are the
    analyst-facing trust signals (a value that couldn't be auto-wired
    surfaces as a gap, never a dangling reference). Returns
    `{ok: false, ...}` with `empty_trace` when the trace has no recorded
    actions (caller should fall back to the hand-author path).
    """
    from fsr_core.agent import skill_trace as _skill_trace
    from fsr_core.agent.skill_trace import SkillTrace
    from fsr_core.compiler import skill_compiler as sc
    from fsr_core.compiler import skill_verify as sv

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
            "no recorded actions in the trace — nothing to compile",
            suggestions=["fall back to the hand-author build path"],
        )

    render_fn = None
    if live:
        try:
            from fsr_core.mcp_server import render_jinja as _render
            render_fn = _render
        except Exception:  # noqa: BLE001
            render_fn = None  # offline fallback

    compiled = sv.compile_and_verify(trace, render_fn=render_fn)
    doc = sc.assemble_playbook(compiled, name=name)
    yaml_text = sc.to_yaml(doc)

    # Confirm the trace-built playbook imports clean (draft tier).
    try:
        from fsr_core.compiler import compile_yaml as _compile
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
# push / run / dry-run — closes the agent's authoring loop without dropping
# out to the CLI. All three mutate state on the live FSR instance.
# ---------------------------------------------------------------------------