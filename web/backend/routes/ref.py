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
def inventory_search(q: str, limit: int = 5) -> dict[str, Any]:
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
