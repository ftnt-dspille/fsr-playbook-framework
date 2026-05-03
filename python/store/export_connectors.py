"""Generate `store/CONNECTORS.md` — agent cheatsheet for every connector,
operation, and parameter known to the live FSR instance.

Output shape is optimized for grep + LLM context: one heading per connector
(grouped by category), with operations and required-param shorthand inline.
Use `fsrpb explain connector <name>` for full per-op detail.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from probes.common import DB_PATH, STORE_DIR

OUT_PATH = STORE_DIR / "CONNECTORS.md"


def _params_summary(rows: list[sqlite3.Row]) -> str:
    """Compact `(req1: type, req2: type, [opt1])` signature."""
    top = [r for r in rows if r["parent_param_name"] is None]
    if not top:
        return "()"
    bits = []
    for r in top:
        name = r["param_name"]
        ptype = r["type"] or "any"
        if r["required"]:
            bits.append(f"{name}: {ptype}")
        else:
            bits.append(f"[{name}: {ptype}]")
    return "(" + ", ".join(bits) + ")"


def build_connectors_md(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> Path:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        connectors = conn.execute(
            "SELECT name, version, label, category, description, publisher, "
            "       active, system, ingestion_supported, source "
            "FROM connectors ORDER BY category, name"
        ).fetchall()

        ops_by_conn: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for r in conn.execute(
            "SELECT connector_name, op_name, title, category, description, "
            "       visible, enabled "
            "FROM operations ORDER BY connector_name, op_name"
        ).fetchall():
            ops_by_conn[r["connector_name"]].append(r)

        params_by_op: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for r in conn.execute(
            "SELECT connector_name, op_name, parent_param_name, condition_value, "
            "       param_name, type, required, default_value, options_json, "
            "       title, tooltip, description "
            "FROM operation_params ORDER BY connector_name, op_name, ord, param_name"
        ).fetchall():
            params_by_op[(r["connector_name"], r["op_name"])].append(r)
    finally:
        conn.close()

    by_category: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for c in connectors:
        cat = c["category"] or "Uncategorized"
        by_category[cat].append(c)

    parts: list[str] = []
    parts.append("# FortiSOAR connectors cheatsheet")
    parts.append("")
    parts.append(
        "Generated from `store/fsr_reference.db` by "
        "`python/store/export_connectors.py`. Source-of-truth is the live FSR "
        "appliance's `/api/integration/connectors/` endpoint plus the catalog "
        "via `/api/query/solutionpacks`."
    )
    parts.append("")
    parts.append(
        f"**{len(connectors)}** connectors · "
        f"**{sum(len(v) for v in ops_by_conn.values())}** operations · "
        f"**{sum(len(v) for v in params_by_op.values())}** parameters across "
        f"**{len(by_category)}** categories."
    )
    parts.append("")
    parts.append(
        "Format per operation: `op_name(req: type, [opt: type])`. Square "
        "brackets denote optional parameters. Conditional / nested params "
        "(rendered when a parent value is set) are omitted from the inline "
        "signature — use `fsrpb explain connector <name>` to see them."
    )
    parts.append("")
    parts.append("---")
    parts.append("")

    parts.append("## Categories")
    parts.append("")
    for cat in sorted(by_category):
        slug = cat.lower().replace(" ", "-").replace("/", "-")
        parts.append(f"- [{cat}](#{slug}) — {len(by_category[cat])}")
    parts.append("")
    parts.append("---")
    parts.append("")

    for cat in sorted(by_category):
        parts.append(f"## {cat}")
        parts.append("")
        for c in sorted(by_category[cat], key=lambda r: r["name"]):
            name = c["name"]
            label = c["label"] or name
            badges = []
            if c["active"]:
                badges.append("installed")
            if c["system"]:
                badges.append("system")
            if c["ingestion_supported"]:
                badges.append("ingestion")
            badge_str = f" _({', '.join(badges)})_" if badges else ""

            parts.append(f"### `{name}` v{c['version']}{badge_str}")
            if label != name:
                parts.append(f"_{label}_")
            if c["description"]:
                parts.append("")
                parts.append(c["description"].strip())
            parts.append("")

            ops = ops_by_conn.get(name, [])
            if not ops:
                parts.append("_(no operations cataloged)_")
                parts.append("")
                continue

            visible_ops = [o for o in ops if o["visible"]]
            hidden_count = len(ops) - len(visible_ops)
            parts.append(f"**{len(ops)} operation(s)**"
                         + (f" (+{hidden_count} hidden)" if hidden_count else "")
                         + ":")
            parts.append("")

            ops_by_op_cat: dict[str, list[sqlite3.Row]] = defaultdict(list)
            for o in visible_ops or ops:
                ops_by_op_cat[o["category"] or "—"].append(o)

            for op_cat in sorted(ops_by_op_cat):
                if op_cat != "—":
                    parts.append(f"_{op_cat}_")
                for o in ops_by_op_cat[op_cat]:
                    sig = _params_summary(params_by_op.get((name, o["op_name"]), []))
                    title = o["title"] or o["op_name"]
                    line = f"- `{o['op_name']}{sig}`"
                    if title != o["op_name"]:
                        line += f" — {title}"
                    parts.append(line)
                parts.append("")
            parts.append("")
        parts.append("---")
        parts.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path


if __name__ == "__main__":
    p = build_connectors_md()
    print(f"wrote {p}")
