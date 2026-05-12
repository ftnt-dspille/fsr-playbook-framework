"""Reference store endpoints — for editor autocompletion + Browse tab.

Read-only against ../store/fsr_reference.db. Cheap queries; no caching
yet (the DB is local SQLite, sub-millisecond reads).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"

# Friendly shorthand types the YAML compiler accepts. Source of truth:
# python/compiler/resolver.py SHORT_TYPE_TO_FSR. Mirrored here so the
# editor doesn't have to import Python.
STEP_TYPE_HINTS: list[dict[str, str]] = [
    {"name": "start", "detail": "manual / designer trigger"},
    {"name": "start_on_create", "detail": "auto-fires on record create (cybersponse.post_create)"},
    {"name": "start_on_update", "detail": "auto-fires on record update (cybersponse.post_update)"},
    {"name": "set_variable", "detail": "store a value into vars"},
    {"name": "decision", "detail": "branch on conditions"},
    {"name": "connector", "detail": "call a connector operation"},
    {"name": "find_record", "detail": "query records from a module"},
    {"name": "create_record", "detail": "create a record in a module"},
    {"name": "update_record", "detail": "update an existing record"},
    {"name": "delay", "detail": "pause for N seconds"},
    {"name": "manual_input", "detail": "wait for human input"},
    {"name": "code_snippet", "detail": "run an inline Python snippet"},
    {"name": "workflow_reference", "detail": "call a child playbook"},
    {"name": "stop", "detail": "terminal no-op"},
    {"name": "end", "detail": "terminal no-op (alias of stop)"},
]


router = APIRouter(prefix="/api/ref", tags=["ref"])


def _conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, f"reference db missing at {DB_PATH}")
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


@router.get("/step-types")
def list_step_types() -> list[dict[str, str]]:
    return STEP_TYPE_HINTS


@router.get("/recipes")
def list_recipes() -> list[dict[str, Any]]:
    """Recipes available for drag/drop into the visual editor."""
    with _conn() as c:
        rows = c.execute(
            "SELECT name, kind, when_to_use FROM recipes ORDER BY kind, name"
        ).fetchall()
    return [{"name": r["name"], "kind": r["kind"], "when_to_use": r["when_to_use"]}
            for r in rows]


@router.get("/step-args/{step_type}")
def step_args_help(step_type: str) -> dict[str, Any]:
    """Hover docs for a friendly step type — what `arguments:` accepts.

    Powers the Monaco hover popup. Returns both the structured spec and
    a pre-rendered markdown blob so the frontend can show either.
    """
    from step_args_help import get_help, render_markdown
    spec = get_help(step_type)
    if spec is None:
        raise HTTPException(404, f"no help entry for step type {step_type!r}")
    return {"type": step_type,
            "spec": spec,
            "markdown": render_markdown(step_type)}


@router.get("/connectors")
def list_connectors(q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    sql = (
        "SELECT name, label, category, description FROM connectors "
        "WHERE active = 1 "
    )
    args: list[Any] = []
    if q:
        sql += "AND (name LIKE ? OR label LIKE ?) "
        args += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY name LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


@router.get("/inventory")
def inventory_summary() -> dict[str, Any]:
    """Audit surface — what does the assistant know?

    Powers the front-end inventory dashboard (the "we're not just an LLM"
    proof). Reads through `python.inventory` so the CLI and web stay in
    sync.
    """
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    import inventory as inv
    return {
        "summary": inv.summary(),
        "top_api_products": inv.list_api_example_products(limit=15),
    }


@router.get("/api-examples")
def api_examples(q: str, product: str | None = None,
                 limit: int = 10) -> list[dict[str, Any]]:
    """FTS search over the api_examples_catalog. Returns entry_id so the
    UI can call /synthesize-http-step on a specific row."""
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    from mcp_server import search_api_examples as _search  # type: ignore
    return _search(query=q, product=product, limit=limit)


@router.get("/synthesize-http-step")
def synthesize_http_step(entry_id: int, step_name: str = "Call API") -> dict[str, Any]:
    """Translate an api_examples_catalog entry into a YAML HTTP-connector step.

    Powers the "Insert as HTTP step" button on the Inventory dashboard.
    Calls through to the same deterministic synthesizer the MCP server
    exposes — no LLM, just a catalog row → http_request step transform.
    """
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    from mcp_server import synthesize_http_step as _synth  # type: ignore
    step = _synth(entry_id=entry_id, step_name=step_name)
    if step.get("error"):
        raise HTTPException(404, step["error"])
    args = step.get("args") or {}
    yaml_lines = [
        f"- id: call_api",
        f"  type: connector",
        f"  name: {step.get('name', step_name)!r}",
        f"  connector: {step.get('connector', 'http')}",
        f"  operation: {step.get('operation', 'http_request')}",
        f"  args:",
        f"    method: {args.get('method', 'GET')}",
        f"    rest_api: {args.get('rest_api', '')!r}",
        f"    auth_type: {args.get('auth_type', 'No Auth')!r}",
    ]
    if args.get("parameter"):
        yaml_lines.append("    parameter:")
        for k, v in args["parameter"].items():
            yaml_lines.append(f"      {k}: {v!r}")
    return {
        "step": step,
        "yaml": "\n".join(yaml_lines),
        "note": step.get("_note", ""),
        "source_url": step.get("_source_url", ""),
    }


@router.get("/inventory/search")
def inventory_search(q: str, limit: int = 15) -> dict[str, Any]:
    import sys as _sys
    _py = REPO_ROOT / "python"
    if str(_py) not in _sys.path:
        _sys.path.insert(0, str(_py))
    import inventory as inv
    return inv.cross_search(q, per_table_limit=limit)


@router.get("/connectors/{name}/operations")
def list_operations(name: str, q: str = "", limit: int = 100) -> list[dict[str, Any]]:
    sql = (
        "SELECT op_name, title, category, description FROM operations "
        "WHERE connector_name = ? AND visible = 1 "
    )
    args: list[Any] = [name]
    if q:
        sql += "AND (op_name LIKE ? OR title LIKE ?) "
        args += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY op_name LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


@router.get("/jinja-filters")
def list_jinja_filters(q: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """Catalog of jinja filters for Monaco autocomplete inside `{{ … | }}`.

    Read-only over `jinja_macros`. Returns name + signature + a one-line
    description so the IDE can render hover docs without a second
    fetch. Limited to ~200 since the full corpus is ~170 filters.
    """
    sql = (
        "SELECT name, signature, description, output_type_observed "
        "FROM jinja_macros "
    )
    args: list[Any] = []
    if q:
        sql += "WHERE name LIKE ? OR description LIKE ? "
        args += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY name LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


@router.get("/modules")
def list_modules() -> list[dict[str, Any]]:
    """Module names + labels from the trained `modules` table.

    Powers the Resource (module) dropdown on trigger and record_crud
    inspector blocks. Empty list when the trained DB hasn't been
    populated yet (fresh install / pre-`fsrpb train`).
    """
    with _conn() as c:
        rows = c.execute(
            "SELECT name, label, plural FROM modules ORDER BY name"
        ).fetchall()
    return [{"name": r["name"], "label": r["label"], "plural": r["plural"]}
            for r in rows]


# Operator catalog per leaf-value type — trimmed from
# `store/QUERY_API.md` §2.1 to surface only the ops that make
# semantic sense for the field type. Keeps the UI from offering
# `like` on a boolean or `gt` on a picklist.
_OPERATORS_BY_TYPE: dict[str, list[str]] = {
    "default":    ["eq", "neq", "in", "nin", "like", "isnull"],
    "integer":    ["eq", "neq", "lt", "lte", "gt", "gte", "in", "nin", "isnull"],
    "decimal":    ["eq", "neq", "lt", "lte", "gt", "gte", "in", "nin", "isnull"],
    "number":     ["eq", "neq", "lt", "lte", "gt", "gte", "in", "nin", "isnull"],
    "checkbox":   ["eq", "neq", "isnull"],
    "boolean":    ["eq", "neq", "isnull"],
    "datetime":   ["eq", "neq", "lt", "lte", "gt", "gte", "isnull"],
    "date":       ["eq", "neq", "lt", "lte", "gt", "gte", "isnull"],
    "picklists":  ["eq", "neq", "in", "nin", "isnull"],
    "lookup":     ["eq", "neq", "in", "nin", "isnull"],
    "manyToMany": ["eq", "neq", "in", "nin", "isnull"],
    "manyToOne":  ["eq", "neq", "in", "nin", "isnull"],
    "oneToMany":  ["eq", "neq", "in", "nin", "isnull"],
    "json":       ["eq", "neq", "like", "contains", "exists", "isnull"],
    "object":     ["eq", "neq", "like", "contains", "exists", "isnull"],
}


@router.get("/modules/{module}/fields")
def get_module_fields(module: str) -> dict[str, Any]:
    """Field catalog for a single module.

    Each field carries its FSR type, required flag, picklist name (when
    applicable), tooltip, and the per-type operator catalog so the
    FilterTreeEditor can scope the operator dropdown by field type.
    """
    with _conn() as c:
        m = c.execute(
            "SELECT name, label, plural FROM modules WHERE name = ?",
            (module,),
        ).fetchone()
        if m is None:
            raise HTTPException(404,
                                f"module {module!r} not found in trained store")
        rows = c.execute(
            "SELECT field_name, title, type, required, picklist_options, tooltip "
            "FROM module_fields WHERE module_name = ? ORDER BY field_name",
            (module,),
        ).fetchall()
    fields = []
    for r in rows:
        ftype = r["type"] or "default"
        ops = _OPERATORS_BY_TYPE.get(ftype, _OPERATORS_BY_TYPE["default"])
        fields.append({
            "name": r["field_name"],
            "title": r["title"],
            "type": ftype,
            "required": bool(r["required"]),
            "picklist_options": r["picklist_options"],
            "tooltip": r["tooltip"],
            "operators": ops,
        })
    return {
        "module": m["name"],
        "label": m["label"],
        "plural": m["plural"],
        "fields": fields,
    }


@router.get("/step-examples/{step_type}")
def step_examples(step_type: str, limit: int = 10) -> dict[str, Any]:
    """Top-N corpus-mined skeletons for a step type, with summaries.

    Powers the Examples tab on every step type. See
    ``web/backend/step_examples.py`` for clustering + summariser.
    """
    from step_examples import cluster_examples, STEP_TYPE_TO_CORPUS
    if step_type not in STEP_TYPE_TO_CORPUS:
        raise HTTPException(404,
            f"step type {step_type!r} has no corpus mapping; "
            f"supported: {sorted(STEP_TYPE_TO_CORPUS)}")
    n = max(1, min(int(limit), 25))
    with _conn() as c:
        clusters = cluster_examples(c, step_type, limit=n)
    return {"step_type": step_type, "examples": clusters}


@router.get("/example-prompts")
def list_example_prompts() -> list[dict[str, Any]]:
    """Sample chat prompts for testing the agent.

    Sourced from `python/evals/tasks/*.json` so the eval corpus and the
    UI picker stay in lockstep — adding a task file gives you a new
    option in the chat starter dropdown automatically.
    """
    import json as _json
    tasks_dir = REPO_ROOT / "python" / "evals" / "tasks"
    if not tasks_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(tasks_dir.glob("*.json")):
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
        except _json.JSONDecodeError:
            continue
        out.append({
            "name": data.get("name", p.stem),
            "prompt": data.get("prompt", ""),
            "notes": data.get("notes", ""),
            "has_gold": bool(data.get("gold_yaml_path")),
        })
    return out
