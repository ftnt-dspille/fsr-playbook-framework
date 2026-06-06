# Chat Intelligence Plan — tune & enhance the investigation→build agent

**Created:** 2026-06-05 · **Status:** Phase 0 not started · **Owner loop:** iterative (Claude + Dylan)

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

### A4 · Fast local loop + live gate  ·  MEDIUM · small
Make `fake_provider` / `lmstudio_provider` the default for **structure** tests
(prompt assembly, tool-registry, intent routing — no API cost), and keep
`calibrate_investigation` (live, Anthropic) as the periodic **capability** gate.
Document the split so I reach for the cheap loop by default. *DoD:* `make chat-fast`
(local, seconds) vs `make chat-calibrate` (live, gated).

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

### B4 · Triage → Build fidelity  ·  CRITICAL
Levers: `system_prompt_build.md` *Triage → build handoff* + *Canonical skeleton*.
The built playbook must actually **automate what was investigated** — same
ops, parameterized to the trigger record, compiling + runnable. Reuse build tasks
`01_…`–`10_…` and `build_trace_fixture`. Gate: `build_fidelity` (ops-overlap with the
investigation) + existing compile/`run_playbook` success.

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
