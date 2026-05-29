"""Tool registry — wraps existing mcp_server.py functions.

Phase 2 v1: read-only authoring tools only. No `run_op`, no `push`, no
destructive actions. Live FSR calls (render_jinja, get_run_env,
list_configured_connectors) are allowed because they're read-only and
gated by the user's `.env`.

Schema generation is deliberately small: we map Python type hints to
the JSON Schema subset Anthropic accepts. If a tool's signature drifts
beyond what we cover, add the case here rather than papering over it.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sqlite3
import sys
import time
import typing
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, get_args, get_origin

import fsr_core.mcp_server as mcp_server


# Allow-list. Names match attribute names on `mcp_server`.
SAFE_TOOLS: list[str] = [
    "find_connector",
    "find_operation",
    "get_op_schema",
    "get_step_type",
    "find_jinja_filter",
    "find_jinja_pattern",
    "get_filter_examples",
    "search_playbooks",
    "verify_playbook",
    "verify_enhancement",
    "emit_decision_step",
    "list_configured_connectors",
    "list_picklists",
    "picklist_for_field",
    "resolve_picklist_value",
    # Phase 0 — authoring loop tools the system prompt mandates.
    "validate_yaml",
    "compile_yaml",
    "analyze_playbook",
    # "find_step_recipe",  # hidden — recipes corpus not populated yet; revisit later
    # Widget card emitters — drive the chat UI's awaiting_* halts.
    "emit_choice_card",
    "emit_action_card",
    "emit_manual_input",
    # Phase 1.1 — HTTP fallback authoring helper.
    "propose_http_fallback",
    # Phase 1.2 — live triage (read-only FSR).
    "why_did_playbook_fail",
    "get_run_env",
    "list_playbook_runs",
    "assert_playbook_outcome",
    # Tier 1+ — gated by the dispatch wrapper below. See `TOOL_TIERS`.
    "run_op",
    "step_through_playbook",
    "dry_run_playbook",
    "diagnose_yaml_against_pb_execution",
    # Phase 1.3 — side-effecting execution (tier-dynamic).
    "push_playbook",
    "run_playbook",
]


# --- Tier model (see docs/plans/HITL_GUARDRAILS_PLAN.md) -------------------
#
# Static per-tool defaults. `run_op` is overridden at call time by
# `_resolve_tier` because its tier depends on the (connector, op) being
# called.

TOOL_TIERS: dict[str, int] = {
    # Tier 0 — pure local compute.
    "find_connector": 0,
    "find_operation": 0,
    "get_op_schema": 0,
    "get_step_type": 0,
    "find_jinja_filter": 0,
    "find_jinja_pattern": 0,
    "get_filter_examples": 0,
    "search_playbooks": 0,
    "list_picklists": 0,
    "picklist_for_field": 0,
    "resolve_picklist_value": 0,
    # Tier 1 — read-only FSR API.
    "verify_playbook": 1,
    "verify_enhancement": 1,
    # Tier 0 — pure local YAML render from a structured payload.
    "emit_decision_step": 0,
    "list_configured_connectors": 1,
    "diagnose_yaml_against_pb_execution": 1,
    # Phase 0 — pure local compute (no FSR I/O).
    "validate_yaml": 0,
    "compile_yaml": 0,
    "analyze_playbook": 0,
    # "find_step_recipe": 0,  # hidden — see SAFE_TOOLS
    "emit_choice_card": 0,
    "emit_action_card": 0,
    "emit_manual_input": 0,
    "propose_http_fallback": 0,
    # Phase 1.2 — read-only FSR API.
    "why_did_playbook_fail": 1,
    "get_run_env": 1,
    "list_playbook_runs": 1,
    "assert_playbook_outcome": 1,
    # Tier-dynamic. Resolved per call.
    "run_op": -1,
    "step_through_playbook": -1,
    "dry_run_playbook": -1,
    "push_playbook": -1,
    "run_playbook": -1,
}

# Op-name / category classifiers used as fallback when op_safety has no
# row for a given (connector, op). Mirrors the heuristics from
# `probe_op_safety` so the wrapper degrades gracefully on fresh DBs.
_REMEDIATION_CATEGORIES = {"remediation", "containment"}
_MANAGEMENT_CATEGORIES = {"management"}
_SAFE_CATEGORIES = {"investigation", "query", "utilities", "enrichment", "verification"}

_SENSITIVE_KEY_RE = re.compile(r"(?i)(password|token|api[_-]?key|secret|authorization|bearer)")


_DB_PATH = Path(__file__).resolve().parents[2] / "store" / "fsr_reference.db"


def _lookup_op_metadata(connector: str, op: str) -> tuple[str | None, str | None]:
    """Return (safety, category) for a given op, or (None, None) if unknown.

    Safety is from `op_safety.safety` ('safe' | 'unsafe' | 'unknown') when
    present, else None. Category is from `operations.category`.
    """
    if not connector or not op or not _DB_PATH.exists():
        return None, None
    try:
        con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            safety: str | None = None
            try:
                row = cur.execute(
                    "SELECT safety FROM op_safety WHERE connector_name=? AND op_name=?",
                    (connector, op),
                ).fetchone()
                if row:
                    safety = (row[0] or "").strip().lower() or None
            except sqlite3.OperationalError:
                pass  # op_safety not probed yet
            row = cur.execute(
                "SELECT category FROM operations WHERE connector_name=? AND op_name=?",
                (connector, op),
            ).fetchone()
            category = (row[0] or "").strip().lower() if row and row[0] else None
            return safety, category
        finally:
            con.close()
    except sqlite3.Error:
        return None, None


def _tier_for_run_op(args: dict[str, Any]) -> int:
    """Resolve effective tier for a `run_op` call from op_safety + category.

    Tier 4 — third-party side effect (remediation / containment).
    Tier 3 — FSR data mutation (management).
    Tier 2 — read-only external (third-party query: safe + non-FSR connector).
    Tier 1 — read-only FSR or safely-classified op.
    Unknowns escalate: default to tier 3 (always prompt).
    """
    connector = (args or {}).get("connector") or ""
    op = (args or {}).get("op") or ""
    safety, category = _lookup_op_metadata(connector, op)
    if category in _REMEDIATION_CATEGORIES:
        return 4
    if category in _MANAGEMENT_CATEGORIES:
        return 3
    if safety == "safe" or category in _SAFE_CATEGORIES:
        # Third-party query → tier 2; FSR-internal query → tier 1.
        # We don't have a reliable "is FSR-internal" flag; treat all
        # external reads as tier 2 (auto-allow + log).
        return 2
    if safety == "unsafe":
        return 4  # unknown category but classifier flagged destructive
    return 3  # unknown / unclassified → require approval


def _tier_for_simulator(args: dict[str, Any]) -> int:
    """`step_through_playbook` / `dry_run_playbook` inherit tier from
    whether they're authorized to execute unsafe ops. With the default
    `execute_unsafe_ops=False` they're tier 1; flipping it to True
    escalates to tier 3 (per-step approval handled in Phase 5)."""
    if args and args.get("execute_unsafe_ops"):
        return 3
    return 1


def _resolve_tier(name: str, args: dict[str, Any]) -> int:
    static = TOOL_TIERS.get(name, 0)
    if static >= 0:
        return static
    if name == "run_op":
        return _tier_for_run_op(args or {})
    if name in ("step_through_playbook", "dry_run_playbook"):
        return _tier_for_simulator(args or {})
    if name == "push_playbook":
        return 3  # writes to FSR — always require approval
    if name == "run_playbook":
        return 3  # triggers live execution — always require approval
    return 0


def _mask_value(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: ("***" if _SENSITIVE_KEY_RE.search(k) else _mask_value(val)) for k, val in v.items()}
    if isinstance(v, list):
        return [_mask_value(x) for x in v]
    return v


def _build_preview(name: str, args: dict[str, Any]) -> dict[str, Any]:
    masked = _mask_value(args or {})
    return {"tool": name, "args": masked}


def _args_hash(name: str, args: dict[str, Any]) -> str:
    payload = json.dumps({"tool": name, "args": args or {}}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# Per-process audit log. The chat backend (Phase 1) will replace this
# with a per-conversation store keyed off the session id.
AUDIT_LOG: list[dict[str, Any]] = []


def _record_audit(name: str, args: dict[str, Any], tier: int, decision: str, *, result_preview: Any = None) -> None:
    AUDIT_LOG.append({
        "ts": time.time(),
        "tool": name,
        "tier": tier,
        "args_hash": _args_hash(name, args),
        "decision": decision,  # "auto_allow" | "approved" | "denied" | "pending"
        "result_preview": result_preview,
    })


def clear_audit_log() -> None:
    """Test/eval harness helper. Per-task resets so the
    `appropriate_approval_requests` gate scores only the calls made
    during the task it's measuring."""
    AUDIT_LOG.clear()


def snapshot_audit_log() -> list[dict[str, Any]]:
    """Return a defensive copy of the audit log for scoring."""
    return [dict(r) for r in AUDIT_LOG]


# --- Eval-mode approval policy (Phase 3) ----------------------------------
#
# Under the chat / agent loop the gate suspends and waits for a human.
# Under the eval harness there's no human in the loop — the policy
# decides for us. Set via env (`EVAL_APPROVAL_POLICY`) or the per-task
# `approval_policy` field, which the harness sets per task before
# calling dispatch. Recognized values:
#   "suspend"          — production behavior (default). Return pending_approval.
#   "approve-all"      — auto-approve every gated call.
#   "deny-tier-3+"     — synthesize `{ok:false, code:user_denied, ...}`.
#   "auto-approve-tier:N" — approve iff tier ≤ N, else deny.
# Anything unrecognized falls back to "suspend".

_EVAL_POLICY_OVERRIDE: str | None = None  # set by the harness per task


def set_eval_policy(policy: str | None) -> None:
    global _EVAL_POLICY_OVERRIDE
    _EVAL_POLICY_OVERRIDE = policy or None


def _active_eval_policy() -> str | None:
    if _EVAL_POLICY_OVERRIDE:
        return _EVAL_POLICY_OVERRIDE
    return os.environ.get("EVAL_APPROVAL_POLICY") or None


def _apply_eval_policy(policy: str, tier: int) -> str:
    """Return 'approve' | 'deny' for a given policy + tier. Anything
    unknown returns 'suspend' so production behavior is the safe
    default."""
    p = policy.strip().lower()
    if p in ("approve-all", "approve"):
        return "approve"
    if p in ("deny-tier-3+", "deny"):
        return "deny"
    if p.startswith("auto-approve-tier:"):
        try:
            cap = int(p.split(":", 1)[1].split(",")[-1].strip())
            return "approve" if tier <= cap else "deny"
        except (ValueError, IndexError):
            return "suspend"
    return "suspend"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]
    tier: int = 0
    confirm_mode: str = "auto"  # auto | log | approve | step_up


def _py_type_to_json(tp: Any) -> dict[str, Any]:
    """Map a Python annotation to a minimal JSON Schema fragment."""
    if tp is inspect.Parameter.empty or tp is Any:
        return {}
    origin = get_origin(tp)
    args = get_args(tp)

    if origin is typing.Union or (origin is None and args):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _py_type_to_json(non_none[0])
        # union of primitives → leave loose
        return {}
    if origin in (list, typing.List):
        inner = args[0] if args else Any
        return {"type": "array", "items": _py_type_to_json(inner) or {}}
    if origin in (dict, typing.Dict):
        return {"type": "object"}
    if tp is str:
        return {"type": "string"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is list:
        return {"type": "array"}
    if tp is dict:
        return {"type": "object"}
    return {}


# Hand-written input_schema overrides for tools whose shape is too nested
# for the auto-from-signature builder. Anthropic enforces these on the
# wire, so e.g. emit_decision_step physically cannot receive a condition
# missing `when:` or a default_branch without `next:`. Keep these in
# sync with the runtime checks inside the tool itself — the override is
# the wire contract; the runtime check covers non-LLM callers.
TOOL_SCHEMA_OVERRIDES: dict[str, dict[str, Any]] = {
    "emit_choice_card": {
        "type": "object",
        "required": ["id", "prompt", "options"],
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1,
                   "description": "Stable choice id; echoed on resume."},
            "prompt": {"type": "string", "minLength": 1},
            "multi": {"type": "boolean", "default": False},
            "min_select": {"type": "integer", "minimum": 0, "default": 1},
            "max_select": {"type": ["integer", "null"], "default": None},
            "options": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "required": ["label", "value"],
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "value": {"type": "string", "minLength": 1,
                                  "description": "Machine-readable; echoed back on resume."},
                        "hint": {"type": "string"},
                    },
                },
            },
        },
    },
    "emit_action_card": {
        "type": "object",
        "required": ["id", "connector", "operation", "summary",
                     "args", "editable_fields"],
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "connector": {"type": "string", "minLength": 1,
                          "description": "Connector name (e.g. fortinet-fortigate)."},
            "operation": {"type": "string", "minLength": 1},
            "summary": {"type": "string", "minLength": 1,
                        "description": "One-line plain-English summary of what will run."},
            "args": {"type": "object",
                     "description": "Operation arguments; widget shows them."},
            "editable_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Args keys the user is allowed to edit before confirm.",
            },
        },
    },
    "emit_manual_input": {
        "type": "object",
        "required": ["id", "workflow_run_iri", "question", "fields"],
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "workflow_run_iri": {"type": "string", "minLength": 1,
                                 "description": "IRI of the paused workflow run."},
            "question": {"type": "string", "minLength": 1},
            "fields": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "label"],
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                        "default": {"type": "string"},
                    },
                },
            },
        },
    },
    "emit_decision_step": {
        "type": "object",
        "required": ["name", "conditions", "default_branch"],
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "pattern": "^[A-Za-z0-9 _]+$",
                "description": ("Step display name. Title Case; letters, "
                                "digits, spaces, and underscores only."),
            },
            "conditions": {
                "type": "array",
                "minItems": 1,
                "description": ("Ordered non-default branches. Evaluated "
                                "top-down; the default_branch is the else."),
                "items": {
                    "type": "object",
                    "required": ["display", "when", "next"],
                    "additionalProperties": False,
                    "properties": {
                        "display": {"type": "string"},
                        "when": {
                            "type": "string",
                            "description": ("Jinja expression returning "
                                            "truthy/falsy. Do not wrap "
                                            "in {{ }} — the tool does that."),
                        },
                        "next": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9 _]+$",
                            "description": "Target step name (verbatim).",
                        },
                    },
                },
            },
            "default_branch": {
                "type": "object",
                "required": ["display", "next"],
                "additionalProperties": False,
                "description": ("The else branch. `default: true` is "
                                "added by the tool; do NOT pass it here."),
                "properties": {
                    "display": {"type": "string"},
                    "next": {
                        "type": "string",
                        "pattern": "^[A-Za-z0-9 _]+$",
                    },
                },
            },
        },
    },
}


def _build_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, p in sig.parameters.items():
        schema = _py_type_to_json(p.annotation)
        if p.default is inspect.Parameter.empty:
            required.append(name)
        else:
            schema = {**schema, "default": p.default} if schema else {"default": p.default}
        props[name] = schema or {}
    return {"type": "object", "properties": props, "required": required}


def _resolve(name: str) -> Callable[..., Any]:
    fn = getattr(mcp_server, name, None)
    if fn is None or not callable(fn):
        raise KeyError(f"unknown tool: {name}")
    return fn


def build_registry() -> dict[str, ToolSpec]:
    out: dict[str, ToolSpec] = {}
    for name in SAFE_TOOLS:
        fn = _resolve(name)
        desc = inspect.getdoc(fn) or f"{name} (no docstring)"
        # First-paragraph only; Anthropic limits description length implicitly.
        short = desc.strip().split("\n\n", 1)[0]
        static_tier = TOOL_TIERS.get(name, 0)
        confirm_mode = "auto" if static_tier in (0, 1) else ("approve" if static_tier in (2, 3) else "step_up")
        if static_tier < 0:
            confirm_mode = "dynamic"
        out[name] = ToolSpec(
            name=name,
            description=short,
            input_schema=TOOL_SCHEMA_OVERRIDES.get(name) or _build_schema(fn),
            fn=fn,
            tier=static_tier,
            confirm_mode=confirm_mode,
        )
    return out


REGISTRY = build_registry()


def anthropic_tools() -> list[dict[str, Any]]:
    """Anthropic's tool-use schema shape."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in REGISTRY.values()
    ]


def openai_tools() -> list[dict[str, Any]]:
    """OpenAI / LM Studio function-calling schema shape. Same registry,
    different envelope: `{type:"function", function:{name, description, parameters}}`."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in REGISTRY.values()
    ]


def dispatch(name: str, arguments: dict[str, Any]) -> Any:
    """Tier-aware dispatch (HITL_GUARDRAILS_PLAN Phase 0).

    Tier 0–2: execute immediately, append an audit row.
    Tier 3+:  if `arguments` lacks a valid `_approval_token`, return a
              `{pending_approval: true, …}` envelope without calling the
              underlying tool. The chat-app loop (Phase 1) suspends on
              this envelope and renders the approval card; on approve,
              the loop re-dispatches with `_approval_token` set.
    """
    spec = REGISTRY.get(name)
    if spec is None:
        return {"error": f"unknown tool: {name}"}

    raw_args = dict(arguments or {})
    # `_approved` sentinel is set by the chat backend when it has
    # already validated the human approval against its session-auth
    # surface. We don't mint HMAC tokens — auth is the existing app
    # auth; this flag is internal-only and the chat layer guarantees
    # it can't originate from the LLM (tool-use args pass through a
    # whitelist enforced one frame up).
    approved = bool(raw_args.pop("_approved", False))
    summary = raw_args.pop("_summary", None)
    tier = _resolve_tier(name, raw_args)

    if tier >= 3 and not approved:
        # Phase 3: eval-mode policy short-circuit. Production callers
        # (the chat loop) leave the policy unset, fall through to the
        # pending_approval envelope, and the chat layer suspends.
        policy = _active_eval_policy()
        policy_decision = _apply_eval_policy(policy, tier) if policy else "suspend"
        if policy_decision == "approve":
            try:
                result = spec.fn(**raw_args)
            except TypeError as e:
                return {"error": f"bad arguments for {name}: {e}"}
            except Exception as e:
                return {"error": f"{type(e).__name__}: {e}"}
            _record_audit(name, raw_args, tier, "approved")
            return result
        if policy_decision == "deny":
            _record_audit(name, raw_args, tier, "denied")
            return {"ok": False, "code": "user_denied",
                    "reason": f"Eval policy '{policy}' denied tier-{tier} action."}

        approval_id = uuid.uuid4().hex
        envelope = {
            "pending_approval": True,
            "approval_id": approval_id,
            "tier": tier,
            "tool": name,
            "preview": _build_preview(name, raw_args),
            "args_hash": _args_hash(name, raw_args),
            "summary": summary,
            "requires_step_up": tier >= 4,
        }
        _record_audit(name, raw_args, tier, "pending", result_preview=envelope)
        return envelope

    try:
        result = spec.fn(**raw_args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # surface to LLM as a tool result, not a 500
        return {"error": f"{type(e).__name__}: {e}"}

    decision = "approved" if approved else ("auto_allow" if tier <= 2 else "approved")
    _record_audit(name, raw_args, tier, decision)
    return result
