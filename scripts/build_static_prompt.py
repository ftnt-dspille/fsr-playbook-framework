#!/usr/bin/env python3
"""Generate `python/agent/static_grammar_block.md` — the cacheable
prompt prefix containing byte-identical-across-tenants reference data.

Output gets prepended to the live `system_prompt.md` so Anthropic
prompt caching can amortize it. See `docs/plans/AGENT_LOOP_REFINEMENT_PLAN.md`
Refinement A.

Re-run any time the underlying corpus refreshes:
    python scripts/build_static_prompt.py

The script is idempotent: if the generated content is unchanged it
leaves the file alone (so git noise is minimal).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from textwrap import indent

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
DB_PATH = REPO / "store" / "fsr_reference.db"
OUT_PATH = PYTHON_DIR / "agent" / "static_grammar_block.md"

if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

# Friendly forms + canonical mapping live in tools_discovery.
# Import only the data; do not pull in MCP server side effects.
from mcp_server.tools_discovery import (  # noqa: E402
    _SHORT_TO_CANONICAL,
    _FRIENDLY_FORMS,
)

# Order step types canonically: triggers first, then authoring, then control.
_STEP_ORDER = [
    "start", "start_on_create", "start_on_update",
    "set_variable", "decision", "connector",
    "find_record", "create_record", "update_record", "insert_record",
    "manual_input", "approval", "code_snippet",
    "delay", "workflow_reference", "stop", "end",
]


def _render_example(example) -> str:
    try:
        import yaml  # type: ignore
        body = yaml.safe_dump(example, sort_keys=False).rstrip()
    except Exception:
        body = json.dumps(example, indent=2)
    return indent(body, "    ")


def _step_section() -> str:
    out: list[str] = ["## 1. Canonical step types (14)\n"]
    out.append(
        "These are the *only* step types the resolver accepts. Use the "
        "friendly short name on the left in YAML. Each section lists "
        "`accepted_keys`, a one-line note, and a worked example. **Reject "
        "any other top-level shape** — there is no `script_step`, "
        "`http_call`, `webhook`, or `branch` type.\n"
    )
    out.append("| Friendly | Canonical FSR | Use when |")
    out.append("|---|---|---|")
    uses = {
        "start": "manual / designer trigger (with optional `module:` for Execute-menu button)",
        "start_on_create": "auto-fires on record creation in `module:`",
        "start_on_update": "auto-fires on record update in `module:` (often with `op: changed`)",
        "set_variable": "compute or stage workflow vars (optionally post a comment)",
        "decision": "branch on Jinja conditions with a single `default: true` else branch",
        "connector": "invoke a connector op; params under `arguments.params`",
        "find_record": "query records from a module with a typed filter tree",
        "create_record": "create a record (alias: `insert_record`)",
        "update_record": "update a record by IRI",
        "insert_record": "alias of create_record",
        "manual_input": "ask the analyst — Context (Record Linked vs Independent), Behavior, InputType",
        "approval": "approve / reject buttons routed to an analyst",
        "code_snippet": "run inline Python (use sparingly — opaque to the typed walker)",
        "delay": "pause for N seconds before next step",
        "workflow_reference": "call another playbook (sync = `apply_async: false`)",
        "stop": "terminate the playbook",
        "end": "terminal node on a linear branch",
    }
    for short in _STEP_ORDER:
        canon = _SHORT_TO_CANONICAL.get(short, "—")
        use = uses.get(short, "")
        out.append(f"| `{short}` | `{canon}` | {use} |")
    out.append("")

    for short in _STEP_ORDER:
        info = _FRIENDLY_FORMS.get(short)
        if not info:
            continue
        keys = info.get("accepted_keys") or []
        out.append(f"### `{short}`\n")
        if keys:
            out.append(f"**Accepted keys**: `{', '.join(keys)}`\n")
        if "when_shape" in info:
            out.append(f"**`when:` filter shape**: {info['when_shape']}\n")
        note = info.get("note") or ""
        if note:
            out.append(note + "\n")
        ex = info.get("example")
        if ex is not None:
            out.append("Example:")
            out.append("```yaml")
            out.append(_render_example(ex).lstrip())
            out.append("```\n")
    return "\n".join(out)


def _fsr_jinja_section() -> str:
    """Authoritative list of FSR-custom Jinja symbols (globals, filters,
    tests). Ansible / stdlib symbols are excluded — the LLM knows those.
    """
    out: list[str] = ["## 2. FortiSOAR-custom Jinja\n"]
    out.append(
        "These symbols come from `sealab.jinja`, `workflow.jinja`, and "
        "`workflow.np_filters` — they are **not** in stock Jinja2 or "
        "Ansible. Prefer them over hand-rolled date / IOC / connector-"
        "config patterns. Pipe filters with `|`, call globals/tests "
        "directly.\n"
    )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    fsr_modules = ("sealab.jinja", "workflow.jinja", "workflow.np_filters")
    for kind, table, header in (
        ("global", "jinja_globals", "Globals (call directly, no pipe)"),
        ("filter", "jinja_macros", "Filters (use with pipe `|`)"),
        ("test", "jinja_tests", "Tests (use with `is`)"),
    ):
        placeholders = ", ".join("?" for _ in fsr_modules)
        rows = conn.execute(
            f"SELECT name, signature, module FROM {table} "
            f"WHERE module IN ({placeholders}) ORDER BY name",
            fsr_modules,
        ).fetchall()
        if not rows:
            continue
        out.append(f"### {header} ({len(rows)})\n")
        for r in rows:
            sig = (r["signature"] or "").strip() or r["name"]
            out.append(f"- `{sig}` — _{r['module']}_")
        out.append("")
    out.append(
        "**Ansible filters worth remembering** (network + json + collections — "
        "FSR includes them, but they're standard Ansible):\n"
    )
    out.append(
        "- IP / network: `ipaddr`, `ipv4`, `ipv6`, `ipwrap`, `ipmath`, "
        "`ipsubnet`, `cidr_merge`, `network_in_network`, `nthhost`\n"
        "- Hashing: `hash`, `to_uuid`, `password_hash`\n"
        "- JSON / queries: `json_query` (JMESPath), `to_json`, `from_json`, "
        "`to_yaml`, `from_yaml`\n"
        "- Collections: `groupby`, `intersect`, `difference`, `union`, "
        "`symmetric_difference`, `flatten`, `dict2items`, `items2dict`"
    )
    out.append("")
    return "\n".join(out)


def _grammar_rules_section() -> str:
    """The Norway problem, step-name charset, vars addressing, decision
    + manual_input mode rules. Same content as the resolver enforces."""
    return """## 3. Grammar rules the resolver enforces

### 3.1 Step-name charset & Norway problem

Step names use Title Case display strings (e.g. `Check Value`,
`Greater Than 10`) and may only contain letters, digits, spaces,
and `_`. **Forbidden**: `-`, `:`, em-dashes, parens, `?`, `/`, `#`,
quotes. The Norway problem: never use unquoted `no`, `false`, `off`,
`yes`, `true`, `on` as bare values — YAML coerces them to booleans.
Quote string values that match those tokens.

### 3.2 Step references in `next:`

Reference a step by writing its `name:` verbatim — same spaces, same
casing. Examples:

```yaml
- type: start
  name: Run
  next: Check Severity
- type: decision
  name: Check Severity
  conditions:
    - display: High
      when: "{{ vars.input.records[0].severity == 'High' }}"
      next: Notify
    - display: Else
      default: true
      next: Skip
```

### 3.3 Runtime access to step outputs

`vars.steps.<name-with-spaces-replaced-by-underscores>.<key>` — same
slug rule applies to child-playbook outputs and to references inside
Jinja:

- Step named `Greater Than 10` → `vars.steps.Greater_Than_10.foo`.
- Trigger params arrive at `vars.input.params.<k>`, NOT `vars.input.<k>`.
- `vars.input.records[0]` is the triggering record for module-bound
  triggers (`start` with `module:`, `start_on_create`, `start_on_update`).

### 3.4 Decision step — exact shape

```yaml
- type: decision
  name: Check Value
  conditions:
    - display: Greater Than 10
      when: "{{ vars.input.value > 10 }}"
      next: Greater Than 10
    - display: Else
      default: true
      next: Not Greater Than 10
```

- Every non-default entry has `display`, `when`, `next`.
- Exactly **one** entry has `default: true`; that entry has
  `display`, `default: true`, `next` and **no** `when`.
- Decisions with zero defaults or two defaults are rejected.

### 3.5 Manual input — mode-driven, not free-form

Every "extra" top-level key on `manual_input` is gated by one of three
UI-mode toggles. Wrong combinations (e.g. internal-only with external
emails populated) are structurally rejected.

- **Mode A — Context**: `Record Linked` (default) vs `Record Independent`.
- **Mode B — Behavior**: who receives the prompt — analyst queue, specific user, etc.
- **Mode C — InputType**: `DecisionBased` (buttons only) vs `InputBased`
  (free-form fields) vs both.

```yaml
- type: manual_input
  name: Ask User
  arguments:
    title: "Approve?"
    description: "Confirm before proceeding."
  options:
    - display: Approve
      primary: true
      next: Do Thing
    - display: Reject
      next: Stop Here
```

The first option is primary unless another is marked. For
`InputBased`, use `inputs:` with typed `kind:` per field (`ipv4`,
`email`, `url`, `integer`, etc. — `text` only for free-form prose).

### 3.6 Set-variable — vars vs message

```yaml
- type: set_variable
  name: Prep
  vars:
    target_org: "{{ vars.input.params.org }}"
    severity: High
  message:
    content: "Block approved for {{ vars.ip }}"
    tags: [auto_block, soc_review]
```

- `vars:` are workflow-scope variables only (never visible to a SOC
  analyst on the record). Flat string→string mapping; do **not** nest.
- `message:` posts a comment to the triggered record. Only set
  `record: "<iri>"` when the playbook has no triggered record
  (designer-only manual run).

### 3.7 Picklists

Picklist values in `arguments:` are friendly strings (`"High"`), not
IRIs — the compiler resolves them. Picklist trigger filters cannot use
`like` against picklist-typed fields (`type`, `severity`, `status`);
filter on string fields, or use `op: changed`.

### 3.8 Connectivity

- Every non-trigger step must be the target of some other step's
  `next:`, decision `conditions[].next`, or `manual_input.options[].next`.
- Every linear branch ends at `type: end` (or `stop`).
- Trigger `start` with no `module:` is a designer-only manual trigger;
  with no `next:` wiring it becomes a *referenced sub-playbook* (only
  correct when another playbook calls this one).
"""


HEADER = """<!-- Auto-generated by scripts/build_static_prompt.py.
     Do not edit by hand; re-run the script. Lives at the top of the
     system prompt for Anthropic prompt caching (5-min ephemeral). -->
# Static grammar block

The rules and shapes below are byte-identical across every FortiSOAR
tenant. Treat them as ground truth; do not call `get_step_type` or
`find_jinja_filter` to re-derive them. Reach for MCP tools only for
tenant-shape facts (installed connectors, picklists, modules, live
runs).

"""


def main() -> int:
    sections = [
        HEADER,
        _step_section(),
        _fsr_jinja_section(),
        _grammar_rules_section(),
    ]
    new_content = "\n".join(s.rstrip() + "\n" for s in sections)
    if OUT_PATH.exists():
        existing = OUT_PATH.read_text(encoding="utf-8")
        if existing == new_content:
            print(f"unchanged: {OUT_PATH.relative_to(REPO)}")
            return 0
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(new_content, encoding="utf-8")
    size_kb = len(new_content.encode("utf-8")) / 1024
    print(f"wrote: {OUT_PATH.relative_to(REPO)} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
