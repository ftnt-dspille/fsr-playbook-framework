"""MCP tools: Tools Corpus"""
from __future__ import annotations
from . import _shared

import json
import sqlite3
import sys
from typing import Any

from ._shared import (
    mcp,
    _err,
    _db,
    _rows,
    REPO_ROOT,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_playbooks(q: str, limit: int = 10,
                     verbose: bool = False) -> list[dict[str, Any]]:
    """Full-text search over playbook patterns seen in production.

    Returns matching playbook names + collections — useful for 'how do
    others do X' pattern mining.

    Args:
        verbose: when True, include `description` (FTS) /
            `uses_connectors_csv` + `step_count` (fallback). Default
            returns the slim row set so a top-of-funnel "what playbooks
            mention X" lookup costs few tokens.
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
                if not verbose:
                    for r in rows:
                        r.pop("description", None)
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
        if not verbose:
            for r in rows:
                r.pop("uses_connectors_csv", None)
                r.pop("step_count", None)
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
# find_step_recipe — prebuilt + validated step fragments
# ---------------------------------------------------------------------------

@mcp.tool()
def find_step_recipe(intent: str = "",
                     connector: str | None = None,
                     step_type: str | None = None,
                     limit: int = 5) -> dict[str, Any]:
    """Look up prebuilt YAML step fragments by intent.

    Each recipe is a small block of one or more steps that is known to
    compile clean (CI-validated). Use this BEFORE drafting common
    patterns from scratch — it eliminates the validate-fix-validate
    cascade for things like:

      - manual_input as the trigger (no `start` step)
      - approve/reject gates
      - FortiGate block_ip with the correct param set per method
      - set_variable shape (arg_list, not step_variables)

    Args:
        intent: natural-language description of what you're trying to
                build, e.g. "block an ip on fortigate using a policy".
        connector: optional filter — only return recipes bound to this
                   connector (e.g. 'fortigate-firewall'). Generic
                   recipes (no connector binding) still match.
        step_type: optional filter — only recipes that include this step
                   type (e.g. 'manual_input', 'connector', 'set_variable').
        limit: max recipes to return (default 5).

    Returns: {ok: true, matches: [{name, description, intent_keywords,
             connector, step_types, steps_yaml, notes}, ...]}.
    """
    sys.path.insert(0, str(REPO_ROOT / "python"))
    from recipes import step_lookup
    matches = step_lookup.find(
        intent=intent, connector=connector, step_type=step_type, limit=limit,
    )
    return {
        "ok": True,
        "matches": [r.to_dict() for r in matches],
        "hint": (
            "Each `steps_yaml` block is paste-ready. Replace placeholders "
            "(<UPPER_CASE> tokens) with your values; update step names "
            "and `next:` targets to fit your playbook. Recipes are "
            "compile-validated — no validation cascade if you keep the "
            "selected param values consistent with the recipe's group."
        ),
    } if matches else {
        "ok": True,
        "matches": [],
        "hint": (
            f"No recipes matched intent={intent!r}. Fall back to "
            f"find_operation + get_op_schema; check `param_groups_by_select` "
            f"on the schema to pick a coherent param set in one shot."
        ),
    }


# ---------------------------------------------------------------------------
# validate_yaml
# ---------------------------------------------------------------------------

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