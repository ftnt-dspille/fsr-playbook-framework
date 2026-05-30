"""Shared MCP infrastructure and helpers."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # The connector runtime (FortiSOAR, Python 3.9) doesn't ship the `mcp`
    # SDK (which needs 3.10+) and doesn't need the stdio server — it only
    # calls the tool *functions*, which are plain callables. Provide a
    # minimal stand-in whose `.tool()` decorator registers nothing and
    # returns the function unchanged, so `fsr_core.mcp_server` imports
    # cleanly and the agent tool registry still works. `.run()` (the stdio
    # transport) is the only thing that genuinely needs the real SDK.
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self._args, self._kwargs = args, kwargs

        def tool(self, *args, **kwargs):
            def _deco(fn):
                return fn
            return _deco

        def run(self, *args, **kwargs):
            raise RuntimeError(
                "MCP stdio server is unavailable: the 'mcp' package is not "
                "installed (it requires Python 3.10+). The tool functions are "
                "still usable directly; only `python -m mcp_server` / `fsrpb "
                "mcp` need the real SDK.")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"

# ---------------------------------------------------------------------------
# MCP server instance (shared across all tools)
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


def _validate_op_exists(connector: str, op: str) -> dict[str, Any] | None:
    """Confirm `op` is a real operation on `connector` per the reference store.

    Returns an `unknown_operation` error envelope (with near-match
    suggestions) when the connector HAS operations catalogued but `op`
    isn't among them — so a hallucinated/typo'd op name becomes an
    actionable error the agent can self-correct against, instead of an
    opaque `execution_failed` after the user has already approved it.

    Returns None (caller proceeds) when:
    - the op exists, OR
    - the connector has zero operations in the store. We can't prove
      non-existence against an empty/un-synced catalogue, so we don't
      false-reject; the connector existence check + live execution still
      guard that path.

    Caller is responsible for validating the connector itself first
    (`run_op` returns `unknown_connector`); this only covers the op.
    """
    import difflib

    if not connector or not op:
        return None
    try:
        with _db() as conn:
            all_ops = [
                r["op_name"] for r in _rows(
                    conn,
                    "SELECT op_name FROM operations WHERE connector_name = ?",
                    (connector,),
                )
            ]
    except sqlite3.Error:
        return None  # store unreadable → don't block; live exec will guard
    if not all_ops or op in all_ops:
        return None
    close = difflib.get_close_matches(op, all_ops, n=5, cutoff=0.4)
    suggestions = [
        f"Use find_operation(connector={connector!r}) to list the real ops",
        "Then get_op_schema(connector, op) before run_op/emit_action_card",
    ]
    if close:
        suggestions.insert(0, f"Did you mean one of: {close}?")
    return _err(
        "unknown_operation",
        f"operation '{op}' not found on connector '{connector}' "
        f"({len(all_ops)} ops catalogued)",
        suggestions=suggestions,
        connector=connector,
        op=op,
        near=close,
    )


# Status precedence: tested_pass and tested_fail beat 'seen'; among those,
# the most recent ts wins. 'seen' is a weak signal (we catalogued the
# row, never exercised it).
_VERIF_RANK = {"tested_pass": 3, "tested_fail": 3, "seen": 1}


def _verifications_for(conn: sqlite3.Connection, kind: str,
                        keys: list[str]) -> dict[str, dict]:
    """Batch-load the strongest verification per key for one kind.

    Returns `{key: {status, method, ts, notes_excerpt}}`. Missing keys
    are absent. Picks tested_* over seen, then newest ts wins.
    """
    if not keys:
        return {}
    placeholders = ",".join("?" * len(keys))
    rows = conn.execute(
        f"""SELECT key, status, method, ts, notes
            FROM verifications
            WHERE kind=? AND key IN ({placeholders})""",
        (kind, *keys),
    ).fetchall()
    best: dict[str, dict] = {}
    for r in rows:
        cur = best.get(r["key"])
        rank = _VERIF_RANK.get(r["status"], 0)
        if cur is None or rank > cur["_rank"] or (
            rank == cur["_rank"] and (r["ts"] or "") > (cur["ts"] or "")
        ):
            notes = r["notes"] or ""
            best[r["key"]] = {
                "status": r["status"],
                "method": r["method"],
                "ts": r["ts"],
                "notes_excerpt": (notes[:160] + "…") if len(notes) > 160 else notes,
                "_rank": rank,
            }
    for v in best.values():
        v.pop("_rank", None)
    return best


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


_LIVE_CLIENT_CACHE: dict[str, Any] = {}


def _live_client():
    """Return a live FSR client or None if env not configured.

    Memoised per-process so we reuse one TLS-pooled session instead of
    paying a fresh handshake on every tool call. Saves ~1.3 s per
    icon/picklist fetch in practice.
    """
    if "client" in _LIVE_CLIENT_CACHE:
        return _LIVE_CLIENT_CACHE["client"]
    try:
        from probes._env import get_client, get_config
    except Exception:  # noqa: BLE001
        return None
    if not get_config().is_live():
        return None
    c = get_client()
    if c is not None:
        _LIVE_CLIENT_CACHE["client"] = c
    return c


def _safe_op_category(connector: str, op: str) -> str:
    """Look up operation category to determine risk level for execution."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT category FROM operations "
            "WHERE connector_name=? AND op_name=?",
            (connector, op),
        ).fetchone()
        return (row["category"] if row else "") or ""
    finally:
        conn.close()
