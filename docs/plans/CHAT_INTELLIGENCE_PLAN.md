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
> (`make tests`) + 295 fsr_playbooks; render bridge + scoring + capture all green. Also fixed 3 stale
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

**The chat brain** — `fsr_playbooks/llm/`:
- `run_turn.py` — the event-consumer loop · `tools.py` — tool dispatch + tier/approval gate · `intents.py` — intent registry
- Dynamic triage: `triage_normalize.py`, `triage_preflight.py`, `triage_scenarios.py`, `triage_sources.py`, `triage_prompt.py`
- Providers: `anthropic_provider.py`, `fake_provider.py`, `lmstudio_provider.py`, `factory.py` (fake/lmstudio = no-cost local iteration)

**The prompts** (the primary tuning levers) — `fsr_playbooks/agent/`:
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

### B2 · Hunt — proactive, hypothesis-driven  ·  HIGH  ·  🟡 gate + offline tests landed; live re-baseline pending
Lever: *Hunting instincts*. Measure hunt **depth** (lateral pivots from a single IOC),
**breadth** (independent hypotheses tried), and stop-criteria (no endless flailing —
ties to `investigation_tool_budget`). New gate: `hunt_depth` on a seeded multi-hop
scenario (the wendy.smith → smithDesktop → 10.50.60.70 → 102.220.160.21 chain).

**Done (offline, 2026-06-08):** `hunt_depth` gate added to
`scoring._score_investigation_quality` — opt-in per fixture via an
`investigation_quality.hunt_chain` (ordered list of pivot-stage fact-matchers,
reusing `_fact_matches`). **Depth** = stages reached, gated at `min_hunt_depth`
(default = chain length); **breadth** = distinct connectors exercised across the
hunt, gated at optional `min_hunt_breadth` (default 0, reported either way);
**stop-criteria** stays on the existing `investigation_tool_budget`. A fixture
without `hunt_chain` skips the gate (depth only means something on a defined
chain). Lever already mapped (`levers.LEVER_MAP["hunt_depth"]` →
`system_prompt_triage.md §Hunting instincts`); `test_lever_coverage` stays green.
Offline pin `python/tests/test_hunt_depth.py` (6 cases) wired into `make chat-fast`
(141 pass ~2s). Wired onto the real seeded fixture
`tasks/29_invest_defense_evasion_host.json` (`min_hunt_depth: 3` — must pivot past
the host into the internal IP; stage 4 = external C2 reported, not required), with
the prompt broadened to "follow the indicators where they lead".

**Pending (live, needs credits — gpt-4o-mini re-baseline):** drive task 29
(`make chat-drive SCENARIO=invest_defense_evasion_host`) to (a) confirm the seeded
IP chain actually surfaces on incident `b4a62c3b…`'s related records, (b) see how
deep gpt-4o-mini hunts vs the bar, (c) tune `system_prompt_triage.md` §Hunting
instincts if it stops at the host, then capture a golden. Per the provider-coupling
note, baseline on the new provider before pinning a live bar.

### B3 · Triage — assessment correctness  ·  HIGH
Levers: `triage_normalize/classify/scenarios` + *What you do* / *Hard rules*. Score
severity/verdict correctness, low-signal handling (don't over-escalate a benign
alert), and scenario classification accuracy. New gate: `triage_assessment` against
labeled scenarios in `triage_scenarios.py`.

### B4 · Triage → Build fidelity  ·  CRITICAL  ·  🟢 action_coverage 1.0 LIVE-PROVEN (0.3.125, 2026-06-06) — staged containment now replayed into the trace-built playbook; grounding 1.0 CLOSED & LIVE-PROVEN on 0.3.126 (2026-06-07) — muted wrapper-internal execute_api_request fan-out; build_fidelity PASS (grounding 1.0, action_coverage 1.0)
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

**`action_coverage` gap — FIX IMPLEMENTED (option i), offline-proven, pending live
re-drive.** The staged containment `fortigate-firewall.block_ip_new` was ABSENT from
the built playbook because it was only **staged** (`emit_action_card`), never executed,
so it wasn't in the recorded trace and the compiler couldn't replay it. **Implemented
option (i): record staged action_cards into the session trace.**
- `SkillCall.staged: bool` flag (default False; omitted from `to_dict` when False so
  legacy fixtures are unchanged; round-trips through JSON).
- `SkillTrace.record_staged_action(connector, op, params, …)` appends a
  `run_connector_action` SkillCall with `observed_output=None`, `staged=True`. Deduped
  by `(connector, op)` against ALL prior calls — re-emitting the card, or staging an
  op that later actually executes, adds only one step (the executed one with its real
  output wins). Module-level `record_staged_action` convenience = no-op when no active
  trace (studio/tests).
- `emit_action_card` (`tools_emit.py`) calls it after its grounding+param validation
  passes, so a staged containment lands on the trace.
- The existing `insert_containment_guard` then gates the replayed containment behind a
  synthesized malicious-verdict decision (safe-by-default), and `wire_record_inputs`
  parameterizes its IOC to the trigger record.
- Tests: `fsr_playbooks/tests/test_staged_action_coverage.py` (8 cases incl. end-to-end
  trace→YAML with a guarded `Block Ip New` step). `make verify` green (336 + 159).
- fsr_playbooks is a **symlink** from the connector → no manual vendor; `deploy.sh` rsyncs
  it into the install package.

**LIVE-PROVEN on 0.3.125 (2026-06-06).** Re-drove the chain (real C2 alert
`54f25f1f…`, `scripts/prompt_loop.py --file _b4_chain.json`, turn 1 triage → turn 2
build). **Two findings:**

1. **A second, latent blocker was the actual cause — `build_playbook_from_trace` was
   never registered.** It sat in the connector's `_BUILD_ONLY_TOOLS` but was **missing
   from `SAFE_TOOLS`**, so it was never in the dispatch registry, never advertised, and
   the provider's intent-slice backstop rejected it (*"intent does not permit it"*) even
   under build intent. The agent ALWAYS hand-authored instead. The earlier "grounding
   1.0 / trace-compiler-first" claim was wrong — the transcripts show the tool rejected,
   then a hand-authored playbook. Fix: added it to `SAFE_TOOLS` (tier 0) + regression
   test (`225d197`). Now the agent calls it first and it succeeds.

2. **`action_coverage 1.00` — CLOSED & live-proven.** With (1) fixed + the staged-action
   trace recording (`6d316f4`), the trace-built playbook now contains the staged
   `fortigate-firewall.block_ip_new` step (`Block Ip New`). `score_build_fidelity` on the
   live transcript: `action_coverage 1.0`, `missing_actions []`. Export:
   `ConnectorsV2/fsr-playbook-builder/exports/loop-b4_triage_build-loop-98594b07-1780797507.json`.

**NEW open gap — `grounding 0.83` (fails the 1.0 gate).** The built playbook carries
6 `fortinet-fortisiem.execute_api_request` steps that aren't in the named-op
investigation set `{virustotal.query_ip, ip-quality-score.get_ip_reputation,
fortinet-fortiguard-ioc.ioc_search, fortinet-fortisiem.get_ip_context}`. Turn 1 made
exactly those 4 NAMED run_op calls — so a named op (FortiSIEM `get_ip_context`,
FortiGuard `ioc_search`) fans out to multiple raw `execute_api_request` HTTP calls that
`record_run_op` captures as generic `execute_api_request` SkillCalls. **Pre-existing
trace-recording fidelity issue, newly VISIBLE now that the compiler actually runs.**
Options: (i) don't record `execute_api_request` sub-calls when they're the
implementation of a named op already on the trace; or (ii) collapse/relabel them to the
parent named op; or (iii) count `execute_api_request` as grounded when its connector
matches an investigated op.

**FIX IMPLEMENTED (option i) — CLOSED & LIVE-PROVEN on 0.3.126 (2026-06-07).** Triaged the
emitting layer: the 6 steps are the submit→poll→fetch `run_op(...,"execute_api_request")`
fan-out inside `_siem_pubv2_query` (`tools_triage.py`) — the engine behind every
`siem_search_*` / `siem_events_for_incident` MCP pivot. The agent never called
`run_op` for them directly (they're not in `investigated`), so the named MCP wrapper's
internal connector calls were polluting the trace as raw-HTTP build steps. Fix:
- `skill_trace.mute_recording()` context manager + `_mute_depth` counter;
  module-level `record_run_op` no-ops while muted (nests safely, unwinds on exception).
- `_siem_pubv2_query` brackets its 3 internal `execute_api_request` call sites in
  `mute_recording()`; `_siem_run` (the `get_associated_events_new` path shared by the
  same pivots) brackets its `run_op` too — so NO wrapper-internal connector call lands
  on the build trace, only the analyst's direct `run_op` calls + staged actions.
- Tests: `test_skill_trace.py::test_mute_recording_*` (suppress + exception-unwind).
  `make verify` green (339 + 159). `fsr_playbooks` is symlinked into the connector → no vendor.
- Grounding math: built is a SET of `(connector, op)` pairs, so the 6 steps were one
  ungrounded pair `(fortinet-fortisiem, execute_api_request)` → 5/6 = 0.83. Muting drops
  that pair → built = {4 named + staged} ⊆ investigated → expect `grounding 1.0`.

**LIVE-PROVEN.** Deployed 0.3.126 (8/8 workers) + re-drove the chain
(`scripts/prompt_loop.py --file _b4_chain.json --scenario b4_triage_build`, real C2 alert
`54f25f1f…`, session `loop-f279bdb5`). Built playbook = {virustotal.query_ip,
ip-quality-score.get_ip_reputation, fortinet-fortiguard-ioc.ioc_search} + staged
`fortigate-firewall.block_ip_new` — **ZERO `fortinet-fortisiem.execute_api_request`
steps** (the `siem_events_for_incident` fan-out is now muted). `score_build_fidelity`:
**grounding 1.0, action_coverage 1.0, PASS**. Export
`exports/loop-b4_triage_build-loop-f279bdb5-1780842267.json`. **Still open:** pin this as
a fast offline golden; the parameterized-to-trigger-record check beyond ops-overlap.

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
