"""probe_jinja_backend — ingest the introspection dump from FSR's workflow env.

Source: `store/incoming/filters.json`, produced by running
`scripts/internal/dump_jinja_filters.py` on the FSR appliance and scp'ing back.

This is the canonical truth — `inspect.signature()` on the actual Python
callables registered with `sealab`'s Jinja Environment. It supersedes the
widget constants and the playbook-guide PDF for parameter shapes.

Trust:
  - Every entry that has a non-error signature gets `tested_pass` via
    `backend_introspect`. This is the highest-trust source we have.
  - We never overwrite live `output_type_observed` (which came from running
    the actual filter through `type_debug` on the wire).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .common import (
    REPO_ROOT,
    probe_session,
    record_verification,
)

PROBE_NAME = "probe_jinja_backend"
INCOMING = REPO_ROOT / "store" / "incoming" / "filters.json"


def _scalarize(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return json.dumps(v)


def _params_for_db(info: dict) -> str | None:
    params = info.get("parameters")
    if not isinstance(params, list):
        return None
    return json.dumps(params)


def _ingest_filters(conn: sqlite3.Connection, filters: dict) -> int:
    n = 0
    for name, info in filters.items():
        if not isinstance(info, dict) or "introspect_error" in info:
            continue
        params_json = _params_for_db(info)
        # Don't clobber description/example/output_type_observed if we already
        # have richer values from widget_constants / live render. Only update
        # the backend-introspection columns + parameters_json.
        existing = conn.execute(
            "SELECT 1 FROM jinja_macros WHERE name = ?", (name,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE jinja_macros SET
                       parameters_json = COALESCE(?, parameters_json),
                       signature       = COALESCE(?, signature),
                       qualname        = ?,
                       module          = ?,
                       source_file     = ?,
                       description     = COALESCE(description, ?)
                   WHERE name = ?""",
                (
                    params_json,
                    info.get("signature"),
                    info.get("qualname"),
                    info.get("module"),
                    info.get("file"),
                    info.get("doc"),
                    name,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO jinja_macros
                   (name, signature, description, parameters_json,
                    qualname, module, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    info.get("signature"),
                    info.get("doc"),
                    params_json,
                    info.get("qualname"),
                    info.get("module"),
                    info.get("file"),
                ),
            )
        record_verification(
            conn, kind="jinja_filter", key=name,
            method="backend_introspect", status="tested_pass",
            notes=f"module={info.get('module')}",
        )
        n += 1
    return n


def _ingest_globals(conn: sqlite3.Connection, globs: dict) -> int:
    n = 0
    for name, info in globs.items():
        if not isinstance(info, dict) or "introspect_error" in info:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO jinja_globals
               (name, qualname, module, source_file, signature,
                parameters_json, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                info.get("qualname"),
                info.get("module"),
                info.get("file"),
                info.get("signature"),
                _params_for_db(info),
                info.get("doc"),
            ),
        )
        record_verification(
            conn, kind="jinja_global", key=name,
            method="backend_introspect", status="tested_pass",
            notes=f"module={info.get('module')}",
        )
        n += 1
    return n


def _ingest_tests(conn: sqlite3.Connection, tests: dict) -> int:
    n = 0
    for name, info in tests.items():
        if not isinstance(info, dict) or "introspect_error" in info:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO jinja_tests
               (name, qualname, module, source_file, signature,
                parameters_json, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                info.get("qualname"),
                info.get("module"),
                info.get("file"),
                info.get("signature"),
                _params_for_db(info),
                info.get("doc"),
            ),
        )
        record_verification(
            conn, kind="jinja_test", key=name,
            method="backend_introspect", status="tested_pass",
            notes=f"module={info.get('module')}",
        )
        n += 1
    return n


def main() -> int:
    if not INCOMING.exists():
        print(f"[{PROBE_NAME}] missing {INCOMING}; "
              f"run scripts/internal/dump_jinja_filters.py on the FSR box and scp the "
              f"result here first.")
        return 2

    data = json.loads(INCOMING.read_text())
    sources = [INCOMING]

    with probe_session(PROBE_NAME, sources) as conn:
        # Wipe verifications we own; we don't drop the tables since other
        # probes also write to jinja_macros.
        conn.execute(
            "DELETE FROM verifications "
            "WHERE method = 'backend_introspect' "
            "  AND kind IN ('jinja_filter','jinja_global','jinja_test')"
        )
        conn.execute("DELETE FROM jinja_globals")
        conn.execute("DELETE FROM jinja_tests")

        n_f = _ingest_filters(conn, data.get("filters") or {})
        n_g = _ingest_globals(conn, data.get("globals") or {})
        n_t = _ingest_tests(conn, data.get("tests") or {})

        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (
                json.dumps({"filters": n_f, "globals": n_g, "tests": n_t,
                            "source": str(INCOMING)}),
                PROBE_NAME,
            ),
        )
        print(f"[{PROBE_NAME}] filters={n_f}  globals={n_g}  tests={n_t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
