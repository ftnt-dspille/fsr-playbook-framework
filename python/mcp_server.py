"""FSR Playbook MCP server.

Exposes the compiler + reference store as MCP tools for any agent
(Claude Code, IDE plugins) to author FortiSOAR playbooks via tool use.

Tools:
  find_connector       — fuzzy-search 714 connectors by name/category/desc
  find_operation       — list or search ops for a specific connector
  get_op_schema        — full param schema + best available output shape
  get_connector_source — fetch operations.py source code (cached after first fetch)
  run_op               — execute one op live; infers + caches real output shape
  get_step_type        — schema + examples for a playbook step type
  find_jinja_filter    — search the Jinja filter catalog
  render_jinja         — render a template against the live FSR endpoint
  search_playbooks     — FTS over playbook_seen patterns
  validate_yaml        — compiler dry-run → structured errors
  compile_yaml         — compile YAML → FSR WorkflowCollection JSON string

Run:
  python python/mcp_server.py          (stdio transport, default)
  fsrpb mcp                            (via CLI entry-point)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"

# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _infer_shape(value: Any, _depth: int = 0) -> Any:
    """Recursively replace leaf values with their type names.

    Keeps dict structure intact so agents can see key names.
    Lists become [<shape of first element>] to stay concise.
    Caps recursion at depth 10 to guard against deeply nested blobs.
    """
    if _depth > 10:
        return "..."
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return []
        return [_infer_shape(value[0], _depth + 1)]
    if isinstance(value, dict):
        return {k: _infer_shape(v, _depth + 1) for k, v in value.items()}
    return type(value).__name__


def _store_observed_schema(connector: str, op: str, data: Any) -> None:
    """Infer shape from live result and persist to operations + verifications."""
    shape = _infer_shape(data)
    shape_json = json.dumps(shape)
    import datetime
    ts = datetime.datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE operations SET output_schema_observed=? WHERE connector_name=? AND op_name=?",
            (shape_json, connector, op),
        )
        conn.execute(
            """INSERT OR REPLACE INTO verifications (kind, key, method, status, ts, notes)
               VALUES ('operation', ?, 'live_op_exec', 'tested_pass', ?, ?)""",
            (f"{connector}:{op}", ts, shape_json[:2000]),
        )


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "fsrpb",
    instructions=(
        "FortiSOAR playbook authoring tools. "
        "Use find_connector → find_operation → get_op_schema to build connector steps. "
        "Use get_step_type for non-connector step schemas. "
        "Use validate_yaml before compile_yaml to catch errors early. "
        "All YAML must conform to the simplified IR documented in AUTHORING.md."
    ),
)


# ---------------------------------------------------------------------------
# find_connector
# ---------------------------------------------------------------------------

@mcp.tool()
def find_connector(q: str, limit: int = 15) -> list[dict[str, Any]]:
    """Fuzzy-search connectors by name, label, category, or description.

    Returns a list of matching connectors with name, label, category, and
    description fields.  Use the `name` field as the connector identifier
    in YAML steps.
    """
    with _db() as conn:
        # Try FTS first (kind='operation' rows have connector name in key)
        # For connector search, fall back to LIKE on connectors table
        rows = _rows(
            conn,
            """SELECT name, label, category, description
               FROM connectors
               WHERE name   LIKE '%' || ? || '%'
                  OR label  LIKE '%' || ? || '%'
                  OR category LIKE '%' || ? || '%'
                  OR description LIKE '%' || ? || '%'
               ORDER BY
                 (name LIKE ? || '%') DESC,
                 name
               LIMIT ?""",
            (q, q, q, q, q, limit),
        )
        if not rows:
            # Broaden: word-by-word
            words = q.split()
            if words:
                w = words[0]
                rows = _rows(
                    conn,
                    """SELECT name, label, category, description
                       FROM connectors
                       WHERE name LIKE '%'||?||'%' OR label LIKE '%'||?||'%'
                       ORDER BY name LIMIT ?""",
                    (w, w, limit),
                )
        return rows


# ---------------------------------------------------------------------------
# find_operation
# ---------------------------------------------------------------------------

@mcp.tool()
def find_operation(connector: str, q: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """List or search operations for a connector.

    Pass `connector` as the connector name (from find_connector).
    `q` is an optional substring filter on op name, title, or description.
    Returns op_name, title, description, annotation.
    """
    with _db() as conn:
        if q:
            rows = _rows(
                conn,
                """SELECT op_name, title, description, annotation
                   FROM operations
                   WHERE connector_name = ?
                     AND (op_name LIKE '%'||?||'%'
                          OR title LIKE '%'||?||'%'
                          OR description LIKE '%'||?||'%')
                   ORDER BY op_name LIMIT ?""",
                (connector, q, q, q, limit),
            )
        else:
            rows = _rows(
                conn,
                """SELECT op_name, title, description, annotation
                   FROM operations
                   WHERE connector_name = ?
                   ORDER BY op_name LIMIT ?""",
                (connector, limit),
            )
        return rows


# ---------------------------------------------------------------------------
# get_op_schema
# ---------------------------------------------------------------------------

@mcp.tool()
def get_op_schema(connector: str, op: str) -> dict[str, Any]:
    """Return the full parameter schema for a connector operation.

    Includes:
    - `params` — input parameters with required/type/picklist info
    - `output_schema_json` — static shape from the connector's info.json (may be
      absent or incomplete for many connectors)
    - `output_schema_observed` — live-run inferred shape from a real FSR execution;
      populated by `run_op` the first time the op is exercised.  This is the most
      reliable source of truth for what the step actually returns.
    - `output_schema_hint` — set to "run run_op to observe real output" when neither
      schema is available, so callers know to execute the op once.
    """
    with _db() as conn:
        op_row = _rows(
            conn,
            "SELECT * FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        )
        if not op_row:
            return {"error": f"operation '{op}' not found on connector '{connector}'"}

        params = _rows(
            conn,
            """SELECT param_name, title, type, required, editable, visible,
                      description, tooltip, placeholder, default_value,
                      options_json
               FROM operation_params
               WHERE connector_name=? AND op_name=?
               ORDER BY ord""",
            (connector, op),
        )
        for p in params:
            if p.get("options_json"):
                try:
                    p["options_json"] = json.loads(p["options_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
        result = dict(op_row[0])
        for col in ("output_schema_json", "conditional_output_schema_json",
                    "output_schema_observed"):
            if result.get(col):
                try:
                    result[col] = json.loads(result[col])
                except (json.JSONDecodeError, TypeError):
                    pass
        result["params"] = params
        # Surface a hint when no output shape is known at all
        if not result.get("output_schema_json") and not result.get("output_schema_observed"):
            result["output_schema_hint"] = (
                "No output schema available. Call run_op with sample params to observe "
                "the real output shape and populate output_schema_observed."
            )
        return result


# Op-name prefixes that are almost certainly read-only API calls.
_SAFE_NAME_PREFIXES: tuple[str, ...] = (
    "get_", "list_", "search_", "fetch_", "query_", "check_",
    "describe_", "lookup_", "find_", "read_", "show_", "view_",
)
# Op-name substrings that indicate destructive / side-effecting calls.
_DESTRUCTIVE_NAME_PARTS: tuple[str, ...] = (
    "delete_", "remove_", "block_", "quarantine_", "isolate_",
    "kill_", "terminate_", "disable_", "revoke_", "purge_",
    "wipe_", "destroy_", "reset_", "clear_", "close_",
    "ban_", "suspend_", "decommission_",
)
# Category strings that signal destructive intent.
_DESTRUCTIVE_CATEGORIES: frozenset[str] = frozenset(
    {"remediation", "Remediation", "containment", "management"}
)


def _op_risk(op_name: str, category: str | None) -> str:
    """Return 'safe', 'destructive', or 'unknown'.

    Uses op name patterns first (most reliable — 86% of ops have no category),
    then falls back to category, then defaults to 'unknown'.
    """
    name_lower = op_name.lower()
    if any(name_lower.startswith(p) for p in _SAFE_NAME_PREFIXES):
        return "safe"
    if any(p in name_lower for p in _DESTRUCTIVE_NAME_PARTS):
        return "destructive"
    if category and category.lower() in {c.lower() for c in _DESTRUCTIVE_CATEGORIES}:
        return "destructive"
    return "unknown"


# ---------------------------------------------------------------------------
# get_connector_source
# ---------------------------------------------------------------------------
# TODO: Find and wire the DELETE endpoint for dev copies so we can clean up
# after fetching source. DELETE /api/integration/connector/development/entity/{dev_id}/
# returns 403 with current API-key auth — needs an admin-scoped key or a
# different route. Until then, each connector accumulates at most one dev copy
# (FSR returns the same dev_id on repeat calls to edit_repo_connector).

@mcp.tool()
def get_connector_source(connector: str, file: str = "operations.py") -> dict[str, Any]:
    """Fetch the Python source code for a connector from the live FSR instance.

    Returns the raw content of `operations.py` (or another file in the connector
    package — `connector.py`, `info.json`, `release_notes.md`).

    **Use this sparingly** — only when the op name and parameter schema are not
    sufficient to understand what the connector actually does (e.g. undocumented
    side effects, ambiguous return shape, or a newly added op with no description).

    **How it works:**
    FSR has no direct file-read API for installed connectors. This tool calls
    `POST /api/integration/connector/development/entity/{id}/` with
    `{edit_repo_connector: true}` to create a development copy, then reads the
    file from that copy.  The result is cached in the local reference store so
    subsequent calls return immediately without hitting the FSR instance again.

    On success: `{ok: true, source: "...", cached: bool}`
    On failure: `{ok: false, error: "..."}`
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client
    except ImportError:
        return {"error": "probes module not available"}

    # --- cache hit ---
    with _db() as conn:
        row = conn.execute(
            "SELECT source_code, version FROM connectors WHERE name=?", (connector,)
        ).fetchone()
        if row and row["source_code"] and file == "operations.py":
            return {"ok": True, "source": row["source_code"], "cached": True}
        version = row["version"] if row else None
    if not version:
        return {"ok": False, "error": f"connector '{connector}' not found in store"}

    client = get_client()
    if client is None:
        return {"ok": False, "error": "FSR instance not configured"}

    # --- Step 1: resolve the connector's numeric entity id ---
    try:
        detail = client.post(f"/api/integration/connectors/{connector}/{version}/?format=json", {})
        entity_id = detail.get("id") if isinstance(detail, dict) else None
    except Exception as exc:
        return {"ok": False, "error": f"could not resolve connector entity id: {exc}"}
    if not entity_id:
        return {"ok": False, "error": f"connector '{connector}' not found on FSR instance"}

    # --- Step 2: get or create the dev copy ---
    try:
        meta = client.post(
            f"/api/integration/connector/development/entity/{entity_id}/?format=json",
            {"edit_repo_connector": True},
        )
    except Exception as exc:
        return {"ok": False, "error": f"dev-copy creation failed: {exc}"}

    if not isinstance(meta, dict):
        return {"ok": False, "error": f"unexpected response from dev-copy endpoint: {meta!r:.200}"}

    dev_id = meta.get("id")
    if not dev_id:
        return {"ok": False, "error": "dev-copy response missing entity id"}

    # Derive the dev directory name from the tree key
    tree = meta.get("tree", {})
    dev_dir = next(iter(tree), None)
    if not dev_dir:
        # Fallback: construct it from name + version
        version_str = meta.get("version", "")
        dev_dir = f"{connector}_{version_str.replace('.', '_')}_dev"

    # --- Step 2: fetch the file ---
    xpath = f"/{dev_dir}/{file}"
    try:
        file_resp = client.post(
            f"/api/integration/connector/development/entity/{dev_id}/files/?format=json",
            {"xpath": xpath},
        )
    except Exception as exc:
        return {"ok": False, "error": f"file fetch failed (xpath={xpath}): {exc}"}

    if isinstance(file_resp, dict):
        content = file_resp.get("fileContent")
    elif isinstance(file_resp, str):
        content = file_resp
    else:
        return {"ok": False, "error": f"unexpected file response type: {type(file_resp).__name__}"}

    if not content:
        return {"ok": False, "error": f"empty response for {xpath}"}

    # --- Cache operations.py ---
    if file == "operations.py":
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE connectors SET source_code=? WHERE name=?",
                (content, connector),
            )

    return {"ok": True, "source": content, "cached": False}


# ---------------------------------------------------------------------------
# run_op
# ---------------------------------------------------------------------------

@mcp.tool()
def run_op(
    connector: str,
    op: str,
    params: dict[str, Any] | None = None,
    config: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Execute a single connector operation on the live FSR instance and return
    its real output.

    This is the authoritative way to discover what a step produces when
    info.json has no output_schema or the static schema is incomplete.

    **Guardrails** — operations are classified by their `category` field:
    - `query / investigation / utilities` → **safe**, runs automatically.
    - `remediation / containment / management` → **destructive**, requires
      `confirm=True`.  The tool returns `{requires_confirmation: true}` when
      confirm is omitted so the caller (agent or user) can decide explicitly.
    - Any other / unknown category → also requires `confirm=True`.

    Pass `confirm=True` only after the user has approved the action or you are
    certain it is a read-only probe with no side effects.

    On success:
    - Returns `{ok: true, data: <actual_output>, output_shape: <inferred_type_shape>}`
    - Stores the inferred shape in `output_schema_observed` so `get_op_schema`
      returns it on all future calls without re-running the operation.
    - Records a `live_op_exec / tested_pass` verification row.

    On failure:
    - Returns `{ok: false, status: <str>, message: <str>}` with the FSR error.
    - Records `live_op_exec / tested_fail` so the store tracks the attempt.

    `params` — dict of input parameter values for the operation.
    `config` — optional connector config name (leave empty for the default config).
    `confirm` — set True to execute operations that are not auto-safe.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client, get_config
    except ImportError:
        return {"error": "probes module not available"}

    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}

    # Resolve connector version + op category from store
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        crow = conn.execute(
            "SELECT version FROM connectors WHERE name=?", (connector,)
        ).fetchone()
        op_row = conn.execute(
            "SELECT category FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
    if crow is None:
        return {"error": f"connector '{connector}' not found in store"}
    version = crow["version"]

    category = op_row["category"] if op_row else None
    risk = _op_risk(op, category)
    if risk != "safe" and not confirm:
        return {
            "requires_confirmation": True,
            "risk": risk,
            "category": category or "unknown",
            "connector": connector,
            "op": op,
            "message": (
                f"Operation '{op}' on '{connector}' has risk level '{risk}' "
                f"(category: {category!r}). Re-call with confirm=True after the "
                "user has approved, or confirm this is a safe read-only probe."
            ),
        }

    body = {
        "connector": connector,
        "operation": op,
        "version": version,
        "config": config,
        "params": params or {},
    }

    client = get_client()
    try:
        resp = client.post("/api/integration/execute/", body)
    except Exception as exc:  # noqa: BLE001
        r = getattr(exc, "response", None)
        status = getattr(r, "status_code", "?")
        msg = (r.text if r is not None else str(exc))[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return {"ok": False, "status": str(status), "message": msg}

    if not isinstance(resp, dict):
        return {"ok": False, "message": f"unexpected response type: {type(resp).__name__}"}

    exec_status = resp.get("status", "")
    if exec_status not in ("Success", "success", "Completed", "completed", ""):
        msg = resp.get("message", "") or json.dumps(resp)[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return {"ok": False, "status": exec_status, "message": msg}

    data = resp.get("data", resp)
    shape = _infer_shape(data)
    _store_observed_schema(connector, op, data)
    return {"ok": True, "data": data, "output_shape": shape}


def _record_verification(connector: str, op: str, status: str, notes: str) -> None:
    import datetime
    ts = datetime.datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO verifications (kind, key, method, status, ts, notes)
               VALUES ('operation', ?, 'live_op_exec', ?, ?, ?)""",
            (f"{connector}:{op}", status, ts, notes),
        )


# ---------------------------------------------------------------------------
# get_step_type
# ---------------------------------------------------------------------------

# Friendly YAML short names → canonical FSR step type names. Mirrors
# compiler.resolver.SHORT_TYPE_TO_FSR; duplicated here to avoid a
# resolver import in the MCP layer.
_SHORT_TO_CANONICAL: dict[str, str] = {
    "connector": "Connectors",
    "set_variable": "SetVariable",
    "decision": "Decision",
    "start": "cybersponse.abstract_trigger",
    "find_record": "FindRecords",
    "update_record": "UpdateRecord",
    "create_record": "InsertData",
    "insert_record": "InsertData",
    "delay": "Delay",
    "manual_input": "ManualInput",
    "code_snippet": "CodeSnippet",
    "approval": "Approval",
    "workflow_reference": "WorkflowReference",
    "stop": "Connectors",
    "end": "Connectors",
    "start_on_create": "cybersponse.post_create",
    "start_on_update": "cybersponse.post_update",
}

# Friendly authoring forms the compiler resolver normalizes. The AI
# should prefer these over the wire form when both work — they're
# shorter, more readable, and harder to malform. Keys that aren't in
# the friendly schema are rejected by the resolver. Coverage matches
# every short type the resolver handles in compiler.resolver.
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
        "accepted_keys": "flat dict of {var_name: value}",
        "example": {
            "type": "set_variable",
            "name": "Stash inputs",
            "arguments": {
                "source_ip": "{{ vars.input.records[0].sourceIp }}",
                "verdict": "pending",
            },
        },
        "do_not_use": [
            "arg_list: [{name, value}, ...] — legacy sugar; use flat dict",
        ],
    },
    "decision": {
        "accepted_keys": ["conditions"],
        "branches": (
            "every conditions[].option must have a branches[label] entry; "
            "fall-through goes on the decision step's `next:`, NOT a branch"
        ),
        "example": {
            "type": "decision",
            "arguments": {
                "conditions": [
                    {"option": "Critical", "condition": "{{ vars.score > 50 }}"},
                ],
            },
            "branches": {"Critical": "set_critical"},
            "next": "set_low",
        },
        "do_not_use": [
            "branch labels that aren't in conditions[].option — "
            "use `next:` for the catch-all default instead",
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
        "accepted_keys": ["title", "description", "options", "inputs"],
        "type_value": "InputBased (only valid value; omit to let compiler fill)",
        "options_shape": "list of strings or {option, primary?} dicts",
        "branches": "each option label becomes a branches: key on the step",
        "inputs_shape": (
            "list of {name, kind, label?, tooltip?, required?, default?, "
            "options?} — kind is one of: text, textarea, richtext, email, "
            "url, password, integer, checkbox, select, datetime, json. "
            "After the operator submits, fields are read at "
            "`vars.steps.<step_name>.input.<name>`. `kind: select` requires "
            "`options:` (list of strings or jinja that resolves to a list)."
        ),
        "example": {
            "type": "manual_input",
            "name": "Triage decision",
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
                "options": [
                    {"option": "approve", "primary": True},
                    {"option": "reject"},
                ],
            },
            "branches": {"approve": "act", "reject": "drop"},
        },
        "do_not_use": [
            "type: textarea / single-select / free-text (no such dispatch — "
            "use `inputs: [{kind: textarea, ...}]` for a textarea field)",
            "label, message (not valid keys — use title/description)",
            "timeout (FSR ignores it)",
            "vars.steps.<id>.input.choice (does not exist; route via branches)",
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


@mcp.tool()
def get_step_type(name: str, verbose: bool = False) -> dict[str, Any]:
    """Return schema and examples for a playbook step type.

    `name` can be the friendly YAML short type (`manual_input`,
    `set_variable`, `decision`, ...) or the canonical FSR name
    (`ManualInput`, `SetVariable`, `Decision`). Friendly short names
    map to their canonical form. The response includes a
    `friendly_form` block with the YAML-author-facing schema (the
    keys our compiler accepts) — prefer that over the wire-format
    `args_schema_json` when authoring YAML.

    By default the response is slim (~1–2 KB): the friendly_form
    suffices for authoring and raw corpus examples are omitted. Pass
    `verbose=True` for the full corpus dump (3 examples, no caps) —
    only useful when debugging an unusual case the friendly_form
    doesn't cover.
    """
    short = name
    canonical = _SHORT_TO_CANONICAL.get(name, name)
    with _db() as conn:
        rows = _rows(
            conn,
            """SELECT * FROM step_types
               WHERE name = ?
                  OR name LIKE '%'||?||'%'
               ORDER BY (name=?) DESC
               LIMIT 1""",
            (canonical, canonical, canonical),
        )
        if not rows:
            rows = _rows(
                conn,
                "SELECT * FROM step_types WHERE name LIKE '%'||?||'%' LIMIT 1",
                (canonical,),
            )
        if not rows:
            return {"error": f"step type '{name}' not found"}

        st = rows[0]
        for col in ("args_schema_json", "ui_schema_json"):
            if st.get(col):
                try:
                    st[col] = json.loads(st[col])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Examples are noisy for the LLM — one corpus playbook can drag
        # in a whole 18 KB Python code blob (verified: code_snippet).
        # When we have a friendly_form, that block already contains a
        # concise example, so skip the corpus dump unless verbose=True.
        # Otherwise, return at most one example and cap it.
        if short in _FRIENDLY_FORMS:
            st["friendly_form"] = _FRIENDLY_FORMS[short]
            if not verbose:
                st["examples_note"] = (
                    "raw corpus examples omitted; use the example in "
                    "friendly_form. Call get_step_type(verbose=True) "
                    "to fetch them."
                )
                return st
        limit = 3 if verbose else 1
        examples = _rows(
            conn,
            """SELECT from_playbook, snippet_json FROM step_examples
               WHERE step_type_name=? LIMIT ?""",
            (st["name"], limit),
        )
        for ex in examples:
            if ex.get("snippet_json"):
                try:
                    ex["snippet_json"] = json.loads(ex["snippet_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if not verbose:
                blob = json.dumps(ex.get("snippet_json"), default=str)
                if len(blob) > 2048:
                    ex["snippet_json"] = (
                        f"<{len(blob)} chars truncated — call with "
                        f"verbose=True for full payload>"
                    )
        st["examples"] = examples
        return st


# ---------------------------------------------------------------------------
# find_jinja_filter
# ---------------------------------------------------------------------------

@mcp.tool()
def find_jinja_filter(q: str, limit: int = 15) -> list[dict[str, Any]]:
    """Search the Jinja filter catalog by name, description, or example.

    Returns name, signature, description, example, output_type_observed,
    is_trusted (1 = live-tested), corpus_uses (real-world occurrence count
    in the live playbook corpus), and curated_doc when present (rich
    long-form notes for complex filters like json_query, picklist,
    fromIRI, resolveRange).

    Use `get_filter_examples(name)` after this to pull more real-world
    usages for a specific filter.
    """
    with _db() as conn:
        rows = _rows(
            conn,
            """SELECT jm.name, jm.signature, jm.description, jm.example,
                      jm.output_type_observed, jm.returns, jm.curated_doc,
                      COALESCE(vv.is_trusted, 0) AS is_trusted,
                      COALESCE((SELECT SUM(occurrences) FROM jinja_filter_usage u
                                WHERE u.filter_name = jm.name), 0) AS corpus_uses
               FROM jinja_macros jm
               LEFT JOIN v_verification_state vv
                 ON vv.kind='jinja_macro' AND vv.key=jm.name
               WHERE jm.name LIKE '%'||?||'%'
                  OR jm.description LIKE '%'||?||'%'
                  OR jm.example LIKE '%'||?||'%'
               ORDER BY (jm.name=?) DESC, corpus_uses DESC, is_trusted DESC, jm.name
               LIMIT ?""",
            (q, q, q, q, limit),
        )
        return rows


@mcp.tool()
def find_jinja_pattern(q: str, kind: str | None = None,
                      limit: int = 12) -> list[dict[str, Any]]:
    """Search the live-corpus Jinja-block catalog by substring + kind.

    Use this when you want to learn FSR idioms — `{% set x = vars.steps.foo %}`,
    `{% for r in vars.input.records %}`, conditional guards, etc — instead of
    only looking up filters. The corpus contains ~7,800 unique blocks mined
    from 1,669 live workflows.

    Args:
        q: substring to match against the raw block, head, vars, or filter chain
        kind: optional — restrict to one block kind. Useful values:
            "expr"   — `{{ … }}` expression blocks (most common)
            "set"    — `{% set var = … %}` assignments
            "for"    — `{% for x in … %}` loops
            "if"     — `{% if cond %}` guards (`elif` is a separate kind)
            "macro"  — `{% macro name(args) %}` definitions
            (omit kind to search across all)
        limit: max results (default 12, ordered by occurrences desc)

    Returns:
        list of {raw, kind, head, filters_csv, vars_csv, from_playbook,
                 from_step, step_type, occurrences}
    """
    sql = (
        """SELECT raw, kind, head, filters_csv, vars_csv,
                  from_playbook, from_step, step_type, occurrences
           FROM jinja_expressions
           WHERE (raw LIKE '%'||?||'%'
              OR head LIKE '%'||?||'%'
              OR COALESCE(filters_csv,'') LIKE '%'||?||'%'
              OR COALESCE(vars_csv,'') LIKE '%'||?||'%')"""
    )
    params: list = [q, q, q, q]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY occurrences DESC LIMIT ?"
    params.append(limit)
    with _db() as conn:
        return _rows(conn, sql, tuple(params))


@mcp.tool()
def get_filter_examples(name: str, limit: int = 8) -> dict[str, Any]:
    """Real-world usages of a Jinja filter, mined from the live playbook corpus.

    Returns the filter's curated long-form doc (when present) plus the top
    `limit` distinct expressions where it's used, ordered by frequency.
    Each example is a full `{{ … }}` block from a real workflow so the
    surrounding context (input shape, downstream chain) is visible.

    Args:
        name: filter name (exact match, e.g. "json_query")
        limit: how many distinct expressions to return (default 8)
    """
    with _db() as conn:
        meta = _rows(
            conn,
            """SELECT name, signature, description, curated_doc, output_type_observed,
                      output_type_declared, parameters_json
               FROM jinja_macros WHERE name = ? LIMIT 1""",
            (name,),
        )
        if not meta:
            return {"error": f"unknown filter {name!r}"}
        examples = _rows(
            conn,
            """SELECT expression, from_playbook, from_step, step_type, occurrences
               FROM jinja_filter_usage
               WHERE filter_name = ?
               ORDER BY occurrences DESC LIMIT ?""",
            (name, limit),
        )
        return {**meta[0], "examples": examples,
                "total_corpus_uses": sum(e["occurrences"] for e in examples)}


# ---------------------------------------------------------------------------
# render_jinja
# ---------------------------------------------------------------------------

@mcp.tool()
def render_jinja(template: str, context: dict[str, Any] | None = None,
                 from_pb_execution: str | None = None) -> dict[str, Any]:
    """Render a Jinja template against the live FSR Jinja engine.

    Uses the same engine as FSR's playbook runtime, so FSR-custom filters
    (`| tojson`, `| b64encode`, `| yaql`, etc.) all work.

    Args:
        template: Jinja source — e.g. `"{{ vars.steps.Get_org.records[0].id }}"`.
        context: dict of variable bindings (e.g. `{"value": [1, 2, 3]}`).
        from_pb_execution: optional workflow PK (string of digits) or task_id UUID.
            When set, the run's `{vars: {...env, steps: {<Name_us>: result}}}`
            is fetched and used as the base context. `context` is then merged
            on top so callers can override individual values for what-if tests.

    Returns:
        `{output: str}` on success, or `{error: str}` if the engine errored
        (template syntax issues, missing var, etc).

    Typical use: after triggering a playbook via `run-playbook`, pass the
    task_id here with the candidate Jinja for the NEXT step's argument to
    confirm it resolves correctly before wiring it into the YAML.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client
    except ImportError:
        return {"error": "pyfsr / probes module not available in this environment"}

    client = get_client()
    if client is None:
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}

    values: dict[str, Any] = {}
    if from_pb_execution:
        run_env = get_run_env(from_pb_execution)  # reuse the same transform
        if "error" in run_env:
            return {"error": f"from_pb_execution lookup failed: {run_env['error']}"}
        values = run_env.get("vars") and {"vars": run_env["vars"]} or {}
    if context:
        # Merge: vars-key deep-merges so caller can override individual fields
        # without losing the run's steps map.
        for k, v in context.items():
            if k == "vars" and isinstance(v, dict) and isinstance(values.get("vars"), dict):
                values["vars"] = {**values["vars"], **v}
            else:
                values[k] = v
    endpoint = "/api/wf/api/jinja-editor/"
    try:
        r = client.post(endpoint, data={"template": template, "values": values})
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:400]}

    if isinstance(r, str):
        return {"output": r}
    if isinstance(r, dict):
        for k in ("result", "output", "rendered", "value"):
            if isinstance(r.get(k), str):
                return {"output": r[k]}
        return {"output": json.dumps(r)}
    return {"error": f"unexpected response type: {type(r).__name__}"}


# ---------------------------------------------------------------------------
# search_playbooks
# ---------------------------------------------------------------------------

@mcp.tool()
def search_playbooks(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Full-text search over playbook patterns seen in production.

    Returns matching playbook names, collection names, and the connectors
    they use — useful for 'how do others do X' pattern mining.
    """
    with _db() as conn:
        # First try FTS table
        try:
            rows = _rows(
                conn,
                """SELECT kind, key, title, description
                   FROM fsr_fts
                   WHERE fsr_fts MATCH ?
                   LIMIT ?""",
                (q, limit),
            )
            if rows:
                return rows
        except sqlite3.OperationalError:
            pass

        # Fallback: LIKE on playbooks_seen
        rows = _rows(
            conn,
            """SELECT collection, workflow, uses_connectors_csv, step_count
               FROM playbooks_seen
               WHERE collection LIKE '%'||?||'%'
                  OR workflow LIKE '%'||?||'%'
                  OR uses_connectors_csv LIKE '%'||?||'%'
               ORDER BY step_count DESC
               LIMIT ?""",
            (q, q, q, limit),
        )
        return rows


# ---------------------------------------------------------------------------
# validate_yaml
# ---------------------------------------------------------------------------

@mcp.tool()
def validate_yaml(yaml_text: str) -> dict[str, Any]:
    """Validate a YAML playbook without producing output JSON.

    Runs the full compiler pipeline (parse → resolve → validate) and
    returns structured errors.  Each error has: code, path, message,
    suggestion (may be empty).

    Returns `{ok: true}` when the playbook is valid.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from compiler import compile_yaml as _compile
    except ImportError as exc:
        return {"error": f"compiler not available: {exc}"}

    result = _compile(yaml_text, DB_PATH)
    if result.ok:
        return {"ok": True}
    return {
        "ok": False,
        "errors": [
            {
                "code": e.code.value,
                "path": e.path,
                "message": e.message,
                "suggestion": e.suggestion or "",
            }
            for e in result.errors
        ],
    }


# ---------------------------------------------------------------------------
# compile_yaml
# ---------------------------------------------------------------------------

@mcp.tool()
def compile_yaml(yaml_text: str) -> dict[str, Any]:
    """Compile a YAML playbook to FortiSOAR WorkflowCollection JSON.

    Returns `{ok: true, json: "..."}` where `json` is the importable
    FSR JSON string, or `{ok: false, errors: [...]}` with structured
    compiler errors.

    The returned JSON can be pushed to FSR via `fsrpb push` or imported
    through the FSR UI (Administration → Import Wizard).
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from compiler import compile_yaml as _compile
    except ImportError as exc:
        return {"error": f"compiler not available: {exc}"}

    result = _compile(yaml_text, DB_PATH)
    if not result.ok:
        return {
            "ok": False,
            "errors": [
                {
                    "code": e.code.value,
                    "path": e.path,
                    "message": e.message,
                    "suggestion": e.suggestion or "",
                }
                for e in result.errors
            ],
        }
    return {"ok": True, "json": json.dumps(result.fsr_json, indent=2)}


@mcp.tool()
def get_run_env(pb_execution: str) -> dict[str, Any]:
    """Fetch the live Jinja context (`vars` + per-step results) of a past playbook execution.

    The single most useful tool when building the NEXT step in a playbook
    that consumes a prior step's output: it returns exactly what
    `vars.steps.<step_name_underscored>.<field>` will resolve to at runtime.
    Hits GET /api/wf/api/workflows/<pk>/?step_detail=true and rebuilds the
    same shape FSR's widget builds (transform: `step.name.replace(" ", "_")`,
    case preserved).

    Args:
        pb_execution: workflow PK (integer string e.g. "676747") OR task_id UUID

    Returns:
        {
          "status": "finished" | "failed" | ...,
          "name": "<workflow name>",
          "vars": {
            "<env field>": ...,
            "steps": {
              "<step name with spaces→_>": <step result>,
              ...
            }
          }
        }
        or {"error": "..."} on lookup failure.
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()

    # task_id (UUID) → workflow PK
    if "-" in pb_execution and not pb_execution.isdigit():
        try:
            pr = client.session.get(
                client.base_url + "/api/wf/api/workflows/"
                f"?task_id={pb_execution}&parent_wf__isnull=True&format=json&limit=1",
                verify=client.verify_ssl,
            )
            members = pr.json().get("hydra:member") or []
        except Exception as e:  # noqa: BLE001
            return {"error": f"task_id lookup failed: {e!r}"}
        if not members:
            return {"error": f"no workflow run found for task_id {pb_execution!r}"}
        pk_url = members[0].get("@id") or ""
        url = client.base_url + "/api" + pk_url + "?step_detail=true"
    else:
        url = client.base_url + f"/api/wf/api/workflows/{pb_execution}/?step_detail=true"

    try:
        r = client.session.get(url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"fetch failed: {e!r}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "body": r.text[:300]}
    data = r.json()
    env_obj = data.get("env") or {}
    steps_arr = data.get("steps") or []
    steps_map: dict = {}
    for s in steps_arr:
        name = s.get("name")
        if isinstance(name, str):
            steps_map[name.replace(" ", "_")] = s.get("result") or {}
    return {
        "status": data.get("status"),
        "name": data.get("name"),
        "vars": dict(env_obj, steps=steps_map),
    }


@mcp.tool()
def list_configured_connectors(probe: bool = False) -> dict[str, Any]:
    """List connectors that are configured AND active on the live FSR instance.

    A connector with no configuration cannot be called — it'll fail at runtime
    even if it appears in `find_connector`. Use this BEFORE picking which
    connector to put in a playbook.

    Args:
        probe: when True, also healthcheck each one (one HTTP call per
            connector — slower but gives live "Available"/"Disconnected"
            status). When False (default), just lists the configured set.

    Returns:
        {configured: [{name, version, label, config_count, status}], probed: bool}
        With probe=True, status is "Available", "Disconnected", or an error.
        With probe=False, status comes from the listing endpoint
        ("Completed" = config saved successfully).
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()
    try:
        r = client.session.post(
            client.base_url
            + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
            json={}, verify=client.verify_ssl,
        )
        rows = (r.json().get("data") or []) if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        return {"error": f"connector_details fetch failed: {e!r}"}

    out: list[dict] = []
    for x in rows:
        item = {
            "name": x.get("name"),
            "version": x.get("version"),
            "label": x.get("label"),
            "config_count": x.get("config_count"),
            "status": x.get("status"),
        }
        if probe and item["name"] and item["version"]:
            try:
                hr = client.session.get(
                    client.base_url
                    + f"/api/integration/connectors/healthcheck/{item['name']}/{item['version']}/",
                    verify=client.verify_ssl,
                )
                item["status"] = (hr.json().get("status") if hr.status_code == 200 else f"http_{hr.status_code}")
            except Exception as e:  # noqa: BLE001
                item["status"] = f"error:{e!r}"
        out.append(item)
    return {"configured": out, "probed": probe, "count": len(out)}


@mcp.tool()
def healthcheck_connector(name: str, version: str | None = None,
                          config: str | None = None) -> dict[str, Any]:
    """Live-check whether a single connector configuration is reachable.

    Use after `list_configured_connectors` to confirm the upstream service
    is actually up before recommending an op to the user.

    Args:
        name: connector name
        version: optional — when omitted, the first configured version is used
        config: optional config UUID — required when the connector has more
            than one configuration and you want a specific one

    Returns:
        {status, message, name, version, config_id}
        status="Available" → green; "Disconnected" → connector configured but
        upstream is down; HTTP 404 → no configuration on this instance.
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not import _env: {e!r}"}
    cfg = get_config()
    if not cfg.is_live():
        return {"error": "FSR instance not configured (FSR_BASE_URL / FSR_API_KEY missing in .env)"}
    client = get_client()
    if version is None:
        try:
            r = client.session.post(
                client.base_url
                + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
                json={}, verify=client.verify_ssl,
            )
            rows = (r.json().get("data") or []) if r.status_code == 200 else []
        except Exception as e:  # noqa: BLE001
            return {"error": f"version lookup failed: {e!r}"}
        cands = [x for x in rows if x.get("name") == name]
        if not cands:
            return {"error": f"no configured connector named {name!r}; pass version explicitly"}
        version = cands[0].get("version")
    url = f"/api/integration/connectors/healthcheck/{name}/{version}/"
    if config:
        url += f"?config={config}"
    try:
        r = client.session.get(client.base_url + url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"healthcheck request failed: {e!r}"}
    if r.status_code == 404:
        return {"name": name, "version": version, "status": "no-config",
                "http_status": 404, "message": "no configuration on this instance"}
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"name": name, "version": version, "http_status": r.status_code,
                "raw": r.text[:500]}


@mcp.tool()
def list_recent_failed_runs(limit: int = 20,
                            playbook: str | None = None,
                            include_finished: bool = False) -> list[dict[str, Any]]:
    """List recent workflow runs (default: failures only) for triage.

    Use this when the user says "my playbook is broken" without naming
    the playbook — fetches the most recently-modified failed/errored
    runs across the instance, with their task_id, name, status, and
    top-level error message.

    Args:
        limit: max rows to return (default 20)
        playbook: optional name filter (client-side substring match)
        include_finished: include finished runs too (default False —
            failed/finished_with_error/terminated only)

    Returns:
        List of {task_id, name, status, error_message, modified, uuid, pk}.
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return [{"error": f"could not import _env: {e!r}"}]
    cfg = get_config()
    if not cfg.is_live():
        return [{"error": "FSR instance not configured"}]
    client = get_client()
    # status__in= is silently ignored on this endpoint; fetch wider and
    # filter client-side. Single status= works exactly though, so use it
    # when caller is asking for a single status.
    fetch = max(limit * 4, 50) if not include_finished else limit
    url = (client.base_url + "/api/wf/api/workflows/?format=json"
           f"&limit={fetch}&ordering=-modified&parent_wf__isnull=True")
    try:
        r = client.session.get(url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return [{"error": f"request failed: {e!r}"}]
    if r.status_code != 200:
        return [{"error": f"HTTP {r.status_code}: {r.text[:200]}"}]
    members = r.json().get("hydra:member") or []
    if not include_finished:
        bad = {"failed", "finished_with_error", "terminated"}
        members = [m for m in members if m.get("status") in bad]
    if playbook:
        members = [m for m in members
                   if playbook.lower() in (m.get("name") or "").lower()]
    out: list[dict[str, Any]] = []
    for m in members[:limit]:
        res = m.get("result") if isinstance(m.get("result"), dict) else {}
        err = (res.get("Error message") or res.get("error")
               or res.get("message")) if isinstance(res, dict) else None
        pk_url = m.get("@id") or ""
        pk = pk_url.rstrip("/").rsplit("/", 1)[-1] if pk_url else None
        out.append({
            "task_id": m.get("task_id"),
            "name": m.get("name"),
            "status": m.get("status"),
            "error_message": err,
            "modified": m.get("modified"),
            "uuid": m.get("uuid"),
            "pk": pk,
        })
    return out


@mcp.tool()
def list_playbook_runs(playbook: str | None = None,
                       playbook_uuid: str | None = None,
                       limit: int = 20,
                       include_finished: bool = False) -> dict[str, Any]:
    """List runs of a single playbook, server-filtered by template_iri.

    Faster + more reliable than `list_recent_failed_runs(playbook=...)`
    when you know which playbook you care about — the API uses
    template_iri to do the filter on its side, so we don't waste a fetch
    of irrelevant rows.

    Args:
        playbook: playbook name (resolved live to uuid).
        playbook_uuid: skip the lookup if you already have the uuid.
        limit: max rows (default 20).
        include_finished: include finished runs too (default failures only).

    Returns:
        {playbook_uuid, runs: [{task_id, name, status, error_message,
         modified, pk}]}.
    """
    client = _live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    if not playbook_uuid:
        if not playbook:
            return {"error": "provide playbook (name) or playbook_uuid"}
        # Resolve name → uuid.
        import urllib.parse
        qs = urllib.parse.urlencode({"name": playbook, "$limit": 5})
        nr = client.session.get(client.base_url + f"/api/3/workflows?{qs}",
                                verify=client.verify_ssl)
        if nr.status_code != 200:
            return {"error": f"name lookup HTTP {nr.status_code}"}
        members = nr.json().get("hydra:member") or []
        if not members:
            return {"error": f"no playbook named {playbook!r}"}
        playbook_uuid = members[0].get("uuid")
    template_iri = f"/api/3/workflows/{playbook_uuid}"
    url = (client.base_url + "/api/wf/api/workflows/?format=json"
           f"&limit={limit * 4 if not include_finished else limit}"
           f"&ordering=-modified&parent_wf__isnull=True"
           f"&template_iri={template_iri}")
    r = client.session.get(url, verify=client.verify_ssl)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    members = r.json().get("hydra:member") or []
    if not include_finished:
        bad = {"failed", "finished_with_error", "terminated"}
        members = [m for m in members if m.get("status") in bad]
    out = []
    for m in members[:limit]:
        res = m.get("result") if isinstance(m.get("result"), dict) else {}
        err = ((res.get("Error message") or res.get("error")
                or res.get("message")) if isinstance(res, dict) else None)
        pk_url = m.get("@id") or ""
        pk = pk_url.rstrip("/").rsplit("/", 1)[-1] if pk_url else None
        out.append({
            "task_id": m.get("task_id"),
            "name": m.get("name"),
            "status": m.get("status"),
            "error_message": err,
            "modified": m.get("modified"),
            "pk": pk,
        })
    return {"playbook_uuid": playbook_uuid, "count": len(out), "runs": out}


# ---------------------------------------------------------------------------
# Picklists
# ---------------------------------------------------------------------------

def _live_client():
    """Return a live FSR client or None if env not configured."""
    try:
        from probes._env import get_client, get_config
    except Exception:  # noqa: BLE001
        return None
    if not get_config().is_live():
        return None
    return get_client()


@mcp.tool()
def list_picklists() -> dict[str, Any]:
    """List every picklist `listName.name` known to the FSR instance.

    Use when the agent needs to discover what picklists exist (e.g.
    'Severity', 'AlertStatus', 'Threat Type') before resolving a value
    to an IRI. Live-fetched once per process and cached.
    """
    client = _live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import list_picklist_names
    names = list_picklist_names(client)
    return {"count": len(names), "names": names}


@mcp.tool()
def get_picklist(name: str) -> dict[str, Any]:
    """List items of a single picklist as [{itemValue, uuid, iri, ordinal}].

    Args:
        name: picklist `listName.name` (e.g. 'AlertStatus', 'Severity').
              Use list_picklists() to discover.
    """
    client = _live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import picklist_values
    items = picklist_values(client, name)
    return {"name": name, "count": len(items), "items": items}


@mcp.tool()
def picklist_for_field(module: str, field: str) -> dict[str, Any]:
    """Auto-discover the picklist behind a (module, field).

    Returns the picklist_name plus the offline list of valid string
    values pulled from the local module_fields cache. Tries heuristic
    names first (e.g. 'AlertStatus' for alerts.status), then falls back
    to a Jaccard-overlap match against all live picklist values. Result
    persists to store/picklist_name_map.json.

    Args:
        module: lowercase module name, e.g. 'alerts', 'incidents'.
        field:  field name, e.g. 'status', 'severity', 'type'.
    """
    client = _live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import picklist_name_for, valid_values
    pn = picklist_name_for(client, module, field)
    return {
        "module": module, "field": field,
        "picklist_name": pn,
        "valid_values_local": valid_values(module, field),
    }


@mcp.tool()
def resolve_picklist_value(value: str, picklist_name: str | None = None,
                           module: str | None = None,
                           field: str | None = None) -> dict[str, Any]:
    """Resolve a friendly value (e.g. 'High') to a picklist IRI.

    Provide either `picklist_name`, or both `module` + `field` to
    auto-discover. Strings that already start with '/api/3/' pass
    through unchanged. Returns close-match suggestions when the value
    isn't an exact itemValue — useful when the LLM authored an invalid
    value like 'In Progress' for AlertStatus (which only has Open,
    Investigating, Pending, Closed, Active, Re-Opened).
    """
    client = _live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    from picklists import resolve_iri, picklist_name_for, picklist_values
    pn = picklist_name
    if pn is None and module and field:
        pn = picklist_name_for(client, module, field)
    if pn is None:
        return {"error": "picklist_name unknown — provide it, or "
                         "(module, field) for auto-discovery"}
    iri = resolve_iri(client, value, picklist_name=pn)
    if iri:
        return {"ok": True, "iri": iri, "picklist_name": pn,
                "value": value}
    items = picklist_values(client, pn)
    valid = [it.get("itemValue") for it in items]
    # Cheap fuzzy: prefix or substring match.
    vl = value.lower()
    suggestions = [v for v in valid if v and (
        v.lower().startswith(vl) or vl in v.lower() or
        v.lower() in vl)]
    return {"ok": False, "picklist_name": pn, "value": value,
            "valid_values": valid, "suggestions": suggestions[:5]}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
