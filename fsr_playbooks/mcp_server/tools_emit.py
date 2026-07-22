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

from ._shared import mcp, _err, _validate_op_params


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
    # Use the SHARED grounding guarantee (offline store + live-definition
    # fallback when the store is un-synced), the same check run_op runs — so a
    # phantom op can't slip through here just because the connector's ops aren't
    # catalogued yet (the sess-uq31go5p live-triage failure). Fails open on any
    # live-lookup hiccup, so a transient network problem never blocks a real op.
    # Pass `args` so the SHARED grounding guarantee validates the argument
    # names too — against the live connector definition when the store is
    # un-synced — so a card with guessed/typo'd params can't reach the analyst
    # for a connector whose params aren't catalogued yet (the live half of the
    # sess-uq31go5p / mail_egress param-flail gap).
    from .tools_execution import validate_op_grounded
    op_err = validate_op_grounded(connector, operation, params=args)
    if op_err is not None:
        return op_err
    # Offline param validation (decisive when params ARE catalogued — select
    # options, types, required). The live fallback above covers the un-synced
    # case; this covers the synced one. Don't render a card whose args are
    # incomplete/invalid — the analyst would approve it only for it to fail
    # post-approval at execute.
    param_err = _validate_op_params(connector, operation, args)
    if param_err is not None:
        return param_err
    # Record the staged action into the session trace so a later trace-built
    # playbook AUTOMATES it — the analyst was offered this containment but it
    # was never executed, so `run_op` never recorded it and the trace compiler
    # had nothing to replay (the `action_coverage` gap). No-op when no trace is
    # active (studio/tests) or the same op is already on the trace. The compiler
    # gates it behind a malicious-verdict decision (`insert_containment_guard`).
    from ..agent.skill_trace import record_staged_action
    record_staged_action(connector, operation, args)
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
def emit_capability_gap_card(
    id: str,
    missing: str,
    why: str,
    fix_steps: list[str],
    resume: dict[str, Any],
    tips: list[dict[str, Any]] | None = None,
    alternatives: list[dict[str, Any]] | None = None,
    docs_url: str | None = None,
) -> dict[str, Any]:
    """Emit a `capability_gap` card when the instance CAN'T do what the
    investigation needs (e.g. no IP-containment connector is configured) —
    so the analyst is never left at a dead end. The card states what's
    missing, why, the concrete steps to enable it, optional automation
    tips, and a RESUME button that re-runs the blocked step after the
    analyst fixes the gap. Prefer this over a bare `emit_choice_card` for
    any missing-capability / not-configured situation.

    Args:
      id: stable card id; echoed on resume.
      missing: the capability the investigation needs, in plain English
        (e.g. "IP containment / block").
      why: one line on why it's unavailable here (e.g. "no tier-3 block_ip
        operation on any configured connector").
      fix_steps: ordered, concrete steps the analyst can take to enable it
        (e.g. ["Configure the fortigate-firewall connector under Settings →
        Connectors", "Grant it firewall-policy write access"]). At least one.
      resume: the re-check button — {label, value}. On click the widget
        resumes the turn echoing `value`; the agent re-runs the blocked
        discovery (e.g. find_containment_actions) and continues. `value`
        must be machine-readable and distinct from any alternative value.
      tips: optional automation/UX recommendations — list of {text, hint?}.
        Use for "how to make this work better next time" guidance (e.g.
        keeping a response connector configured, granting probe access).
      alternatives: optional manual fallbacks the analyst can pick instead
        of fixing the gap now — list of {label, value, hint?} (e.g.
        "Escalate to T2", "Document & close"). Same resume semantics as a
        choice_card option. Values must be unique across resume+alternatives.
      docs_url: optional link to setup/configuration docs.

    Returns {ok: True, card:{type:"capability_gap", ...}} on success, else
    {ok: False, code, message}."""
    for label, val in (("id", id), ("missing", missing), ("why", why)):
        if not isinstance(val, str) or not val.strip():
            return _err("missing_field", f"{label} must be a non-empty string")
    if not isinstance(fix_steps, list) or not fix_steps or not all(
            isinstance(s, str) and s.strip() for s in fix_steps):
        return _err("bad_fix_steps",
                    "fix_steps must be a non-empty list of non-empty strings",
                    suggestions=["give at least one concrete step, e.g. "
                                 "'Configure the <name> connector'"])
    if not isinstance(resume, dict):
        return _err("bad_resume", "resume must be an object {label, value}")
    seen_values: set[str] = set()
    for k in ("label", "value"):
        if not resume.get(k) or not isinstance(resume[k], str):
            return _err("bad_resume", f"resume missing string field {k!r}")
    seen_values.add(resume["value"])

    if tips is not None:
        if not isinstance(tips, list):
            return _err("bad_tips", "tips must be a list of {text, hint?}")
        for i, t in enumerate(tips):
            if not isinstance(t, dict) or not t.get("text") or not isinstance(
                    t["text"], str):
                return _err("bad_tips", f"tips[{i}] needs a string 'text' field")

    if alternatives is not None:
        if not isinstance(alternatives, list):
            return _err("bad_alternatives",
                        "alternatives must be a list of {label, value, hint?}")
        for i, a in enumerate(alternatives):
            if not isinstance(a, dict):
                return _err("bad_alternatives",
                            f"alternatives[{i}] must be an object")
            for k in ("label", "value"):
                if not a.get(k) or not isinstance(a[k], str):
                    return _err("bad_alternatives",
                                f"alternatives[{i}] missing string field {k!r}")
            if a["value"] in seen_values:
                return _err("duplicate_value",
                            f"alternatives[{i}].value duplicates resume or an "
                            f"earlier alternative")
            seen_values.add(a["value"])

    card: dict[str, Any] = {
        "type": "capability_gap",
        "id": id,
        "missing": missing,
        "why": why,
        "fix_steps": fix_steps,
        "resume": {"label": resume["label"], "value": resume["value"]},
    }
    if tips:
        card["tips"] = tips
    if alternatives:
        card["alternatives"] = alternatives
    if docs_url:
        card["docs_url"] = docs_url
    return {"ok": True, "card": card}


@mcp.tool()
def emit_playbook_offer(
    id: str,
    summary: str,
    title_suggestion: str | None = None,
    editable_title: bool = True,
    yaml: str | None = None,
) -> dict[str, Any]:
    """Emit a `playbook_offer` card offering the analyst a one-click
    "Save as Playbook" CTA (contract §5, `awaiting_playbook_offer`).

    Two modes, one terminal affordance:

    - **Triage close (no `yaml`).** Call at the CLOSE of a triage session,
      after you have approved & executed at least one containment action.
      The card's draft body is compiled from the recorded session trace.
      Only call this when the triage is substantially complete; do NOT
      offer after every single action.
    - **Direct build (`yaml=<final YAML>`).** A hand-authored build turn has
      no trace; once `verify_playbook` passes, calling this with the final
      validated YAML is the MANDATORY terminal action — the card carries the
      YAML and accept compiles + pushes it deterministically. Never end a
      successful build turn by telling the user to call `push_playbook`
      themselves.

    You supply only the conversational framing (`summary`, optional
    `title_suggestion`). The card's reviewable-draft body — the per-step
    `ops_summary` with plain-English wiring labels, verify badges, and the
    `draft_steps` tree — is built HERE from the recorded session trace via
    the deterministic skill compiler. You do NOT hand-write step wiring;
    that is exactly the guess-the-jinja failure mode this flow removes.

    Args:
      id: stable card id; echoed back on accept/decline.
      summary: the body text the analyst reads (e.g. "I've blocked the C2 IP
        and quarantined the host. Save this as a re-runnable playbook?").
      title_suggestion: optional pre-filled playbook name the analyst may
        edit before accepting.
      editable_title: whether the widget shows an editable title field
        (default True).

    Returns {ok: True, card:{type:"playbook_offer", ...}} on success, or
    {ok: False, code, message} — notably `empty_trace` when no action was
    recorded (there is nothing to offer; do not call it then). The card always
    carries `has_mutating_action` (bool); when the trace is purely read-only it
    also carries an `advisory` note so the analyst can decide — the offer is
    never refused for lacking a containment step."""
    for label, val in (("id", id), ("summary", summary)):
        if not isinstance(val, str) or not val.strip():
            return _err("missing_field", f"{label} must be a non-empty string")

    if yaml is not None:
        return _offer_from_yaml(id, summary, yaml,
                                title_suggestion=title_suggestion,
                                editable_title=editable_title)

    from fsr_playbooks.agent import skill_trace as _skill_trace
    from fsr_playbooks.agent.skill_trace import SkillTrace
    from fsr_playbooks.compiler import skill_compiler as _sc
    from fsr_playbooks.compiler import skill_verify as _sv

    trace = _skill_trace.get_active_trace() or SkillTrace()
    if len(trace) == 0:
        return _err(
            "empty_trace",
            "no recorded actions to offer as a playbook",
            suggestions=["offer only after >=1 action was approved & executed"],
        )

    compiled = _sv.compile_and_verify(trace)
    draft = _sc.summarize_for_offer(trace, compiled)
    if not draft["ops_summary"]:
        return _err(
            "empty_trace",
            "the recorded actions did not map to any known skill — nothing to "
            "offer",
        )

    # A2 advisory (NOT a gate): the offer is never refused for a read-only
    # trace. We classify each recorded op (method-aware — a GET
    # `execute_api_request` is read-only, a POST is not) and add an advisory
    # that keeps a human in the loop:
    #   • all ops provably safe → "only read-only lookups" note.
    #   • some op `unknown` (can't prove read-only, not clearly destructive) →
    #     name them so the analyst reviews before saving, rather than silently
    #     baking a possible state-change into the playbook.
    # A destructive op sets has_mutating_action (the load-bearing flag).
    from .tools_discovery import _op_risk
    risked = [
        (str(c.resolved_inputs.get("operation") or ""),
         _op_risk(str(c.resolved_inputs.get("operation") or ""), None,
                  c.resolved_inputs))
        for c in trace.calls
    ]
    risks = [r for _, r in risked]
    has_mutating = any(r == "destructive" for r in risks)
    all_read_only = bool(risks) and all(r == "safe" for r in risks)
    # Dedupe unknown op names, preserve first-seen order.
    unknown_ops: list[str] = []
    for name, r in risked:
        if r == "unknown" and name and name not in unknown_ops:
            unknown_ops.append(name)

    card: dict[str, Any] = {
        "type": "playbook_offer",
        "id": id,
        "summary": summary,
        "ops_summary": draft["ops_summary"],
        "editable_title": bool(editable_title),
        "has_mutating_action": has_mutating,
    }
    if all_read_only:
        card["advisory"] = (
            "This triage recorded only read-only lookups — saving it produces "
            "an enrichment playbook with no containment step. Save it if that "
            "is what you want."
        )
    elif unknown_ops and not has_mutating:
        names = ", ".join(unknown_ops)
        card["advisory"] = (
            "Before saving, confirm these step(s) are safe to re-run "
            f"automatically: {names}. They aren't recognized as read-only "
            "lookups, so they may change state — review them in the draft below."
        )
        card["needs_review_ops"] = unknown_ops
    if title_suggestion and title_suggestion.strip():
        card["title_suggestion"] = title_suggestion.strip()
    if draft.get("draft_steps"):
        card["draft_steps"] = draft["draft_steps"]
    return {"ok": True, "card": card}


@mcp.tool()
def emit_patch_proposal(
    id: str,
    title: str,
    before_yaml: str,
    after_yaml: str,
    rationale: str | None = None,
    target_step: str | None = None,
    target_path: str | None = None,
    tier: int | None = None,
    reply_tool: str | None = None,
) -> dict[str, Any]:
    """Emit a `patch_proposal` card: a value-level fix the agent proposes for
    ONE step/field of the open playbook, shown in chat as a before→after diff
    the analyst accepts or rejects inline. Use this — not a prose "you could
    change X to Y" — whenever you want to offer a concrete, one-click edit to
    the playbook the user has open (e.g. correct a jinja expression, fix a
    wrong arg value, tighten a condition). The turn HALTS on the card; on accept
    the widget resumes and the connector applies the fix via `reply_tool`.

    Distinct from the YAML pane's whole-document "Check & fix" panel (driven by
    validate_yaml's `corrected_yaml`): this is a targeted, agent-initiated CHAT
    card scoped to one step/field.

    Args:
      id: stable card id; echoed on resume.
      title: one-line plain-English summary of the fix (e.g. "Fix the IP jinja
        in step 'Block source'").
      before_yaml: the current snippet being replaced (the step/field as it is
        now). Shown as the "before" side of the diff. Keep it minimal — just the
        lines that change — so the diff is readable.
      after_yaml: the proposed replacement snippet. Shown as "after".
      rationale: optional one line on WHY (e.g. "records[0] is empty on a
        record-action trigger; use vars.input.records[0]").
      target_step: optional step display name the patch targets (for the card's
        header).
      target_path: optional dotted path within the step (e.g.
        "arguments.ip") for precise attribution.
      tier: optional approval tier; >=3 gates the Apply button behind step-up,
        mirroring action_card. Defaults to 0 (no step-up).
      reply_tool: the tool the connector invokes on accept. Defaults to
        "apply_patch".

    Returns {ok: True, card:{type:"patch_proposal", ...}} on success, else
    {ok: False, code, message}."""
    for label, val in (("id", id), ("title", title),
                       ("before_yaml", before_yaml), ("after_yaml", after_yaml)):
        if not isinstance(val, str) or not val.strip():
            return _err("missing_field", f"{label} must be a non-empty string")
    if before_yaml.strip() == after_yaml.strip():
        return _err("noop_patch",
                    "before_yaml and after_yaml are identical — there is "
                    "nothing to change. Only propose a patch that alters the "
                    "playbook.")
    if tier is not None and (not isinstance(tier, int) or tier < 0):
        return _err("bad_tier", "tier must be a non-negative integer")
    card: dict[str, Any] = {
        "type": "patch_proposal",
        "proposal_id": id,
        "title": title.strip(),
        "before_yaml": before_yaml,
        "after_yaml": after_yaml,
        "tier": tier if isinstance(tier, int) else 0,
        "reply_tool": (reply_tool or "apply_patch"),
    }
    if isinstance(rationale, str) and rationale.strip():
        card["rationale"] = rationale.strip()
    target: dict[str, str] = {}
    if isinstance(target_step, str) and target_step.strip():
        target["step"] = target_step.strip()
    if isinstance(target_path, str) and target_path.strip():
        target["path"] = target_path.strip()
    if target:
        card["target"] = target
    return {"ok": True, "card": card}


def _offer_from_yaml(id: str, summary: str, yaml_text: str, *,
                     title_suggestion: str | None,
                     editable_title: bool) -> dict[str, Any]:
    """Direct-build mode of `emit_playbook_offer` (§A): the card carries the
    final validated YAML; accept compiles + pushes THAT text deterministically
    (no trace involved). The steps list is a display summary parsed from the
    YAML — best-effort, never a gate (the YAML already passed validate/verify
    before the model offers it)."""
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return _err("missing_field", "yaml must be a non-empty string")

    ops_summary: list[dict[str, Any]] = []
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text)
        pbs = (doc or {}).get("playbooks") or []
        steps = (pbs[0] or {}).get("steps") or [] if pbs else []
        for s in steps:
            if isinstance(s, dict) and s.get("name"):
                ops_summary.append({"label": str(s["name"]),
                                    "step_type": str(s.get("type") or "")})
    except Exception:  # noqa: BLE001 — display summary only, never block
        ops_summary = []

    card: dict[str, Any] = {
        "type": "playbook_offer",
        "id": id,
        "summary": summary,
        "ops_summary": ops_summary,
        "editable_title": bool(editable_title),
        # Hand-authored YAML: step risk isn't trace-classified, so flag for
        # review rather than asserting safety either way.
        "has_mutating_action": False,
        "advisory": ("Built from the YAML above (not a recorded triage trace) "
                     "— review the steps before saving."),
        "final_yaml": yaml_text,
    }
    if title_suggestion and title_suggestion.strip():
        card["title_suggestion"] = title_suggestion.strip()
    return {"ok": True, "card": card}


@mcp.tool()
def emit_enhancement_offer(
    id: str,
    summary: str,
    verified_id: str,
) -> dict[str, Any]:
    """Apply a verified edit to the playbook the analyst has OPEN. This is the
    MANDATORY terminal action of an enhance turn — the only thing that makes an
    edit real.

    Enhance mode's counterpart to `emit_playbook_offer`. That one CREATES a new
    playbook; this one UPDATES the open one in place (the connector routes
    accept through the designer's own snapshot-then-PUT path, so the analyst
    keeps a restore point in the Versions tab).

    **You do not pass YAML.** You pass the `verified_id` that
    `verify_enhancement` handed back when it returned `ready_to_push: True`,
    and the card carries those exact bytes. This is deliberate and it is the
    whole point of the tool: a live session verified one document and then
    re-typed a subtly different one into chat three times, the widget scraped
    the last prose fence, and the analyst's playbook got YAML no gate had ever
    seen — while the transcript showed a green verify. Removing the parameter
    removes the failure mode.

    So the enhance turn is exactly:
        verify_enhancement(before, after, user_message)  ->  verified_id
        emit_enhancement_offer(id, summary, verified_id) ->  card, turn halts

    Never end an enhance turn by printing the revised playbook and hoping the
    analyst pastes or saves it. If the verify did not pass, do not call this —
    fix the findings and re-verify.

    Args:
      id: stable card id; echoed back on accept/decline.
      summary: what the analyst reads — one or two plain-English lines on what
        this edit changes and why (e.g. "Adds a manual-input approval gate
        before the block, wired Confirm -> Block IP and Cancel -> Manual
        Review."). Describe the change, not the YAML.
      verified_id: the handle from the passing `verify_enhancement` call.

    Returns {ok: True, card:{type:"enhancement_offer", ...}} — the card carries
    `final_yaml` (the verified bytes), `diff_summary`, and any non-blocking
    `warnings` so the analyst reviews them before applying. On a bad handle
    returns {ok: False, code: "unknown_verified_id"} — re-run
    verify_enhancement and use the fresh id; do NOT work around it by
    presenting YAML in chat."""
    for label, val in (("id", id), ("summary", summary),
                       ("verified_id", verified_id)):
        if not isinstance(val, str) or not val.strip():
            return _err("missing_field", f"{label} must be a non-empty string")

    from . import _verified_yaml
    entry = _verified_yaml.lookup(verified_id.strip())
    if entry is None:
        return _err(
            "unknown_verified_id",
            f"no verified enhancement is registered under {verified_id!r}. A "
            "verified_id is only valid within the turn that produced it.",
            suggestions=[
                "call verify_enhancement(before_yaml, after_yaml, user_message) "
                "again and pass the verified_id it returns",
                "do NOT fall back to pasting the YAML into your reply — the "
                "analyst's playbook is only updated through this card",
            ],
        )

    yaml_text = entry["yaml"]
    ops_summary: list[dict[str, Any]] = []
    try:
        import yaml as _yaml
        doc = _yaml.safe_load(yaml_text)
        pbs = (doc or {}).get("playbooks") or []
        steps = (pbs[0] or {}).get("steps") or [] if pbs else []
        for s in steps:
            if isinstance(s, dict) and s.get("name"):
                ops_summary.append({"label": str(s["name"]),
                                    "step_type": str(s.get("type") or "")})
    except Exception:  # noqa: BLE001 — display summary only, never block
        ops_summary = []

    diff = entry.get("diff_summary") or {}
    card: dict[str, Any] = {
        "type": "enhancement_offer",
        "id": id,
        "summary": summary,
        "verified_id": verified_id.strip(),
        "final_yaml": yaml_text,
        "ops_summary": ops_summary,
        "diff_summary": diff,
        "steps_added": list(diff.get("steps_added") or []),
        "steps_removed": list(diff.get("steps_removed") or []),
        "steps_modified": list(diff.get("steps_modified") or []),
    }
    # Non-blocking findings still reach the human. verify_enhancement lets
    # warnings through to ready_to_push, so this card is the last place an
    # analyst can see "this will compile but the connector will reject it at
    # runtime" before it becomes their saved playbook.
    warnings = entry.get("warnings") or []
    if warnings:
        card["warnings"] = warnings
    return {"ok": True, "card": card}


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
