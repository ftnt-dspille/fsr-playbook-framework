"""Generate `store/RECIPES.md` — copy-paste YAML templates for the patterns
agents actually need.

Three sources stitched together:
  1. The hand-curated `examples/*.yaml` — the canonical "this works" set.
  2. The `recipes` table — trigger-pattern frequency, mined from
     `probe_playbooks`. Useful for "which trigger should I pick".
  3. The `playbooks_seen` connector-frequency rollup — "what real playbooks
     orchestrate" so agents have a sense of the common-case shapes.

Don't write recipes that copy logic from `STEP_TYPES.md` — that file already
has per-step examples. RECIPES.md is for *multi-step compositions*.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from probes.common import DB_PATH, REPO_ROOT, STORE_DIR

OUT_PATH = STORE_DIR / "RECIPES.md"
EXAMPLES_DIR = REPO_ROOT / "examples"


EXAMPLE_HEADERS: dict[str, dict[str, str]] = {
    "hello_connector.yaml": {
        "title": "Hello world — start → set_variables → connector",
        "use_when": "Smoke-testing the compiler end-to-end, or as the skeleton "
                    "of a one-off automation. Three steps and you're done.",
    },
    "decision_branch.yaml": {
        "title": "Decision branch — route by condition",
        "use_when": "Any time the next step depends on data: severity tiers, "
                    "indicator types, IOC categories, approval/deny.",
    },
    "find_and_update.yaml": {
        "title": "Find and update — the canonical mutation pattern",
        "use_when": "Look up a record by query, then mutate it. Most ingestion "
                    "playbooks reduce to this. Pair with a Decision branch on "
                    "the find_record result count to handle no-match.",
    },
    "manual_input_then_act.yaml": {
        "title": "Manual input — pause for human approval",
        "use_when": "Approval flows. Bot proposes an action, user confirms via "
                    "the FSR UI before the next step runs.",
    },
    "parent_calls_child.yaml": {
        "title": "Parent calls child — playbook composition",
        "use_when": "Reusable subroutines. Anything called from more than one "
                    "place should live in a child playbook + workflow_reference.",
    },
}


def _read_example(name: str) -> str:
    path = EXAMPLES_DIR / name
    if not path.exists():
        return f"# (missing: {path.relative_to(REPO_ROOT)})"
    return path.read_text().rstrip()


def build_recipes_md(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> Path:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        triggers = conn.execute(
            "SELECT name, when_to_use, source_playbook FROM recipes "
            "WHERE kind = 'trigger_pattern' ORDER BY CAST(source_playbook AS INTEGER) DESC"
        ).fetchall()

        connector_freq = conn.execute(
            "SELECT uses_connectors_csv, COUNT(*) AS c "
            "FROM playbooks_seen "
            "WHERE uses_connectors_csv IS NOT NULL AND uses_connectors_csv != '' "
            "GROUP BY uses_connectors_csv ORDER BY c DESC LIMIT 25"
        ).fetchall()

        total_pbs = conn.execute("SELECT COUNT(*) FROM playbooks_seen").fetchone()[0]
    finally:
        conn.close()

    parts: list[str] = []
    parts.append("# FortiSOAR playbook recipes")
    parts.append("")
    parts.append(
        "Generated from `examples/*.yaml` + `store/fsr_reference.db` by "
        "`python/store/export_recipes.py`. Recipes are *multi-step* "
        "compositions — for per-step shape see `STEP_TYPES.md`, for connector "
        "ops see `CONNECTORS.md`."
    )
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Curated patterns")
    parts.append("")
    parts.append(
        "Each pattern below is a complete, importable YAML. Compile with "
        "`fsrpb compile <file>`; push with `fsrpb push <file>`. They round-trip "
        "lossless against the live instance."
    )
    parts.append("")

    for fname, meta in EXAMPLE_HEADERS.items():
        parts.append(f"### {meta['title']}")
        parts.append("")
        parts.append(f"**Use when**: {meta['use_when']}")
        parts.append("")
        parts.append(f"_File_: `examples/{fname}`")
        parts.append("")
        parts.append("```yaml")
        parts.append(_read_example(fname))
        parts.append("```")
        parts.append("")
        parts.append("---")
        parts.append("")

    parts.append("## Trigger-type frequency (from live instance)")
    parts.append("")
    parts.append(
        "Which trigger to pick when authoring? Frequencies below are observed "
        f"across **{total_pbs}** playbooks on the connected instance. Match "
        "your authoring intent to the pattern that already dominates real-world "
        "use."
    )
    parts.append("")
    parts.append("| Trigger step type | Playbooks | When to use |")
    parts.append("|---|---:|---|")

    trigger_use_when = {
        "cybersponse.action": "User clicks a Module Action button on a record. Most common.",
        "cybersponse.abstract_trigger": "Generic programmatic trigger (called by other playbooks or the API).",
        "cybersponse.post_create": "Fire when a record is created in a module.",
        "cybersponse.post_update": "Fire when a record is updated in a module.",
        "cybersponse.post_delete": "Fire when a record is deleted in a module.",
        "cybersponse.api_call": "External system POSTs to a webhook URL exposed by FSR.",
    }
    for r in triggers:
        step_type = r["name"].removeprefix("trigger:")
        parts.append(
            f"| `{step_type}` | {r['source_playbook']} | "
            f"{trigger_use_when.get(step_type, '—')} |"
        )
    parts.append("")
    parts.append("---")
    parts.append("")

    parts.append("## Common connector orchestrations")
    parts.append("")
    parts.append(
        "Top connectors invoked by real playbooks on the connected instance. "
        "Use this to ground recipe choice — if a connector dominates the table, "
        "examples for it likely exist in `pb_examples/all_fsr_evoke_playbooks.json` "
        "and can be pulled with `fsrpb pull` for read-only inspection."
    )
    parts.append("")
    parts.append("| Connector(s) used | Playbook count |")
    parts.append("|---|---:|")
    for r in connector_freq:
        csv = r["uses_connectors_csv"].replace("|", "\\|")
        parts.append(f"| `{csv}` | {r['c']} |")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(
        "**Adding a new recipe**: drop a hand-curated YAML in `examples/`, add "
        "a row to `EXAMPLE_HEADERS` in `python/store/export_recipes.py`, "
        "regenerate. Recipe YAMLs double as round-trip regression fixtures."
    )
    parts.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path


if __name__ == "__main__":
    p = build_recipes_md()
    print(f"wrote {p}")
