"""Audit surface for the SQLite reference store.

Single source of truth for "what does the assistant know?" — both the
`fsrpb inventory` CLI and the planned `/api/ref/inventory` web route call
into here. Read-only over the active reference DB plus the ATTACHed
api_examples_catalog.

Trust model: any row with `is_trusted=1` in `v_verification_state` was
confirmed live + tested; everything else is `seen`-only and may drift.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from probes.common import open_db


def _safe_count(conn: sqlite3.Connection, sql: str,
                params: tuple = ()) -> int:
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0


def summary() -> dict[str, Any]:
    """Per-table row counts, last probe timestamps, catalog presence."""
    with open_db(create=False) as conn:
        ref = {
            "connectors": _safe_count(conn, "SELECT COUNT(*) FROM connectors"),
            "operations": _safe_count(conn, "SELECT COUNT(*) FROM operations"),
            "operation_params": _safe_count(
                conn, "SELECT COUNT(*) FROM operation_params"),
            "step_types": _safe_count(conn, "SELECT COUNT(*) FROM step_types"),
            "jinja_macros": _safe_count(
                conn, "SELECT COUNT(*) FROM jinja_macros"),
            "playbooks_seen": _safe_count(
                conn, "SELECT COUNT(*) FROM playbooks_seen"),
        }
        trusted = _safe_count(
            conn,
            "SELECT COUNT(*) FROM v_verification_state WHERE is_trusted = 1",
        )
        seen_total = _safe_count(
            conn, "SELECT COUNT(*) FROM v_verification_state")
        last_probes: list[dict[str, Any]] = []
        try:
            for r in conn.execute(
                "SELECT probe_name, ts, version FROM _probe_runs "
                "ORDER BY ts DESC LIMIT 20"
            ):
                last_probes.append(
                    {"probe": r[0], "ts": r[1], "version": r[2]})
        except sqlite3.OperationalError:
            pass
        catalog = {
            "products": _safe_count(conn, "SELECT COUNT(*) FROM catalog.products"),
            "entries": _safe_count(conn, "SELECT COUNT(*) FROM catalog.entries"),
            "connector_lifecycle": _safe_count(
                conn, "SELECT COUNT(*) FROM catalog.connector_lifecycle"),
        }
    return {
        "reference_db": ref,
        "trust": {"trusted": trusted, "total": seen_total},
        "last_probes": last_probes,
        "catalog": catalog,
    }


def list_connectors(limit: int = 50, q: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT name, version, category, "
        "CASE WHEN is_trusted=1 THEN 'trusted' ELSE 'seen' END AS trust "
        "FROM connectors c LEFT JOIN v_verification_state v "
        "ON v.kind='connector' AND v.key=c.name "
    )
    params: list[Any] = []
    if q:
        sql += "WHERE c.name LIKE ? OR c.label LIKE ? "
        params += [f"%{q}%", f"%{q}%"]
    sql += "ORDER BY c.name LIMIT ?"
    params.append(limit)
    with open_db(create=False) as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params))]


def list_api_example_products(limit: int = 50,
                              q: str | None = None) -> list[dict[str, Any]]:
    """Top products in the api_examples_catalog by entry count."""
    sql = (
        "SELECT p.name, p.category, COUNT(e.id) AS entry_count "
        "FROM catalog.products p LEFT JOIN catalog.entries e "
        "ON e.product_id = p.id "
    )
    params: list[Any] = []
    if q:
        sql += "WHERE p.normalized LIKE ? "
        params.append(f"%{q.lower()}%")
    sql += "GROUP BY p.id ORDER BY entry_count DESC LIMIT ?"
    params.append(limit)
    with open_db(create=False) as conn:
        try:
            return [dict(r) for r in conn.execute(sql, tuple(params))]
        except sqlite3.OperationalError as exc:
            return [{"error": str(exc)}]


def stale_probes(max_age_days: int = 7) -> list[dict[str, Any]]:
    """Probes that haven't run within max_age_days."""
    with open_db(create=False) as conn:
        try:
            rows = conn.execute(
                "SELECT probe_name, MAX(ts) AS last_ts FROM _probe_runs "
                "GROUP BY probe_name "
                "HAVING julianday('now') - julianday(MAX(ts)) > ?",
                (max_age_days,),
            ).fetchall()
            return [{"probe": r[0], "last_ts": r[1]} for r in rows]
        except sqlite3.OperationalError:
            return []


def _tokens_clause(fields: list[str], tokens: list[str]) -> tuple[str, list[str]]:
    """Build an AND-of-OR LIKE clause: every token must appear in at
    least one of the provided fields. So `ip address` matches rows
    where some field has 'ip' AND some (possibly different) field has
    'address' — closer to user expectation than naive substring."""
    parts: list[str] = []
    params: list[str] = []
    for tok in tokens:
        ors = " OR ".join(f"{f} LIKE ?" for f in fields)
        parts.append(f"({ors})")
        params.extend(f"%{tok}%" for _ in fields)
    return " AND ".join(parts) if parts else "1=1", params


def cross_search(q: str, per_table_limit: int = 15) -> dict[str, list[dict[str, Any]]]:
    """Run the same query across every cataloged surface: connectors,
    operations, jinja filters, step types, modules, module fields,
    playbook step examples, and API examples.

    Multi-token queries are AND-matched: `ip address` requires both
    tokens to appear (each in any of the searched fields). Single-token
    queries are simple substring.

    Useful when the user asks "what do we know about X?" and we don't
    yet know which table holds the answer.
    """
    tokens = [t for t in q.strip().split() if t]
    if not tokens:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    with open_db(create=False) as conn:
        # Connectors — search name + label + description.
        clause, params = _tokens_clause(
            ["name", "label", "description"], tokens)
        out["connectors"] = [dict(r) for r in conn.execute(
            f"SELECT name, version, category, label "
            f"FROM connectors WHERE {clause} LIMIT ?",
            (*params, per_table_limit))]
        # Operations — name + title + description (and prefer the
        # connector's name match too).
        clause, params = _tokens_clause(
            ["op_name", "title", "description", "connector_name"], tokens)
        out["operations"] = [dict(r) for r in conn.execute(
            f"SELECT connector_name, op_name, title, category "
            f"FROM operations WHERE {clause} LIMIT ?",
            (*params, per_table_limit))]
        # Step types.
        try:
            clause, params = _tokens_clause(
                ["name", "label", "description"], tokens)
            out["step_types"] = [dict(r) for r in conn.execute(
                f"SELECT name, label, description "
                f"FROM step_types WHERE {clause} LIMIT ?",
                (*params, per_table_limit))]
        except sqlite3.OperationalError:
            out["step_types"] = []
        # Jinja macros / filters.
        try:
            clause, params = _tokens_clause(["name", "signature"], tokens)
            out["jinja_macros"] = [dict(r) for r in conn.execute(
                f"SELECT name, signature FROM jinja_macros "
                f"WHERE {clause} LIMIT ?",
                (*params, per_table_limit))]
        except sqlite3.OperationalError:
            out["jinja_macros"] = []
        # Modules + module fields.
        try:
            clause, params = _tokens_clause(["name", "label", "plural"], tokens)
            out["modules"] = [dict(r) for r in conn.execute(
                f"SELECT name, label, plural FROM modules "
                f"WHERE {clause} LIMIT ?",
                (*params, per_table_limit))]
        except sqlite3.OperationalError:
            out["modules"] = []
        try:
            clause, params = _tokens_clause(
                ["field_name", "label", "module_name"], tokens)
            out["module_fields"] = [dict(r) for r in conn.execute(
                f"SELECT module_name, field_name, label, type "
                f"FROM module_fields WHERE {clause} LIMIT ?",
                (*params, per_table_limit))]
        except sqlite3.OperationalError:
            out["module_fields"] = []
        # Playbook step corpus (live + sp_export). Match step name +
        # playbook + collection so authors can find prior examples.
        try:
            clause, params = _tokens_clause(
                ["step_name", "step_type_name", "playbook_name", "collection"],
                tokens,
            )
            out["playbook_steps"] = [dict(r) for r in conn.execute(
                f"SELECT step_type_name, step_name, playbook_name, "
                f"collection, source FROM playbook_steps "
                f"WHERE {clause} LIMIT ?",
                (*params, per_table_limit))]
        except sqlite3.OperationalError:
            out["playbook_steps"] = []
        # API examples (cross-vendor catalog, when attached).
        try:
            clause, params = _tokens_clause(
                ["p.normalized", "e.action_normalized", "e.action", "e.http_path"],
                [t.lower() for t in tokens],
            )
            out["api_examples"] = [dict(r) for r in conn.execute(
                f"SELECT p.name AS product, e.action, e.http_method, "
                f"e.http_path, e.id AS entry_id "
                f"FROM catalog.entries e "
                f"JOIN catalog.products p ON p.id = e.product_id "
                f"WHERE {clause} LIMIT ?",
                (*params, per_table_limit))]
        except sqlite3.OperationalError as exc:
            out["api_examples"] = [{"error": str(exc)}]
    return out
