"""Audit known params per step type by combining three sources:

1. **Resolver allowlists** — what `compiler/resolver.py` accepts as
   friendly + canonical args per step type. Mirrored here so the
   audit tool doesn't have to AST-parse resolver.py. Keep in sync
   when those allowlists change.
2. **Corpus observations** — `playbook_steps` arguments_json top-level
   key frequencies, grouped by `step_type_name`. Ground truth for
   what real FSR playbooks actually use.
3. **Mismatches** — keys observed in the corpus but absent from both
   allowlists. These are resolver gaps (the `condition`-on-everything
   discovery from 2026-05-08 was found exactly this way).

Drives the `fsrpb dump-step-params` CLI, which writes a Markdown
report per step type to a directory you can browse alongside the
FSR Studio UI for cross-checking.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


# Maps the FSR canonical step_type_name (column in `playbook_steps`)
# to the simplified-IR / resolver short type for cross-referencing.
TYPE_NAME_TO_RESOLVER: dict[str, str] = {
    "Connectors": "connector",
    "SetVariable": "set_variable",
    "Decision": "decision",
    "ManualInput": "manual_input",
    "ApprovalManualInput": "manual_input",
    "CodeSnippet": "code_snippet",
    "Delay": "utils_delay",
    "WorkflowReference": "workflow_reference",
    "UpdateRecord": "update_record",
    "FindRecords": "find_records",
    "InsertData": "create_record",
    "DeleteRecord": "delete_record",
    "cybersponse.post_create": "start_on_create",
    "cybersponse.post_update": "start_on_update",
    "cybersponse.post_delete": "start_on_delete",
    "cybersponse.api_call": "start_on_api_call",
    "cybersponse.action": "start",
    "cybersponse.abstract_trigger": "start",
    "SendMail": "send_email",
    "IngestBulkFeed": "ingest_bulk_feed",
    "RunScript": "run_script",
    "ManualTask": "manual_task",
    "Approval": "approval",
}


# Mirrors the `_FRIENDLY` / `_CANONICAL` sets in `compiler/resolver.py`
# for each normalize function. Source-of-truth comment per entry.
ALLOWLISTS: dict[str, dict[str, set[str]]] = {
    # post_create / post_update — _normalize_post_create_update_args
    # resolver.py:744
    "start_on_create": {
        "friendly":  {"module", "modules", "when", "mock_result", "condition"},
        "canonical": {"resource", "resources", "step_variables",
                      "triggerOnSource", "triggerOnReplicate",
                      "__triggerLimit", "fieldbasedtrigger", "useMockOutput"},
    },
    "start_on_update": {
        "friendly":  {"module", "modules", "when", "mock_result", "condition"},
        "canonical": {"resource", "resources", "step_variables",
                      "triggerOnSource", "triggerOnReplicate",
                      "__triggerLimit", "fieldbasedtrigger", "useMockOutput"},
    },

    # record CRUD — _normalize_record_crud_args  resolver.py:869
    "create_record": {
        "friendly":  {"module", "mock_result", "condition"},
        "canonical": {"collection", "collectionType", "resource",
                      "operation", "fieldOperation", "step_variables",
                      "__bulk", "__recommend", "_showJson", "useMockOutput"},
    },
    "update_record": {
        "friendly":  {"module", "mock_result", "condition"},
        "canonical": {"collection", "collectionType", "resource",
                      "operation", "fieldOperation", "step_variables",
                      "__bulk", "__recommend", "_showJson", "useMockOutput"},
    },
    "find_records": {
        "friendly":  {"module", "mock_result", "condition"},
        "canonical": {"collection", "collectionType", "resource",
                      "operation", "fieldOperation", "step_variables",
                      "__bulk", "__recommend", "_showJson", "useMockOutput"},
    },
    "delete_record": {
        "friendly":  {"module", "mock_result", "condition"},
        "canonical": {"collection", "collectionType", "resource",
                      "operation", "fieldOperation", "step_variables",
                      "__bulk", "__recommend", "_showJson", "useMockOutput"},
    },

    # code_snippet — resolver.py:1447
    "code_snippet": {
        "friendly":  {"code", "python", "config", "mock_result", "condition"},
        "canonical": {"connector", "operation", "operationTitle", "params",
                      "pickFromTenant", "step_variables", "version"},
    },

    # delay — resolver.py:1497
    "utils_delay": {
        "friendly":  {"seconds", "minutes", "hours", "days", "mock_result",
                      "condition"},
        "canonical": {"connector", "operation", "operationTitle", "params",
                      "step_variables", "version"},
    },

    # connector — resolver.py:1829 (no _FRIENDLY / _CANONICAL set;
    # uses _CONNECTOR_RESERVED + per-op param schemas)
    "connector": {
        "friendly":  set(),
        "canonical": {"connector", "operation", "operationTitle", "version",
                      "config", "params", "step_variables", "pickFromTenant",
                      "name", "mock_result", "useMockOutput", "condition"},
    },

    # decision — _normalize_decision_args  resolver.py:1155
    "decision": {
        "friendly":  {"conditions"},
        "canonical": {"step_variables"},
    },

    # manual_input — _normalize_manual_input_args  resolver.py:1194
    "manual_input": {
        "friendly":  {"title", "description", "options", "inputs"},
        "canonical": {"step_variables"},
    },

    # workflow_reference — _resolve_workflow_reference_args  resolver.py:2003
    "workflow_reference": {
        "friendly":  {"target"},
        "canonical": {"workflowReference", "arguments", "apply_async",
                      "pass_input_record", "pass_parent_env", "step_variables",
                      "ignore_errors"},
    },
}


# Top-level keys every step accepts (for_each + step_variables sit
# at the arguments root regardless of step type).
GLOBAL_RESERVED = {"for_each", "step_variables"}


# Per-resolver-type "open key" markers — these step types accept
# *arbitrary* user keys at the arguments root, so unrecognized-key
# detection produces noise. The note is rendered into each report
# instead of a gap list.
OPEN_TYPES: dict[str, str] = {
    "set_variable": (
        "set_variable accepts arbitrary user-chosen variable names at "
        "the arguments root (each becomes a `vars.steps.<step>.<name>` "
        "binding). Unrecognized-key detection is suppressed here — "
        "audit only the canonical fields."
    ),
    "connector": (
        "connector accepts any registered op parameter at the arguments "
        "root; the resolver auto-lifts op-specific keys into "
        "`params:`. Unrecognized-key detection is suppressed because "
        "the universe is per-op, not static."
    ),
    "manual_input": (
        "manual_input's `inputs:` / `options:` lists carry user-chosen "
        "field names that surface here; suppressed."
    ),
}


@dataclass
class StepTypeAudit:
    fsr_type_name: str
    resolver_type: str | None
    total_steps: int
    observed_keys: dict[str, int]  # key → count
    friendly_allowed: set[str]
    canonical_allowed: set[str]
    unrecognized: list[tuple[str, int]]  # corpus keys not in either set


def collect_corpus_keys(db: sqlite3.Connection) -> dict[str, Counter]:
    """For each step_type_name in playbook_steps, count top-level
    arguments_json keys."""
    out: dict[str, Counter] = {}
    for row in db.execute(
        "SELECT step_type_name, arguments_json FROM playbook_steps"
    ):
        ttype, args_json = row
        if not args_json:
            continue
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(args, dict):
            continue
        c = out.setdefault(ttype, Counter())
        for k in args:
            c[k] += 1
    return out


def audit_step_type(fsr_type_name: str,
                    counter: Counter,
                    total_with_args: int) -> StepTypeAudit:
    resolver_type = TYPE_NAME_TO_RESOLVER.get(fsr_type_name)
    allow = ALLOWLISTS.get(resolver_type or "", {})
    friendly = allow.get("friendly", set())
    canonical = allow.get("canonical", set())
    accepted = friendly | canonical | GLOBAL_RESERVED

    unrecognized: list[tuple[str, int]] = []
    if resolver_type and accepted and resolver_type not in OPEN_TYPES:
        for k, n in counter.most_common():
            if k not in accepted:
                unrecognized.append((k, n))

    return StepTypeAudit(
        fsr_type_name=fsr_type_name,
        resolver_type=resolver_type,
        total_steps=total_with_args,
        observed_keys=dict(counter.most_common()),
        friendly_allowed=friendly,
        canonical_allowed=canonical,
        unrecognized=unrecognized,
    )


def render_audit_md(a: StepTypeAudit) -> str:
    lines: list[str] = []
    lines.append(f"# {a.fsr_type_name}")
    lines.append("")
    lines.append(f"- FSR step_type_name: `{a.fsr_type_name}`")
    lines.append(f"- Resolver short type: "
                 f"`{a.resolver_type or '(unmapped)'}`")
    lines.append(f"- Corpus rows with arguments: **{a.total_steps:,}**")
    lines.append("")
    lines.append("## Resolver allowlists (friendly + canonical)")
    if a.resolver_type and (a.friendly_allowed or a.canonical_allowed):
        lines.append("")
        lines.append("| friendly | canonical |")
        lines.append("|---|---|")
        rows = max(len(a.friendly_allowed), len(a.canonical_allowed))
        f_sorted = sorted(a.friendly_allowed)
        c_sorted = sorted(a.canonical_allowed)
        for i in range(rows):
            f = f"`{f_sorted[i]}`" if i < len(f_sorted) else ""
            c = f"`{c_sorted[i]}`" if i < len(c_sorted) else ""
            lines.append(f"| {f} | {c} |")
    else:
        lines.append("")
        lines.append("_(no resolver mapping or no allowlists declared)_")
    lines.append("")
    if a.resolver_type in OPEN_TYPES:
        lines.append("> **Note:** " + OPEN_TYPES[a.resolver_type])
        lines.append("")
    lines.append("## Corpus observations (top-level arguments keys)")
    lines.append("")
    lines.append("| key | count | % of rows | accepted? |")
    lines.append("|---|---:|---:|---|")
    accepted = a.friendly_allowed | a.canonical_allowed | GLOBAL_RESERVED
    for k, n in a.observed_keys.items():
        pct = (100.0 * n / a.total_steps) if a.total_steps else 0
        if not a.resolver_type:
            tag = "—"
        elif k in accepted:
            tag = "✓"
        else:
            tag = "✗ unrecognized"
        lines.append(f"| `{k}` | {n} | {pct:.1f}% | {tag} |")
    lines.append("")
    if a.unrecognized:
        lines.append("## ⚠ Unrecognized keys (resolver gaps)")
        lines.append("")
        lines.append("These keys appear in real corpus playbooks but the "
                     "resolver doesn't whitelist them. Either widen the "
                     "allowlist or confirm FSR ignores them at runtime "
                     "(probe before adding).")
        lines.append("")
        for k, n in a.unrecognized:
            lines.append(f"- `{k}` ({n} rows)")
        lines.append("")
    return "\n".join(lines)


def write_audit_dir(out_dir: Path, db_path: Path) -> dict[str, Path]:
    """Write one MD per step type. Returns the {type: path} map."""
    out_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    by_type = collect_corpus_keys(db)
    written: dict[str, Path] = {}
    summary_rows: list[tuple[str, int, int, int]] = []  # type, rows, ok, gaps
    for ttype, counter in sorted(by_type.items()):
        total = sum(counter.values()) // max(1, len(counter)) if counter else 0
        # Better approximation of "rows with this type": run a count.
        cur = db.execute(
            "SELECT COUNT(*) FROM playbook_steps WHERE step_type_name = ?",
            (ttype,))
        total = cur.fetchone()[0]
        a = audit_step_type(ttype, counter, total)
        path = out_dir / f"{ttype.replace('.', '_')}.md"
        path.write_text(render_audit_md(a))
        written[ttype] = path
        summary_rows.append((ttype, total, len(a.observed_keys),
                             len(a.unrecognized)))
    # Index file
    idx_lines = ["# Step type param audit", "",
                 "| step_type | corpus rows | distinct keys | gaps |",
                 "|---|---:|---:|---:|"]
    for t, rows, keys, gaps in sorted(summary_rows):
        gap_marker = f"**{gaps}**" if gaps else "—"
        idx_lines.append(f"| [{t}]({t.replace('.', '_')}.md) | "
                         f"{rows:,} | {keys} | {gap_marker} |")
    (out_dir / "INDEX.md").write_text("\n".join(idx_lines) + "\n")
    db.close()
    return written
