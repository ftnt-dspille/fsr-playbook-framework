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
