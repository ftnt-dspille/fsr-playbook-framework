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

import difflib
import json
import re
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
# Structured error envelope (uniform tool I/O contract)
# ---------------------------------------------------------------------------

def _err(code: str, message: str,
         suggestions: list[str] | None = None,
         **extra: Any) -> dict[str, Any]:
    """Return the canonical `{ok: false, code, message, suggestions, ...}`
    failure envelope.

    Every MCP tool that exposes a recoverable failure mode (compiler
    rejects, missing connector, FSR not configured, op risk gate, …)
    should return through this helper so the LLM caller can branch on
    `code` + iterate against `suggestions` instead of regex-parsing
    prose.
    """
    out: dict[str, Any] = {
        "ok": False,
        "code": code,
        "message": message,
        "suggestions": list(suggestions or []),
    }
    out.update(extra)
    return out


def _serialize_compiler_error(e: Any) -> dict[str, Any]:
    """Compiler error → tool-result item with `suggestions: [...]` array.

    Keeps the legacy singular `suggestion` key populated so existing
    consumers (frontend Monaco markers, CLI pretty-printer) keep working
    untouched while LLMs see the array form documented in the system
    prompt's "Tool error contract" section.
    """
    sug = e.suggestion or ""
    return {
        "code": e.code.value,
        "path": e.path,
        "message": e.message,
        "suggestion": sug,
        "suggestions": [sug] if sug else [],
    }


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        from probes.common import CATALOG_DB_PATH
        if CATALOG_DB_PATH.exists():
            conn.execute(f"ATTACH DATABASE '{CATALOG_DB_PATH}' AS catalog")
    except Exception:
        pass
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
def find_connector(q: str, limit: int = 15,
                   verbose: bool = False) -> dict[str, Any]:
    """Fuzzy-search connectors by name, label, category, or description.

    Default response is terse (name/label/category only) to keep tool
    cost down. Pass `verbose=True` for full descriptions.

    Returns `{matches, suggestion?}`. When the query has zero hits we
    suggest a near-match instead of leaving the agent guessing.
    """
    with _db() as conn:
        cols = ("name, label, category, description" if verbose
                else "name, label, category")
        rows = _rows(
            conn,
            f"""SELECT {cols}
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
                    f"""SELECT {cols}
                       FROM connectors
                       WHERE name LIKE '%'||?||'%' OR label LIKE '%'||?||'%'
                       ORDER BY name LIMIT ?""",
                    (w, w, limit),
                )
        out: dict[str, Any] = {"matches": rows}
        if not rows:
            # Surface a near-match so the agent doesn't loop guessing
            # connector names. Same difflib pass the resolver uses.
            all_names = [r["name"] for r in _rows(
                conn, "SELECT name FROM connectors", ()
            )]
            close = difflib.get_close_matches(q, all_names, n=3, cutoff=0.45)
            if close:
                out["suggestion"] = (
                    f"no exact matches for {q!r}; did you mean one of "
                    f"{close}? Pass one of those as `q=` to retry."
                )
                out["near"] = close
            else:
                out["suggestion"] = (
                    f"no matches and no close suggestions for {q!r}. "
                    f"Try a broader keyword (vendor name, action verb)."
                )
        return out


# ---------------------------------------------------------------------------
# find_operation
# ---------------------------------------------------------------------------

@mcp.tool()
def find_operation(connector: str, q: str = "", limit: int = 10,
                   verbose: bool = False) -> dict[str, Any]:
    """List or search operations for a connector.

    Pass `connector` as the connector name (from find_connector).
    `q` is an optional substring filter on op name, title, or description.

    Default response is terse (op_name + title only). Pass `verbose=True`
    for descriptions. Returns `{matches, suggestion?}`. On zero hits,
    suggests near-matching ops so the agent doesn't loop guessing.
    """
    with _db() as conn:
        cols = ("op_name, title, description, annotation" if verbose
                else "op_name, title")
        if q:
            rows = _rows(
                conn,
                f"""SELECT {cols}
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
                f"""SELECT {cols}
                   FROM operations
                   WHERE connector_name = ?
                   ORDER BY op_name LIMIT ?""",
                (connector, limit),
            )
        out: dict[str, Any] = {"matches": rows}
        if not rows:
            all_ops = [r["op_name"] for r in _rows(
                conn,
                "SELECT op_name FROM operations WHERE connector_name = ?",
                (connector,),
            )]
            if not all_ops:
                # Connector is itself unknown — bigger problem.
                out["suggestion"] = (
                    f"connector {connector!r} has no operations in the "
                    f"reference store. Verify the connector name with "
                    f"find_connector before searching its ops."
                )
            elif q:
                close = difflib.get_close_matches(q, all_ops, n=5, cutoff=0.4)
                out["suggestion"] = (
                    f"no operations matching {q!r} on {connector!r}; "
                    + (f"closest: {close}" if close
                       else f"this connector has {len(all_ops)} ops total — "
                            f"omit `q=` to list them all (or pass a more "
                            f"general keyword).")
                )
                if close:
                    out["near"] = close
        return out


# ---------------------------------------------------------------------------
# get_op_schema
# ---------------------------------------------------------------------------

@mcp.tool()
def get_op_schema(connector: str, op: str,
                  verbose: bool = False) -> dict[str, Any]:
    """Return the parameter schema for a connector operation.

    Slim by default (~1.5 KB): `op_name`, `title`, `description`, and a
    trimmed `params` list (name/type/required/options/description). The
    raw `output_schema_json` and `conditional_output_schema_json` blobs
    are summarized to top-level keys only. Pass `verbose=True` for the
    full row with all output schemas.

    Returns the canonical `_err()` envelope (`ok:false, code, ...`) on
    miss:
    - `code: "connector_not_found"` when the connector itself is
      unknown — call `find_connector` first.
    - `code: "not_found"` when the connector exists but the op doesn't
      — the response includes a `near` list of close op names.
    """
    with _db() as conn:
        op_row = _rows(
            conn,
            "SELECT * FROM operations WHERE connector_name=? AND op_name=?",
            (connector, op),
        )
        if not op_row:
            connector_ops = [r["op_name"] for r in _rows(
                conn,
                "SELECT op_name FROM operations WHERE connector_name=?",
                (connector,),
            )]
            if not connector_ops:
                all_connectors = [r["name"] for r in _rows(
                    conn, "SELECT name FROM connectors", ()
                )]
                near = difflib.get_close_matches(
                    connector, all_connectors, n=3, cutoff=0.5
                )
                return _err(
                    "connector_not_found",
                    f"connector {connector!r} has no operations in the "
                    f"reference store",
                    suggestions=[
                        "call find_connector first to confirm the name"
                        + (f" — close matches: {near}" if near else "")
                    ],
                    near=near,
                )
            near = difflib.get_close_matches(op, connector_ops, n=5, cutoff=0.4)
            return _err(
                "not_found",
                f"operation {op!r} not found on connector {connector!r}",
                suggestions=[
                    f"closest ops: {near}" if near else
                    f"call find_operation(connector={connector!r}) to "
                    f"list its {len(connector_ops)} ops"
                ],
                near=near,
            )

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

        if verbose:
            result = dict(op_row[0])
            for col in ("output_schema_json", "conditional_output_schema_json",
                        "output_schema_observed"):
                if result.get(col):
                    try:
                        result[col] = json.loads(result[col])
                    except (json.JSONDecodeError, TypeError):
                        pass
            result["params"] = params
        else:
            row = op_row[0]
            slim_params = [
                {k: p[k] for k in (
                    "param_name", "title", "type", "required",
                    "options_json", "description"
                ) if p.get(k) not in (None, "")}
                for p in params
            ]
            result = {
                "op_name": row.get("op_name"),
                "connector_name": row.get("connector_name"),
                "title": row.get("title"),
                "description": row.get("description"),
                "annotation": row.get("annotation"),
                "params": slim_params,
            }
            for col in ("output_schema_json", "conditional_output_schema_json",
                        "output_schema_observed"):
                blob = row.get(col)
                if not blob:
                    continue
                try:
                    parsed = json.loads(blob)
                    if isinstance(parsed, dict):
                        result[f"{col}_keys"] = sorted(parsed.keys())[:30]
                    else:
                        result[f"{col}_summary"] = (
                            f"<{type(parsed).__name__}, "
                            f"{len(blob)} chars — pass verbose=True>"
                        )
                except (json.JSONDecodeError, TypeError):
                    pass

        if not op_row[0].get("output_schema_json") and \
                not op_row[0].get("output_schema_observed"):
            result["output_schema_hint"] = (
                "No output schema available. Call run_op with sample "
                "params to observe the real output shape and populate "
                "output_schema_observed."
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
        return _err("probes_unavailable", "probes module not available")

    cfg = get_config()
    if not cfg.is_live():
        return _err(
            "no_live_fsr",
            "FSR instance not configured",
            suggestions=[
                "Set FSR_BASE_URL and FSR_API_KEY in .env",
                "Run `fsrpb env` to confirm the live target",
            ],
        )

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
        near = []
        if crow is None:
            near = [r[0] for r in conn.execute(
                "SELECT name FROM connectors WHERE name LIKE ? LIMIT 5",
                (f"%{connector}%",),
            ).fetchall()]
    if crow is None:
        return _err(
            "unknown_connector",
            f"connector '{connector}' not found in store",
            suggestions=near or [
                "Run `find_connector` to search the catalog",
            ],
            connector=connector,
        )
    version = crow["version"]

    category = op_row["category"] if op_row else None
    risk = _op_risk(op, category)
    if risk != "safe" and not confirm:
        return {
            "ok": False,
            "code": "requires_confirmation",
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
            "suggestions": [
                f"If you're certain this is safe, retry with confirm=True",
                f"Otherwise ask the user before mutating state on the live FSR",
            ],
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
        return _err(
            "transport_failed", msg,
            suggestions=[
                "Check FSR connectivity and `fsrpb health`",
                "Confirm the connector config is configured + active",
            ],
            status=str(status),
        )

    if not isinstance(resp, dict):
        return _err(
            "bad_response_shape",
            f"unexpected response type: {type(resp).__name__}",
        )

    exec_status = resp.get("status", "")
    if exec_status not in ("Success", "success", "Completed", "completed", ""):
        msg = resp.get("message", "") or json.dumps(resp)[:600]
        _record_verification(connector, op, "tested_fail", msg[:2000])
        return _err(
            "execution_failed", msg,
            suggestions=[
                "Inspect `params` against `get_op_schema` required fields",
                "If auth/scope error, verify the connector config on FSR",
            ],
            status=exec_status,
        )

    data = resp.get("data", resp)
    shape = _infer_shape(data)
    _store_observed_schema(connector, op, data)
    # Surface the observed top-level keys inline so the agent can wire
    # `{{ vars.steps.<step>.<key> }}` references in a follow-up step
    # without a round-trip back to get_op_schema. List payloads expose
    # the first element's keys (collection shape).
    sample = data[0] if isinstance(data, list) and data else data
    top_keys = sorted(sample.keys()) if isinstance(sample, dict) else []
    return {
        "ok": True,
        "data": data,
        "output_shape": shape,
        "output_top_keys": top_keys,
        "output_is_list": isinstance(data, list),
        "schema_cached": True,
    }


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
            known = list(_SHORT_TO_CANONICAL.keys()) + [
                r["name"] for r in _rows(
                    conn, "SELECT name FROM step_types", ()
                )
            ]
            near = difflib.get_close_matches(name, known, n=3, cutoff=0.4)
            return _err(
                "not_found",
                f"step type {name!r} not found",
                suggestions=[
                    f"did you mean {', '.join(near)}?" if near else
                    "use a canonical FSR name like ManualInput, "
                    "Decision, SetVariable, Connectors, UpdateRecord"
                ],
                near=near,
            )

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
        `{output: <value>}` on success — value preserves its native type
        (str, int, float, bool, list, dict). `{error: str}` if the engine
        errored (template syntax issues, missing var, etc).

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
            if k in r:
                return {"output": r[k]}
        return {"output": r}
    return {"output": r}


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


@mcp.tool()
def review_chat_session(session_id: str) -> dict[str, Any]:
    """Mine one chat session for known failure patterns and return a
    structured report.

    Use this when the user asks "why did session X go wrong?" or when
    sweeping their thumbs-down feedback. Detectors covered:
    user feedback rating, validate-fix-validate spirals, empty/heavy
    tool results, UUID step ids, set_variable typos, missing
    `collection:` recurrences, unknown connector/op references, and
    sessions that never deployed. Source-of-truth for the patterns
    is `python/chat_review.py`.

    Returns: `{session_id, headline, findings[], stats}`. Each finding
    has `{severity: error|warning|info, code, title, detail, turn?,
    suggestion?}`. The headline is a one-liner suitable for chat output.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        import chat_review
    except ImportError as exc:
        return _err("chat_review_unavailable", f"chat_review not importable: {exc}")
    try:
        report = chat_review.review_session(session_id)
    except FileNotFoundError as e:
        return _err("history_db_missing", str(e))
    except LookupError as e:
        return _err("session_not_found", str(e))
    return report.to_dict()


@mcp.tool()
def review_recent_thumbs_down(limit: int = 10) -> dict[str, Any]:
    """Sweep the most recent thumbs-down sessions and run the chat-review
    pattern detectors against each. Useful for "what's been going wrong
    recently?" — returns one row per session with its headline + top 3
    findings, plus a cross-session pattern frequency map.

    Returns:
      {
        sessions: [{session_id, rating, summary, headline, top_findings[]}, ...],
        common_patterns: {<code>: <count>, ...}
      }
    """
    import sqlite3 as _sql
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        import chat_review
    except ImportError as exc:
        return _err("chat_review_unavailable", f"chat_review not importable: {exc}")
    db_path = chat_review._DEFAULT_DB
    if not db_path.exists():
        return _err("history_db_missing", f"history db not found at {db_path}")
    conn = _sql.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = _sql.Row
    rows = conn.execute(
        "SELECT session_id, rating, summary, ts FROM chat_feedback "
        "WHERE rating='down' ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    out_sessions: list[dict[str, Any]] = []
    pattern_counts: dict[str, int] = {}
    for r in rows:
        try:
            rep = chat_review.review_session(r["session_id"])
        except Exception as e:  # noqa: BLE001
            out_sessions.append({
                "session_id": r["session_id"],
                "rating": r["rating"],
                "summary": r["summary"],
                "review_error": str(e),
            })
            continue
        for f in rep.findings:
            pattern_counts[f.code] = pattern_counts.get(f.code, 0) + 1
        out_sessions.append({
            "session_id": r["session_id"],
            "rating": r["rating"],
            "summary": r["summary"],
            "ts": r["ts"],
            "headline": rep.headline,
            "top_findings": [f.to_dict() for f in rep.findings[:3]],
            "stats": rep.stats,
        })
    common = sorted(pattern_counts.items(), key=lambda kv: -kv[1])
    return {
        "sessions": out_sessions,
        "common_patterns": dict(common),
    }


@mcp.tool()
def find_step_examples(step_type: str,
                       contains: str | None = None,
                       limit: int = 20) -> list[dict[str, Any]]:
    """Search the `playbook_steps` corpus for real-world examples of a step type.

    Backed by `probe_playbook_steps`, which indexes every step from every
    FSR playbook JSON export on disk (SP bundles + store/incoming drops).
    Use this when tightening linting/validation to mine real-world
    argument shapes — e.g. "show me every ManualInput that uses
    formType=lookup" or "every Decision with a timeout block".

    Args:
        step_type: step_types.name, e.g. 'ManualInput', 'Decision',
                   'SetVariable', 'Connectors'.
        contains:  optional substring matched against the raw
                   arguments_json (case-sensitive). Examples:
                       'ipv4'                 — any ipv4 input
                       '"formType": "lookup"' — any lookup-typed field
                       '"default": true'      — any default branch
                       '"timeout":'           — any step with a timeout
        limit:     max rows (default 20).

    Returns: list of {step_name, playbook_name, source, source_path, arguments}.
    """
    with _db() as conn:
        sql = ("SELECT step_name, playbook_name, source, source_path, "
               "arguments_json FROM playbook_steps WHERE step_type_name = ?")
        params: list[Any] = [step_type]
        if contains:
            sql += " AND arguments_json LIKE ?"
            params.append(f"%{contains}%")
        sql += " LIMIT ?"
        params.append(limit)
        rows = _rows(conn, sql, tuple(params))
    for r in rows:
        try:
            r["arguments"] = json.loads(r.pop("arguments_json"))
        except (json.JSONDecodeError, KeyError):
            pass
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
        return _err("compiler_unavailable", f"compiler not available: {exc}")

    result = _compile(yaml_text, DB_PATH)
    if result.ok:
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
# resolve_yaml — L2 gate: structural validation + live prechecks
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
    """L2 success-ladder gate: full whole-YAML resolvability check.

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

    client = _live_client()
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
        return _err("compiler_unavailable", f"compiler not available: {exc}")

    result = _compile(yaml_text, DB_PATH)
    if not result.ok:
        return _err(
            "compile_failed",
            f"{len(result.errors)} compiler error(s); see `errors` for codes "
            "and suggestions",
            errors=[_serialize_compiler_error(e) for e in result.errors],
        )
    return {"ok": True, "json": json.dumps(result.fsr_json, indent=2)}


# ---------------------------------------------------------------------------
# push / run / dry-run — closes the agent's authoring loop without dropping
# out to the CLI. All three mutate state on the live FSR instance.
# ---------------------------------------------------------------------------

@mcp.tool()
def push_playbook(yaml_text: str) -> dict[str, Any]:
    """Compile a YAML playbook and push it to the live FSR instance.

    Idempotent: PUT first, POST on 404, hard-purge + POST on 409 (matches
    `fsrpb push --mode replace`). Use after `validate_yaml` returns clean.

    Returns:
        {ok: true, collection_uuid, collection_name, workflows: [{name, uuid}],
         action: "put"|"post"|"purge_post"} on success.
        {ok: false, errors: [...]} on compile failure.
        {ok: false, error: str} on push failure.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from compiler import compile_yaml as _compile
        from probes._env import get_client, get_config
        from e2e.runner import _push, _PushError
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed: {e!r}"}
    if not get_config().is_live():
        return {"ok": False, "error": "FSR instance not configured"}
    result = _compile(yaml_text, DB_PATH)
    if not result.ok:
        return {"ok": False, "errors": [
            {"code": e.code.value, "path": e.path, "message": e.message,
             "suggestion": e.suggestion or ""}
            for e in result.errors
        ]}
    coll = result.fsr_json["data"][0]
    client = get_client()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            _push(client, coll, Path(td))
        except _PushError as e:
            return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "collection_uuid": coll["uuid"],
        "collection_name": coll["name"],
        "workflows": [{"name": w.get("name"), "uuid": w.get("uuid")}
                      for w in coll.get("workflows", [])],
    }


@mcp.tool()
def run_playbook(playbook: str,
                 input: dict[str, Any] | None = None,
                 collection: str | None = None,
                 record: str | None = None,
                 follow: bool = True,
                 timeout_s: int = 180,
                 use_mock_output: bool = False) -> dict[str, Any]:
    """Trigger a deployed playbook and (optionally) poll until terminal.

    Args:
        playbook: workflow name OR uuid OR `Collection:Name` shorthand
        input: trigger params; FSR maps these to `vars.input.params.<k>`
        collection: collection name to disambiguate duplicate workflow names
        record: "<module>:<uuid>" for record-context (cybersponse.action)
            triggers; omit for /notrigger style (designer Run button)
        follow: if True, poll until terminal status (default 180s timeout)
        timeout_s: poll timeout when follow=True
        use_mock_output: honor each step's `arguments.mock_result` instead
            of running live (good for dry-running without external API calls)

    Returns:
        {ok, status, task_id, wf_uuid, wf_pk, error_message?, failed_steps?}.
        `ok` is True only when status == "finished"; "finished_with_error"
        and "failed" return ok=False with diagnostics.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from probes._env import get_client, get_config
        from cli import _resolve_workflow_ident
        from e2e.runner import _fetch_trigger_route_uuid
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed: {e!r}"}
    if not get_config().is_live():
        return {"ok": False, "error": "FSR instance not configured"}
    client = get_client()
    wf_uuid = _resolve_workflow_ident(client, playbook, collection)
    if not wf_uuid:
        return {"ok": False, "error": f"no playbook matching {playbook!r}"}

    if record:
        if ":" not in record:
            return {"ok": False, "error": "record must be '<module>:<uuid>'"}
        module, rec_uuid = record.split(":", 1)
        route_uuid = _fetch_trigger_route_uuid(client, wf_uuid)
        if not route_uuid:
            return {"ok": False, "error": (
                "no trigger.route on workflow — playbook is not a "
                "record-action style trigger; omit `record`"
            )}
        path = f"/api/triggers/1/action/{route_uuid}"
        body = {"singleRecordExecution": True, "__resource": module,
                "__uuid": wf_uuid,
                "records": [f"/api/3/{module}/{rec_uuid}"]}
    else:
        path = f"/api/triggers/1/notrigger/{wf_uuid}"
        body = {"input": {}, "request": {"data": input or {}},
                "useMockOutput": bool(use_mock_output), "globalMock": False}

    try:
        r = client.session.post(client.base_url + path, json=body,
                                verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"trigger failed: {e!r}"}
    if r.status_code >= 400:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    try:
        resp = r.json()
    except Exception:  # noqa: BLE001
        resp = {}
    task_id = resp.get("task_id") if isinstance(resp, dict) else None
    if not follow or not task_id:
        return {"ok": True, "status": "triggered", "task_id": task_id,
                "wf_uuid": wf_uuid}

    import time
    terminal = {"finished", "failed", "terminated", "skipped",
                "finished_with_error", "rejected"}
    poll_url = (client.base_url + "/api/wf/api/workflows/?format=json"
                f"&limit=1&ordering=-modified&task_id={task_id}"
                "&parent_wf__isnull=True")
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            pr = client.session.get(poll_url, verify=client.verify_ssl)
            members = (pr.json() or {}).get("hydra:member") or []
        except Exception:  # noqa: BLE001
            members = []
        if members:
            rec = members[0]
            status = rec.get("status", "unknown")
            if status in terminal:
                wf_pk = (rec.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
                ok = status == "finished"
                out: dict[str, Any] = {"ok": ok, "status": status,
                                       "task_id": task_id, "wf_uuid": wf_uuid,
                                       "wf_pk": wf_pk}
                if not ok:
                    # Pull the full record for step-level diagnostics.
                    try:
                        fr = client.session.get(
                            client.base_url + "/api" + (rec.get("@id") or ""),
                            verify=client.verify_ssl)
                        full = fr.json() if fr.status_code == 200 else rec
                    except Exception:  # noqa: BLE001
                        full = rec
                    top = full.get("result") or {}
                    out["error_message"] = (
                        (top.get("Error message") if isinstance(top, dict) else None)
                        or full.get("errorMessage") or full.get("error"))
                    failed = []
                    for s in full.get("steps") or []:
                        if s.get("status") in ("failed", "finished_with_error",
                                               "terminated"):
                            res = s.get("result") or {}
                            failed.append({
                                "name": s.get("name"),
                                "status": s.get("status"),
                                "error": (res.get("Error message")
                                          or res.get("error")
                                          or res.get("message")
                                          or json.dumps(res)[:300]
                                          if isinstance(res, dict) else str(res)),
                            })
                    out["failed_steps"] = failed
                return out
        time.sleep(2)
    return {"ok": False, "status": "timeout", "task_id": task_id,
            "wf_uuid": wf_uuid,
            "error_message": f"timeout after {timeout_s}s"}


@mcp.tool()
def dry_run_playbook(yaml_text: str, playbook: str,
                     input: dict[str, Any] | None = None,
                     timeout_s: int = 180,
                     cleanup: bool = True,
                     use_mock_output: bool = False) -> dict[str, Any]:
    """Compile + push + run + auto-cleanup. The agent's full E2E loop in one tool.

    Args:
        yaml_text: full YAML source.
        playbook: workflow name to trigger after push (one playbook in the
            collection — the agent picks which one).
        input: trigger params (mapped to `vars.input.params.<k>`).
        timeout_s: poll timeout (default 180s).
        cleanup: hard-purge the collection after the run (default True).
            Set False to keep the collection on the instance for inspection.
        use_mock_output: run with each step's `arguments.mock_result` instead
            of live external calls.

    Returns:
        {ok, status, task_id, wf_pk, collection_uuid, error_message?,
         failed_steps?, cleaned_up: bool}.
    """
    push = push_playbook(yaml_text)
    if not push.get("ok"):
        return {"ok": False, "stage": "push", **push}
    run = run_playbook(playbook, input=input,
                       collection=push.get("collection_name"),
                       follow=True, timeout_s=timeout_s,
                       use_mock_output=use_mock_output)
    coll_uuid = push["collection_uuid"]
    cleaned = False
    if cleanup:
        try:
            from probes._env import get_client
            from e2e.runner import _hard_purge
            client = get_client()
            # Re-fetch the workflow uuids in case the push reshaped them.
            sys.path.insert(0, str(REPO_ROOT / "python"))
            _hard_purge(client, coll_uuid,
                        {"workflows": [{"uuid": w["uuid"]}
                                       for w in push.get("workflows", [])]})
            cleaned = True
        except Exception:  # noqa: BLE001
            cleaned = False
    return {**run, "stage": "run", "collection_uuid": coll_uuid,
            "cleaned_up": cleaned}


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

    # task_id (UUID) → workflow PK. Try live, then historical (purged after ~30-60 min).
    is_uuid = "-" in pb_execution and not pb_execution.isdigit()
    pk_url = None
    base_path = None
    if is_uuid:
        for path in ("/api/wf/api/workflows/", "/api/wf/api/historical-workflows/"):
            try:
                pr = client.session.get(
                    client.base_url + path
                    + f"?task_id={pb_execution}&parent_wf__isnull=True&format=json&limit=1",
                    verify=client.verify_ssl,
                )
                members = (pr.json() or {}).get("hydra:member") or []
            except Exception:  # noqa: BLE001
                continue
            if members:
                pk_url = members[0].get("@id") or ""
                base_path = path
                break
        if not pk_url:
            return {"error": f"no workflow run found for task_id {pb_execution!r} (checked live + historical)"}
        url = client.base_url + "/api" + pk_url + "?step_detail=true"
    else:
        url = client.base_url + f"/api/wf/api/workflows/{pb_execution}/?step_detail=true"

    try:
        r = client.session.get(url, verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"fetch failed: {e!r}"}
    # Numeric PK can live in either table — fall back to historical on 404.
    if r.status_code == 404 and not is_uuid:
        url = client.base_url + f"/api/wf/api/historical-workflows/{pb_execution}/?step_detail=true"
        try:
            r = client.session.get(url, verify=client.verify_ssl)
        except Exception as e:  # noqa: BLE001
            return {"error": f"historical fetch failed: {e!r}"}
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


def _fetch_runs_both(client, *, limit: int, extra_qs: str = "") -> list[dict[str, Any]]:
    """Fetch from /workflows/ AND /historical-workflows/, merge by modified desc.

    FSR purges live workflow logs to the historical table every ~30-60 min for
    performance, so any triage tool that only hits /workflows/ goes blind to
    older failures. Historical also returns richer fields (`result`, `steps`,
    `env`) inline. Dedup by `@id` in case a run is in both during the move.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in ("/api/wf/api/workflows/", "/api/wf/api/historical-workflows/"):
        url = (client.base_url + path
               + f"?format=json&limit={limit}&ordering=-modified"
               + f"&parent_wf__isnull=True{extra_qs}")
        try:
            r = client.session.get(url, verify=client.verify_ssl)
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        for m in (r.json().get("hydra:member") or []):
            iri = m.get("@id") or ""
            if iri and iri in seen:
                continue
            seen.add(iri)
            m["_source"] = "historical" if "historical" in path else "live"
            out.append(m)
    out.sort(key=lambda m: m.get("modified") or "", reverse=True)
    return out


def _shape_run(m: dict) -> dict:
    res = m.get("result") if isinstance(m.get("result"), dict) else {}
    err = ((res.get("Error message") or res.get("error")
            or res.get("message")) if isinstance(res, dict) else None)
    pk_url = m.get("@id") or ""
    pk = pk_url.rstrip("/").rsplit("/", 1)[-1] if pk_url else None
    return {
        "task_id": m.get("task_id"),
        "name": m.get("name"),
        "status": m.get("status"),
        "error_message": err,
        "modified": m.get("modified"),
        "uuid": m.get("uuid"),
        "pk": pk,
        "source": m.get("_source"),  # "live" or "historical"
    }


@mcp.tool()
def list_tags(prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List FortiSOAR tag names; use to discover tags before filtering runs by them.

    Backed by `GET /api/3/tags?$export=true`. The instance can have 10k+ tags
    (most are auto-generated from threat-intel data), so always pass a prefix
    when looking for workflow-noise tags like "system" or "testing".

    Args:
        prefix: case-insensitive tag prefix (uses `uuid$like=<prefix>%` —
            the tag entity's primary key IS the tag string). Pass None to
            page through everything.
        limit: max tag names to return.

    Returns:
        {"total": <int>, "tags": [<name>, ...]}.
    """
    client = _live_client()
    if client is None:
        return {"error": "FSR instance not configured"}
    qs = "$export=true"
    if prefix:
        import urllib.parse
        # tag entity stores the tag string in the `uuid` column; use
        # SQL LIKE wildcard which is `%` (URL-encoded `%25`).
        qs += f"&uuid$like={urllib.parse.quote(prefix, safe='')}%25"
    qs += f"&$limit={limit}"
    try:
        r = client.session.get(client.base_url + "/api/3/tags?" + qs,
                               verify=client.verify_ssl)
    except Exception as e:  # noqa: BLE001
        return {"error": f"request failed: {e!r}"}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    body = r.json() or {}
    tags = body.get("hydra:member") or []
    return {"total": body.get("hydra:totalItems"), "tags": tags[:limit]}


def _build_run_filter_qs(*, modified_after: str | None,
                         modified_before: str | None,
                         tags_include: str | None,
                         tags_exclude: str | None,
                         user_iri: str | None) -> str:
    """Compose the optional server-side filter querystring shared by both
    /workflows/ and /historical-workflows/ listings.
    """
    import urllib.parse
    parts: list[str] = []
    if modified_after:
        parts.append("modified_after=" + urllib.parse.quote(modified_after, safe=":"))
    if modified_before:
        parts.append("modified_before=" + urllib.parse.quote(modified_before, safe=":"))
    if tags_include is not None:
        # CSV like "system,testing" — keep commas unencoded.
        parts.append("tags_include=" + urllib.parse.quote(tags_include, safe=","))
    if tags_exclude is not None:
        parts.append("tags_exclude=" + urllib.parse.quote(tags_exclude, safe=","))
    if user_iri:
        # IRI like "/api/3/people/<uuid>" — keep slashes.
        parts.append("user=" + urllib.parse.quote(user_iri, safe="/"))
    return ("&" + "&".join(parts)) if parts else ""


@mcp.tool()
def list_recent_failed_runs(limit: int = 20,
                            playbook: str | None = None,
                            include_finished: bool = False,
                            modified_after: str | None = None,
                            modified_before: str | None = None,
                            tags_include: str | None = None,
                            tags_exclude: str | None = "system",
                            user_iri: str | None = None) -> list[dict[str, Any]]:
    """List recent workflow runs (default: failures only) for triage.

    Use this when the user says "my playbook is broken" without naming
    the playbook — fetches the most recently-modified failed/errored
    runs across the instance from BOTH the live and historical workflow
    tables (FSR purges live → historical every ~30-60 min).

    Args:
        limit: max rows to return (default 20)
        playbook: optional name filter (client-side substring match)
        include_finished: include finished runs too (default False —
            failed/finished_with_error/terminated only)
        modified_after: ISO timestamp, e.g. "2026-05-01 05:00:00" (server-side)
        modified_before: ISO timestamp (server-side)
        tags_include: CSV of tag names to require (server-side)
        tags_exclude: CSV of tag names to exclude (default "system" to hide
            framework noise; pass "" to include them)
        user_iri: full IRI like "/api/3/people/<uuid>" — filter by triggering
            user (server-side)

    Returns:
        List of {task_id, name, status, error_message, modified, uuid,
        pk, source} where source is "live" or "historical".
    """
    try:
        from probes._env import get_client, get_config
    except Exception as e:  # noqa: BLE001
        return [{"error": f"could not import _env: {e!r}"}]
    cfg = get_config()
    if not cfg.is_live():
        return [{"error": "FSR instance not configured"}]
    client = get_client()
    # Fetch wider when filtering client-side so we still hit the limit
    # after the status filter trims rows.
    fetch = max(limit * 4, 50) if not include_finished else limit
    extra = _build_run_filter_qs(
        modified_after=modified_after, modified_before=modified_before,
        tags_include=tags_include, tags_exclude=tags_exclude,
        user_iri=user_iri,
    )
    members = _fetch_runs_both(client, limit=fetch, extra_qs=extra)
    if not include_finished:
        bad = {"failed", "finished_with_error", "terminated"}
        members = [m for m in members if m.get("status") in bad]
    if playbook:
        members = [m for m in members
                   if playbook.lower() in (m.get("name") or "").lower()]
    return [_shape_run(m) for m in members[:limit]]


@mcp.tool()
def list_playbook_runs(playbook: str | None = None,
                       playbook_uuid: str | None = None,
                       limit: int = 20,
                       include_finished: bool = False,
                       modified_after: str | None = None,
                       modified_before: str | None = None,
                       tags_include: str | None = None,
                       tags_exclude: str | None = "system",
                       user_iri: str | None = None) -> dict[str, Any]:
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
    fetch = limit * 4 if not include_finished else limit
    extra = _build_run_filter_qs(
        modified_after=modified_after, modified_before=modified_before,
        tags_include=tags_include, tags_exclude=tags_exclude,
        user_iri=user_iri,
    )
    members = _fetch_runs_both(
        client, limit=fetch,
        extra_qs=f"&template_iri={template_iri}{extra}",
    )
    if not include_finished:
        bad = {"failed", "finished_with_error", "terminated"}
        members = [m for m in members if m.get("status") in bad]
    runs = [_shape_run(m) for m in members[:limit]]
    return {"playbook_uuid": playbook_uuid, "count": len(runs), "runs": runs}


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
# api_examples_catalog integration (HTTP virtual-connector fallback)
# ---------------------------------------------------------------------------
# The reference DB ATTACHes the read-only catalog at common.py:62. These
# tools surface 207k+ third-party API examples so the assistant can author
# playbooks via the FortiSOAR HTTP connector when a native connector for
# the target vendor is missing.
#
# Auth taxonomy: the catalog stores free-text auth_method strings; the
# HTTP connector expects an `auth_type` enum. Mapping is deterministic.
_HTTP_AUTH_MAP = {
    "basic": "Basic",
    "bearer": "Bearer Token",
    "token": "Bearer Token",
    "api key": "API Key in Header",
    "apikey": "API Key in Header",
    "oauth": "OAuth 2.0",
    "oauth2": "OAuth 2.0",
    "no auth": "No Auth",
    "none": "No Auth",
}


def _map_http_auth(catalog_auth: str | None) -> str:
    if not catalog_auth:
        return "No Auth"
    a = catalog_auth.lower()
    for needle, mapped in _HTTP_AUTH_MAP.items():
        if needle in a:
            return mapped
    return "No Auth"


@mcp.tool()
def search_api_examples(query: str, product: str | None = None,
                        limit: int = 10) -> list[dict[str, Any]]:
    """Search the api_examples_catalog (207k entries / 6,927 products).

    Use when no native FortiSOAR connector exists for the target vendor.
    Pair the result with `synthesize_http_step` to emit an HTTP-connector
    step pre-filled with method/path/auth/params drawn from a real example.

    Returns: list of {entry_id, product, action, http_method, http_path,
    auth_method, description, source_url, code_snippet (if any)}.
    """
    with _db() as conn:
        try:
            sql = (
                "SELECT e.id AS entry_id, p.name AS product, e.action, "
                "e.http_method, e.http_path, e.auth_method, e.description, "
                "e.source_url, e.code_snippet, e.code_lang "
                "FROM catalog.entries_fts f "
                "JOIN catalog.entries e ON e.rowid = f.rowid "
                "JOIN catalog.products p ON p.id = e.product_id "
                "WHERE entries_fts MATCH ? "
            )
            params: list[Any] = [query]
            if product:
                sql += "AND p.normalized LIKE ? "
                params.append(f"%{product.lower()}%")
            sql += "ORDER BY e.example_quality DESC LIMIT ?"
            params.append(limit)
            return _rows(conn, sql, tuple(params))
        except sqlite3.OperationalError as exc:
            return [{"error": f"catalog DB unavailable: {exc}"}]


@mcp.tool()
def synthesize_http_step(entry_id: int,
                         step_name: str = "Call API") -> dict[str, Any]:
    """Translate a catalog entry into a FortiSOAR HTTP-connector step.

    Deterministic transformer (no LLM). Returns a YAML-ready dict shaped
    like the simplified IR for a `connector` step targeting the `http`
    connector's `http_request` op, with method/rest_api/auth_type/header/
    parameter pre-filled from the catalog entry.

    The agent should still review and fill in: secrets (basic_password,
    bearer_token, api_key), the base URL (catalog stores path only),
    response_path for nested payloads, and any body shape for write ops.
    """
    with _db() as conn:
        try:
            row = conn.execute(
                "SELECT e.id, p.name AS product, e.action, e.http_method, "
                "e.http_path, e.auth_method, e.parameters_json, "
                "e.description, e.source_url "
                "FROM catalog.entries e JOIN catalog.products p "
                "ON p.id = e.product_id WHERE e.id = ?",
                (entry_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            return {"error": f"catalog DB unavailable: {exc}"}
    if not row:
        return {"error": f"entry_id {entry_id} not found"}
    params_raw = row["parameters_json"] or "[]"
    try:
        params_list = json.loads(params_raw)
    except (TypeError, ValueError):
        params_list = []
    query_params: dict[str, str] = {}
    for p in params_list if isinstance(params_list, list) else []:
        if not isinstance(p, dict):
            continue
        loc = (p.get("in") or "").lower()
        nm = p.get("name")
        if nm and loc in ("query", ""):
            query_params[nm] = p.get("example") or f"<{nm}>"
    return {
        "step_type": "connector",
        "name": step_name,
        "connector": "http",
        "operation": "http_request",
        "args": {
            "method": (row["http_method"] or "GET").upper(),
            "rest_api": row["http_path"] or "",
            "auth_type": _map_http_auth(row["auth_method"]),
            "header": {},
            "parameter": query_params,
        },
        "_note": (
            f"Synthesized from {row['product']}/{row['action']}. "
            "TODO: fill secrets, prefix rest_api with base URL, set "
            "response_path for nested payloads, populate body for "
            "write operations."
        ),
        "_source_url": row["source_url"],
    }


# ---------------------------------------------------------------------------
# step_through_playbook — L3 success-ladder gate (in-editor stepper)
# ---------------------------------------------------------------------------

# `dry_run_playbook` (compile + push + run + cleanup) is the full E2E loop
# and modifies live FSR state. The stepper below is a *pre-push* L3 check:
# walk the playbook step-by-step against accumulated context, render each
# step's arguments, execute safe connector ops, simulate the rest, and
# surface per-step outputs so the agent can spot rendering failures and
# shape mismatches without touching the appliance's record store.

def _safe_op_category(connector: str, op: str) -> str:
    with _db() as conn:
        row = conn.execute(
            "SELECT category FROM operations "
            "WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
    return (row["category"] if row else "") or ""


def _next_step(step: dict, taken_branch: str | None,
               by_id: dict[str, dict]) -> str | None:
    """Pick the next step id for the stepper.

    Linear: follow `next`. Decision: follow `branches[taken_branch]` if
    provided, else the first branch (deterministic default — agent can
    pin a path with branch_choices).
    """
    nxt = step.get("next")
    if nxt:
        return nxt
    branches = step.get("branches") or {}
    if not branches:
        return None
    if taken_branch and taken_branch in branches:
        return branches[taken_branch]
    # Deterministic default: lowest-key branch.
    first_key = sorted(branches.keys())[0]
    return branches[first_key]


@mcp.tool()
def step_through_playbook(yaml_text: str,
                          playbook: str | None = None,
                          input: dict[str, Any] | None = None,
                          branch_choices: dict[str, str] | None = None,
                          execute_safe_ops: bool = True,
                          max_steps: int = 30) -> dict[str, Any]:
    """L3 gate: walk a playbook step-by-step *without* pushing to FSR.

    For each step in the chosen execution path:
      1. Render its arguments against the accumulated `vars.steps.*` +
         `vars.input.*` context using the live FSR's Jinja engine.
      2. If the step is a query-class connector op AND `execute_safe_ops`
         is True, execute it live via `run_op` (read-only — same risk
         gate as `run_op` itself; destructive ops are skipped with a
         simulated placeholder).
      3. Otherwise simulate: record the rendered args and an empty
         `output` so downstream steps can keep rendering.
    Returns the per-step trace + the first error encountered (if any).
    Lets the agent see exactly where rendering or shape assumptions break
    before any live write happens.

    Args:
      yaml_text: the simplified-IR YAML.
      playbook: name of the workflow to step through (default: first one).
      input: vars.input.params.* values.
      branch_choices: {step_id: branch_label} pinning decision-step paths.
      execute_safe_ops: if False, every step is simulated (purely offline).
      max_steps: hard cap to prevent runaway loops.

    Response shape:
      { ok, playbook, trace: [ {step_id, type, rendered_args, output,
                                output_top_keys, status, note} ],
        first_error: {step_id, message} | None,
        steps_executed: int }
    """
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"yaml parse failed: {exc}"}

    pbs = doc.get("playbooks") or []
    if not pbs:
        return {"ok": False, "error": "no playbooks in YAML"}
    pb = next((p for p in pbs if p.get("name") == playbook), pbs[0])
    steps = pb.get("steps") or []
    by_id = {s["id"]: s for s in steps if isinstance(s, dict) and "id" in s}
    if not by_id:
        return {"ok": False, "error": "no steps with ids in playbook"}

    start = next((s for s in steps if isinstance(s, dict)
                  and (s.get("type") or "").startswith("start")), steps[0])

    # Accumulated context for Jinja rendering. Mirrors the FSR runtime
    # contract: vars.steps.<step_jinja_key>.<output_keys>; vars.input.*.
    vars_ctx: dict[str, Any] = {
        "input": {"params": dict(input or {})},
        "steps": {},
    }

    trace: list[dict[str, Any]] = []
    first_error: dict[str, Any] | None = None
    branch_choices = branch_choices or {}

    cur = start
    for _ in range(max_steps):
        if cur is None:
            break
        sid = cur.get("id", "?")
        stype = cur.get("type", "")
        step_record: dict[str, Any] = {
            "step_id": sid,
            "type": stype,
            "rendered_args": {},
            "output": None,
            "output_top_keys": [],
            "status": "skipped",
            "note": "",
        }

        # 1) Render args via the live FSR's Jinja engine, walking
        # nested dicts/lists. Falls back to raw values if no live FSR
        # (so the trace still shows what the agent wrote).
        raw_args = cur.get("arguments") or cur.get("args") or {}
        client = _live_client()
        render_errors: list[str] = []

        def _render_walk(value: Any, path: str = "") -> Any:
            if isinstance(value, str):
                if "{{" not in value or client is None:
                    return value
                try:
                    out = client.post(
                        "/api/wf/api/jinja-editor/",
                        data={"template": value,
                              "values": {"vars": vars_ctx}},
                    )
                    if isinstance(out, dict):
                        for k in ("result", "output", "rendered", "value"):
                            if k in out:
                                return out[k]
                        return out
                    return out if out is not None else value
                except Exception as exc:  # noqa: BLE001
                    render_errors.append(f"{path}: {exc}")
                    return value
            if isinstance(value, dict):
                return {k: _render_walk(v, f"{path}.{k}" if path else k)
                        for k, v in value.items()}
            if isinstance(value, list):
                return [_render_walk(v, f"{path}[{i}]")
                        for i, v in enumerate(value)]
            return value

        rendered = (_render_walk(raw_args)
                    if isinstance(raw_args, dict) else {})
        if render_errors:
            step_record["note"] = "jinja render failed: " + "; ".join(
                render_errors[:3])
            if first_error is None:
                first_error = {"step_id": sid,
                               "message": render_errors[0]}
        step_record["rendered_args"] = rendered

        # 2) Execute or simulate.
        sim_output: Any = None
        if stype == "connector" and execute_safe_ops:
            cn = rendered.get("connector") or cur.get("connector")
            opn = rendered.get("operation") or cur.get("operation")
            cat = _safe_op_category(cn or "", opn or "")
            risk = _op_risk(opn or "", cat)
            if risk == "safe" and cn and opn:
                try:
                    op_result = run_op(connector=cn, op=opn,
                                       params=rendered, confirm=False)
                    if op_result.get("ok"):
                        sim_output = op_result.get("data")
                        step_record["output_top_keys"] = (
                            op_result.get("output_top_keys") or [])
                        step_record["status"] = "executed"
                    else:
                        step_record["status"] = "exec_failed"
                        step_record["note"] = op_result.get("message", "")
                        if first_error is None:
                            first_error = {
                                "step_id": sid,
                                "message": step_record["note"]
                                or "connector exec failed",
                            }
                except Exception as exc:  # noqa: BLE001
                    step_record["status"] = "exec_failed"
                    step_record["note"] = str(exc)
                    if first_error is None:
                        first_error = {"step_id": sid, "message": str(exc)}
            else:
                step_record["status"] = "simulated"
                step_record["note"] = (
                    f"non-safe op (risk={risk}); simulated to keep "
                    "stepper read-only")
        elif stype == "set_variable":
            # The handler writes each arg_list item into vars.steps.<sid>.<name>.
            sim_output = {}
            arg_list = rendered.get("arg_list") or []
            if isinstance(arg_list, list):
                for item in arg_list:
                    if isinstance(item, dict) and "name" in item:
                        sim_output[item["name"]] = item.get("value")
            else:
                sim_output = {k: v for k, v in rendered.items()
                              if k != "step_variables"}
            step_record["status"] = "simulated"
        elif stype.startswith("start"):
            sim_output = {}
            step_record["status"] = "simulated"
            step_record["note"] = "trigger entry"
        elif stype in {"stop", "end"}:
            step_record["status"] = "simulated"
            step_record["note"] = "terminal"
            trace.append(step_record)
            break
        else:
            sim_output = {}
            step_record["status"] = "simulated"
            step_record["note"] = (
                f"step type {stype!r} not executed; rendered args "
                "captured for downstream inspection")

        # Update context. Use jinja key (name with spaces → underscores)
        # to match the FSR runtime contract, falling back to id.
        jkey = (cur.get("name") or sid).replace(" ", "_")
        if step_record["status"] == "executed":
            vars_ctx["steps"][jkey] = sim_output
            sample = sim_output[0] if (
                isinstance(sim_output, list) and sim_output
            ) else sim_output
            if isinstance(sample, dict):
                step_record["output_top_keys"] = sorted(sample.keys())
        else:
            vars_ctx["steps"][jkey] = sim_output if sim_output is not None else {}
            if isinstance(sim_output, dict):
                step_record["output_top_keys"] = sorted(sim_output.keys())
        step_record["output"] = sim_output
        trace.append(step_record)

        # 3) Advance.
        nxt_id = _next_step(cur, branch_choices.get(sid), by_id)
        if not nxt_id or nxt_id not in by_id:
            break
        cur = by_id[nxt_id]

    return {
        "ok": first_error is None,
        "playbook": pb.get("name"),
        "trace": trace,
        "first_error": first_error,
        "steps_executed": len(trace),
    }


# ---------------------------------------------------------------------------
# Recipe prechecks (success-ladder L2 building blocks)
# ---------------------------------------------------------------------------

@mcp.tool()
def precheck_connector_installed(name: str,
                                 version: str | None = None) -> dict[str, Any]:
    """Verify a connector is installed on the live FSR before authoring
    a recipe or playbook against it.

    Catches the silent-failure case where a recipe ships compile-clean
    but the first connector step fails at runtime with "configuration
    not found." On miss, returns close-match suggestions drawn from the
    appliance's actual catalog.
    """
    client = _live_client()
    if client is None:
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR instance not configured"}
    from recipes.prechecks import check_connector_installed
    return check_connector_installed(client, name, version).to_dict()


@mcp.tool()
def precheck_picklist_value(picklist_name: str,
                            value: str) -> dict[str, Any]:
    """Verify a friendly value resolves to an IRI on the live FSR before
    embedding `{{ 'PL' | picklist('value') }}` in a playbook.

    Catches typos like 'In Progress' for AlertStatus (which only has
    Open / Investigating / Pending / Closed / Active / Re-Opened).
    Returns close-match suggestions when the value isn't an exact
    itemValue.
    """
    client = _live_client()
    if client is None:
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR instance not configured"}
    from recipes.prechecks import check_picklist_value
    return check_picklist_value(client, picklist_name, value).to_dict()


def _build_query_filters(filters: Any) -> dict[str, Any]:
    """Normalize a friendly filter spec to an FSR /api/query body.

    Accepts either a `{field: value, ...}` dict (AND-combined eq filters)
    or a pre-shaped `{logic, filters: [...]}` body, which is passed
    through unchanged.
    """
    if isinstance(filters, dict) and "filters" in filters and "logic" in filters:
        return filters
    if not isinstance(filters, dict):
        raise ValueError("filters must be a dict")
    flist = []
    for field, value in filters.items():
        flist.append({
            "field": field, "operator": "eq", "value": value, "type": "primitive",
        })
    return {"logic": "AND", "filters": flist} if flist else {
        "logic": "AND", "filters": [],
    }


_COUNT_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


def _query_module(client: Any, module: str, body: dict[str, Any],
                  limit: int = 5) -> dict[str, Any]:
    """POST /api/query/<module> with a filter body. Returns hydra payload."""
    url = client.base_url + f"/api/query/{module}?$limit={int(limit)}"
    r = client.session.post(url, json=body, verify=client.verify_ssl)
    if r.status_code != 200:
        return {"_http_status": r.status_code, "_error": r.text[:500]}
    return r.json()


def _assert_one(client: Any, a: dict[str, Any]) -> dict[str, Any]:
    kind = a.get("kind")
    module = a.get("module")
    if not kind:
        return {"ok": False, "code": "missing_kind", "message": "assertion requires `kind`"}
    if not module and kind in ("record_exists", "record_count", "field_equals"):
        return {"ok": False, "code": "missing_module",
                "message": f"{kind} requires `module`", "kind": kind}
    try:
        body = _build_query_filters(a.get("filters", {}))
    except ValueError as e:
        return {"ok": False, "code": "bad_filters", "message": str(e), "kind": kind}

    if kind == "record_exists":
        data = _query_module(client, module, body, limit=1)
        if "_error" in data:
            return {"ok": False, "code": "query_failed", "kind": kind,
                    "message": f"HTTP {data.get('_http_status')}: {data['_error']}"}
        total = int(data.get("hydra:totalItems", len(data.get("hydra:member", []))))
        ok = total > 0
        return {"ok": ok, "kind": kind, "module": module,
                "code": "ok" if ok else "no_match",
                "observed_count": total,
                "message": (f"found {total} matching record(s)" if ok else
                            f"no records matched filters in module '{module}'")}

    if kind == "record_count":
        op = a.get("op", "eq")
        expected = a.get("value")
        if op not in _COUNT_OPS:
            return {"ok": False, "code": "bad_op", "kind": kind,
                    "message": f"op must be one of {sorted(_COUNT_OPS)}"}
        if not isinstance(expected, (int, float)):
            return {"ok": False, "code": "bad_value", "kind": kind,
                    "message": "record_count `value` must be a number"}
        data = _query_module(client, module, body, limit=1)
        if "_error" in data:
            return {"ok": False, "code": "query_failed", "kind": kind,
                    "message": f"HTTP {data.get('_http_status')}: {data['_error']}"}
        total = int(data.get("hydra:totalItems", len(data.get("hydra:member", []))))
        ok = _COUNT_OPS[op](total, expected)
        return {"ok": ok, "kind": kind, "module": module,
                "code": "ok" if ok else "count_mismatch",
                "observed_count": total, "op": op, "expected": expected,
                "message": (f"count {total} {op} {expected}" if ok else
                            f"count {total} not {op} {expected}")}

    if kind == "field_equals":
        field = a.get("field")
        expected = a.get("value")
        if not field:
            return {"ok": False, "code": "missing_field", "kind": kind,
                    "message": "field_equals requires `field`"}
        data = _query_module(client, module, body, limit=2)
        if "_error" in data:
            return {"ok": False, "code": "query_failed", "kind": kind,
                    "message": f"HTTP {data.get('_http_status')}: {data['_error']}"}
        members = data.get("hydra:member", [])
        total = int(data.get("hydra:totalItems", len(members)))
        if total == 0:
            return {"ok": False, "code": "no_match", "kind": kind, "module": module,
                    "field": field, "expected": expected,
                    "message": f"no records matched filters in module '{module}'"}
        if total > 1:
            return {"ok": False, "code": "ambiguous", "kind": kind, "module": module,
                    "field": field, "expected": expected, "observed_count": total,
                    "message": (f"filters matched {total} records; field_equals "
                                "needs exactly one. Tighten filters.")}
        rec = members[0] if members else {}
        # Walk dotted field path against the record (supports nested keys).
        actual: Any = rec
        for part in str(field).split("."):
            if isinstance(actual, dict) and part in actual:
                actual = actual[part]
            else:
                actual = None
                break
        ok = actual == expected
        return {"ok": ok, "kind": kind, "module": module, "field": field,
                "expected": expected, "observed": actual,
                "code": "ok" if ok else "field_mismatch",
                "message": (f"{module}.{field} == {expected!r}" if ok else
                            f"{module}.{field}: expected {expected!r}, "
                            f"got {actual!r}")}

    return {"ok": False, "code": "unknown_kind", "kind": kind,
            "message": (f"unknown assertion kind '{kind}'; expected one of "
                        "record_exists, record_count, field_equals")}


@mcp.tool()
def assert_playbook_outcome(assertions: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a playbook produced its intended effect on the live FSR.

    Run a list of declarative assertions against the live FSR (typically
    after `run_playbook`/`dry_run_playbook`) to confirm the playbook did
    what its description says it does — closes Level 5 of the success
    ladder and gives the LLM-evaluation harness a deterministic scorer.

    Each assertion is a dict with one of three shapes:

    - `{"kind": "record_exists", "module": "alerts",
        "filters": {"name": "Demo alert", "severity.itemValue": "High"}}`
       passes when ≥1 matching record exists.

    - `{"kind": "record_count", "module": "indicators",
        "filters": {"sourceId": "feed-123"}, "op": "gte", "value": 10}`
       passes when the count satisfies the comparison. `op` is one of
       eq | ne | gt | gte | lt | lte.

    - `{"kind": "field_equals", "module": "alerts",
        "filters": {"name": "Demo alert"}, "field": "status.itemValue",
        "value": "Closed"}`
       requires exactly one matching record and checks a (dotted) field.

    `filters` accepts a friendly `{field: value, ...}` dict (AND-combined
    eq) OR a full `{logic, filters: [...]}` query body for OR / range /
    nested logic.

    Returns `{ok, total, passed, failed, results: [...]}` where each
    result has `ok`, `code`, `message`, plus echoed inputs and
    `observed`/`observed_count` so the agent can self-correct without
    a follow-up tool call.
    """
    if not isinstance(assertions, list) or not assertions:
        return {"ok": False, "code": "empty_assertions",
                "message": "assertions must be a non-empty list"}
    client = _live_client()
    if client is None:
        return {"ok": False, "code": "no_live_fsr",
                "message": "FSR instance not configured"}
    results = [_assert_one(client, a if isinstance(a, dict) else {})
               for a in assertions]
    passed = sum(1 for r in results if r.get("ok"))
    return {
        "ok": passed == len(results),
        "total": len(results), "passed": passed, "failed": len(results) - passed,
        "results": results,
    }


@mcp.tool()
def generate_recipe(
    kind: str,
    info_json_path: str,
    target_module: str = "alerts",
    fetch_op: str | None = None,
    dedup_field: str | None = None,
    severity_field: str = "severity",
    status_field: str = "status",
    severity_enum: list[str] | None = None,
    status_enum: list[str] | None = None,
    config_uuid: str = "REPLACE_WITH_CONFIG_UUID",
    persist: bool = False,
    when_to_use: str | None = None,
) -> dict[str, Any]:
    """Synthesize an ingestion playbook from a connector's `info.json`.

    Wraps the same generators `fsrpb generate-recipe` calls so an LLM
    agent can mint a recipe inline from a single tool call instead of
    shelling out. Returns both the FSR JSON (importable directly) and
    the decompiled YAML (so the agent can present an editable form to
    the user before pushing).

    Args:
        kind: `threat-feed` or `data-ingest`.
        info_json_path: filesystem path to the connector's info.json
            (typically pulled out of the RPM cache).
        target_module: data-ingest only — `alerts` (default) or
            `incidents`.
        fetch_op: explicit fetch op override (data-ingest); auto-detect
            scans the connector's ops by name when omitted.
        dedup_field: vendor field used as `sourceId` for upsert.
        severity_field, status_field: vendor fields carrying severity /
            status enum strings.
        severity_enum, status_enum: comma list of vendor enum values
            (data-ingest only) — needed for the picklist-resolve macro.
        config_uuid: connector configuration uuid; recipe ships
            `REPLACE_WITH_CONFIG_UUID` placeholder when omitted so the
            user can substitute post-import.
        persist: when True, decompile the FSR JSON to YAML and store
            into the `recipes` table keyed `<kind>:<connector>` so
            `find_recipe` can return it later.
        when_to_use: optional human-readable trigger description
            recorded with `persist=True`.

    Returns:
        {ok: true, kind, name, connector, fsr_json, yaml,
         persisted: bool} on success, or the standard error envelope
        with `code` ∈ {`bad_kind`, `info_json_missing`,
        `generator_failed`}.
    """
    if kind not in ("threat-feed", "data-ingest"):
        return _err("bad_kind",
                    f"unknown recipe kind {kind!r}",
                    suggestions=["threat-feed", "data-ingest"])
    p = Path(info_json_path)
    if not p.exists():
        return _err("info_json_missing",
                    f"info.json not found at {info_json_path}",
                    suggestions=["check the path",
                                 "extract from store/rpm_cache/"])
    try:
        info = json.loads(p.read_text())
    except Exception as exc:  # noqa: BLE001
        return _err("info_json_invalid", f"info.json parse failed: {exc}")

    sys.path.insert(0, str(REPO_ROOT / "python"))
    try:
        from recipes import (generate_data_ingest_recipe,  # noqa: PLC0415
                             generate_threat_feed_recipe)
        if kind == "threat-feed":
            fsr_json = generate_threat_feed_recipe(
                info, connector_config_uuid=config_uuid,
            )
        else:
            fsr_json = generate_data_ingest_recipe(
                info,
                target_module=target_module,
                fetch_op_name=fetch_op,
                dedup_field=dedup_field,
                severity_field=severity_field,
                status_field=status_field,
                severity_enum=severity_enum,
                status_enum=status_enum,
                connector_config_uuid=config_uuid,
            )
    except Exception as exc:  # noqa: BLE001
        return _err("generator_failed", repr(exc),
                    suggestions=["call list_configured_connectors to "
                                 "find a real config_uuid",
                                 "set fetch_op explicitly if auto-"
                                 "detect picked the wrong op"])

    # Decompile to YAML for the agent + (optional) persistence.
    try:
        from compiler.decompiler import decompile_to_yaml  # noqa: PLC0415
        yaml_text = decompile_to_yaml(fsr_json, DB_PATH)
    except Exception as exc:  # noqa: BLE001
        yaml_text = f"# decompile failed: {exc!r}\n"

    connector = info.get("name") or "unknown"
    name = f"{kind.replace('-', '_')}:{connector}"
    persisted = False
    if persist:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO recipes
                       (name, kind, when_to_use, yaml_template, source_playbook)
                       VALUES (?,?,?,?,?)""",
                    (name, kind.replace("-", "_"),
                     when_to_use or f"{kind} ingestion for {connector}",
                     yaml_text, connector),
                )
                conn.commit()
            persisted = True
        except Exception:  # noqa: BLE001
            persisted = False

    return {
        "ok": True,
        "kind": kind,
        "name": name,
        "connector": connector,
        "fsr_json": fsr_json,
        "yaml": yaml_text,
        "persisted": persisted,
    }


@mcp.tool()
def find_recipe(query: str = "", kind: str | None = None,
                limit: int = 10) -> dict[str, Any]:
    """Look up persisted recipes by name / connector / kind.

    Returns recipes previously stored via `generate_recipe(persist=True)`
    or the CLI's `--persist`. `query` is a substring match against
    `name`, `source_playbook`, or `when_to_use`. `kind` filters to
    `threat_feed` / `data_ingest` etc. Returns the YAML template so
    the agent can paste it into the editor verbatim.
    """
    sql_parts = ["1=1"]
    args: list[Any] = []
    if query:
        sql_parts.append(
            "(name LIKE ? OR source_playbook LIKE ? OR when_to_use LIKE ?)"
        )
        like = f"%{query}%"
        args.extend([like, like, like])
    if kind:
        sql_parts.append("kind = ?")
        args.append(kind.replace("-", "_"))
    args.append(int(limit))
    with _db() as conn:
        rows = _rows(
            conn,
            "SELECT name, kind, when_to_use, yaml_template, source_playbook "
            f"FROM recipes WHERE {' AND '.join(sql_parts)} "
            "ORDER BY name LIMIT ?",
            tuple(args),
        )
    return {"ok": True, "count": len(rows), "recipes": rows}


_JINJA_BLOCK_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def _walk_args_with_path(
    value: Any, prefix: str = "",
) -> list[tuple[str, str]]:
    """Yield (dotted_path, string_value) for every string leaf in a
    nested dict/list. Used to find Jinja templates inside step args."""
    out: list[tuple[str, str]] = []
    if isinstance(value, str):
        out.append((prefix or "(root)", value))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(_walk_args_with_path(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(_walk_args_with_path(v, f"{prefix}[{i}]"))
    return out


@mcp.tool()
def diagnose_yaml_against_pb_execution(
    yaml_text: str, pb_execution: str,
) -> dict[str, Any]:
    """Diagnose why a playbook run failed by re-rendering each step's
    arguments against the run's actual `vars` env.

    Closes the failure-recovery loop: instead of squinting at FSR's
    per-step audit log, this tool pulls the run's `{vars: {...env,
    steps: {...}}}` context, then walks the YAML's step args and
    renders every embedded `{{ ... }}` block against that context.
    Surface output:

    - `run_status`: terminal status from the FSR side.
    - `step_diagnostics`: one row per (step, arg_path, template) with
      `rendered` on success or `code` + `message` on render failure.
      Common codes: `step_missing` (a referenced `vars.steps.<key>` has
      no entry in the run env — typo or unreached step), `render_error`
      (Jinja engine threw — bad filter/expr), `attribute_missing` (the
      template rendered "None" because a path traversed an empty leg).
    - `hints`: top-level suggestions distilled from the diagnostics
      (e.g. "step Foo references vars.steps.Bar but Bar didn't run").

    Args:
        yaml_text: the playbook YAML you want to diagnose.
        pb_execution: workflow PK (digits, e.g. "676747") OR task_id UUID
            of the failed (or completed) run to use as the env source.
    """
    env_out = get_run_env(pb_execution)
    if "error" in env_out or env_out.get("ok") is False:
        return _err(
            "run_env_unavailable",
            (env_out.get("error") or env_out.get("message")
             or "could not fetch run env"),
            suggestions=[
                "Confirm the pb_execution id / task_id is correct",
                "Historical runs are purged after ~60 min on most FSRs",
            ],
            pb_execution=pb_execution,
        )

    run_status = env_out.get("status")
    run_vars = env_out.get("vars") or {}
    steps_in_env = (run_vars.get("steps") or {}) if isinstance(run_vars, dict) else {}

    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception as exc:  # noqa: BLE001
        return _err("yaml_parse_failed", f"YAML parse error: {exc}",
                    suggestions=["Run `validate_yaml` first to surface "
                                 "structural issues"])

    diagnostics: list[dict[str, Any]] = []
    referenced_step_keys: set[str] = set()
    vars_steps_re = re.compile(r"vars\.steps\.([A-Za-z0-9_]+)")

    playbooks = doc.get("playbooks") or []
    for pb in playbooks if isinstance(playbooks, list) else []:
        if not isinstance(pb, dict):
            continue
        pb_name = pb.get("name") or "<unnamed>"
        for s in (pb.get("steps") or []):
            if not isinstance(s, dict):
                continue
            step_name = s.get("name") or s.get("id") or "<unnamed>"
            args = s.get("arguments") or s.get("args") or {}
            for arg_path, leaf in _walk_args_with_path(args):
                blocks = _JINJA_BLOCK_RE.findall(leaf)
                if not blocks:
                    continue
                # Track every vars.steps.<key> reference for hints.
                for blk in blocks:
                    for m in vars_steps_re.finditer(blk):
                        referenced_step_keys.add(m.group(1))
                # Render the full leaf string (preserves surrounding text).
                try:
                    r = render_jinja(template=leaf,
                                     context=None,
                                     from_pb_execution=pb_execution)
                except Exception as exc:  # noqa: BLE001
                    diagnostics.append({
                        "playbook": pb_name, "step": step_name,
                        "arg_path": arg_path, "template": leaf,
                        "ok": False, "code": "render_threw",
                        "message": repr(exc),
                    })
                    continue
                if isinstance(r, dict) and r.get("error"):
                    diagnostics.append({
                        "playbook": pb_name, "step": step_name,
                        "arg_path": arg_path, "template": leaf,
                        "ok": False, "code": "render_error",
                        "message": str(r.get("error"))[:400],
                    })
                else:
                    rendered = (r.get("output") if isinstance(r, dict) else r)
                    code = "ok"
                    if rendered in ("", None, "None"):
                        code = "empty_render"
                    diagnostics.append({
                        "playbook": pb_name, "step": step_name,
                        "arg_path": arg_path, "template": leaf,
                        "rendered": rendered, "ok": code == "ok",
                        "code": code,
                    })

    # Distill top-level hints.
    hints: list[str] = []
    available = sorted(steps_in_env.keys())
    for key in sorted(referenced_step_keys):
        if key not in steps_in_env:
            hints.append(
                f"step reference `vars.steps.{key}` has no entry in the "
                f"run env — either {key!r} did not execute, or the step "
                f"name in YAML doesn't match (use display name with "
                f"spaces→underscores). Available: "
                + (", ".join(available[:8]) or "(none)")
            )
    fail_n = sum(1 for d in diagnostics if not d.get("ok"))
    return {
        "ok": fail_n == 0 and run_status not in ("failed", "Failed"),
        "pb_execution": pb_execution,
        "run_status": run_status,
        "playbook_name": env_out.get("name"),
        "step_diagnostics": diagnostics,
        "available_step_keys": available,
        "summary": {
            "total_templates": len(diagnostics),
            "render_failures": fail_n,
            "referenced_step_keys": sorted(referenced_step_keys),
        },
        "hints": hints,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
