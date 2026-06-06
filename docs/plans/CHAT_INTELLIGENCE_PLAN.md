# Chat Intelligence Plan — tune & enhance the investigation→build agent

**Created:** 2026-06-05 · **Status:** Phase 0 complete + live-exercised (A1+A2+A3+A4+A6); B1 first rung shipped; A5 deferred · **Owner loop:** iterative (Claude + Dylan)

> **B1 + A4 session (2026-06-06, cont.):** **B1 — both stale goldens re-captured GREEN**
> (offline pin: 0 stale warnings). Live-tuned `system_prompt_triage.md` over deploys
> 0.3.117→**0.3.121**: (1) rule 3 `find_containment_actions` now non-terminal → deliverable
> fixed; (2) elevated **two-module correlation** (`search_module_records` on BOTH `alerts`
> AND `incidents`) into the numbered hunt loop → mail-egress **recall 5/5 = 1.00** (was stuck
> 0.67); (3) within-turn budget discipline (no re-`get_record`, batch related-activity +
> enrichment, stage ONE card, call containment-discovery once) → no_spiral 4/5, budget best
> 10–12 (clean runs **6/6**). Residual: mail-egress budget passes ~40% (intermittent extra
> searches/cards) — stochastic tail, deliberately stopped tuning. cleartext_c2 still 6/6 (no
> regression). **A4 — `make chat-fast` SHIPPED**: 13-file offline STRUCTURE/contract suite
> (prompt assembly, intent routing, tool registry, A3 lever map, A6 golden pin),
> deterministic, **122 pass ~1.5s, no API** — default tuning loop vs live `make chat-calibrate`.
> A5 (trend) deferred. Next rung: **B4** (triage→build fidelity).

> **Live-drive session (2026-06-06):** forticloud reachable; first live `chat-drive
> --task invest_outbound_cleartext_c2` (deployed connector 0.3.116) →
> recall 1.00, budget 12/12, render clean, BUT two FAILs: (a) `no_spiral` — 5
> consecutive `run_op` enrichment calls (serial, not fanned out) → tripped the ≤4
> limit AND ate the budget; (b) `investigation_deliverable` — agent ended its turn
> on a bare `find_containment_actions` (12th/last call) with no card staged. Same
> root cause: serial enrichment crowded the card out of the budget (exactly rule
> #6's warning). This *confirms the 2 stale goldens are a real capability gap, not
> just a stale bar.* Fixes this session: **A3 lever gaps closed** — added levers for
> `no_spiral`, build-track `tool_budget`, `verify_called_before_submit`,
> `final_verify_ready_to_push`, `matches_example`, `live_tested` (were "unmapped");
> new `python/tests/test_lever_coverage.py` drives `score()` and asserts every
> counted gate resolves to a real lever (A3 DoD now *enforced*). **B-track prompt
> edit (staged, NOT yet live-validated):** `system_prompt_triage.md` rule 3 now makes
> `find_containment_actions` non-terminal — must be followed by `emit_action_card`/
> `emit_capability_gap_card` in the same turn. **PENDING:** redeploy connector to
> pick up the prompt edit → re-drive `invest_outbound_cleartext_c2` → if deliverable
> + no_spiral clear, re-capture both stale goldens (`calibrate --capture`).

> **Phase 0 progress (2026-06-06):** A1 `fsrpb chat-drive` (live sync `chat_turn`+`chat_resume`
> → trace → score → render-validate → one-screen verdict with per-gate lever) + `make chat-drive`;
> A2 `--capture-fixture` (run → proposed `tasks/*.json` + golden, human-reviewed); A3 shared
> `python/evals/levers.py` (gate→prompt-lever, extended to build/offer/hunt; `calibrate` now imports
> it); A6 `python/tests/test_golden_traces_pin.py` (offline, runs under `make tests`). New node render
> bridge `widgets-src/fsrSocAssistant/tools/render_check.cjs`. Offline-verified: **812 pytest pass**
> (`make tests`) + 295 fsr_core; render bridge + scoring + capture all green. Also fixed 3 stale
> fixtures (`test_linter` `query_url` needs `url:`; `test_corpus_validator` `vars.op` needs a
> `set_variable`) that collided with the in-progress validator hardening (missing-required→error,
> undefined-`vars`, malformed-Jinja) — fixtures updated, validators left intact. **Surfaced finding:**
> 2 committed golden traces
> (`invest_excessive_mail_egress` 19>12 budget, `invest_outbound_cleartext_c2` no deliverable) are
> **stale** vs current fixture quality knobs — the pin warns (recall intact) and flags re-capture
> live. **Pending:** live `fsrpb chat-drive` against forticloud (needs creds/connector reachable) +
> re-capture the 2 stale goldens. A4/A5 (fast/live split, trend) deliberately deferred.

## North star
Make the chat agent measurably smarter at the full chain — **investigate → hunt →
triage → build a playbook out of it** — AND make that improvement *cheap and safe
to iterate on*. Every capability gain lands behind an eval gate so a prompt tweak
that helps one case can't silently regress another.

Two intertwined tracks:
- **Track A — the tuning loop** (make it *easy* to enhance): one command to drive a
  real scenario, score it, and tell me which prompt lever to edit.
- **Track B — the capability ladder** (make it *smart*): raise investigate / hunt /
  triage / build quality, each pinned by a gate from Track A.

Track A is the force multiplier — build enough of it first that Track B work is
fast, then alternate.

---

## What already exists (build on this, don't rebuild)

**The chat brain** — `fsr_core/llm/`:
- `run_turn.py` — the event-consumer loop · `tools.py` — tool dispatch + tier/approval gate · `intents.py` — intent registry
- Dynamic triage: `triage_normalize.py`, `triage_preflight.py`, `triage_scenarios.py`, `triage_sources.py`, `triage_prompt.py`
- Providers: `anthropic_provider.py`, `fake_provider.py`, `lmstudio_provider.py`, `factory.py` (fake/lmstudio = no-cost local iteration)

**The prompts** (the primary tuning levers) — `fsr_core/agent/`:
- `system_prompt_triage.md` — sections: *Record context · What you do · Hunting instincts · Hard rules · Quick-action intents*
- `system_prompt_build.md` — sections: *Workflow · Triage → build handoff · Canonical skeleton*

**The eval harness** — `python/evals/`:
- `harness.py::run_matrix` · `scoring.py` (recall gate `INVESTIGATION_RECALL_GATE=0.8`; quality gates: `investigation_tool_budget`, `investigation_no_param_flail`, `investigation_blind_param_retry`, `investigation_deliverable`)
- `calibrate_investigation.py` — drives the **live** triage agent per fixture and already maps each gate failure → the prompt **lever** most likely to fix it (`_lever_for`)
- `tasks/` (build tasks `01_…`–`10_…`), `golden_traces/`, `build_trace_fixture.py`, `parity_report.py`, `providers.py`
- Run history: `store/eval_runs/*.{log,summary.json}`

**Live drivers** — `python/demo_hunt.py`, `_poll_then_hunt.py`, `chat_review.py`; plus
the synchronous `/api/integration/execute/` recipe proven 2026-06-05 (see
`[[todo_ui_scenario_testing]]` live-driving note): `chat_turn` sync with
`{messages:[{role,content}], intent, mode:"live", detached:false}` returns the full
transcript in one call.

**Gap:** these are powerful but scattered. There is no *single* "drive → score →
attribute → diff vs. last run" command, no triage/hunt/build fixture-capture from a
real run, and no trend view. That's Phase 0.

---

## Track A — the tuning loop (do first)

### A1 · One-command drive-and-score  ·  HIGH · medium
Formalize the proven `/tmp/drive_live.py` into `python/chat_drive.py` (or a
`fsrpb chat-drive` CLI subcommand). Given a scenario (message + intent + optional
seed entity), it: drives a real sync `chat_turn` (and `chat_resume` for multi-turn /
approval flows), captures the transcript, runs `scoring.py` gates against an
expected-facts fixture, **render-validates** the transcript through the widget's
`fsrPbRender` (node, the 2026-06-05 check), and prints a one-screen verdict.
*DoD:* `fsrpb chat-drive <scenario>` → recall/quality/deliverable/render verdict in <2 min.

### A2 · Capture any real run → fixture/golden  ·  HIGH · small
Extend `build_trace_fixture.py` to mint an **investigation/triage** fixture (not just
build): from a captured transcript, propose `required_facts`, `forbidden_pivots`,
tool budget, and a golden trace. One command turns "that run was good/bad" into a
permanent regression case. *DoD:* a real triage run becomes a committed fixture in one step.

### A3 · Prompt-lever attribution for every gate  ·  HIGH · small
Generalize `calibrate_investigation._lever_for` from the investigation gates to
**all** tracks (hunt, triage-assessment, build-fidelity). Each failing case prints
"edit *<section>* of *<prompt file>*" so a red eval points at the exact lever. *DoD:*
every gate has a lever; the calibrate report is a prompt-edit worklist.

### A4 · Fast local loop + live gate  ·  MEDIUM · small  ·  ✅ DONE 2026-06-06
`make chat-fast` runs a 13-file offline STRUCTURE/contract suite (prompt
assembly, intent routing, tool registry, A3 lever map, A6 golden pin),
deterministic (`-p no:randomly`), 122 pass in ~1.5s with **no API**. It's the
default loop while tuning prompts/tools/intents; `make chat-calibrate` (live,
Anthropic) stays the periodic capability gate. `CHAT_FAST_TESTS` in the Makefile
is the curated list — add a test here when a new structural contract lands.
*DoD met:* `make chat-fast` (local, seconds) vs `make chat-calibrate` (live, gated).

### A5 · Trend dashboard  ·  MEDIUM · small
Aggregate `store/eval_runs/*.summary.json` into a single trend table (recall,
each quality gate, build success) over time, so a prompt edit's net effect across
the whole suite is visible at a glance. *DoD:* `fsrpb chat-trend` prints the matrix.

### A6 · Golden-trace regression pin  ·  HIGH · small
Wire `golden_traces/` into the fast suite so an edit that improves case X but breaks
the tool-sequence of case Y fails loudly. *DoD:* a known-good edit passes; a
deliberately-bad prompt edit reddens a golden case.

---

## Track B — the capability ladder (each pinned by a Track-A gate)

### B1 · Investigate — recall & pivot quality  ·  CRITICAL
Lever: `system_prompt_triage.md` *Hunting instincts* + the op-def cache. Push recall
past the 0.8 gate on the fixture suite; add pivot-*correctness* (right indicator,
right connector) beyond raw recall. Gate: `investigation_recall` + a new
`investigation_pivot_precision`.

### B2 · Hunt — proactive, hypothesis-driven  ·  HIGH
Lever: *Hunting instincts*. Measure hunt **depth** (lateral pivots from a single IOC),
**breadth** (independent hypotheses tried), and stop-criteria (no endless flailing —
ties to `investigation_tool_budget`). New gate: `hunt_depth` on a seeded multi-hop
scenario (the wendy.smith → smithDesktop → 10.50.60.70 → 102.220.160.21 chain).

### B3 · Triage — assessment correctness  ·  HIGH
Levers: `triage_normalize/classify/scenarios` + *What you do* / *Hard rules*. Score
severity/verdict correctness, low-signal handling (don't over-escalate a benign
alert), and scenario classification accuracy. New gate: `triage_assessment` against
labeled scenarios in `triage_scenarios.py`.

### B4 · Triage → Build fidelity  ·  CRITICAL  ·  🟢 LIVE CHAIN PROVEN (0.3.123, 2026-06-06) — gate fires, grounding 1.0; open: action_coverage (staged-not-executed containment)
Levers: `system_prompt_build.md` *Triage → build handoff* + *Canonical skeleton*.
The built playbook must actually **automate what was investigated** — same
ops, parameterized to the trigger record, compiling + runnable. Reuse build tasks
`01_…`–`10_…` and `build_trace_fixture`. Gate: `build_fidelity` (ops-overlap with the
investigation) + existing compile/`run_playbook` success.

**Done:** `scoring.score_build_fidelity(trace, yaml)` grades two sub-metrics over
(connector, op) sets — **grounding** (every built connector op was actually
exercised in the investigation; gate 1.0 — no invented ops) and **action_coverage**
(the `emit_action_card` op appears as a playbook step). Auto-skips on standalone
authoring tasks / investigation mode. Wired into `score()` as a counted gate;
`build_fidelity` lever added; offline pin `python/tests/test_build_fidelity.py`
(10 cases) in `make chat-fast`. Two built-ops sources: a standalone build run's
emitted ```yaml fence (`chat_drive._extract_yaml`), OR a triage→build *chain*'s
`playbook_offer` card `ops_summary` (`scoring.ops_from_offer_card` →
`score_build_fidelity(..., built_ops=…)`). `chat_drive.attach_build_fidelity`
detects an offer card in the transcript and folds the gate into the verdict, so
both a one-shot build and an investigate→offer chain are graded.
**Live chain — two drives, 2026-06-06, connector 0.3.122 (real C2 alert `54f25f1f…`).**

*Drive 1 (FLAWED — driver bug).* Scripted triage turn → follow-up `build` turn,
but the follow-up sent only the NEW user message in `messages[]`. The build turn
replied *"I don't see a prior triage conversation in this session history."* I first
read this as a connector defect (session discontinuity). **It is not** — see drive 2.
`chat_turn` feeds the LLM ONLY the caller-supplied `messages[]` (`operations.py`
`prior = params.get("messages")`, line ~1748); the real widget replays the FULL
accumulated conversation each turn. Drive 1 just didn't replay it.

*Drive 2 (CORRECTED).* Same `session_id`, turn 2 replays widget-style
`[user, assistant(turn-1 summary), user("build it")]`, intent `build`. Result:
the build turn **saw the prior investigation**, authored a containment playbook
(`get_step_type` → `get_op_schema`/`find_operation` → `validate_yaml` ×3 →
`push_playbook`) and reached **`approval_required`** (HITL on push). **The triage→build
chain works end-to-end** when the conversation is replayed. (Transcript:
`store/eval_runs/chatchain_1780788431.json`.)

**Two real gaps remain (both narrower than the original mis-finding):**
1. **Build agent bypasses the trace compiler.** It said *"I don't have a recorded
   trace … the enrichment queries were live lookups, not playbook steps"* and never
   called `build_playbook_from_trace` — it hand-authored. This is FALSE: source
   confirms `run_op` records every executed op into the active SkillTrace
   (`tools_execution.py` `record_run_op`, both paths) and `_session_trace_scope`
   persists/loads it by `session_id`, so the triage enrichment ops WERE recorded.
   The build prompt says call `build_playbook_from_trace` FIRST
   (`system_prompt_build.md` §*Triage → build handoff*) — the agent didn't.
   **Prompt-adherence fix, not a data-availability fix.**
2. **`build_fidelity` still didn't fire from this chain** — the agent went the
   `push_playbook`/HITL route, not `emit_playbook_offer`, and `attach_build_fidelity`
   keys off the offer card. The authored YAML lives in `last_assistant_yaml`, so the
   gate COULD grade via the existing `_extract_yaml` path; and note hand-authored
   containment ops (fortigate block) were NOT exercised in triage, so grounding would
   correctly score < 1.0 (the gate doing its job).

**(a) DONE — live-proven on 0.3.123.** Tightened `system_prompt_build.md`
§*Triage → build handoff*: calling `build_playbook_from_trace` FIRST is now mandatory,
with an explicit rebuttal of the "those were just live lookups, not steps"
rationalization (every `run_op` is recorded). Re-drove the same chain →
`build_playbook_from_trace` is the **first** build op, the agent emits
`emit_playbook_offer` (`awaiting_playbook_offer`), and **`build_fidelity` fires
end-to-end**: `grounding 1.00` (all 4 built ops — ip-quality-score/fortiguard-ioc/
fortisiem/virustotal — really ran in triage; zero invented ops), `action_coverage
0.00`. The trace compiler produced a grounded, runnable enrichment playbook from the
real run. Transcript: `store/eval_runs/chatchain_1780789560.json`. **(b) proved
unnecessary** — forcing the trace compiler routed the agent to the offer-card path the
gate already grades, so no gate-widening was needed.

**New open gap — `action_coverage`.** The staged containment `fortigate-firewall.
block_ip_new` is ABSENT from the built playbook because it was only **staged**
(`emit_action_card`), never executed, so it's not in the recorded trace and the
compiler can't replay it. The build prompt (§handoff) already says an approved
containment should appear as a manual-approval step — so the fix is: after the trace
compiler returns the enrichment backbone, the build agent must **append the staged
containment action as a confirmed/manual-approval step** (the one op it legitimately
hand-adds beyond the trace). Options: (i) record staged action_cards into the session
trace so the compiler replays them too; or (ii) prompt the build agent to read the
staged action from history and add it. **Next:** implement one of those → re-drive →
expect `action_coverage 1.0` + `build_fidelity` PASS → pin THAT chain as a golden.
Plus the still-open parameterized-to-trigger-record check beyond ops-overlap.

### B5 · End-to-end chain  ·  HIGH
Score the whole investigate→hunt→triage→build chain as ONE run (the `build_run_proof`
shape, live). Gate: the chain reaches a runnable playbook whose ops trace back to the
investigation, with no human repair.

---

## Phasing & cadence
1. **Phase 0 = Track A1–A3 + A6** (the loop + attribution + regression pin) — until I can
   drive→score→attribute→pin in one pass. *This is the "make it easier for you" deliverable.*
2. **Then alternate Track B**, one rung at a time, each landing with: a fixture (A2), a
   gate (A3 lever), and a golden pin (A6). Order by live impact: B1 → B4 → B2 → B3 → B5.
3. **A4/A5** slot in opportunistically to keep the loop cheap and visible.

## Definition of done (for the plan as a whole)
- I can take a vague ask ("triage feels shallow on phishing") → drive a real scenario →
  get a scored verdict that names the prompt section to edit → make the edit → re-run
  the fast suite (seconds) → confirm no golden regressions → periodically confirm live.
- Every capability claim ("hunting is deeper now") is backed by a gate, not vibes.

## Risks
- **Live cost/flakiness** (Anthropic + forticloud 502s as seen 2026-06-05): default to
  the local structure loop; batch live calibration.
- **Overfitting prompts to fixtures**: keep a held-out scenario set; watch the trend (A5),
  not single cases.
- **Prompt levers interact**: A6 golden pins are the guardrail against whack-a-mole.

## Cross-refs
- `AGENT_HARDENING_PLAN.md` (Phase 1 shipped; this plan subsumes the "investigation
  quality" thread 1.4 and Phase 4) · `docs/AGENT_TOOL_USAGE.md` (gate p95 sources)
- Live-driving recipe + grounding: memory `[[todo_ui_scenario_testing]]`,
  `[[forticloud_demo_scenario]]`, `[[agent_triage_pivot_toolset]]`
</content>
