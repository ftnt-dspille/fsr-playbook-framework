"""probe_step_handlers — ingest workflow.eval.FUNCTION_MAP signatures.

Source: `store/incoming/function_map.json`, produced by running
`scripts/internal/dump_function_map.py` on the FSR appliance.

The 43 step types exposed by `/api/3/workflow_step_types/` carry an
`args_schema_json.script` field of the form `/wf/workflow/tasks/<name>`,
where `<name>` is a key in the live `workflow.eval.FUNCTION_MAP` dict
(44 entries — covers all step types plus a few internal helpers like
`add_one`, `no_op`, `panic`).

That callable is the canonical handler. Its `inspect.signature()` is
the source of truth for what `arguments` a step must provide. The
existing `step_types.args_schema_json` only carries a script pointer
plus a few pre-bound args — useful, but not enough for validation.

Trust: backend_introspect / tested_pass.
"""
from __future__ import annotations

import json
import sqlite3

from .common import (
    REPO_ROOT,
    probe_session,
    record_verification,
)

PROBE_NAME = "probe_step_handlers"
INCOMING = REPO_ROOT / "store" / "incoming" / "function_map.json"


def _ingest(conn: sqlite3.Connection, function_map: dict) -> int:
    n = 0
    for name, info in function_map.items():
        if not isinstance(info, dict):
            continue
        params = info.get("parameters")
        params_json = json.dumps(params) if isinstance(params, list) else None
        signature = info.get("signature") or info.get("text_signature")
        conn.execute(
            """INSERT OR REPLACE INTO step_handlers
               (name, signature, parameters_json, qualname, module,
                source_file, doc)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                signature,
                params_json,
                info.get("qualname"),
                info.get("module"),
                info.get("file"),
                info.get("doc"),
            ),
        )
        record_verification(
            conn, kind="step_handler", key=name,
            method="backend_introspect", status="tested_pass",
            notes=f"sig={signature}" if signature else "no_signature",
        )
        n += 1
    return n


def main() -> int:
    if not INCOMING.exists():
        raise SystemExit(
            f"missing {INCOMING}. Run scripts/internal/dump_function_map.py on FSR "
            f"and scp /tmp/function_map.json to {INCOMING}"
        )
    payload = json.loads(INCOMING.read_text())
    function_map = payload.get("function_map", {})
    sources = [INCOMING]

    with probe_session(PROBE_NAME, sources) as conn:
        conn.execute("DELETE FROM step_handlers")
        conn.execute(
            "DELETE FROM verifications "
            "WHERE kind = 'step_handler' AND method = 'backend_introspect'"
        )
        n = _ingest(conn, function_map)

        notes = json.dumps({"step_handlers": n})
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] step_handlers={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
