"""Constrained-generation emitters for hot step shapes.

These tools take strict structured input (enforced by Anthropic's
`input_schema` on the wire -- the model cannot send a malformed call)
and return the canonical YAML fragment for that step. The agent splices
the returned YAML into its draft instead of hand-writing the shape.

Why this exists: the validate→fix loop spends ~30% of its turns on
shape errors (missing required keys, wrong nesting, malformed decision
branches) that constrained generation makes literally impossible. See
`docs/plans/AGENT_LOOP_REFINEMENT_PLAN.md` §B.

Schema overrides for these tools live in
`web/backend/llm/tools.py::TOOL_SCHEMA_OVERRIDES`; the auto-from-signature
builder is too weak for nested-object validation. Keep the override and
the runtime check in this module in sync -- the override is the wire
contract, the runtime check is the belt-and-suspenders for callers
(eval harness, tests) that bypass the LLM.
"""
from __future__ import annotations

import re
from typing import Any

from ._shared import (
    _err,
    _validate_op_params,
    get_grounded_yaml,
    load_yaml_text,
    mcp,
)

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
    decision YAML -- the schema is enforced, so malformed shapes
    (missing `default: true`, branches without `when`, etc.) cannot be
    produced.

    Args:
      name: step display name. Letters/digits/spaces/underscores only.
      conditions: ordered list of non-default branches. Each entry:
        {display: str, when: str (Jinja expression), next: str (target step name)}.
        Must have at least one entry.
      default_branch: the else branch. Shape: {display: str, next: str}.
        `default: true` is added by this tool -- do NOT pass it.

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
                        (f"conditions[{i}] sets default -- only the "
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
    # exactly matches the canonical shape in system_prompt.md §3 --
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
    allow_text: bool = False,
) -> dict[str, Any]:
    """Emit a `choice_card` so the widget renders pickable chips and
    halts the turn until the user picks. Use this for branching
    decisions ("immediate action vs build a playbook", "which
    connector?", etc.) instead of asking in prose.

    `options` is a list of `{label, value, hint?}`. `value` is what the
    widget echoes back on resume -- pick stable, machine-readable values.

    `allow_text=True` adds a text box under the chips so the analyst can
    answer in their own words instead; the typed text comes back as the
    value. Use it for open questions ("what should this playbook do?") where
    the options are only starting points. Leave it off for a real fork."""
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
    if not isinstance(allow_text, bool):
        return _err("bad_allow_text", "allow_text must be boolean")
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
            **({"allow_text": True} if allow_text else {}),
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
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Emit an `action_card` so the widget renders an editable preview
    of a connector operation and halts the turn until the user confirms
    or cancels. On confirm, the widget calls chat_resume with the
    (possibly-edited) args and the agent runs the operation in the
    next turn.

    `requested_by` is declared intent consumed by the hunt-floor guard
    upstream (`_loop_helpers.TriageDiscipline`), not by the card: an
    analyst-ordered containment stages without first clearing the
    investigation floor. Accepted-and-ignored here so the advertised
    schema and the registered signature can't drift -- an arg the model
    is told it may send must not TypeError at dispatch."""
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
        # Say what to DO, not just what is wrong. The model's intent when it
        # lists a field it did not fill is "let the analyst supply this one",
        # and the widget cannot render an editable field it has no value for.
        # The terse form of this message cost a whole extra tool call on three
        # of the five investigation fixtures in run 20260813T211826Z -- the
        # agent re-emitted the identical card with the field dropped. Both
        # remedies are legitimate; naming them makes the retry unnecessary.
        # ...but "add it to args" is only legitimate for a name the operation
        # ACCEPTS. Offering it unconditionally contradicts the param validator
        # below, and the model oscillates between the two errors: measured on
        # contain_block_ip_direct (run 20260815T152033Z) as up to FIVE
        # emit_action_card attempts against a 10-call budget --
        #   add vdom+ngfw_mode -> bad_params (ngfw_mode is not a param)
        #   -> drop both       -> editable_fields_not_in_args -> ...
        # So split the names by what the op actually takes.
        #
        # For a plain optional param there is only ONE sensible outcome and the
        # model already expressed it by listing the field: render it blank and
        # editable so the analyst can fill it. Making that a round trip is a
        # toll on the approval gate itself -- deterministic, once per card,
        # paid on every containment. So DO it instead of asking: prefill "".
        # The error is reserved for the cases where the blank is genuinely
        # wrong and only the model can choose (a select, a required param) or
        # where honouring the field is impossible (not a param at all).
        from ._shared import op_param_facts
        known = op_param_facts(connector, operation)
        healed, removable, selects, required = [], [], {}, []
        for f in bad:
            fact = (known or {}).get(f)
            if known is None or (fact and not fact["options"]
                                 and not fact["required"]):
                healed.append(f)
            elif fact is None:
                removable.append(f)
            elif fact["options"]:
                selects[f] = fact["options"]
            else:
                required.append(f)
        parts = []
        for f, opts in selects.items():
            parts.append(
                f"'{f}' is a select and does not accept a blank value -- "
                f"either add it to args as one of {opts}, or remove it from "
                f"editable_fields")
        if required:
            parts.append(
                f"{required} is required by '{operation}', so it cannot be "
                f"left blank -- add it to args with a real value")
        if removable:
            parts.append(
                f"remove {removable} from editable_fields -- "
                f"'{operation}' on '{connector}' has no such parameter, so "
                f"adding it to args will be rejected as an invalid argument")
        if parts:
            still_bad = list(selects) + required + removable
            return _err("editable_fields_not_in_args",
                        f"editable_fields not present in args: {still_bad}. "
                        + "; ".join(parts) + ".")
        # Only blanks left to fill: heal and carry on. `args` is the model's
        # dict, so copy rather than mutate its caller-visible object.
        args = {**args, **{f: "" for f in healed}}
    # Don't render an approval card for a connector/op that doesn't exist --
    # the analyst would approve a phantom action that then fails at execute.
    # Use the SHARED grounding guarantee (offline store + live-definition
    # fallback when the store is un-synced), the same check run_op runs -- so a
    # phantom op can't slip through here just because the connector's ops aren't
    # catalogued yet (the sess-uq31go5p live-triage failure). Fails open on any
    # live-lookup hiccup, so a transient network problem never blocks a real op.
    # Pass `args` so the SHARED grounding guarantee validates the argument
    # names too -- against the live connector definition when the store is
    # un-synced -- so a card with guessed/typo'd params can't reach the analyst
    # for a connector whose params aren't catalogued yet (the live half of the
    # sess-uq31go5p / mail_egress param-flail gap).
    from .tools_execution import validate_op_grounded
    op_err = validate_op_grounded(connector, operation, params=args)
    if op_err is not None:
        return op_err
    # Offline param validation (decisive when params ARE catalogued -- select
    # options, types, required). The live fallback above covers the un-synced
    # case; this covers the synced one. Don't render a card whose args are
    # incomplete/invalid -- the analyst would approve it only for it to fail
    # post-approval at execute.
    param_err = _validate_op_params(connector, operation, args)
    if param_err is not None:
        return param_err
    # Configured-ness check: emit_action_card is triage-only, so a live box is
    # always available in production. An op that exists in the catalog but has
    # no active configuration on this instance cannot run once approved -- the
    # analyst would say yes and execution would fail. Catch it here (before the
    # card renders) instead of after approval. Fails open on any preflight
    # hiccup (transient network, no live target, box unreachable) so a real op
    # is never false-rejected.
    try:
        from .tools_execution import _live_client_for_grounding, _preflight_connector
        _client = _live_client_for_grounding()
        if _client is not None:
            cfg_err = _preflight_connector(_client, connector)
            if cfg_err is not None:
                return cfg_err
    except Exception:
        pass  # fail open -- never block a real op on a preflight hiccup
    # Record the staged action into the session trace so a later trace-built
    # playbook AUTOMATES it -- the analyst was offered this containment but it
    # was never executed, so `run_op` never recorded it and the trace compiler
    # had nothing to replay (the `action_coverage` gap). No-op when no trace is
    # active (studio/tests) or the same op is already on the trace. The compiler
    # gates it behind a malicious-verdict decision (`insert_containment_guard`).
    from ..agent.skill_trace import record_staged_action
    record_staged_action(connector, operation, args)
    card: dict[str, Any] = {
        "type": "action_card",
        "id": id,
        "connector": connector,
        "operation": operation,
        "summary": summary,
        "args": args,
        "editable_fields": editable_fields,
    }
    # State the branch, don't just imply it. For a discriminated op (fortigate
    # `block_ip_new` takes `ip_addresses` under `method: Quarantine Based` and
    # `ip_block_policy` under `Policy Based`) the validator resolved the active
    # branch and discarded it, so the analyst saw a set of fields with nothing
    # saying WHICH branch made them the right fields -- and the wrong branch is
    # a silent no-op reported as Success. Annotation only: never blocks a card.
    from ._shared import op_branch_for
    try:
        branch = op_branch_for(connector, operation, args)
    except Exception:  # noqa: BLE001
        branch = []
    if branch:
        card["branch"] = branch
    return {"ok": True, "card": card}


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
    investigation needs (e.g. no IP-containment connector is configured) --
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
      resume: the re-check button -- {label, value}. On click the widget
        resumes the turn echoing `value`; the agent re-runs the blocked
        discovery (e.g. find_containment_actions) and continues. `value`
        must be machine-readable and distinct from any alternative value.
      tips: optional automation/UX recommendations -- list of {text, hint?}.
        Use for "how to make this work better next time" guidance (e.g.
        keeping a response connector configured, granting probe access).
      alternatives: optional manual fallbacks the analyst can pick instead
        of fixing the gap now -- list of {label, value, hint?} (e.g.
        "Escalate to T2", "Document & close"). Same resume semantics as a
        choice_card option. Values must be unique across resume+alternatives.
      docs_url: optional link to setup/configuration docs.

    Returns {ok: True, card:{type:"capability_gap", ...}} on success, else
    {ok: False, code, message}."""
    # Every problem in ONE refusal, like emit_verdict: reporting the first only
    # cost 4-5 rounds per card live (bad_payload -> bad_resume -> bad_tips ->
    # bad_alternatives), each a full LLM round.
    problems: list[tuple[str, str]] = []

    def bad(code: str, message: str) -> None:
        problems.append((code, message))

    for label, val in (("id", id), ("missing", missing), ("why", why)):
        if not isinstance(val, str) or not val.strip():
            bad("missing_field", f"{label} must be a non-empty string")
    if not isinstance(fix_steps, list) or not fix_steps or not all(
            isinstance(s, str) and s.strip() for s in fix_steps):
        bad("bad_fix_steps",
            "fix_steps must be a non-empty list of non-empty strings, e.g. "
            "'Configure the <name> connector'")
    seen_values: set[str] = set()
    if not isinstance(resume, dict):
        bad("bad_resume", "resume must be an object {label, value}")
    else:
        for k in ("label", "value"):
            if not resume.get(k) or not isinstance(resume[k], str):
                bad("bad_resume", f"resume missing string field {k!r}")
        if isinstance(resume.get("value"), str):
            seen_values.add(resume["value"])

    if tips is not None:
        if not isinstance(tips, list):
            bad("bad_tips", "tips must be a list of {text, hint?}")
        else:
            for i, t in enumerate(tips):
                if not isinstance(t, dict) or not t.get("text") or not isinstance(
                        t["text"], str):
                    bad("bad_tips", f"tips[{i}] needs a string 'text' field")

    if alternatives is not None:
        if not isinstance(alternatives, list):
            bad("bad_alternatives",
                "alternatives must be a list of {label, value, hint?}")
        else:
            for i, a in enumerate(alternatives):
                if not isinstance(a, dict):
                    bad("bad_alternatives", f"alternatives[{i}] must be an object")
                    continue
                ok = True
                for k in ("label", "value"):
                    if not a.get(k) or not isinstance(a[k], str):
                        bad("bad_alternatives",
                            f"alternatives[{i}] missing string field {k!r}")
                        ok = False
                if ok and a["value"] in seen_values:
                    bad("duplicate_value",
                        f"alternatives[{i}].value duplicates resume or an "
                        f"earlier alternative")
                if ok:
                    seen_values.add(a["value"])

    if problems:
        code, message = problems[0]
        if len(problems) > 1:
            message = (f"{len(problems)} problems -- fix all of them in one retry: "
                       + "; ".join(f"({n}) {m}" for n, (_, m)
                                   in enumerate(problems, 1)))
        return _err(code, message,
                    problems=[{"code": c, "message": m} for c, m in problems])

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
    """CREATE a NEW playbook -- the MANDATORY terminal action of a build turn.
    Call this to deliver any playbook that does not exist yet, as soon as
    `verify_playbook` returns `ready_to_push=True`. Nothing you build is real
    until this runs: a build turn that ends in prose, or that prints YAML at
    the analyst, has delivered nothing -- do not narrate the result instead,
    and never tell the analyst to run `push_playbook` themselves. NOT for
    editing a playbook the analyst already has open; that is
    `emit_enhancement_offer`. The test is whether the playbook exists yet --
    new one → this tool, changing an existing one → that one.

    (Emits a `playbook_offer` card with a one-click "Save as Playbook" CTA;
    contract §5, `awaiting_playbook_offer`.)

    Two modes, one terminal affordance:

    - **Triage close (no `yaml`).** Call at the CLOSE of a triage session,
      after you have approved & executed at least one containment action.
      The card's draft body is compiled from the recorded session trace.
      Only call this when the triage is substantially complete; do NOT
      offer after every single action.
    - **Direct build (`yaml=<final YAML>`).** A hand-authored build turn has
      no trace; once `verify_playbook` passes, calling this with the final
      validated YAML is the MANDATORY terminal action -- the card carries the
      YAML and accept compiles + pushes it deterministically. Never end a
      successful build turn by telling the user to call `push_playbook`
      themselves.

    You supply only the conversational framing (`summary`, optional
    `title_suggestion`). The card's reviewable-draft body -- the per-step
    `ops_summary` with plain-English wiring labels, verify badges, and the
    `draft_steps` tree -- is built HERE from the recorded session trace via
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
    {ok: False, code, message} -- notably `empty_trace` when no action was
    recorded (there is nothing to offer; do not call it then). The card always
    carries `has_mutating_action` (bool); when the trace is purely read-only it
    also carries an `advisory` note so the analyst can decide -- the offer is
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
            "the recorded actions did not map to any known skill -- nothing to "
            "offer",
        )

    # A2 advisory (NOT a gate): the offer is never refused for a read-only
    # trace. We classify each recorded op (method-aware -- a GET
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
            "This triage recorded only read-only lookups -- saving it produces "
            "an enrichment playbook with no containment step. Save it if that "
            "is what you want."
        )
    elif unknown_ops and not has_mutating:
        names = ", ".join(unknown_ops)
        card["advisory"] = (
            "Before saving, confirm these step(s) are safe to re-run "
            f"automatically: {names}. They aren't recognized as read-only "
            "lookups, so they may change state -- review them in the draft below."
        )
        card["needs_review_ops"] = unknown_ops
    if title_suggestion and title_suggestion.strip():
        card["title_suggestion"] = title_suggestion.strip()
    if draft.get("draft_steps"):
        card["draft_steps"] = draft["draft_steps"]
    return {"ok": True, "card": card}


_FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*\n(.*?)\n?\s*```\s*$", re.S)


def _unfence(text: str) -> str:
    """A snippet wrapped in a ```yaml fence is still the snippet."""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


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
    the analyst accepts or rejects inline. Use this -- not a prose "you could
    change X to Y" -- whenever you want to offer a concrete, one-click edit to
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
        now). Shown as the "before" side of the diff. Keep it minimal -- just the
        lines that change -- so the diff is readable.
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
    # Live (effect probe A5): both sides arrived wrapped in ```yaml fences,
    # which the card's diff would show as lines and no apply can match.
    before_yaml, after_yaml = _unfence(before_yaml), _unfence(after_yaml)
    # `tier` rides inside emit_card's payload, which the arg gate does not
    # type: "0" / 0.0 are the same tier, so take them (lossless).
    if isinstance(tier, str) and tier.strip().isdigit():
        tier = int(tier.strip())
    elif isinstance(tier, float) and tier.is_integer():
        tier = int(tier)
    if before_yaml.strip() == after_yaml.strip():
        return _err("noop_patch",
                    "before_yaml and after_yaml are identical -- there is "
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


_NON_ACTION_STEP_TYPES = frozenset({"end", "stop"})


def _has_action_steps(yaml_text: str) -> bool:
    """Whether any playbook in the YAML has a step other than its trigger and
    end markers. Unparseable YAML counts as having actions -- verify already
    judged it, and this check must not invent a second parse failure."""
    try:
        doc, _ = load_yaml_text(yaml_text, allow_grounding=False)
        pbs = (doc or {}).get("playbooks") or []
    except Exception:  # noqa: BLE001
        return True
    if not isinstance(pbs, list) or not pbs:
        return True
    for pb in pbs:
        for s in (pb or {}).get("steps") or [] if isinstance(pb, dict) else []:
            stype = str((s or {}).get("type") or "") if isinstance(s, dict) else ""
            if stype and not stype.startswith("start") and stype not in _NON_ACTION_STEP_TYPES:
                return True
    return False


def _step_names(yaml_text: str) -> list[str]:
    """Step `name:` values of the first playbook, in order. [] if unparseable."""
    try:
        doc, _ = load_yaml_text(yaml_text, allow_grounding=False)
        pbs = (doc or {}).get("playbooks") or []
        steps = (pbs[0] or {}).get("steps") or [] if pbs else []
        return [str(s["name"]) for s in steps
                if isinstance(s, dict) and s.get("name")]
    except Exception:  # noqa: BLE001 -- an unparseable offer fails elsewhere
        return []


def _guard_against_open_playbook(yaml_text: str) -> dict[str, Any] | None:
    """Refuse an offer that would overwrite the OPEN playbook, or lose its work.

    Two rules this tool's own docstring already states and never enforced. Both
    are checked against the grounded document -- the appliance's own copy of
    what the analyst has open -- so neither depends on classifying the turn,
    reading the analyst's words, or the model choosing to behave. That matters:
    the read-only tool slice is keyed on a structured `quick_action`, which only
    the widget's chips ever send. A free-typed ask, an MCP caller, or any other
    client reaches this tool with the full authoring surface, so the tool has to
    hold the line by itself.

    Measured live (session sess-n3d7p4a1, .159): "Explain what this playbook
    does, step by step, in plain language" ended at a tier-3 offer whose YAML
    had replaced the phishme-intelligence and carbonblack hunt steps with
    "Hunt Domains Placeholder" / "Hunt Files Placeholder", summarised as "ready
    for deployment". Approving it would have gutted a working playbook. The
    approval card was never the safeguard here -- it asks a human to confirm an
    action, not to diff two documents.

    Returns an error envelope to refuse, or None to allow.
    """
    open_yaml = get_grounded_yaml()
    if not open_yaml:
        return None                     # nothing open -- a genuine new build

    open_steps = _step_names(open_yaml)
    if not open_steps:
        return None                     # cannot read the open doc: do not block

    # RULE 1 -- new vs existing. "NOT for editing a playbook the analyst
    # already has open; that is emit_enhancement_offer. The test is whether the
    # playbook exists yet." Something IS open, so this is an edit.
    offered_steps = _step_names(yaml_text)
    lost = [n for n in open_steps if n not in set(offered_steps)]

    # RULE 2 -- loss. Named separately because it is the destructive half and
    # deserves its own words: a step the analyst has is missing from the offer.
    if lost:
        return _err(
            "offer_drops_open_steps",
            "This offer is missing "
            f"{len(lost)} step(s) that the OPEN playbook has: "
            + ", ".join(repr(n) for n in lost[:6])
            + ("..." if len(lost) > 6 else "")
            + ". Accepting it would delete them. If you meant to change the "
            "open playbook, use verify_enhancement + emit_card(card_type='enhancement_offer'), "
            "which edits it in place and keeps a restore point. If a step "
            "references a connector this box does not have, say so in prose -- "
            "replacing it with a placeholder loses the analyst's real step.",
            suggestions=[
                "emit_card(card_type='enhancement_offer', payload={verified_id: ..., summary: ...}) to edit the open playbook",
                "answer in prose if the analyst only asked you to explain",
            ],
        )
    return _err(
        "playbook_already_open",
        "A playbook is already open, so this is an edit, not a new playbook. "
        "emit_card(card_type='playbook_offer') CREATES; use verify_enhancement + "
        "emit_card(card_type='enhancement_offer') to UPDATE the open one in place.",
        suggestions=["emit_card(card_type='enhancement_offer', payload={id, summary, verified_id})"],
    )


def _yaml_ops_summary(yaml_text: str) -> list[dict[str, Any]]:
    """The offer card's step list, read from verified YAML. A connector step
    keeps its connector + operation: without them the card listed every step
    of a saved investigation as "siem_search (.)". Display only -- a parse
    failure yields an empty list, never a refusal."""
    out: list[dict[str, Any]] = []
    try:
        doc, _ = load_yaml_text(yaml_text)
        pbs = (doc or {}).get("playbooks") or []
        steps = (pbs[0] or {}).get("steps") or [] if pbs else []
        for s in steps:
            if not (isinstance(s, dict) and s.get("name")):
                continue
            entry = {"label": str(s["name"]), "step_type": str(s.get("type") or "")}
            for key in ("connector", "operation"):
                if s.get(key):
                    entry[key] = str(s[key])
            out.append(entry)
    except Exception:  # noqa: BLE001 -- display summary only, never block
        return []
    return out


def _offer_from_yaml(id: str, summary: str, yaml_text: str, *,
                     title_suggestion: str | None,
                     editable_title: bool) -> dict[str, Any]:
    """Direct-build mode of `emit_playbook_offer` (§A): the card carries the
    final validated YAML; accept compiles + pushes THAT text deterministically
    (no trace involved). The steps list is a display summary parsed from the
    YAML.

    The card verifies the bytes it carries. It used to trust that the model
    had verified them -- live, the model verified one playbook, re-typed it
    into this call with two `next:` links missing, listed the warnings in
    prose, and offered it anyway; the saved playbook ran only its first step.
    The enhance path closes the same hole with `verified_id`; here the gate
    runs on the offered text itself, so verified and delivered cannot differ.
    """
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return _err("missing_field", "yaml must be a non-empty string")

    guard = _guard_against_open_playbook(yaml_text)
    if guard is not None:
        return guard

    from .tools_verify import verify_playbook
    verdict = verify_playbook(yaml_text)
    if not verdict.get("ready_to_push"):
        return _err(
            "offer_not_verified",
            "this YAML does not pass verify_playbook, so it cannot be offered. "
            "Fix the required_fixes and offer again -- do not describe the "
            "problems to the analyst and offer it anyway.",
            suggestions=list(verdict.get("next_actions") or []),
            required_fixes=verdict.get("required_fixes") or [],
        )

    if not _has_action_steps(yaml_text):
        # Live: "I want to create a new playbook." ended on a Save card for a
        # start -> end playbook. Saving it gives the analyst nothing; the turn
        # should have asked what the playbook is for.
        return _err(
            "offer_has_no_actions",
            "this playbook has only trigger/end steps -- there is nothing to "
            "save yet. Ask the analyst what it should do (what starts it and "
            "what it does), and end the turn.",
            suggestions=["emit_card(card_type='choice', ...) or one plain "
                         "question -- no playbook_offer until it does something"],
        )

    ops_summary = _yaml_ops_summary(yaml_text)

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
                     "-- review the steps before saving."),
        "final_yaml": yaml_text,
    }
    # Non-blocking findings reach the analyst on the card, not only in the
    # model's prose, which is where they were live -- and then ignored.
    if verdict.get("warnings"):
        card["warnings"] = verdict["warnings"]
    if title_suggestion and title_suggestion.strip():
        card["title_suggestion"] = title_suggestion.strip()
    return {"ok": True, "card": card}


@mcp.tool()
def emit_enhancement_offer(
    id: str,
    summary: str,
    verified_id: str,
) -> dict[str, Any]:
    """UPDATE a playbook the analyst ALREADY HAS OPEN -- the MANDATORY terminal
    action of an enhance turn, and the only thing that makes an edit real.
    Requires an existing open playbook to edit, and a `verified_id` from
    `verify_enhancement`. If the analyst asked you to build, create, or write
    a playbook that does not exist yet, this is the WRONG tool -- there is
    nothing for it to update -- use `emit_playbook_offer` instead.

    Enhance mode's counterpart to `emit_playbook_offer`. That one CREATES a new
    playbook; this one UPDATES the open one in place (the connector routes
    accept through the designer's own snapshot-then-PUT path, so the analyst
    keeps a restore point in the Versions tab).

    **You do not pass YAML.** You pass the `verified_id` that `edit_playbook`
    (or `verify_enhancement`) handed back when it returned `ready_to_push: True`,
    and the card carries those exact bytes. This is deliberate and it is the
    whole point of the tool: a live session verified one document and then
    re-typed a subtly different one into chat three times, the widget scraped
    the last prose fence, and the analyst's playbook got YAML no gate had ever
    seen -- while the transcript showed a green verify. Removing the parameter
    removes the failure mode.

    So the enhance turn is exactly:
        edit_playbook(operations=[...])                  ->  verified_id
        emit_enhancement_offer(id, summary, verified_id) ->  card, turn halts

    Never end an enhance turn by printing the revised playbook and hoping the
    analyst pastes or saves it. If the verify did not pass, do not call this --
    fix the findings and re-verify.

    Args:
      id: stable card id; echoed back on accept/decline.
      summary: what the analyst reads -- one or two plain-English lines on what
        this edit changes and why (e.g. "Adds a manual-input approval gate
        before the block, wired Confirm -> Block IP and Cancel -> Manual
        Review."). Describe the change, not the YAML.
      verified_id: the handle from the passing `verify_enhancement` call.

    Returns {ok: True, card:{type:"enhancement_offer", ...}} -- the card carries
    `final_yaml` (the verified bytes), `diff_summary`, and any non-blocking
    `warnings` so the analyst reviews them before applying. On a bad handle
    returns {ok: False, code: "unknown_verified_id"} -- re-run
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
                "do NOT fall back to pasting the YAML into your reply -- the "
                "analyst's playbook is only updated through this card",
            ],
        )

    yaml_text = entry["yaml"]
    ops_summary = _yaml_ops_summary(yaml_text)

    diff = entry.get("diff_summary") or {}
    card: dict[str, Any] = {
        "type": "enhancement_offer",
        "id": id,
        "summary": summary,
        "verified_id": verified_id.strip(),
        "final_yaml": yaml_text,
        # Deletions `verify_enhancement` judged intentional. The accept path
        # forwards these to `update_playbook` as `acknowledged_drops`, which is
        # the only way a requested deletion can clear the fail-closed pre-write
        # guard. Rides on the CARD rather than being recomputed at apply time so
        # the acknowledgement is bound to the same verdict as the bytes -- the
        # analyst approves one document with one set of consequences.
        "acknowledged_drops": list(entry.get("acknowledged_drops") or []),
        "ops_summary": ops_summary,
        "diff_summary": diff,
        "steps_added": list(diff.get("steps_added") or []),
        "steps_removed": list(diff.get("steps_removed") or []),
        "steps_modified": list(diff.get("steps_modified") or []),
        # The per-step before/after payloads the card renders as the diff.
        # The name lists above stay as the header index.
        "changes": list(diff.get("changes") or []),
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



#: The verdict vocabulary. The validator below and the forced-verdict directive
#: (`_loop_helpers.verdict_directive`) both read these, so the model is told the
#: exact set it will be checked against. `needs_more_info` is the "could not
#: conclude" value -- a model left to guess writes `inconclusive` and is refused.
VERDICT_DISPOSITIONS = ("true_positive", "false_positive", "benign", "suspicious",
                        "needs_more_info")
VERDICT_SEVERITIES = ("critical", "high", "medium", "low", "info")


def verdict_contract() -> str:
    """The verdict payload contract in one sentence, from the validator's own
    constants. Read by the refusal (so a repair is one retry) and by the
    forced-verdict directive, so the two can't state different rules."""
    return (
        "payload = {disposition: one of " + ", ".join(VERDICT_DISPOSITIONS)
        + " (needs_more_info when you cannot conclude); severity: one of "
        + ", ".join(VERDICT_SEVERITIES) + "; confidence: a number 0.0-1.0; "
        "summary: plain English, at most 600 characters; findings: a non-empty "
        "list of {claim: string, evidence: [tool_use ids from this turn]}; "
        "unknowns: a list of open questions, required when confidence < 0.8; "
        "recommended_actions (optional): a list of {label: string, tool?, args?}}"
    )


def emit_verdict(
    disposition: str,
    severity: str,
    confidence: float,
    summary: str,
    findings: list[dict[str, Any]],
    unknowns: list[str] | None = None,
    recommended_actions: list[dict[str, Any]] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Emit a `verdict` card with a structured investigation conclusion.

    NOTE: This is an internal implementation function. The public interface is
    emit_card(card_type='verdict', payload={...}). Do not advertise this tool
    separately; it is only callable through emit_card routing.

    Args:
      disposition: one of true_positive, false_positive, benign, suspicious, needs_more_info
      severity: one of critical, high, medium, low, info
      confidence: float 0.0-1.0, how sure the verdict is
      summary: plain-English summary (≤600 chars)
      findings: list of {claim: str, evidence: [tool_call_id, ...]}; each must have
        ≥1 finding and ≥1 evidence id (a tool_use id from THIS session)
      unknowns: open questions that could shift the verdict; empty only if confidence ≥ 0.8
      recommended_actions: optional list of {label, tool?, args?} for next steps
      id: optional card id; generated if absent
    """
    # Collect EVERY problem, not the first. Live, a verdict took nine
    # emit_card calls: each refusal named one defect (shape, disposition,
    # confidence type, claim, evidence type, action shape, action label, ids)
    # and the model fixed exactly that one. One refusal listing all of them,
    # plus the contract, is one repair.
    problems: list[tuple[str, str]] = []

    def bad(code: str, message: str) -> None:
        problems.append((code, message))

    if not isinstance(disposition, str) or disposition not in VERDICT_DISPOSITIONS:
        bad("bad_disposition",
            f"disposition must be one of: {', '.join(VERDICT_DISPOSITIONS)} "
            f"(got {disposition!r})")
    if not isinstance(severity, str) or severity not in VERDICT_SEVERITIES:
        bad("bad_severity",
            f"severity must be one of: {', '.join(VERDICT_SEVERITIES)} "
            f"(got {severity!r})")
    numeric = isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
    if not numeric:
        bad("bad_confidence", "confidence must be a number")
    elif not (0.0 <= confidence <= 1.0):
        bad("bad_confidence", "confidence must be between 0.0 and 1.0")
    if not isinstance(summary, str) or not summary.strip():
        bad("missing_summary", "summary must be a non-empty string")
    elif len(summary) > 600:
        bad("summary_too_long", "summary must be ≤600 chars")
    if not isinstance(findings, list) or not findings:
        bad("no_findings", "findings must be a non-empty list of {claim, evidence}")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            bad("bad_finding", f"findings[{i}] must be an object")
            continue
        if not f.get("claim") or not isinstance(f["claim"], str):
            bad("bad_finding", f"findings[{i}] must have a non-empty string 'claim'")
        if not f.get("evidence"):
            bad("bad_finding_evidence",
                f"findings[{i}].evidence must be a non-empty list of "
                f"tool_call_ids (strings)")
        elif not isinstance(f["evidence"], list):
            bad("bad_finding_evidence", f"findings[{i}].evidence must be a list")
        else:
            for j, eid in enumerate(f["evidence"]):
                if not isinstance(eid, str) or not eid.strip():
                    bad("bad_evidence_id",
                        f"findings[{i}].evidence[{j}] must be a non-empty "
                        f"string (a tool_use_id)")
    # Check unknowns and confidence consistency
    unknowns_list: list[str] = []
    if unknowns is not None:
        if not isinstance(unknowns, list):
            bad("bad_unknowns", "unknowns must be a list of strings or null")
        else:
            unknowns_list = [str(u).strip() for u in unknowns if u]
    if numeric and not unknowns_list and confidence < 0.8:
        bad("confidence_unknowns_conflict",
            "unknowns list cannot be empty when confidence < 0.8; list "
            "open questions or raise confidence to ≥0.8")
    if recommended_actions is not None:
        if not isinstance(recommended_actions, list):
            bad("bad_actions", "recommended_actions must be a list")
        else:
            for i, a in enumerate(recommended_actions):
                if not isinstance(a, dict):
                    bad("bad_action", f"recommended_actions[{i}] must be an object")
                elif not a.get("label") or not isinstance(a["label"], str):
                    bad("bad_action",
                        f"recommended_actions[{i}] must have a 'label' field")
    # Evidence ids are checked in the same pass: the ninth live attempt was
    # refused for citing prose instead of tool_use ids, AFTER eight structural
    # repairs -- it could have been told the first time.
    from ._citation_validator import validate_evidence_ids
    cited = [eid for f in findings if isinstance(f, dict)
             and isinstance(f.get("evidence"), list)
             for eid in f["evidence"] if isinstance(eid, str) and eid.strip()]
    id_hints: list[str] = []
    if cited:
        id_err = validate_evidence_ids(cited)
        if id_err is not None:
            bad(id_err.get("code") or "invalid_evidence_ids",
                id_err.get("message") or "unknown evidence ids")
            id_hints = list(id_err.get("suggestions") or [])
    if problems:
        code, message = problems[0]
        if len(problems) > 1:
            message = (f"{len(problems)} problems -- fix all of them in one retry: "
                       + "; ".join(f"({n}) {m}" for n, (_, m)
                                   in enumerate(problems, 1)))
        return _err(code, message, suggestions=[*id_hints, verdict_contract()],
                    problems=[{"code": c, "message": m} for c, m in problems])
    # Generate id if missing
    if not id or not isinstance(id, str):
        import uuid  # noqa: PLC0415
        id = uuid.uuid4().hex[:16]
    card: dict[str, Any] = {
        "type": "verdict_card",
        "id": id,
        "disposition": disposition,
        "severity": severity,
        "confidence": float(confidence),
        "summary": summary.strip(),
        "findings": findings,
    }
    if unknowns_list:
        card["unknowns"] = unknowns_list
    if recommended_actions:
        card["recommended_actions"] = recommended_actions
    return {"ok": True, "card": card}


# ---------------------------------------------------------------------------
# Phase 1 consolidation: one card emitter over the seven emit_* card tools.
# The specialized names stay registered during the migration; each one's
# runtime validation is the single source of truth, so emit_card only routes.
# emit_decision_step is NOT a card (it renders a YAML step) and stays apart.
# ---------------------------------------------------------------------------

# The vocabulary the model reaches for vs the one the card functions declare.
# Every card emission in the 2026-08-18 investigation sweep was REFUSED on its
# first attempt and self-repaired on the second -- 4 fixtures out of 4, three
# `bad_payload` and one `bad_option`. The model does not send garbage; it sends
# the same card described with the words the tool docs use everywhere else
# (`params` is what run_op takes, `title`/`description` is how every other
# surface names a heading, `{id,label,detail}` is the shape of an option
# elsewhere). Each refusal costs a full LLM round-trip and a tool call against
# the turn budget, and the repaired call drops the extra keys anyway.
#
# So accept the shape the model emits -- the same convention `dispatch` already
# applies to run_op's stringified `params` and emit_card's top-level fields.
# Only ever fill a canonical key that is ABSENT: a payload that already speaks
# the declared vocabulary is passed through untouched.
_CARD_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    # canonical field -> the aliases seen in real traces, in priority order
    "action": {
        "args": ("params", "parameters", "arguments"),
        "summary": ("title", "description", "summary_text"),
        # the model reaches for its run_op vocabulary here (live, 2026-08-18)
        "operation": ("op", "op_name", "operation_name"),
    },
    "choice": {
        "prompt": ("question", "title", "text"),
        "allow_text": ("free_text", "allow_free_text"),
    },
    "capability_gap": {
        "missing": ("gap", "capability"),
    },
}

# Per-option aliases for a choice card's `options` entries.
_OPTION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "value": ("id", "key"),
    "label": ("text", "name", "title"),
    "hint": ("detail", "description"),
}


def _normalize_card_payload(kt: str, payload: dict[str, Any]) -> tuple[
        dict[str, Any], list[str]]:
    """Rewrite a card payload into the declared vocabulary.

    Returns `(payload, dropped)` where `dropped` names the keys the card
    function has no parameter for. Dropping is not silent: the caller reports
    them on the result, because the alternative today is a hard refusal whose
    self-repair drops exactly the same keys one round-trip later.
    """
    out = dict(payload)
    for canon, aliases in _CARD_SYNONYMS.get(kt, {}).items():
        if out.get(canon) not in (None, "", {}, []):
            continue
        for alias in aliases:
            if out.get(alias) not in (None, "", {}, []):
                out[canon] = out.pop(alias)
                break

    if kt == "choice" and isinstance(out.get("options"), list):
        opts = []
        for opt in out["options"]:
            if not isinstance(opt, dict):
                opts.append(opt)
                continue
            o = dict(opt)
            for canon, aliases in _OPTION_SYNONYMS.items():
                if o.get(canon):
                    continue
                for alias in aliases:
                    if o.get(alias):
                        o[canon] = o[alias] if canon == "label" else o.pop(alias)
                        break
            opts.append(o)
        out["options"] = opts

    # An action card with no `editable_fields` is the commonest omission. The
    # analyst must be able to correct the args they are approving (a wrong IP
    # in a block is the whole reason the card exists), so default to the args
    # that were sent rather than to nothing.
    if kt == "action" and "editable_fields" not in out:
        if isinstance(out.get("args"), dict):
            out["editable_fields"] = list(out["args"])

    return out, []


CARD_TYPES: dict[str, str] = {
    "choice": "emit_choice_card",
    "action": "emit_action_card",
    "manual_input": "emit_manual_input",
    "capability_gap": "emit_capability_gap_card",
    "playbook_offer": "emit_playbook_offer",
    "patch_proposal": "emit_patch_proposal",
    "enhancement_offer": "emit_enhancement_offer",
    "verdict": "emit_verdict",
}


@mcp.tool()
def emit_card(card_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """ONE card emitter -- pick `card_type`, pass that card's fields as
    `payload`; the turn halts on the rendered card.

    Which card_type to pick: `choice` = branching question as pickable chips
    (never ask in prose). `action` = editable preview of a connector op the
    analyst confirms before it runs. `manual_input` = form for a paused
    playbook gate. `capability_gap` = the instance CANNOT do what is needed
    (nothing configured for it) -- name the gap + fix steps, never dead-end
    in prose. `playbook_offer` = deliver a NEW playbook (the mandatory
    terminal action of a build turn). `enhancement_offer` = apply a verified
    edit to the OPEN playbook (terminal action of an enhance turn; needs
    `verified_id` from edit_playbook). `patch_proposal` = one-click
    before/after fix to one step or field of the open playbook. `verdict` =
    structured investigation conclusion with disposition, severity, confidence,
    and cited findings (evidence tied to tool_call_ids).
    """
    kt = (card_type or "").strip().lower()
    fn_name = CARD_TYPES.get(kt)
    if fn_name is None:
        return _err("unknown_card_type",
                    f"card_type {card_type!r} not recognized",
                    suggestions=[f"valid card_types: {sorted(CARD_TYPES)}"])
    if not isinstance(payload, dict):
        return _err("bad_payload", "payload must be an object holding the "
                                   "card's fields")
    import inspect  # noqa: PLC0415

    import fsr_playbooks.mcp_server as _pkg  # noqa: PLC0415 - registration cycle
    fn = getattr(_pkg, fn_name)

    # Speak the model's dialect before validating (see _CARD_SYNONYMS).
    payload, _ = _normalize_card_payload(kt, payload)

    # Keys the card function has no parameter for would TypeError below. The
    # refusal is honest but expensive -- the model's repair drops these keys
    # anyway -- so drop them here and SAY SO on the result rather than
    # spending a round-trip to arrive at the same card.
    params = list(inspect.signature(fn).parameters)
    ignored = sorted(k for k in payload if k not in params)
    if ignored:
        payload = {k: v for k, v in payload.items() if k in params}
    # A card id is bookkeeping, not content -- a payload that is otherwise
    # complete must not bounce for lacking one (live: an action card with
    # every real field right was refused twice before the model thought to
    # invent an id).
    if "id" in params and not payload.get("id"):
        import uuid  # noqa: PLC0415
        payload["id"] = uuid.uuid4().hex[:16]
    # Name what is MISSING, not just what is accepted. Live (B3a sweep): the
    # model passed a `find(kind="action")` row -- connector/op/title/
    # required_params -- as an action card. `op`/`title` normalize, but it had
    # no `args`; the refusal listed all seven params, and the model narrated
    # the fix to the analyst instead of resending the card.
    sig = inspect.signature(fn).parameters
    missing = [k for k, p in sig.items()
               if p.default is inspect.Parameter.empty and k not in payload]
    if kt == "action" and "args" in missing:
        # editable_fields defaults from args (_normalize_card_payload), so it
        # is only "missing" because args is; naming both sends the model after
        # a field it never needed to write.
        missing = [k for k in missing if k != "editable_fields"]
    if missing:
        hints = [f"missing: {missing} -- resend emit_card(card_type={kt!r}) "
                 f"with them in `payload`; it takes {params}"]
        if kt == "action" and "args" in missing:
            hints.append("`args` is the operation's parameter VALUES as an "
                         "object, filled from the request (e.g. {\"ip\": "
                         "\"<the IP>\"}) -- not the catalog's "
                         "`required_params` list; get the names from "
                         "get_op_schema(connector, operation)")
        if kt == "verdict":
            hints.append(verdict_contract())
        return _err("bad_payload",
                    f"payload for card_type {kt!r} is missing {missing}",
                    suggestions=hints)
    try:
        out = fn(**payload)
    except TypeError:
        hints = [f"{fn_name} takes: {params}"]
        if kt == "verdict":
            hints.append(verdict_contract())
        return _err("bad_payload",
                    f"payload does not match card_type {kt!r}",
                    suggestions=hints)
    if isinstance(out, dict):
        out.setdefault("card_type", kt)
        if ignored and out.get("ok"):
            out["ignored_fields"] = ignored
    return out
