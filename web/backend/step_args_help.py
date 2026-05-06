"""Curated `arguments:` documentation per step type.

Powers the Monaco hover popup over `arguments:` (and child keys) in the
chat-app editor. Source-of-truth for what each friendly step type
accepts, drawn from:
  - the resolver normalizers in `python/compiler/resolver.py`,
  - the validator co-presence rules in `python/compiler/validator.py`,
  - corpus findings in `MI_DECISION_VALIDATION_AUDIT.md`,
  - the canonical step-type catalog in `MANUAL_INPUT.md`.

Each entry is a dict shaped like:
  {
    "summary": "<one-line gist>",
    "args": [
      {"name": "...", "required": bool, "kind": "...",
       "description": "...", "mode_note": "..."},
      ...
    ],
    "examples": ["yaml snippet", ...],
  }

Why a hand-curated dict and not introspection? Friendly-form keys
(`title`, `inputs`, `module`, `branches`) don't exist in the canonical
JSON shape — they only live in the resolver normalizers. The agent
needs *authoring* docs, not runtime schema.
"""
from __future__ import annotations

from typing import Any


_MANUAL_INPUT: dict[str, Any] = {
    "summary": (
        "Pause the playbook for a human response. Friendly form: "
        "`title`, `description`, `options`, `inputs`. Mode-aware: see "
        "Context (record-linked vs independent), Audience (internal vs "
        "external), Assignment (owner_detail)."
    ),
    "args": [
        {"name": "title", "required": False, "kind": "string",
         "description": "Prompt heading shown to the user. Jinja-templated."},
        {"name": "description", "required": False, "kind": "markdown string",
         "description": "Body text. Markdown allowed."},
        {"name": "options", "required": False, "kind": "list[str|dict]",
         "description": "Buttons. Each: `{option, primary?, next?}`. "
                        "`next:` per option points at the next step "
                        "(lifted into branches at compile time)."},
        {"name": "inputs", "required": False, "kind": "list[dict]",
         "description": "Form fields. Each: `{name, kind, label?, "
                        "tooltip?, required?, default?, options?, "
                        "module?, picklist?}`. Kinds: text, textarea, "
                        "richtext, html, password, ipv4, ipv6, domain, "
                        "email, url, phone, filehash, integer, decimal, "
                        "checkbox, datetime, date, select, multiselect, "
                        "picklist, multiselectpicklist, lookup, file, "
                        "image, json. `lookup` requires `module:`; "
                        "`picklist` requires `picklist:`."},
        {"name": "type", "required": False, "kind": "enum",
         "description": "`InputBased` (default — form prompt) or "
                        "`DecisionBased` (button-only, no input form)."},
        {"name": "is_approval", "required": False, "kind": "bool",
         "description": "Style as Approve/Reject (UI overlay only)."},
        # Context mode
        {"name": "isRecordLinked", "required": False, "kind": "bool",
         "mode": "Context",
         "description": "true ⇒ pair with `record:` (Jinja IRI of the "
                        "record to attach). false ⇒ Record Independent; "
                        "leave `record:` empty."},
        {"name": "record", "required": False, "kind": "string (Jinja IRI)",
         "mode": "Context",
         "description": "Record IRI to attach. Required iff "
                        "`isRecordLinked: true`."},
        {"name": "resources", "required": False, "kind": "string",
         "mode": "Context",
         "description": "Module name when record-linked (alerts, "
                        "incidents, indicators…)."},
        # Audience mode
        {"name": "unauthenticated_input", "required": False, "kind": "bool",
         "mode": "Audience",
         "description": "true ⇒ external mode (publicly resolvable form "
                        "link). Pair with `external_channel_list` and "
                        "delivery configs."},
        {"name": "inputExternalUser", "required": False, "kind": "bool",
         "mode": "Audience",
         "description": "Open form to non-FSR users. Usually paired "
                        "with `unauthenticated_input: true`."},
        {"name": "external_channel_list", "required": False,
         "kind": "list[picklist IRI]", "mode": "Audience",
         "description": "Delivery channels for external mode (email, "
                        "Slack, Teams)."},
        {"name": "inline_channel_list", "required": False,
         "kind": "list[picklist IRI]", "mode": "Audience",
         "description": "In-app notification channels (mention "
                        "sources)."},
        {"name": "customEmailExternal", "required": False, "kind": "string",
         "mode": "Audience (external)",
         "description": "Custom external email subject. Requires "
                        "external mode; flagged otherwise."},
        {"name": "external_email_subject", "required": False, "kind": "string",
         "mode": "Audience (external)"},
        {"name": "external_email_attachments", "required": False,
         "kind": "list", "mode": "Audience (external)"},
        {"name": "custom_email_body_external", "required": False,
         "kind": "string", "mode": "Audience (external)"},
        {"name": "internal_email_subject", "required": False,
         "kind": "string", "mode": "Audience (internal email)"},
        {"name": "customEmailInternal", "required": False,
         "kind": "string", "mode": "Audience (internal email)"},
        {"name": "custom_email_body_internal", "required": False,
         "kind": "string", "mode": "Audience (internal email)"},
        {"name": "internal_email_attachments", "required": False,
         "kind": "list", "mode": "Audience (internal email)"},
        {"name": "email_notification", "required": False, "kind": "dict",
         "description": "`{enabled: bool, smtpParameters: list}`."},
        # Assignment mode
        {"name": "owner_detail", "required": False, "kind": "dict",
         "mode": "Assignment",
         "description": "`{isAssigned, assignedToPerson?, "
                        "assignedToTeam?, assignedToRecord?, "
                        "assignedToField?}`. When `isAssigned: true`, "
                        "exactly one of the four targets must be set."},
        # Other
        {"name": "timeout", "required": False, "kind": "dict",
         "description": "`{days, hours, minutes, step_iri}` — auto-route "
                        "to step_iri if no response within window."},
        {"name": "agent_id", "required": False, "kind": "uuid|null",
         "description": "Route prompt to a specific agent (multi-tenant)."},
        {"name": "step_variables", "required": False, "kind": "list",
         "description": "Vars exposed to downstream steps (typically empty)."},
        {"name": "label", "required": False, "kind": "string"},
        {"name": "message", "required": False, "kind": "string"},
        {"name": "inputInternalUsers", "required": False, "kind": "list"},
    ],
    "examples": [
        "title: Approve?\noptions:\n  - {option: yes, primary: true, next: do_block}\n  - {option: no,  next: end_pb}",
        "title: Enter IP\ninputs:\n  - {name: ip, kind: ipv4, label: Address, required: true}",
        "title: Pick reviewer\ninputs:\n  - {name: who, kind: lookup, module: people, required: true}",
    ],
}


_DECISION: dict[str, Any] = {
    "summary": (
        "Branch the playbook on Jinja conditions. Each entry in "
        "`conditions[]` is either a non-default branch (with both "
        "`option` and `condition`) or the single default fall-through "
        "(`default: true`, no condition). Branch targets are wired via "
        "`branches:` on the step or a step-level `next:` fall-through."
    ),
    "args": [
        {"name": "conditions", "required": True, "kind": "list[dict]",
         "description": "List of branches. Each non-default entry: "
                        "`{option, condition, [step_name?]}`. The single "
                        "default entry: `{option?, default: true, "
                        "[step_name?]}` — must omit `condition`."},
        {"name": "step_variables", "required": False, "kind": "list",
         "description": "Scratch vars exposed downstream."},
    ],
    "examples": [
        "conditions:\n  - {option: 'yes', condition: \"{{ x > 5 }}\"}\n  - {option: 'no', default: true}\nbranches:\n  'yes': handle_high\n  'no':  handle_low",
        "conditions:\n  - {option: 'yes', condition: \"{{ x }}\"}\nbranches:\n  'yes': handle_yes\nnext: handle_no   # implicit default fall-through",
    ],
}


_CONNECTOR: dict[str, Any] = {
    "summary": "Invoke one connector operation. Friendly form takes "
               "`connector`, `operation`, `params`, optional `config`.",
    "args": [
        {"name": "connector", "required": True, "kind": "string",
         "description": "Connector name (e.g. `splunk`, `cyops_utilities`)."},
        {"name": "operation", "required": True, "kind": "string",
         "description": "Operation name on that connector."},
        {"name": "params", "required": False, "kind": "dict",
         "description": "Per-operation arguments. Validated against the "
                        "operation_params catalog when known."},
        {"name": "config", "required": False, "kind": "string",
         "description": "Connector-config name (resolved to UUID at "
                        "compile time). Defaults to the connector's "
                        "default config."},
        {"name": "version", "required": False, "kind": "string"},
        {"name": "step_variables", "required": False, "kind": "list"},
    ],
    "examples": [
        "connector: splunk\noperation: search\nparams:\n  query: \"index=main\"\n  earliest: -15m",
    ],
}


_SET_VARIABLE: dict[str, Any] = {
    "summary": "Set named workflow variables. Friendly form: `arg_list` "
               "as a list of `{name, value}` pairs. Each becomes "
               "`vars.steps.<step_name>.<name>` downstream.",
    "args": [
        {"name": "arg_list", "required": True, "kind": "list[dict]",
         "description": "Each: `{name, value}`. Value can be Jinja."},
    ],
    "examples": [
        "arg_list:\n  - {name: severity, value: 'high'}\n  - {name: count, value: \"{{ vars.steps.find.data | length }}\"}",
    ],
}


_FIND_RECORD: dict[str, Any] = {
    "summary": "Query an FSR module for matching records.",
    "args": [
        {"name": "module", "required": True, "kind": "string",
         "description": "Module name (alerts, incidents, indicators, …)."},
        {"name": "query", "required": True, "kind": "dict",
         "description": "FSR query body (`{filters: [...], sort: [...], "
                        "limit, page}` etc.)."},
    ],
}


_CREATE_RECORD: dict[str, Any] = {
    "summary": "Insert a new record. Compiles to `InsertData` "
               "(`/api/3/<module>`); on-create triggers fire as normal.",
    "args": [
        {"name": "module", "required": True, "kind": "string"},
        {"name": "resource", "required": True, "kind": "dict",
         "description": "Field map for the new record."},
        {"name": "operation", "required": False, "kind": "enum",
         "description": "`Append` (default) or `Overwrite`. Affects "
                        "fields with multi-value semantics."},
        {"name": "fieldOperation", "required": False, "kind": "dict"},
        {"name": "__bulk", "required": False, "kind": "bool",
         "description": "Batch insert (still fires on-create triggers — "
                        "different from `ingest_bulk_feed` which "
                        "intentionally bypasses them)."},
    ],
}


_UPDATE_RECORD: dict[str, Any] = {
    "summary": "Patch fields on an existing record.",
    "args": [
        {"name": "module", "required": True, "kind": "string"},
        {"name": "resource", "required": True, "kind": "dict"},
        {"name": "operation", "required": False, "kind": "enum"},
        {"name": "fieldOperation", "required": False, "kind": "dict"},
    ],
}


_INGEST_BULK_FEED: dict[str, Any] = {
    "summary": "High-volume threat-feed insertion via "
               "`/api/ingest-feeds/`. **Bypasses on-create playbook "
               "triggers** (intentional; do NOT use for alerts/"
               "incidents where triggers must fire — use `create_record` "
               "with `__bulk: true` for those).",
    "args": [
        {"name": "module", "required": True, "kind": "string",
         "description": "Typically `threat_intel_feeds` or `indicators`."},
        {"name": "resource", "required": True, "kind": "dict|list[dict]"},
    ],
}


_WORKFLOW_REFERENCE: dict[str, Any] = {
    "summary": "Invoke another playbook as a sub-flow.",
    "args": [
        {"name": "target", "required": True, "kind": "string",
         "description": "Local playbook name in the same collection. "
                        "Compiler rewrites to `workflowReference` IRI."},
        {"name": "params", "required": False, "kind": "dict",
         "description": "Inputs handed to the sub-playbook."},
    ],
}


_DELAY: dict[str, Any] = {
    "summary": "Pause the playbook for a fixed duration.",
    "args": [
        {"name": "delay_value", "required": True, "kind": "number",
         "description": "Magnitude (paired with `delay_unit`)."},
        {"name": "delay_unit", "required": True, "kind": "enum",
         "description": "`seconds`, `minutes`, `hours`, `days`."},
    ],
}


_CODE_SNIPPET: dict[str, Any] = {
    "summary": "Run an inline Python snippet via FSR's CodeSnippet "
               "step type. Friendly form: `code:`. Compiles to a "
               "`code-snippet.python_inline_code_editor` connector call.",
    "args": [
        {"name": "code", "required": True, "kind": "string (Python)",
         "description": "Python source to execute."},
        {"name": "config", "required": False, "kind": "string"},
    ],
}


_START: dict[str, Any] = {
    "summary": "Manual trigger. With `module:` it becomes "
               "`cybersponse.post_create`-style record-bound; without, "
               "it's `cybersponse.abstract_trigger` (designer / pure "
               "manual button).",
    "args": [
        {"name": "module", "required": False, "kind": "string",
         "description": "If set, the trigger binds to record actions on "
                        "this module."},
        {"name": "title", "required": False, "kind": "string"},
        {"name": "params", "required": False, "kind": "dict",
         "description": "Schema for the playbook's input parameters."},
    ],
}


_STOP: dict[str, Any] = {
    "summary": "Terminal no-op. Compiles to `cyops_utilities.no_op` so "
               "every branch path has an explicit endpoint.",
    "args": [],
}


# Index keyed by friendly type. Aliases share the same entry.
STEP_ARGS_HELP: dict[str, dict[str, Any]] = {
    "manual_input": _MANUAL_INPUT,
    "decision": _DECISION,
    "connector": _CONNECTOR,
    "set_variable": _SET_VARIABLE,
    "find_record": _FIND_RECORD,
    "create_record": _CREATE_RECORD,
    "insert_record": _CREATE_RECORD,
    "update_record": _UPDATE_RECORD,
    "ingest_bulk_feed": _INGEST_BULK_FEED,
    "workflow_reference": _WORKFLOW_REFERENCE,
    "delay": _DELAY,
    "code_snippet": _CODE_SNIPPET,
    "start": _START,
    "start_on_create": _START,
    "start_on_update": _START,
    "stop": _STOP,
    "end": _STOP,
}


def get_help(step_type: str) -> dict[str, Any] | None:
    return STEP_ARGS_HELP.get(step_type)


def render_markdown(step_type: str) -> str | None:
    """Render the help entry as a Monaco-friendly markdown string."""
    spec = get_help(step_type)
    if not spec:
        return None
    out: list[str] = [f"### `{step_type}` — arguments", "", spec["summary"], ""]
    if spec.get("args"):
        # Group by mode if any arg carries one.
        modes: dict[str, list[dict]] = {}
        plain: list[dict] = []
        for a in spec["args"]:
            m = a.get("mode")
            if m:
                modes.setdefault(m, []).append(a)
            else:
                plain.append(a)
        if plain:
            out.append("**Common keys**")
            out.append("")
            for a in plain:
                req = "**required**" if a.get("required") else "optional"
                kind = a.get("kind", "")
                desc = a.get("description", "")
                out.append(f"- `{a['name']}` _{kind}_ · {req}"
                           + (f" — {desc}" if desc else ""))
            out.append("")
        for mode, items in modes.items():
            out.append(f"**{mode} mode**")
            out.append("")
            for a in items:
                req = "**required**" if a.get("required") else "optional"
                kind = a.get("kind", "")
                desc = a.get("description", "")
                out.append(f"- `{a['name']}` _{kind}_ · {req}"
                           + (f" — {desc}" if desc else ""))
            out.append("")
    if spec.get("examples"):
        out.append("**Examples**")
        out.append("")
        for ex in spec["examples"]:
            out.append("```yaml")
            out.append(ex)
            out.append("```")
            out.append("")
    return "\n".join(out).rstrip() + "\n"
