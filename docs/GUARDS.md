---
title: Agent loop guards -- what each one does and why it stays
category: architecture
status: canonical
topics: [agent-loop, guards, delivery, triage-discipline, dispatch, turn-plan]
summary: Every guard in the agent loop, at dispatch, in the argument gate and in the turn plan, where each lives, how often it fires, and the rule for adding or removing one.
---

# Agent loop guards

Guards sit in five places. Read the one that owns the mistake before adding a
new one.

| Where | What is guarded |
|---|---|
| `fsr_playbooks/llm/agent_loop.py` | The loop driver. End-of-turn nudges and loop-delivered offers, the verdict round, containment follow-through, assessment, and `guarded_dispatch` (bad-arguments envelope, not-in-slice refusal, repeated-failed-call refusal). |
| `fsr_playbooks/llm/_loop_helpers.py` | The guard classes: `TriageDiscipline` (dispatch envelopes), `EnhanceDeliveryGuard`, `CreateDeliveryGuard`, `BuildProgressGuard`, `VerdictDeliveryGuard`, `ContainmentFollowThrough`, `PromisedActionGuard`, `ProgressMeter`. |
| `fsr_playbooks/llm/tools.py` | The dispatch stages `_DISPATCH_STAGES`: `_refuse_for_turn` (the read-only-turn refusal, then `TurnPlan.gate_refusal`), `_fold_emit_card_payload`, `_redirect_run_not_author`, `_coerce_args`, `_check_args`, `_default_live_probe`. Also the `_approved` wire-key refusal (`reserved_key_rejected`) when a call is built. |
| `fsr_playbooks/llm/arg_gate.py` | The one argument gate for every tool (unknown keys, required keys, types, enums, nested shape), plus the `tool_models.CROSS_FIELD_RULES` (rules across arguments a schema cannot say) that `_check_args` runs after it. Code `invalid_tool_args`. |
| `fsr_playbooks/llm/turn_plan.py` | `TurnPlan.gate_refusal`: the playbook-side rule on build turns (`not_a_playbook_tool`), the fail-closed `state_unresolved` failsafe, and the open-playbook frontier (`not_afforded`). |

The approval decision is not a guard in this sense. `fsr_playbooks/llm/authorization.py`
`authorize()` decides it, once (see `CLAUDE.md`).

No provider carries its own copy of any of this (`tests/test_one_agent_loop.py`
enforces that for the loop).

## The rule

A guard is a backstop for a tool contract the model can get wrong. Before
adding one, ask whether a tool change can make the mistake impossible instead.
When a tool change lands, delete the guard it replaces. Never decide by parsing
wording (the request or the model's prose); decide on structure: which tools
ran, what they returned, what is mounted.

A guard that replaces a model round with loop code is still a guard. The loop
does the step itself and the audit below counts it under the same name.

## Audit (local session store)

Source: `agent_usage.stop_reason` in the local session DB
(`~/.connector_fsr_soc_assistant.db`, read-only copy), 2026-07-29 to 2026-10-10,
31,618 usage rows over 14,244 sessions. Counts are rows with that marker, and
the date is the last fire seen. Rows written before 2026-10-09 may predate the
loop-delivery change in `c48e97f`. Figures marked "earlier" come from the
2026-10 audit and are not in `agent_usage`.

### End-of-turn

| Guard | Marker | Fires | What it does now | Decision |
|---|---|---|---|---|
| Verdict delivery | `verdict_guard_forced` | 110 (to 2026-10-09) | Triage gathered evidence and never concluded: one `emit_card(verdict)` round pinned by `tool_choice`, citing this turn's evidence ids, one repair attempt | Keep. The verdict's findings are model-authored; nothing deterministic can write them. |
| Fabricated call (`PromisedActionGuard`) | `promised_action_forced` | 30 | The model wrote `[called x(...)]` / `[tool result: ...]` as prose: one directive | Keep the structural half (our own marker syntax). The phrase-regex half that matched promises was deleted: it was intent detection over wording. |
| Stall (`ProgressMeter`) | none (`record_guard_fire`) | 14 (earlier) | Rounds that only repeat or only fail: one no-tools wrap-up | Keep. |
| Budget cliff | `max_tool_turns` | 36 | Out of tool rounds: wrap-up when nothing is delivered, else the budget-ask card | Keep. |
| Build progress | `build_progress_forced` | 37 | Researched step types / op schemas and never drafted: one directive | Keep. No tool change removes "stopped before starting". |
| Unverified draft (never clean) | `unverified_draft_forced` | 10 (last 2026-09-28) | A build turn ran validate/compile, the draft never checked clean, and the turn stopped: one directive to verify and offer | Keep. Reachable: `test_draft_then_stop_is_nudged_into_verify_and_offer` drives it. Its replacement covers only the clean case (below). |
| Unverified draft (clean) | `unverified_draft_verified` | 0 (since 2026-10-09) | The last validate/compile passed clean with action steps and the turn ends: the loop runs `verify_playbook` itself. A pass is delivered with no model round; a fail goes back with the verify result in history | Replacement for the row above. Covered by `test_a_clean_draft_is_verified_and_delivered_by_the_loop` and `test_a_clean_draft_that_fails_verify_goes_back_with_its_fixes`. |
| Create delivery | `create_delivery_forced` | 28 (last 2026-10-06) | A verify passed and the turn ends without the offer card: the loop emits `playbook_offer` with the verified bytes. No model round | Keep. This is the replacement contract, not a fallback nudge. |
| Enhance delivery | `enhance_delivery_forced` | 0 | A verify passed and the turn ends without the offer card: the loop emits `enhancement_offer` with the blessed `verified_id`. No model round | Keep. It is the same loop code as create delivery and costs no model round. Zero recorded fires means the model delivered by itself in every recorded enhance turn; the path is still reachable and covered by `test_anthropic_enhance_delivery_forced.py` and `test_openai_enhance_delivery_forced.py`. |
| Failed edit | `failed_edit_forced` | 0 | The last edit still has required fixes: one directive | Keep; measure. |
| Containment follow-through | `containment_follow_through` | 25 (since 2026-10-05) | Unattended (auto-triage) true positive with nothing staged: one directive | Keep; only auto-triage turns can fire it. |
| Forced assessment | `assessment_forced` | 5 | Ran tools, wrote nothing | Keep. |
| Self-repair | n/a | n/a | The last fenced ```yaml block in a terminal round fails the compile or the connector check: one repair round, up to `MAX_SELF_REPAIR_TURNS` (2). Once the cap is spent, a failing fence is neutralised in the delivered text (a note naming what failed), in the terminal round, the tool-round prose and the wrap-up. | Keep. The widget saves the last fence and has no other signal, so the loop is the only place a failing fence can be stopped. |

Delivery is decided on structure: the loop emits an offer only when a verify
passed, the offer tool is advertised, the model has not already delivered, and
(for create) no playbook is open and the analyst has not been asked a choice.

### Dispatch

Dispatch refusals are returned to the model as tool results. Counts are
substring matches on `agent_tool_calls.result_summary` in the same DB.

| Guard | Where | Code or envelope | Recorded | Decision |
|---|---|---|---|---|
| Repeated failed call | `agent_loop.guarded_dispatch` | `repeated_call_guard` | 133 | Keep. |
| Not in the advertised slice | `agent_loop.guarded_dispatch` | "not available in this session" error | 3 (earlier) | Keep; defense in depth for the intent slice. |
| Unreadable tool arguments | `agent_loop.guarded_dispatch` | `bad_tool_arguments` | 34 | Keep; structural. |
| Hunt floor | `TriageDiscipline` | `guard_defer` / `hunt_floor_guard` | 47 | Keep. |
| Defer (`guard_defer` on `emit_card`) | `TriageDiscipline` | `guard_defer` | 59 | Keep. |
| Call-once discovery | `TriageDiscipline` | `guard_redirect` / `call_once_guard` | 13 | Keep. Terminal; the signature is remembered. |
| Duplicate search | `TriageDiscipline` | `guard_redirect` / `duplicate_search_guard` | 106 | Keep. |
| Capability gap | `TriageDiscipline` | `guard_redirect` / `capability_guard` | 0 | Keep; terminal. |
| Enrichment cap | `TriageDiscipline` | `guard_redirect` / `enrichment_cap_guard` | 0 | Keep; terminal. |
| Forbidden pivot and internal-IP correlation search | removed | n/a | 438 (earlier) | Removed by owner decision. The only internal-address protection kept is the repo-level infra-leak check (`scripts/check_infra_leaks.py`). |

### Argument gate, turn plan and approval

| Guard | Where | Code | Recorded | Decision |
|---|---|---|---|---|
| Argument gate (`arg_gate` plus `CROSS_FIELD_RULES`) | `tools._check_args` | `invalid_tool_args` (message "invalid arguments") | 183 | Keep. The one gate for every tool; runs before authorization so a bad call never raises a card. |
| Read-only turn refusal | `tools._refuse_for_turn` / `turn_refusal` | `read_only_turn` | 0 | Keep. Refused rather than carded (tracker #117). |
| Run, not author | `tools._redirect_run_not_author` | `run_not_author` (or redirect to `run_playbook`) | 0 | Keep. Keyed on the call's shape. |
| Playbook side is playbook tools only | `TurnPlan.gate_refusal` | `not_a_playbook_tool` | 104 | Keep. See `CLAUDE.md`. Structural, not prompt wording. |
| Open-playbook frontier and create-new refusal | `TurnPlan.gate_refusal` | `not_afforded` | 15 | Keep. |
| Failsafe (plan could not be derived) | `TurnPlan.gate_refusal` | `state_unresolved` | 0 | Keep. Fails closed. |
| Wire-supplied `_approved` | `tools` call build | `reserved_key_rejected` | 0 | Keep. Tier-gate bypass attempt. |
| User denied | `authorization.authorize` / `approvals` | `user_denied` | 0 | Not a guard; the approval outcome. |

## Changelog

- 2026-10-12: self-repair. A failing fence is no longer delivered after the cap:
  `_neutralise_failing_fences` replaces it with a note. The fence text is held
  back from the stream until its round ends (`FenceHold`), so prose still
  streams. Cap value measured on five live Frank build turns: two repairs, one
  recovered on its first attempt; kept at 2.
- 2026-10-11: inventory extended to the tools.py and arg_gate.py dispatch
  stages and TurnPlan.gate_refusal. Audit counts refreshed from the local
  session DB. The delivery rows now say what the loop does, not that a
  forced nudge remains.
