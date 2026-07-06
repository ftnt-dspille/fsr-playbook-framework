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
import logging
import os
import re
import sqlite3
import time
import typing
import uuid
from dataclasses import dataclass
from typing import Any, Callable, get_args, get_origin

import fsr_playbooks.mcp_server as mcp_server
from .._db import default_db_path


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
    "healthcheck_connector",
    "list_picklists",
    "picklist_for_field",
    "resolve_picklist_value",
    # Phase 0 — authoring loop tools the system prompt mandates.
    "validate_yaml",
    "compile_yaml",
    "analyze_playbook",
    # Trace compiler (SKILL_BASED_PLAYBOOK §3–5) — build a grounded playbook
    # from the session's recorded action trace instead of hand-authoring. The
    # build prompt mandates calling this FIRST; without it in the registry the
    # tool is never advertised/dispatchable and the agent silently falls back
    # to hand-authoring (losing trace grounding + staged-action coverage).
    "build_playbook_from_trace",
    # "find_step_recipe",  # hidden — recipes corpus not populated yet; revisit later
    # Widget card emitters — drive the chat UI's awaiting_* halts.
    "emit_choice_card",
    "emit_action_card",
    "emit_manual_input",
    "emit_capability_gap_card",
    "emit_playbook_offer",
    # Phase 1.1 — HTTP fallback authoring helper.
    "propose_http_fallback",
    # Phase 1.2 — live triage (read-only FSR).
    # NOC / FortiManager + FortiAnalyzer device diagnostics (read-only).
    # Tier 1+ — gated by the dispatch wrapper below. See `TOOL_TIERS`.
    "run_op",
    "step_through_playbook",
    "dry_run_playbook",
    "diagnose_yaml_against_pb_execution",
    # Phase 1.3 — side-effecting execution (tier-dynamic).
    "push_playbook",
    "run_playbook",
    # Connector & playbook-run discovery — shared with the SOC triage path.
    # RECONCILIATION_PLAN: connector-awareness is authoring (knowing what
    # connectors are installed/configured/running + what actions a step can
    # call), NOT alert investigation, so it lives in the library. Tier 1.
    "get_run_env",
    "list_configured_connectors",
    "list_playbook_runs",
    "find_containment_actions",
    "find_enrichment_actions",
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
    "healthcheck_connector": 1,
    "diagnose_yaml_against_pb_execution": 1,
    # Phase 0 — pure local compute (no FSR I/O).
    "validate_yaml": 0,
    "compile_yaml": 0,
    "analyze_playbook": 0,
    # Local compile from the recorded trace (offline by default; the push is a
    # separate, tier-gated tool). Pure authoring → tier 0.
    "build_playbook_from_trace": 0,
    # "find_step_recipe": 0,  # hidden — see SAFE_TOOLS
    "emit_choice_card": 0,
    "emit_action_card": 0,
    "emit_manual_input": 0,
    "emit_capability_gap_card": 0,
    "emit_playbook_offer": 0,
    "propose_http_fallback": 0,
    # Phase 1.2 — read-only FSR API.
    # Tier-dynamic. Resolved per call.
    "run_op": -1,
    "step_through_playbook": -1,
    "dry_run_playbook": -1,
    "push_playbook": -1,
    "run_playbook": -1,
    # Connector & playbook-run discovery — read-only, auto-confirm.
    "get_run_env": 1,
    "list_configured_connectors": 1,
    "list_playbook_runs": 1,
    "find_containment_actions": 1,
    "find_enrichment_actions": 1,
}

# Op-name / category classifiers used as fallback when op_safety has no
# row for a given (connector, op). Mirrors the heuristics from
# `probe_op_safety` so the wrapper degrades gracefully on fresh DBs.
_REMEDIATION_CATEGORIES = {"remediation", "containment"}
_MANAGEMENT_CATEGORIES = {"management"}
_SAFE_CATEGORIES = {"investigation", "query", "utilities", "enrichment", "verification"}

# Keys whose values are masked to `***` in any human-facing preview / audit
# surface (S4). Covers common credential-field spellings so a tool that names
# its secret `passwd` / `client_credential` / `private_key` doesn't leak it into
# an approval card. `secret` also catches `client_secret`; `api[_-]?key` catches
# `apikey`/`api-key`; `key` is scoped to *_key / private/access/session variants
# rather than matching every field containing "key".
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)("
    r"passw(or)?d|passwd|pwd"
    r"|token"
    r"|api[_-]?key"
    r"|secret"
    r"|authorization|bearer"
    r"|credential"
    r"|(private|access|session|secret|signing)[_-]?key"
    r")"
)


_DB_PATH = default_db_path()


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


def _op_presence(connector: str, op: str) -> tuple[bool, bool]:
    """Return (op_exists, connector_known) from the reference catalog.

    op_exists       — there is an `operations` row for (connector, op).
    connector_known — the catalog has at least one op for `connector`.

    A guessed / mistyped op on a connector we *do* have a catalog for is
    ``(False, True)``: it cannot execute (it doesn't exist), so the tier gate
    should let it dispatch to a self-correcting ``unknown_operation`` error
    rather than escalate it to human approval. Best-effort: any DB problem
    returns ``(False, False)`` so the caller stays conservative (escalates).
    """
    if not connector or not op or not _DB_PATH.exists():
        return False, False
    try:
        con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            op_row = cur.execute(
                "SELECT 1 FROM operations WHERE connector_name=? AND op_name=? LIMIT 1",
                (connector, op),
            ).fetchone()
            conn_row = cur.execute(
                "SELECT 1 FROM operations WHERE connector_name=? LIMIT 1",
                (connector,),
            ).fetchone()
            return bool(op_row), bool(conn_row)
        finally:
            con.close()
    except sqlite3.Error:
        return False, False


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
    if safety == "unsafe":
        # A probe-flagged destructive op MUST win over the catch-all
        # `investigation` category below. FortiEDR's `isolate_collector` /
        # `set_collector_state` are categorized `investigation` in the catalog
        # but are real host-containment actions (op_safety='unsafe'). Without
        # this ordering they auto-allow at tier 2 (no approval card) AND get
        # dropped from find_containment_actions' tier>=3 guard — so "isolate
        # this host" would execute ungated and the proper op wouldn't surface.
        return 4
    if safety == "safe" or category in _SAFE_CATEGORIES:
        # Third-party query → tier 2; FSR-internal query → tier 1.
        # We don't have a reliable "is FSR-internal" flag; treat all
        # external reads as tier 2 (auto-allow + log).
        return 2
    # Unknown / unclassified. Before escalating to approval, separate a
    # guessed/mistyped op from a real-but-unclassified one. If the connector's
    # catalog is known to us but this op isn't in it, the op cannot run — it
    # doesn't exist. Gating a non-existent op for human approval just halts the
    # hunt and hides the `unknown_operation` error (with the real op names) that
    # lets the agent self-correct. Let it dispatch (tier 1) so run_op bounces
    # back the correction. A connector we have NO catalog for stays conservative
    # (tier 3) — it could carry a real mutating op we simply haven't probed.
    op_exists, connector_known = _op_presence(connector, op)
    if connector_known and not op_exists:
        return 1
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


# Approval previews are for human display in the widget, which renders them as
# JSON.stringify(preview.args). Unbounded values (e.g. push_playbook's full
# `yaml_text`, or a 60-IOC list) produce a multi-KB wall of text that makes the
# approval popup unusable. Cap individual strings and list lengths so the
# preview stays a readable summary, never the whole payload.
_PREVIEW_MAX_STR = 600
_PREVIEW_MAX_LIST = 50


def _mask_value(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: ("***" if _SENSITIVE_KEY_RE.search(k) else _mask_value(val)) for k, val in v.items()}
    if isinstance(v, list):
        return [_mask_value(x) for x in v]
    return v


def _truncate_value(v: Any) -> Any:
    """Bound a (already-masked) preview value to a human-readable size."""
    if isinstance(v, str):
        if len(v) > _PREVIEW_MAX_STR:
            return v[:_PREVIEW_MAX_STR] + f"… [+{len(v) - _PREVIEW_MAX_STR} chars truncated]"
        return v
    if isinstance(v, dict):
        return {k: _truncate_value(val) for k, val in v.items()}
    if isinstance(v, list):
        capped = [_truncate_value(x) for x in v[:_PREVIEW_MAX_LIST]]
        if len(v) > _PREVIEW_MAX_LIST:
            capped.append(f"… [+{len(v) - _PREVIEW_MAX_LIST} more items truncated]")
        return capped
    return v


def _build_preview(name: str, args: dict[str, Any]) -> dict[str, Any]:
    masked = _truncate_value(_mask_value(args or {}))
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


# --- Read-only auto-approve policy ----------------------------------------
#
# Read-only actions (tier 1–2: FSR/third-party queries) auto-run without an
# approval card. This is the intended default — a SOC analyst shouldn't have to
# click "approve" to let the agent *look* at a record. The behavior used to be
# implicit in the `tier >= 3` gate; this flag makes it an explicit, documented,
# operator-toggleable policy.
#
#   FSR_AUTO_APPROVE_READONLY=1  (default) — tier 1–2 auto-run, tier 3+ gated.
#   FSR_AUTO_APPROVE_READONLY=0            — paranoid mode: tier 1+ all gated;
#                                            only tier-0 local tools auto-run.
#
# Deferred (not built here): "allow-once / always-allow this specific tool"
# — a per-(tool[,connector,op]) grant that survives one approval. This flag is
# the coarse read-only switch, not that per-tool machinery.
_READONLY_AUTO_APPROVE_OVERRIDE: bool | None = None  # test/host override


def set_readonly_auto_approve(enabled: bool | None) -> None:
    """Programmatic override for the read-only auto-approve flag. `None`
    reverts to the env default. Mirrors `set_eval_policy`."""
    global _READONLY_AUTO_APPROVE_OVERRIDE
    _READONLY_AUTO_APPROVE_OVERRIDE = enabled


def _readonly_auto_approve() -> bool:
    if _READONLY_AUTO_APPROVE_OVERRIDE is not None:
        return _READONLY_AUTO_APPROVE_OVERRIDE
    raw = os.environ.get("FSR_AUTO_APPROVE_READONLY")
    if raw is None:
        return True  # default: read-only auto-runs
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _approval_floor() -> int:
    """Minimum tier that requires human approval. Default 3 (read-only
    tier 1–2 auto-runs). With read-only auto-approve disabled, everything
    above tier 0 (local, side-effect-free tools) is gated."""
    return 3 if _readonly_auto_approve() else 1


# --- Per-session approval grants -------------------------------------------
#
# Once a human approves a tool/action, the grant store tracks future approvals:
#   - "once": auto-approve exactly the next matching call, then consume the grant.
#   - "always": auto-approve all matching future calls (until session ends).
#
# Key: (session_id, tool_name, op_key) where op_key is None for regular tools
# or f"{connector}:{operation}" for run_op-style dynamic dispatch.
# Value: "once" | "always"
#
# In-memory only; persistence is out of scope for this phase.

_APPROVAL_GRANTS: dict[tuple[str, str, str | None], str] = {}


def grant_tool_approval(
    session_id: str, tool_name: str, *, op_key: str | None = None, mode: str = "once"
) -> None:
    """Grant a tool approval for a session. Mode is 'once' (consume after next
    matching call) or 'always' (persist until session ends).

    Args:
        session_id: Session identifier (e.g., chat session UUID).
        tool_name: Name of the tool being granted (e.g., 'run_op').
        op_key: Optional operation key for tools with dynamic tier (e.g.,
            'fortigate:block_ip' for run_op). None for tools with static tier.
        mode: 'once' or 'always'. Defaults to 'once'.
    """
    if mode not in ("once", "always"):
        raise ValueError(f"Invalid grant mode {mode!r}; must be 'once' or 'always'")
    key = (session_id, tool_name, op_key)
    _APPROVAL_GRANTS[key] = mode


def _consume_grant(
    session_id: str, tool_name: str, op_key: str | None = None
) -> bool:
    """Check if a matching grant exists and consume it if mode == 'once'.

    Returns True if a grant was found (and consumed for 'once' mode),
    False otherwise. After this returns True, dispatch() treats the call
    as if a human approved it."""
    key = (session_id, tool_name, op_key)
    mode = _APPROVAL_GRANTS.get(key)
    if mode is None:
        return False
    if mode == "once":
        del _APPROVAL_GRANTS[key]
    return True


def clear_session_grants(session_id: str) -> None:
    """Clear all grants (both 'once' and 'always') for a session. Call this
    when the session ends or on logout."""
    to_delete = [k for k in _APPROVAL_GRANTS if k[0] == session_id]
    for k in to_delete:
        del _APPROVAL_GRANTS[k]


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
    "emit_capability_gap_card": {
        "type": "object",
        "required": ["id", "missing", "why", "fix_steps", "resume"],
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1,
                   "description": "Stable card id; echoed on resume."},
            "missing": {"type": "string", "minLength": 1,
                        "description": "Capability the investigation needs, "
                                       "in plain English (e.g. 'IP containment')."},
            "why": {"type": "string", "minLength": 1,
                    "description": "One line on why it's unavailable here."},
            "fix_steps": {
                "type": "array",
                "minItems": 1,
                "description": "Ordered concrete steps to enable the capability.",
                "items": {"type": "string", "minLength": 1},
            },
            "resume": {
                "type": "object",
                "required": ["label", "value"],
                "additionalProperties": False,
                "description": "Re-check button. On click the widget resumes "
                               "the turn echoing `value`; the agent re-runs the "
                               "blocked discovery and continues.",
                "properties": {
                    "label": {"type": "string", "minLength": 1},
                    "value": {"type": "string", "minLength": 1,
                              "description": "Machine-readable; echoed on resume."},
                },
            },
            "tips": {
                "type": "array",
                "description": "Automation/UX recommendations.",
                "items": {
                    "type": "object",
                    "required": ["text"],
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "hint": {"type": "string"},
                    },
                },
            },
            "alternatives": {
                "type": "array",
                "description": "Manual fallbacks (resume semantics like a "
                               "choice_card option).",
                "items": {
                    "type": "object",
                    "required": ["label", "value"],
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "value": {"type": "string", "minLength": 1},
                        "hint": {"type": "string"},
                    },
                },
            },
            "docs_url": {"type": "string"},
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


def _ensure_mcp_materialized() -> None:
    """Lazy hook: materialize FortiSOAR native-MCP-gateway tools into REGISTRY
    before the tool list is sent to the LLM. No-op unless the connector called
    ``materializer.configure(mcp_allowlist=...)`` at session setup; default
    empty allow-list → nothing materialized. See
    :mod:`fsr_playbooks.mcp_server.materializer`."""
    try:
        from ..mcp_server import materializer
    except ImportError:
        return
    materializer.ensure_initialized()


def anthropic_tools() -> list[dict[str, Any]]:
    """Anthropic's tool-use schema shape."""
    _ensure_mcp_materialized()
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in REGISTRY.values()
    ]


def openai_tools() -> list[dict[str, Any]]:
    """OpenAI / LM Studio function-calling schema shape. Same registry,
    different envelope: `{type:"function", function:{name, description, parameters}}`."""
    _ensure_mcp_materialized()
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


def dispatch(
    name: str, arguments: dict[str, Any], *, _internal: bool = False,
    session_id: str | None = None
) -> Any:
    """Tier-aware dispatch (HITL_GUARDRAILS_PLAN Phase 0).

    Tier 0–2: execute immediately, append an audit row.
    Tier 3+:  if `arguments` lacks a valid `_approval_token`, return a
              `{pending_approval: true, …}` envelope without calling the
              underlying tool. The chat-app loop (Phase 1) suspends on
              this envelope and renders the approval card; on approve,
              the loop re-dispatches with `_approval_token` set.

    Approval grants: if a matching grant exists for (session_id, tool_name),
    the pending_approval envelope is skipped and the action auto-runs,
    audited as 'auto_allow_grant'. Grants can be 'once' (consumed on match)
    or 'always' (persistent until session ends).
    """
    spec = REGISTRY.get(name)
    if spec is None:
        return {"error": f"unknown tool: {name}"}

    raw_args = dict(arguments or {})
    # `_approved` is an internal-only sentinel: it bypasses the HITL tier
    # gate and may ONLY be set by the resume path (post human-approval),
    # which calls dispatch with `_internal=True`. Any `_approved` arriving
    # on a normal dispatch originates from untrusted input — the LLM's
    # tool-use args or a compromised/MITM'd wire frame — and is a gate-
    # bypass injection attempt (S1). Reject it loudly rather than honor it.
    if "_approved" in raw_args and not _internal:
        logging.getLogger(__name__).error(
            "rejected wire-supplied _approved on tool '%s' "
            "(tier-gate bypass attempt)",
            name,
        )
        return {
            "ok": False,
            "code": "reserved_key_rejected",
            "error": (
                "The '_approved' flag is internal-only and cannot be supplied "
                "in tool arguments. The action was NOT executed."
            ),
        }
    approved = bool(raw_args.pop("_approved", False)) if _internal else False
    summary = raw_args.pop("_summary", None)

    # Validate tool arguments using pydantic models if available.
    # Validation errors don't fail the dispatch — they're surfaced as
    # tool results so the model can see and potentially fix bad args.
    try:
        from .tool_models import TOOL_MODELS
        if name in TOOL_MODELS:
            try:
                TOOL_MODELS[name](**raw_args)
            except Exception as e:
                from pydantic import ValidationError
                if isinstance(e, ValidationError):
                    errors = "; ".join(
                        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                        for err in e.errors()
                    )
                    return {"error": f"invalid arguments for {name}: {errors}"}
                raise
    except ImportError:
        pass  # tool_models not available; skip validation
    tier = _resolve_tier(name, raw_args)

    floor = _approval_floor()
    if tier >= floor and not approved:
        # Check for approval grants before policy/pending_approval.
        # Build op_key for tools with dynamic tier (run_op, etc.).
        op_key: str | None = None
        if name == "run_op":
            connector = (raw_args or {}).get("connector") or ""
            op = (raw_args or {}).get("op") or ""
            op_key = f"{connector}:{op}" if connector and op else None

        if session_id and _consume_grant(session_id, name, op_key):
            # Grant exists (and 'once' grants are consumed). Execute with the
            # grant decision, bypassing the approval envelope.
            try:
                result = spec.fn(**raw_args)
            except TypeError as e:
                return {"error": f"bad arguments for {name}: {e}"}
            except Exception as e:
                return {"error": f"{type(e).__name__}: {e}"}
            _record_audit(name, raw_args, tier, "auto_allow_grant")
            return result

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
