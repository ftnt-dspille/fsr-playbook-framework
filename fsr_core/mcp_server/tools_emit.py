"""Constrained-generation emitters for hot step shapes.

These tools take strict structured input (enforced by Anthropic's
`input_schema` on the wire — the model cannot send a malformed call)
and return the canonical YAML fragment for that step. The agent splices
the returned YAML into its draft instead of hand-writing the shape.

Why this exists: the validate→fix loop spends ~30% of its turns on
shape errors (missing required keys, wrong nesting, malformed decision
branches) that constrained generation makes literally impossible. See
`docs/plans/AGENT_LOOP_REFINEMENT_PLAN.md` §B.

Schema overrides for these tools live in
`web/backend/llm/tools.py::TOOL_SCHEMA_OVERRIDES`; the auto-from-signature
builder is too weak for nested-object validation. Keep the override and
the runtime check in this module in sync — the override is the wire
contract, the runtime check is the belt-and-suspenders for callers
(eval harness, tests) that bypass the LLM.
"""
from __future__ import annotations

import re
from typing import Any

from ._shared import mcp, _err, _validate_op_exists


# Step-name charset rule from system_prompt.md §"Hard rules" #2.
_NAME_RE = re.compile(r"^[A-Za-z0-9 _]+$")


def _bad_name(name: str) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return "must be a non-empty string"
    if not _NAME_RE.match(name):
        return ("must contain only letters, digits, spaces, and underscores "
                "(no hyphens, colons, em-dashes, parens, or '?')")
    return None


@mcp.tool()
def emit_decision_step(
    name: str,
    conditions: list[dict[str, Any]],
    default_branch: dict[str, Any],
) -> dict[str, Any]:
    """Emit a canonical `decision` step. Prefer this over hand-writing
    decision YAML — the schema is enforced, so malformed shapes
    (missing `default: true`, branches without `when`, etc.) cannot be
    produced.

    Args:
      name: step display name. Letters/digits/spaces/underscores only.
      conditions: ordered list of non-default branches. Each entry:
        {display: str, when: str (Jinja expression), next: str (target step name)}.
        Must have at least one entry.
      default_branch: the else branch. Shape: {display: str, next: str}.
        `default: true` is added by this tool — do NOT pass it.

    Returns: {ok: True, yaml: "<fenced YAML fragment>"} on success.
    On a runtime-check failure: {ok: False, code, message, suggestions}.
    """
    err = _bad_name(name)
    if err:
        return _err("invalid_step_name", f"name {err}",
                    suggestions=["pick a Title Case display string"])

    if not isinstance(conditions, list) or not conditions:
        return _err("empty_conditions",
                    "conditions must be a non-empty list",
                    suggestions=["add at least one {display, when, next} entry"])

    for i, c in enumerate(conditions):
        if not isinstance(c, dict):
            return _err("malformed_condition",
                        f"conditions[{i}] must be an object")
        missing = [k for k in ("display", "when", "next") if not c.get(k)]
        if missing:
            return _err("missing_condition_field",
                        f"conditions[{i}] missing: {missing}",
                        suggestions=["every condition needs display, when, next"])
        if "default" in c:
            return _err("default_in_condition",
                        (f"conditions[{i}] sets default — only the "
                         "default_branch carries `default: true`"))
        ne = _bad_name(c["next"])
        if ne:
            return _err("invalid_branch_target",
                        f"conditions[{i}].next: {ne}")

    if not isinstance(default_branch, dict):
        return _err("missing_default_branch",
                    "default_branch must be an object {display, next}")
    db_missing = [k for k in ("display", "next") if not default_branch.get(k)]
    if db_missing:
        return _err("missing_default_branch_field",
                    f"default_branch missing: {db_missing}")
    ne = _bad_name(default_branch["next"])
    if ne:
        return _err("invalid_branch_target", f"default_branch.next: {ne}")

    # Render. YAML emit is hand-rolled (not yaml.dump) so the output
    # exactly matches the canonical shape in system_prompt.md §3 —
    # key ordering, double-quoted `when:`, no flow style.
    lines: list[str] = []
    lines.append("- type: decision")
    lines.append(f"  name: {name}")
    lines.append("  conditions:")
    for c in conditions:
        lines.append(f"    - display: {c['display']}")
        # `when` is a Jinja expression; quote it so YAML doesn't try to
        # interpret braces, colons, or pipes as structure.
        when = c["when"].replace('"', '\\"')
        lines.append(f'      when: "{when}"')
        lines.append(f"      next: {c['next']}")
    lines.append(f"    - display: {default_branch['display']}")
    lines.append("      default: true")
    lines.append(f"      next: {default_branch['next']}")
    return {"ok": True, "yaml": "\n".join(lines) + "\n"}


# --- Widget card emitters --------------------------------------------------
#
# These are not playbook step emitters; they're conversation-flow events
# the agent emits to drive the widget UI (per
# `FSR_PLAYBOOK_BUILDER_CONNECTOR_CONTRACT.md`). Each tool validates its
# input and echoes it back; the connector's `_wire_transcript`
# post-processes the tool_use into a dedicated transcript event so the
# widget sees a `choice_card` / `action_card` / `manual_input` and the
# envelope's stop_reason becomes the matching `awaiting_*`.
#
# Behavior contract: when the agent calls one of these tools, the turn
# ends after the call. The connector truncates any further transcript
# events past the card so the widget always sees the card as the last
# event of the turn.


@mcp.tool()
def emit_choice_card(
    id: str,
    prompt: str,
    options: list[dict[str, Any]],
    multi: bool = False,
    min_select: int = 1,
    max_select: int | None = None,
) -> dict[str, Any]:
    """Emit a `choice_card` so the widget renders pickable chips and
    halts the turn until the user picks. Use this for branching
    decisions ("immediate action vs build a playbook", "which
    connector?", etc.) instead of asking in prose.

    `options` is a list of `{label, value, hint?}`. `value` is what the
    widget echoes back on resume — pick stable, machine-readable values."""
    if not isinstance(id, str) or not id.strip():
        return _err("missing_id", "id must be a non-empty string")
    if not isinstance(prompt, str) or not prompt.strip():
        return _err("missing_prompt", "prompt must be a non-empty string")
    if not isinstance(options, list) or len(options) < 2:
        return _err("too_few_options",
                    "options must be a list of at least 2 entries")
    seen_values: set[str] = set()
    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            return _err("bad_option", f"options[{i}] must be an object")
        for k in ("label", "value"):
            if not opt.get(k) or not isinstance(opt[k], str):
                return _err("bad_option",
                            f"options[{i}] missing string field {k!r}")
        if opt["value"] in seen_values:
            return _err("duplicate_value",
                        f"options[{i}].value duplicates an earlier entry")
        seen_values.add(opt["value"])
    if not isinstance(multi, bool):
        return _err("bad_multi", "multi must be boolean")
    if not isinstance(min_select, int) or min_select < 0:
        return _err("bad_min_select", "min_select must be a non-negative int")
    if max_select is not None:
        if not isinstance(max_select, int) or max_select < min_select:
            return _err("bad_max_select",
                        "max_select must be an int >= min_select")
    return {
        "ok": True,
        "card": {
            "type": "choice_card",
            "id": id,
            "prompt": prompt,
            "multi": multi,
            "min_select": min_select,
            "max_select": max_select,
            "options": options,
        },
    }


@mcp.tool()
def emit_action_card(
    id: str,
    connector: str,
    operation: str,
    summary: str,
    args: dict[str, Any],
    editable_fields: list[str],
) -> dict[str, Any]:
    """Emit an `action_card` so the widget renders an editable preview
    of a connector operation and halts the turn until the user confirms
    or cancels. On confirm, the widget calls chat_resume with the
    (possibly-edited) args and the agent runs the operation in the
    next turn."""
    for label, val in (("id", id), ("connector", connector),
                       ("operation", operation), ("summary", summary)):
        if not isinstance(val, str) or not val.strip():
            return _err("missing_field", f"{label} must be a non-empty string")
    if not isinstance(args, dict):
        return _err("bad_args", "args must be an object")
    if not isinstance(editable_fields, list) or not all(
            isinstance(f, str) for f in editable_fields):
        return _err("bad_editable_fields",
                    "editable_fields must be a list of strings")
    bad = [f for f in editable_fields if f not in args]
    if bad:
        return _err("editable_fields_not_in_args",
                    f"editable_fields not present in args: {bad}")
    # Don't render an approval card for a connector/op that doesn't exist —
    # the analyst would approve a phantom action that then fails at execute.
    # (No-op when the connector has no ops catalogued; see _validate_op_exists.)
    op_err = _validate_op_exists(connector, operation)
    if op_err is not None:
        return op_err
    return {
        "ok": True,
        "card": {
            "type": "action_card",
            "id": id,
            "connector": connector,
            "operation": operation,
            "summary": summary,
            "args": args,
            "editable_fields": editable_fields,
        },
    }


@mcp.tool()
def emit_manual_input(
    id: str,
    workflow_run_iri: str,
    question: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Emit a `manual_input` event so the widget renders a form for a
    paused playbook gate. `workflow_run_iri` ties the response back to
    the FortiSOAR workflow runtime; the widget submits via the
    connector's `respond_manual_input` operation, not `chat_resume`."""
    for label, val in (("id", id), ("workflow_run_iri", workflow_run_iri),
                       ("question", question)):
        if not isinstance(val, str) or not val.strip():
            return _err("missing_field", f"{label} must be a non-empty string")
    if not isinstance(fields, list) or not fields:
        return _err("no_fields",
                    "fields must be a non-empty list of {name, label, default?}")
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            return _err("bad_field", f"fields[{i}] must be an object")
        for k in ("name", "label"):
            if not f.get(k) or not isinstance(f[k], str):
                return _err("bad_field",
                            f"fields[{i}] missing string field {k!r}")
    return {
        "ok": True,
        "card": {
            "type": "manual_input",
            "id": id,
            "workflow_run_iri": workflow_run_iri,
            "question": question,
            "fields": fields,
        },
    }
