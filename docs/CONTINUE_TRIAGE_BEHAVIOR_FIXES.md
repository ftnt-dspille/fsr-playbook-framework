# Continue: triage agent behavior fixes

Created 2026-06-02. Source evidence: widget export
`fsr_all_widgets/widgets-src/fsrPlaybookBuilder/exports/fsrpb-chat-sess-kysr33eq-1780430936817.md`
(session `sess-kysr33eq`, widget v1.1.2, connector 0.3.94, contract 2.8.0).

All work is in **`FSRPlaybookYaml/fsr_core`** (canonical). The connector vendors a
copy via `build.sh` — do NOT edit the connector copy; re-vendor at the end. Tests
run via the `.venv` (`make tests` / `./.venv/bin/python -m pytest`), never system python.

## The evidence (what the export showed)

User typed two low-signal messages — `test` (turn 1) and `what's next` (turn 3) —
over incident `192.168.77.24 → 87.224.7.73` (FortiSOAR id 563). For each turn the
agent fired ~9 tools but emitted **zero analyst-facing text**. Whole-session usage:
**668 output tokens** vs 10,759 in. Symptoms map to 4 problems below.

---

## Problem 1 — No written assessment (highest impact, do first)

Both turns ended `stop_reason=end_turn` with the last assistant block containing only
tool calls + one IOC card, no narrative. The agent looks like it "didn't answer."

**Fix options (pick A, fall back to B):**
- **A. Post-loop guarantee.** In `fsr_core/llm/run_turn.py`, after the tool loop
  completes, inspect the final assistant content. If it has no text block (only
  tool_use/cards), issue ONE more model turn with a forced directive: *"Summarize
  the triage: what you found, severity verdict, and the single recommended next
  action. Do not call tools."* Emit that text as the closing block.
- **B. Prompt-only.** In `triage_prompt.py`, add a hard rule: "Every turn MUST end
  with a written assessment (findings → verdict → next action), even after tools."
  Cheaper but model may still skip it — prefer A, keep B as reinforcement.

**Tests:** new test in `tests/` driving the fake provider to return a tools-only
final block → assert a text/assessment block is appended. Assert no extra model
call when the final block already has text (don't double-summarize).

Files: `run_turn.py` (~lines 250–340 where stop_reason/final is set), `triage_prompt.py`.

## Problem 2 — `what's next` re-ran the identical investigation

Turn 4 repeated turn 2's tool sequence byte-for-byte instead of advancing. It
ignored already-established facts (87.224.7.73 = clean/GB/Spitfire).

**Fix:** carry a compact "investigation state so far" into the next turn's context —
either (a) ensure prior turns' tool results survive context assembly (check the
trim/summarize path in `_loop_helpers.py` / `triage_normalize.py`), or (b) inject a
short synthesized "Established so far:" preface built from prior tool results. Prompt
rule: "Do not re-run enrichment already completed this conversation; advance to the
next logical step (containment / response)."

**Tests:** two-turn fake-provider scenario; assert turn 2 does NOT re-issue an
enrichment op already successful in turn 1; assert it proposes a next step.

Files: `_loop_helpers.py`, `triage_normalize.py`, `triage_prompt.py`.

## Problem 3 — Trivial input (`test`) launched a full 9-tool hunt

A one-word `test` should not trigger autonomous investigation.

**Fix:** add a low-signal input gate in the triage pre-flight
(`triage_preflight.py` / `intents.py`). Classify trivial/greeting/test/empty-direction
messages; for those, respond conversationally (orient on the case + offer choices)
or ask one clarifying question — skip the auto-investigation. `what's next` is
"continue" intent → summarize state + propose next step (ties into Problem 2).

**Tests:** classifier unit tests for `test`, `hi`, `what's next`, and a real
directive ("build the attack timeline") — only the last should auto-investigate.

Files: `triage_preflight.py`, `intents.py`.

## Problem 4 — Repeated self-correctable SIEM 400s

`siem_events_for_incident` and `siem_search_ip` both 400'd because the agent passed
the **FortiSOAR record id (563)** instead of the **FortiSIEM `incidentId` (11521)** —
which is present in `alert.sourcedata.incident_data.incidentId`. Same 400 recurred in
both turns; no adaptation.

**Fix:**
- When building FortiSIEM op params, resolve `incidentId` from the linked alert's
  `sourcedata` rather than the FortiSOAR id. Check the SIEM tool wrappers in
  `fsr_core/llm/tools.py` (`siem_events_for_incident`, `siem_search_ip`).
- Add a repeated-error guard: if an op returns the identical `code/op/query` 400
  twice, stop retrying that shape and surface the blocker in the assessment.

**Tests:** fake SIEM op returning 400 with the incidentId hint → assert the agent
re-resolves incidentId from sourcedata OR stops after one retry (no infinite/dup).

Files: `tools.py` (SIEM wrappers), loop guard in `run_turn.py` / `_loop_helpers.py`.

---

## Suggested order
1. **P1 forced assessment** — biggest perceived-quality win, smallest blast radius.
2. **P3 low-signal gate** — stops the "test → 9 tools" overreaction.
3. **P2 no-repeat / advance** — needs P3's intent classification.
4. **P4 SIEM grounding** — independent; can parallelize.

## STATUS — 2026-06-02 (all four implemented + tested, offline-green)

- **P1 forced assessment — DONE.** Option A in `anthropic_provider.py`. New
  `_wrapup_call` helper does ONE no-tools round; the `end_turn` branch fires it
  when the turn ran tools but the final assistant block has no text
  (`any_tools_run and not final_text`), capped by `assessment_forced`. The
  max-tool-turns tail was refactored onto the same helper. Tests:
  `fsr_core/tests/test_forced_assessment.py` (forces when tools-only; no extra
  call when final has text; never for a pure-text turn).
- **P3 low-signal gate — DONE.** `intents.classify_message` →
  `trivial|continue|directive` + `gate_directive`; `triage_preflight` takes
  `user_message`, appends the gate, returns `message_class`. Wired in
  `demo_hunt.py` and the connector (`operations._resolve_system_prompt` now
  threads `user_message=_clean_latest_user`). Tests:
  `test_low_signal_gate.py` + connector `test_resolve_system_prompt_triage_low_signal_gates`.
- **P2 no-repeat/advance — DONE (prompt-side).** New "Across turns — advance,
  don't restart" rule in `system_prompt_triage.md` + the `continue` gate from
  P3. Test: `test_triage_prompt.py::test_base_prompt_has_no_repeat_across_turns_rule`.
- **P4 SIEM grounding + repeated-error guard — DONE.** Grounding was already in
  the prompt/normalizer (incidentId from sourcedata). Added an in-turn
  repeated-error guard in `anthropic_provider._guarded_dispatch`: an identical
  `(name, args)` shape that already failed this turn is NOT re-run — returns a
  `repeated_call_guard` envelope telling the model to adapt or report. Test:
  `test_repeated_error_guard.py`.

`make verify` green: 213 fsr_core + 154 connector. NOTE: connector's `fsr_core`
is a **symlink** to canonical in-tree, so no manual re-vendor needed for tests;
the rm-rf/recopy vendoring only happens at package/deploy time.

### LEFT (deploy + live — not done here)
- Bump connector version, `deploy.sh`, verify the hunt UX renders in the widget
  (ad-hoc Playwright per the no-page-tester rule). Contract unchanged (no
  envelope shape change), so no contract bump.

## Definition of done
- New unit tests for each problem, all green via `.venv` (`make verify`).
- A two-turn end-to-end fake-provider scenario reproducing the export's `test` /
  `what's next` flow now yields: a written assessment each turn, no duplicated
  enrichment, and a sane response to trivial input.
- Re-vendor into the connector (`build.sh`), bump connector, deploy, and verify the
  hunt UX renders in the widget (ad-hoc Playwright per the no-page-tester rule).
- Bump contract only if the envelope shape changes (it shouldn't for these).
