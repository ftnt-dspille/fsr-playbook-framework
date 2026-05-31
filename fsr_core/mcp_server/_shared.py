"""Shared MCP infrastructure and helpers."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

class _FallbackFastMCP:
    """No-op FastMCP shim for connector runtimes.

    FortiSOAR's connector sandbox only calls these functions directly; it
    doesn't run the stdio MCP server. Some sandbox builds expose import stubs
    that satisfy `from mcp.server.fastmcp import FastMCP` but are not callable,
    so we validate the imported object before using it.
    """

    def __init__(self, *args, **kwargs):
        self._args, self._kwargs = args, kwargs

    def tool(self, *args, **kwargs):
        def _deco(fn):
            return fn
        return _deco

    def run(self, *args, **kwargs):
        raise RuntimeError(
            "MCP stdio server is unavailable: the real 'mcp' package is not "
            "installed. The tool functions are still usable directly; only "
            "`python -m mcp_server` / `fsrpb mcp` need the real SDK.")


try:
    from mcp.server.fastmcp import FastMCP as _ImportedFastMCP
except Exception:  # noqa: BLE001
    FastMCP = _FallbackFastMCP
else:
    FastMCP = _ImportedFastMCP if callable(_ImportedFastMCP) else _FallbackFastMCP

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"

# ---------------------------------------------------------------------------
# MCP server instance (shared across all tools)
# ---------------------------------------------------------------------------
def _make_mcp():
    server = FastMCP(
        "fsrpb",
        instructions=(
            "FortiSOAR playbook authoring tools. "
            "Use find_connector → find_operation → get_op_schema to build connector steps. "
            "Use get_step_type for non-connector step schemas. "
            "Use validate_yaml before compile_yaml to catch errors early. "
            "All YAML must conform to the simplified IR documented in AUTHORING.md."
        ),
    )
    if not callable(getattr(server, "tool", None)):
        raise TypeError("FastMCP.tool is not callable")
    if not callable(server.tool()):
        raise TypeError("FastMCP.tool() did not return a decorator")
    return server


try:
    mcp = _make_mcp()
except Exception:  # noqa: BLE001
    mcp = _FallbackFastMCP("fsrpb")

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


def _capability_gap_suggestion(
    *,
    id: str,
    missing: str,
    why: str,
    fix_steps: list[str],
    resume_value: str,
    resume_label: str = "Re-check & continue",
    tips: list[dict[str, Any]] | None = None,
    alternatives: list[dict[str, Any]] | None = None,
    docs_url: str | None = None,
) -> dict[str, Any]:
    """Build a `suggested_card` payload (the kwargs for
    `emit_capability_gap_card`) for a missing-capability dead end, so every
    tool that hits one offers the analyst the SAME never-dead-end shape:
    what's missing, why, concrete fix steps, a resume button, and optional
    tips / manual fallbacks. The agent forwards this straight into
    `emit_capability_gap_card` (see system_prompt_triage.md). Returns the
    kwargs dict only — the emitter adds `type` and validates."""
    card: dict[str, Any] = {
        "id": id,
        "missing": missing,
        "why": why,
        "fix_steps": list(fix_steps),
        "resume": {"label": resume_label, "value": resume_value},
    }
    if tips:
        card["tips"] = tips
    if alternatives:
        card["alternatives"] = alternatives
    if docs_url:
        card["docs_url"] = docs_url
    return card


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


# Param types whose value is constrained to an options_json picklist.
_SELECT_TYPES = {"select", "multiselect", "picklist", "radio"}
# Param types we type-check (loosely — FSR coerces strings → ints/bools at
# execute, so we only reject values that can't possibly coerce).
_INT_TYPES = {"integer", "number"}
_BOOL_TYPES = {"checkbox", "boolean", "bool"}


def _is_jinja(val: Any) -> bool:
    """A value the agent left as a template (`{{vars.x}}`) — we can't
    validate its concrete content, so membership/type checks must skip it."""
    return isinstance(val, str) and "{{" in val and "}}" in val


def _validate_op_params(connector: str, op: str,
                        params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate `params` against the operation's parameter schema.

    Mirrors `_validate_op_exists`: catches typo'd/unknown params, missing
    required params, and select values outside the option set BEFORE the op
    runs — so a malformed call surfaces as an actionable `bad_params` error
    the agent self-corrects against, instead of an opaque post-approval
    `execution_failed` (or, worse, an approval card the analyst signs off on
    that then fails).

    Returns an error envelope with an `issues` list, or None when the call
    is well-formed. Returns None (don't block) when:
    - the op has no params catalogued (un-synced store → can't prove a param
      is unknown; live execute will guard), OR
    - the store is unreadable.

    Conditional sub-params are resolved from submitted parent values, so
    required checks only apply to the active branch. Values left as Jinja
    templates are skipped for membership/type (we can't see their runtime
    content). Type checks are deliberately loose — FSR coerces `"5"`→5 and
    `"true"`→bool at execute, so we only reject values that cannot coerce at
    all.
    """
    import difflib
    import json as _json

    if not connector or not op:
        return None
    params = params or {}
    try:
        with _db() as conn:
            rows = _rows(
                conn,
                "SELECT param_name, title, type, required, options_json, "
                "parent_param_name, condition_value "
                "FROM operation_params WHERE connector_name=? AND op_name=?",
                (connector, op),
            )
    except sqlite3.Error:
        return None  # store unreadable → don't block; live exec will guard
    if not rows:
        return None  # no schema catalogued → can't validate

    def _clean(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text != "" else None

    def _matches(value: Any, expected: str | None) -> bool:
        if expected is None:
            return False
        if isinstance(value, list):
            return any(str(item) == expected for item in value)
        return str(value) == expected

    rows_by_name: dict[str, list[dict[str, Any]]] = {}
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    top_level: list[dict[str, Any]] = []
    for r in rows:
        rows_by_name.setdefault(r["param_name"], []).append(r)
        parent = _clean(r["parent_param_name"])
        if parent is None:
            top_level.append(r)
        else:
            children_by_parent.setdefault(parent, []).append(r)

    known_names = set(rows_by_name)
    active: dict[str, dict[str, Any]] = {}
    stack = list(top_level)
    while stack:
        r = stack.pop(0)
        name = r["param_name"]
        active.setdefault(name, r)
        if name not in params:
            continue
        for child in children_by_parent.get(name, []):
            if _matches(params.get(name), _clean(child["condition_value"])):
                stack.append(child)

    issues: list[dict[str, Any]] = []

    # 1. Unknown params (typo detector).
    for key in params:
        if key not in known_names:
            close = difflib.get_close_matches(key, list(known_names), n=3, cutoff=0.5)
            issues.append({
                "param": key,
                "problem": "unknown",
                "near": close,
                "detail": (f"'{key}' is not a parameter of {connector}/{op}"
                           + (f"; did you mean {close}?" if close else "")),
            })

    # 2. Missing required params on the active conditional branch only.
    for name, r in active.items():
        if not r["required"]:
            continue
        val = params.get(name)
        if name not in params or val is None or val == "":
            issues.append({
                "param": name,
                "problem": "missing_required",
                "detail": f"required parameter '{name}' "
                          f"({r['title'] or name}) is missing",
            })

    # 3. Select-option membership + loose type checks.
    for name, candidates in rows_by_name.items():
        if name not in params:
            continue
        r = active.get(name) or candidates[0]
        val = params[name]
        if val is None or _is_jinja(val):
            continue
        ptype = (r["type"] or "").lower()
        opts = None
        if r["options_json"]:
            try:
                parsed = _json.loads(r["options_json"])
                if isinstance(parsed, list) and parsed:
                    opts = [str(o) for o in parsed]
            except (ValueError, TypeError):
                opts = None
        if opts is not None and ptype in _SELECT_TYPES:
            vals = val if isinstance(val, list) else [val]
            bad = [v for v in vals
                   if not _is_jinja(v) and str(v) not in opts]
            if bad:
                issues.append({
                    "param": name,
                    "problem": "bad_select_value",
                    "options": opts,
                    "detail": f"{name}={bad!r} not in allowed options {opts}",
                })
            continue
        if ptype in _INT_TYPES and not _coerces_to_int(val):
            issues.append({
                "param": name, "problem": "bad_type",
                "detail": f"{name} expects an integer; got {val!r}",
            })
        elif ptype in _BOOL_TYPES and not _coerces_to_bool(val):
            issues.append({
                "param": name, "problem": "bad_type",
                "detail": f"{name} expects a boolean; got {val!r}",
            })

    if not issues:
        return None
    return _err(
        "bad_params",
        f"operation '{op}' on '{connector}' called with {len(issues)} "
        f"invalid argument(s)",
        suggestions=[
            f"Call get_op_schema({connector!r}, {op!r}) to see the exact "
            "parameter names, types, required flags, and select options",
            "Re-issue the call with corrected args (fix the issues below)",
        ],
        connector=connector,
        op=op,
        issues=issues,
    )


def _coerces_to_int(val: Any) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, int):
        return True
    if isinstance(val, str):
        try:
            int(val.strip())
            return True
        except ValueError:
            return False
    return False


def _coerces_to_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return True
    if isinstance(val, str):
        return val.strip().lower() in {"true", "false", "0", "1", "yes", "no"}
    if isinstance(val, int):
        return val in (0, 1)
    return False


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
    ts = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
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
