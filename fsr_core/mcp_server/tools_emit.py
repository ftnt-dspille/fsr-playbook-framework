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

from ._shared import mcp, _err


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
