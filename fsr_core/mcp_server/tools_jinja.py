"""MCP tools: Tools Jinja"""
from __future__ import annotations
from . import _shared

import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from ._shared import (
    mcp,
    _err,
    _db,
    _rows,
    _verifications_for,
    _serialize_compiler_error,
    _infer_shape,
    _store_observed_schema,
    REPO_ROOT,
)
# Import DB_PATH for local use
DB_PATH = _shared.DB_PATH

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def find_jinja_filter(q: str, limit: int = 15,
                      verbose: bool = False) -> list[dict[str, Any]]:
    """Search the Jinja filter catalog by name, description, or example.

    Returns name, signature, description, example, output_type_observed,
    is_trusted (1 = live-tested), and corpus_uses (real-world occurrence
    count in the live playbook corpus).

    Use `get_filter_examples(name)` after this to pull the curated
    long-form doc and more real-world usages for a specific filter.

    Args:
        verbose: when True, include `curated_doc` (rich long-form notes
            for complex filters like json_query, picklist, fromIRI,
            resolveRange) inline. Default omits it — fetch via
            `get_filter_examples` once you've picked a filter.
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
        if not verbose:
            for r in rows:
                r.pop("curated_doc", None)
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

    # FSR sometimes returns the body as a JSON-encoded string (when the
    # response Content-Type is text/plain but the payload is `{"result":
    # 5}`). Unwrap so callers see the native scalar, not a quoted blob.
    if isinstance(r, str):
        s = r.strip()
        if s and s[0] in "{[":
            try:
                r = json.loads(s)
            except Exception:
                return {"output": r}
        else:
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
def find_jinja_example(filter: str | None = None,
                        var_path: str | None = None,
                        intent: str | None = None,
                        step_type: str | None = None,
                        limit: int = 8) -> dict[str, Any]:
    """Search 7,789 real `{{…}}` / `{%…%}` expressions observed in
    actual FSR playbooks plus 1,690 indexed filter usages.

    At least one of `filter`, `var_path`, or `intent` must be set.
    - `filter`: filter name (`replace`, `tojson`, `picklist`,
      `json_query`, …) — narrows to expressions using that filter.
    - `var_path`: substring match against normalized `vars_csv`
      (e.g. `vars.input.records`, `vars.steps.fetch_alerts`).
    - `intent`: substring against the raw expression — useful for
      finding patterns like `replace('T', ' ')` or
      `picklist('AlertStatus'`.
    - `step_type`: optional filter to expressions found in a given
      step type (`SetVariable`, `Decision`, `UpdateRecord`, …).

    Results ranked by observed `occurrences` (most-used first) so the
    agent gets the idiomatic form rather than a one-off.
    """
    if not (filter or var_path or intent):
        return {"ok": False, "code": "missing_query",
                "message": "pass at least one of filter / var_path / intent"}
    where: list[str] = []
    args: list[Any] = []
    if filter:
        where.append("(filters_csv LIKE '%'||?||'%')")
        args.append(filter)
    if var_path:
        where.append("(vars_csv LIKE '%'||?||'%')")
        args.append(var_path)
    if intent:
        where.append("(raw LIKE '%'||?||'%')")
        args.append(intent)
    if step_type:
        where.append("step_type = ?")
        args.append(step_type)
    args.append(limit)
    sql = (
        "SELECT raw, kind, filters_csv, vars_csv, step_type, "
        "from_playbook, from_step, occurrences "
        "FROM jinja_expressions WHERE "
        + " AND ".join(where)
        + " ORDER BY occurrences DESC, length(raw) ASC LIMIT ?"
    )
    with _db() as conn:
        rows = _rows(conn, sql, tuple(args))
        out: dict[str, Any] = {"matches": rows, "count": len(rows)}
        if filter and not rows:
            usage = _rows(
                conn,
                """SELECT expression, from_playbook, from_step, occurrences
                   FROM jinja_filter_usage
                   WHERE filter_name=?
                   ORDER BY occurrences DESC LIMIT ?""",
                (filter, limit),
            )
            if usage:
                out["matches"] = usage
                out["count"] = len(usage)
                out["note"] = (
                    f"no jinja_expressions hit; falling back to "
                    f"jinja_filter_usage rows for filter {filter!r}."
                )
        if filter and not out["count"]:
            out["suggestion"] = (
                f"no usage of filter {filter!r} on record. Check "
                f"get_jinja_filters for the canonical name."
            )
    return out