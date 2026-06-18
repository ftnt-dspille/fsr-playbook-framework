"""Build `store/fsr_reference.json` from the SQLite reference DB.

The TS compiler (and the future FortiSOAR widget) consumes this JSON instead
of opening SQLite. SQLite stays the agent/dev-loop interface; JSON is the
shipped artifact.

Run after `fsrpb refresh` (all probes done). Idempotent.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from probes.common import DB_PATH, STORE_DIR

OUT_PATH = STORE_DIR / "fsr_reference.json"


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_reference_json(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> Path:
    """Query every reference table and emit a single JSON file."""
    conn = sqlite3.connect(db_path)
    try:
        connectors = _rows(
            conn,
            "SELECT name, version, label, category, description, publisher "
            "FROM connectors ORDER BY name",
        )
        operations = _rows(
            conn,
            "SELECT connector_name, op_name, title, category, description, "
            "       output_schema_json "
            "FROM operations ORDER BY connector_name, op_name",
        )
        params = _rows(
            conn,
            "SELECT connector_name, op_name, param_name, title, type, required, "
            "       default_value, options_json, tooltip, ord "
            "FROM operation_params "
            "ORDER BY connector_name, op_name, ord, param_name",
        )
        step_handlers = _rows(
            conn,
            "SELECT name, signature, parameters_json, qualname, module, "
            "       source_file, doc "
            "FROM step_handlers ORDER BY name",
        )
        step_types = _rows(
            conn,
            "SELECT uuid, name, label, category, description, args_schema_json, "
            "       occurrences, common_pitfalls "
            "FROM step_types ORDER BY name",
        )
        modules = _rows(conn, "SELECT name, label, plural, description FROM modules ORDER BY name")
        module_fields = _rows(
            conn,
            "SELECT module_name, field_name, title, type, required, "
            "       picklist_options, tooltip "
            "FROM module_fields ORDER BY module_name, field_name",
        )
        jinja_macros = _rows(
            conn,
            "SELECT name, signature, returns, description, example, "
            "       parameters_json, input_type_hint, output_type_declared, "
            "       output_type_observed, qualname, module, source_file "
            "FROM jinja_macros ORDER BY name",
        )
        jinja_globals_ = _rows(
            conn,
            "SELECT name, qualname, module, source_file, signature, "
            "       parameters_json, description, output_type_observed "
            "FROM jinja_globals ORDER BY name",
        )
        jinja_tests_ = _rows(
            conn,
            "SELECT name, qualname, module, source_file, signature, "
            "       parameters_json, description "
            "FROM jinja_tests ORDER BY name",
        )
        jinja_vars = _rows(
            conn,
            "SELECT scope, var_name, type, description "
            "FROM jinja_context_vars ORDER BY scope, var_name",
        )
        api_endpoints = _rows(
            conn,
            "SELECT path_pattern, http_method, service, controller, summary, "
            "       response_kind, source "
            "FROM api_endpoints ORDER BY service, path_pattern, http_method",
        )
        recipes = _rows(
            conn,
            "SELECT name, kind, when_to_use, yaml_template, source_playbook "
            "FROM recipes ORDER BY name",
        )
        meta_runs = _rows(
            conn,
            "SELECT probe_name, ts, row_counts, version FROM _probe_runs "
            "WHERE id IN (SELECT MAX(id) FROM _probe_runs GROUP BY probe_name)",
        )
    finally:
        conn.close()

    bundle = {
        "schema_version": 1,
        "meta": {"last_probe_runs": meta_runs},
        "connectors": connectors,
        "operations": operations,
        "operation_params": params,
        "step_types": step_types,
        "step_handlers": step_handlers,
        "modules": modules,
        "module_fields": module_fields,
        "jinja": {
            "filters": jinja_macros,
            "globals": jinja_globals_,
            "tests": jinja_tests_,
            "context_vars": jinja_vars,
            # legacy alias — old TS code may still read jinja.macros
            "macros": jinja_macros,
        },
        "recipes": recipes,
        "api_endpoints": api_endpoints,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2, sort_keys=False))
    return out_path


if __name__ == "__main__":
    p = build_reference_json()
    print(f"wrote {p}")
