"""Backfill `operation_examples` from `playbook_steps`.

For every distinct (connector, operation) seen in real playbooks we
already store as `playbook_steps` rows (step_type_name='Connectors'),
emit up to N distinct param-shape snippets so `find_operation_example`
can ground the agent's authoring in real usage.

Idempotent: clears `pb_examples`-sourced rows before reinserting.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "store" / "fsr_reference.db"

MAX_PER_OP = 5


def backfill(db_path: Path = DB_PATH, max_per_op: int = MAX_PER_OP) -> dict:
    inserted = 0
    pairs = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM operation_examples WHERE source='pb_examples'"
        )
        rows = conn.execute(
            """SELECT arguments_json, playbook_name, step_name
               FROM playbook_steps
               WHERE step_type_name='Connectors'"""
        ).fetchall()

        # Group by (connector, op); dedup by params signature so we
        # don't waste a slot on five identical {{vars.x}} snippets.
        bucket: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
        for args_json, pb_name, step_name in rows:
            try:
                a = json.loads(args_json)
            except Exception:
                continue
            connector = a.get("connector")
            op = a.get("operation")
            if not connector or not op:
                continue
            params = a.get("params") or {}
            sig = json.dumps(params, sort_keys=True)[:600]
            if sig in bucket[(connector, op)]:
                continue
            bucket[(connector, op)][sig] = {
                "params": params,
                "pb": pb_name,
                "step": step_name,
            }

        for (connector, op), examples in bucket.items():
            pairs += 1
            for entry in list(examples.values())[:max_per_op]:
                snippet = json.dumps({
                    "connector": connector,
                    "operation": op,
                    "params": entry["params"],
                }, indent=2)
                notes = (
                    f"from playbook={entry['pb']!r} step={entry['step']!r}"
                )
                conn.execute(
                    """INSERT INTO operation_examples
                       (connector_name, op_name, source, example_kind,
                        snippet, notes)
                       VALUES (?, ?, 'pb_examples', 'json', ?, ?)""",
                    (connector, op, snippet, notes),
                )
                inserted += 1
        conn.commit()
    return {
        "ok": True,
        "pairs_seen": pairs,
        "examples_inserted": inserted,
    }


if __name__ == "__main__":
    print(json.dumps(backfill(), indent=2))
