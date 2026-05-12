"""Generate `store/STEP_TYPES.md` — agent cheatsheet for FortiSOAR playbook
step types, ordered by real-world frequency on the live instance.

Each step type entry shows:
  - canonical name + UUID
  - category / parent grouping
  - occurrences count (how often it appears across all 1664 playbooks)
  - args_schema_json (the partial schema returned by /api/3/workflow_step_types/)
  - up to 3 sample arguments-blobs from real workflow_steps records
  - common pitfalls (hand-curated in step_types.common_pitfalls)

When `probe_step_types_backend` lands (TODO #2), this file will gain
canonical celery-task signatures per step type. For now it's our best view
into "how do I configure step type X" without grepping pb_examples.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from probes.common import DB_PATH, STORE_DIR

OUT_PATH = STORE_DIR / "STEP_TYPES.md"


def _pretty_json(blob: str | None, indent: int = 2) -> str:
    if not blob:
        return ""
    try:
        return json.dumps(json.loads(blob), indent=indent, sort_keys=False)
    except Exception:
        return blob


def _examples_for(conn: sqlite3.Connection, step_type_name: str, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT from_playbook, snippet_json FROM step_examples "
        "WHERE step_type_name = ? LIMIT ?",
        (step_type_name, limit),
    ).fetchall()
    out = []
    for from_pb, snippet in rows:
        try:
            parsed = json.loads(snippet)
        except Exception:
            parsed = {"raw": snippet}
        out.append({"source": from_pb, "snippet": parsed})
    return out


def build_step_types_md(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> Path:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT name, uuid, label, category, description, args_schema_json, "
            "       occurrences, common_pitfalls "
            "FROM step_types ORDER BY occurrences DESC, name"
        ).fetchall()

        examples_by_type = {
            r["name"]: _examples_for(conn, r["name"]) for r in rows
        }
    finally:
        conn.close()

    parts: list[str] = []
    parts.append("# FortiSOAR playbook step types")
    parts.append("")
    parts.append("Generated from `store/fsr_reference.db` by "
                 "`python/store/export_step_types.py`. Source-of-truth is the live "
                 "FSR appliance's `/api/3/workflow_step_types/` endpoint plus mined "
                 "samples from `/api/3/workflow_steps?$relationships=true`.")
    parts.append("")
    parts.append("Each step type is ordered by **observed frequency** across the "
                 f"{len(rows)} step types and ~7000 step instances on the connected "
                 "instance. The top of this list is what real playbooks reach for first.")
    parts.append("")
    parts.append("**Schema completeness caveat**: the `arguments` blob shown per step "
                 "type is what the API returned — it's a partial schema (often just a "
                 "`script` pointer + pre-bound args). To get canonical Python signatures "
                 "for each step's celery handler, run `scripts/internal/dump_step_types.py` on "
                 "the FSR appliance and ingest the result. Until then, the **examples** "
                 "section per step is the most reliable guide to what `arguments` should "
                 "look like.")
    parts.append("")
    parts.append("---")
    parts.append("")

    for r in rows:
        name = r["name"]
        parts.append(f"## `{name}`")
        if r["label"] and r["label"] != name:
            parts.append(f"_label: {r['label']}_")
        parts.append("")

        meta_bits = []
        if r["occurrences"]:
            meta_bits.append(f"**Occurrences**: {r['occurrences']}")
        if r["category"]:
            meta_bits.append(f"**Category**: `{r['category']}`")
        if r["uuid"]:
            meta_bits.append(f"**UUID**: `{r['uuid']}`")
        if meta_bits:
            parts.append(" · ".join(meta_bits))
            parts.append("")

        if r["description"]:
            parts.append(r["description"].strip())
            parts.append("")

        if r["args_schema_json"]:
            parts.append("**Declared arguments shape** (from API):")
            parts.append("```json")
            parts.append(_pretty_json(r["args_schema_json"]))
            parts.append("```")
            parts.append("")

        examples = examples_by_type.get(name, [])
        if examples:
            parts.append(f"**Real-world examples** ({len(examples)}):")
            parts.append("")
            for i, ex in enumerate(examples, 1):
                parts.append(f"<details><summary>Example {i} ({ex['source']})</summary>")
                parts.append("")
                parts.append("```json")
                parts.append(json.dumps(ex["snippet"], indent=2))
                parts.append("```")
                parts.append("")
                parts.append("</details>")
                parts.append("")

        if r["common_pitfalls"]:
            parts.append(f"**Pitfalls**: {r['common_pitfalls']}")
            parts.append("")

        parts.append("---")
        parts.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path


if __name__ == "__main__":
    p = build_step_types_md()
    print(f"wrote {p}")
