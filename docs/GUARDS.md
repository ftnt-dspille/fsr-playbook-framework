---
title: Agent loop guards -- what each one does and why it stays
category: architecture
status: canonical
topics: [agent-loop, guards, delivery, triage-discipline]
summary: Every end-of-turn guard and dispatch guard in llm/agent_loop.py, how often it fires, and the rule for adding or removing one.
---

# Agent loop guards

All guards live in one place now: `fsr_playbooks/llm/agent_loop.py` drives them
and `fsr_playbooks/llm/_loop_helpers.py` defines them. No provider carries its
own copy (`tests/test_one_agent_loop.py` enforces that).

## The rule

A guard is a backstop for a tool contract the model can get wrong. Before
adding one, ask whether a tool change can make the mistake impossible instead.
When a tool change lands, delete the guard it replaces. Never decide by parsing
wording (the request or the model's prose); decide on structure: which tools
ran, what they returned, what is mounted.

## Audit (local session store, 5,751 turns over three weeks)

Fires are counted from the `usage` events' `stop_reason` and from guard
envelopes in tool results. Most traffic is sweeps and the analyst sim.

### End-of-turn

| Guard | Fires | What it does now | Decision |
|---|---|---|---|
| Verdict delivery | 57 | Triage gathered evidence and never concluded: one `emit_card(verdict)` round pinned by `tool_choice`, citing this turn's evidence ids, one repair attempt | Keep. The verdict's findings are model-authored; nothing deterministic can write them. |
| Fabricated call (`PromisedActionGuard`) | 30 (both halves, before the split) | The model wrote `[called x(...)]` / `[tool result: ...]` as prose: one directive | Keep the structural half (our own marker syntax). The phrase-regex half that matched promises ("please approve the card") is **deleted**: it was intent detection over wording. |
| Stall (`ProgressMeter`) | 14 | Rounds that only repeat or only fail: one no-tools wrap-up | Keep. |
| Budget cliff | 10 | Out of tool rounds: wrap-up when nothing is delivered, else the budget-ask card | Keep. |
| Build progress | 9 | Researched step types / op schemas and never drafted: one directive | Keep. No tool change removes "stopped before starting". |
| Unverified draft | 9 | Drafted, checked with validate/compile, stopped | **Replaced.** When the last check passed clean and has action steps, the loop runs `verify_playbook` itself: a pass is delivered with no model round; a fail goes back to the model with the verify result in history. The old directive remains only for a draft that never checked clean. |
| Create delivery | 8 | `verify_playbook` passed, no offer card | **Replaced.** The loop emits the `playbook_offer` with the verified bytes itself. It used to spend a `tool_choice`-pinned model round asking for the call, which was one more chance to narrate. |
| Enhance delivery | 0 | Edit verified, no Apply card | **Replaced** the same way (`enhancement_offer` with the blessed `verified_id`). |
| Failed edit | new | The last edit still has required fixes: one directive | Keep; measure. |
| Containment follow-through | 0 locally | Unattended (auto-triage) true positive with nothing staged: one directive | Keep; only auto-triage turns can fire it. |
| Forced assessment | 2 | Ran tools, wrote nothing | Keep. |
| Self-repair | n/a | A fenced ```yaml block in prose that does not compile: one repair round | Keep while fenced YAML counts as a deliverable (`analyst_has_the_yaml`). |

### Dispatch (inside the loop's `guarded_dispatch` and `TriageDiscipline`)

| Guard | Fires | Decision |
|---|---|---|
| Forbidden pivot: internal-IP correlation and external enrichment of an internal IP | 438 | **Open question for the owner.** By far the most frequent guard, so the model keeps reaching for it, and each refusal costs a round. Either the policy is right and the tool descriptions should stop inviting the call, or searching alerts by an internal host is legitimate (lateral movement) and the guard should go. |
| Repeated failed call | 79 | Keep. |
| Unreadable tool arguments | 33 | Keep; structural. |
| Hunt floor | 26 | Keep. |
| Defer (`guard_defer` on `emit_card`) | 26 | Keep. |
| Not in the advertised slice | 3 | Keep; defense in depth for the intent slice. |
