"""Gate -> prompt-lever attribution, shared across the tuning loop.

A red eval gate should be self-documenting: it names the exact prompt section
(and file) most likely to fix it, so "failure -> file-to-change" is a lookup,
not a grep. Both the live capability gate (`calibrate_investigation.py`) and the
one-command tuning loop (`chat_drive.py`) read from this single map so they can
never drift in what they tell you to edit.

Originally local to `calibrate_investigation.py` and scoped to the investigation
gates; lifted here and extended to the build / offer-timing / hunt tracks so
*every* non-skipped gate in `scoring.score(...)` has a lever (Chat Intelligence
Plan, Track A3).
"""
from __future__ import annotations

# Keys match the gate names emitted by `scoring.score(...)` (the keys under
# `out["levels"]`), plus the synthetic `<forbidden>` marker the recall scorer
# raises when a forbidden pivot fired. Each value points at the prompt section
# + file an editor should reach for first.
LEVER_MAP: dict[str, str] = {
    # ---- investigation / hunt / triage track -> system_prompt_triage.md ----
    "investigation_recall": "fixture required_facts vs. system_prompt_triage.md "
                            "pivot guidance (agent didn't reach the required op)",
    "investigation_tool_budget": "system_prompt_triage.md §pivot-discipline + "
                                 "2.8 parallel dispatch (too many calls)",
    "investigation_no_param_flail": "fsr_playbooks validate_op_grounded + connector_op_defs "
                                    "op-def cache (guessed param names)",
    "investigation_blind_param_retry": "run_op bad_params inline valid_params + "
                                       "system_prompt_triage.md 'call get_op_schema "
                                       "before run_op' (hammered without lookup)",
    "investigation_deliverable": "system_prompt_triage.md emit_action_card staging rule "
                                 "(hunt ended without a card)",
    "<forbidden>": "system_prompt_triage.md forbidden-pivot rule "
                   "(fired an internal-source TI lookup)",
    # Hunt depth/breadth (Track B2) — placeholder until the gate lands; the
    # lever is already known so a future red gate is self-documenting.
    "hunt_depth": "system_prompt_triage.md §Hunting instincts "
                  "(too few lateral pivots from the seed IOC)",
    # Build-metric gates (emitted by score_build_metrics, also surfaced on
    # investigation drives) — same triage-prompt levers, no `investigation_` prefix.
    "tool_budget": "system_prompt_triage.md §pivot-discipline + 2.8 parallel "
                   "dispatch (too many total tool calls)",
    "no_spiral": "system_prompt_triage.md 2.8 parallel dispatch / §pivot-discipline "
                 "(too many of the SAME tool back-to-back — batch run_op enrichment "
                 "in one dispatch instead of one IOC at a time)",
    # ---- build / triage->build fidelity track -> system_prompt_build.md ----
    "draft": "system_prompt_build.md §Canonical skeleton "
             "(emitted YAML did not compile)",
    "verified": "system_prompt_build.md §Canonical skeleton + verify loop "
                "(playbook not statically sound / not ready_to_push)",
    "adherence": "system_prompt_build.md §Workflow "
                 "(final answer omitted the fenced ```yaml block)",
    "offer_timing": "system_prompt_build.md §Triage -> build handoff "
                    "(offered the save at the wrong moment, or not at all)",
    "build_fidelity": "system_prompt_build.md §Triage -> build handoff + "
                      "§Canonical skeleton (built playbook invents ops the "
                      "investigation never ran, or omits the staged action)",
    "verify_called_before_submit": "system_prompt_build.md §verify loop "
                                   "(submitted without calling verify first)",
    "final_verify_ready_to_push": "system_prompt_build.md §Canonical skeleton + "
                                  "verify loop (last verify was not ready_to_push)",
    "matches_example": "system_prompt_build.md §Canonical skeleton "
                       "(compiled IR diverged from the reference example)",
    "live_tested": "system_prompt_build.md §Canonical skeleton "
                   "(dry-run did not reach a terminal state — check trigger/wiring)",
    # ---- HITL approval behaviour -> tools.py tier gate + triage prompt ----
    "appropriate_approval_requests": "fsr_playbooks/llm/tools.py tier/approval gate + "
                                     "system_prompt_triage.md containment rules "
                                     "(over- or under-escalated tier-3+ ops)",
}


def lever_for(key: str) -> str:
    """Return the prompt-lever hint for a gate name, or a fallback prompting a
    manual trace inspection when the gate isn't mapped yet."""
    return LEVER_MAP.get(key, "unmapped — inspect trace")
