# Agent hardening plan — path to SOC-deployable

**Why this exists.** The [Agentic IR&R Architecture Review](../AGENTIC_IR_ARCHITECTURE_REVIEW.md)
(2026-05-30) found a sound spine with a cluster of trust-breaking gaps. This plan orders the fixes
into shippable phases. It is the **actionable companion** to that review — the review is the
durable assessment; this is the backlog.

**Bar:** "a SOC analyst trusts this to investigate and stage containment with appropriate
human-in-the-loop." Phases are ordered by `severity × value`. Effort: `small (1–3h)`,
`medium (4–12h)`, `large (1–3d)`.

**Where edits land:** all `fsr_core` changes go in **`FSRPlaybookYaml/fsr_core`** (canonical). The
connector vendors it via `scripts/build.sh`; never edit the vendored copy under
`ConnectorsV2/fsr-playbook-builder/fsr-playbook-builder/fsr_core`. After landing, re-vendor + bump
`info.json` + `scripts/install_to_fsr.py`.

---

## ✅ Phase 0 — Authoring loop SAFE_TOOLS (absorbed from AGENT_TOOL_REGISTRY_FIX_PLAN.md, verified 2026-05-30)

All authoring tools are in `SAFE_TOOLS`, `TOOL_TIERS`, and the built `REGISTRY`. Verified by `python -c "from fsr_core.llm.tools import REGISTRY; print(sorted(REGISTRY))"`. Tiers correct: `validate_yaml`/`compile_yaml`/`analyze_playbook` at tier 0; `why_did_playbook_fail`/`get_run_env`/`list_playbook_runs`/`assert_playbook_outcome` at tier 1; `push_playbook`/`run_playbook`/`dry_run_playbook` at tier -1 (dynamic, HITL-gated). Only intentional omission: `find_step_recipe` (corpus not populated). `MAX_TOOL_TURNS = 16` (raised from 12); live calibration run did not hit the ceiling.

---

## ✅ Done (2026-05-30)

- **Op-name existence validation** — `_shared._validate_op_exists` (offline store) +
  `tools_execution._validate_op_live` (live fallback) + `emit_action_card` guard + triage prompt
  "never guess an op name." Tests: `python/tests/test_op_existence.py` (10). Returns
  `unknown_operation` with near-matches; agent self-corrects within the turn. This is the **template**
  for Phase 1.1 below.
- **1.1 Argument validation against the op schema** — `_shared._validate_op_params(connector, op,
  params)` loads top-level `operation_params` and flags unknown params (typo detector + near-match),
  missing-required, out-of-set select values, and gross type errors. No-ops when no params are
  catalogued; skips Jinja-templated values; ignores conditional sub-params; type checks are loose
  (FSR coerces `"5"`→5). Wired into `run_op` (before the execute POST) and `emit_action_card` (before
  rendering). Tests: `python/tests/test_op_params.py` (11).
- **1.2 Tool errors marked `is_error`** — `anthropic_provider._is_error_result` recognizes both the
  `{ok: false}` envelope and bare `{error: …}`; applied to all three `tool_result` build sites
  (stream loop + the two resume-path blocks). Made the `anthropic` SDK import lazy so the module +
  its pure helpers import without the SDK installed. Tests: `python/tests/test_tool_result_is_error.py`
  (5).
- **1.3 Mutating-op gate — resolved via existing tier gateway (MVP).** The human-approval guarantee
  is already structural at the `dispatch` layer: a mutating `run_op` resolves to tier 3/4 and returns
  a `pending_approval` envelope (no execution) unless `_approved=True`, which is set *only* by the
  connector's `_resume_action_card_execute` after a human approves the card. The connector also
  auto-cards a mutating `run_op` so the agent can't execute one silently. Per product direction
  (2026-05-30): MVP with normal agents — dangerous mutations ask a person; an "allow once / always
  allow per-tool" memory mechanism is explicitly out of scope for now. No `run_op` code change made.
  Residual gap: the LM Studio provider auto-executes tier-3+ (bypassing this gate) — tracked as **3.3**.
- **1.5 Widget contract version aligned** — widget `WIDGET_CONTRACT_VERSION` `2.0.0`→`2.1.0`
  (`view.controller.js:34`) to match connector `CONTRACT_VERSION = "2.1.0"`; the
  `incident_smtp_intrusion` fixture bumped to match. Contract-drift e2e tests pass.
- **2.1 `get_record` tool** — `tools_triage.get_record(iri | module+uuid, relationships=True)`
  wrapping `GET /api/3/<module>/<uuid>?$relationships=true`; tier-1 read-only, in `SAFE_TOOLS` +
  `TOOL_TIERS`. Normalises pasted IRIs (leading slash / querystring), maps 404→`not_found`. Closes
  the prompt↔tool gap behind the attack-timeline / blast-radius quick actions. Tests:
  `python/tests/test_get_record.py` (6). Also fixed a pre-existing `make verify` failure: the 1.1
  param guard had broken `test_sim_run_op_integration::test_search_events_returns_ordered_sequence`
  (called `search_events` with empty params → now-required `attribute`/`select_clause` missing);
  test updated to pass valid params. **Still needs re-vendor into the connector** (`scripts/build.sh`
  + `info.json`/`install_to_fsr.py` bump) before the tool is live on the box.

  **Still open in Phase 1: 1.4** (investigation-quality eval family — large).

---

## Phase 1 — Trust-critical (do first)

### 1.1 Argument validation against the operation schema  ·  HIGH · medium  ·  ✅ DONE
The op *name* is validated; its *arguments* are not. `run_op` posts params straight to FSR; required
fields, types, and select-option membership are all checked only at execution → analysts approve
invalid cards that fail post-approval.
- **Add** `_validate_op_params(connector, op, params) -> dict|None` (mirror `_validate_op_exists`):
  load `operation_params` (required, type, `options_json`, bounds); flag unknown params (typo
  detector), missing required, bad types, out-of-set select values; return `_err('bad_params', …,
  suggestions=[…])`.
- **Call sites:** `run_op` (before the execute POST) and `emit_action_card` (after the op-existence
  check, before rendering the card).
- **Test:** required-missing and bad-select cases → card not rendered, agent re-calls with complete
  args; analyst never sees the incomplete card.

### 1.2 Tool errors marked `is_error`  ·  CRITICAL · small  ·  ✅ DONE
`anthropic_provider.py:398-404` builds `tool_result` with content only. Add
`"is_error": isinstance(result, dict) and "error" in result` (also recognize the `{ok: false}`
envelope). Without it the self-repair loop is guessing.
- **Test:** mock a transient connector 500 → next loop escalates/alternates instead of blindly
  retrying; error logged as `is_error`.

### 1.3 Structural gate on mutating ops in `run_op`  ·  HIGH · medium  ·  ✅ DONE (via tier gateway — see above)
Make the triage rule real: in `run_op`, if `confirm=True` and the op's category is
containment/remediation/destructive, return `_err('confirm_not_allowed_in_triage', …,
suggestions=['use emit_action_card'])` instead of executing. Reword the prompt from aspiration to
fact ("`run_op(confirm=True)` on a mutating op raises an error").
- **Test:** triage task with a destructive op → `run_op(confirm=True)` errors; agent switches to
  `emit_action_card`.

### 1.4 Investigation-quality eval family  ·  CRITICAL · large  ·  ✅ GATE STRENGTHENED (2026-05-30)
Add 4–5 investigation-scope tasks scored on **recall** (`facts_fetched / required_facts`), not YAML
shape: phishing (email/URL/sender-IP pivots), lateral movement, data exfil, a **negative case**
(internal RFC1918 IP → refuse external TI), and **graceful partial failure** (TI timeout → flag the
gap distinctly from "no threats"). Gate: `investigation_recall >= 0.8`.
- **Test:** phishing task audit log shows the expected `get_record`/`run_op` pivots; computed recall
  meets gate.

#### Live calibration run — 2026-05-30 (`store/eval_runs/calibrate_20260530T192043Z.{log,summary.json}`)
Drove all 5 investigation fixtures through the REAL Haiku triage loop on the forticloud box
(`python/evals/calibrate_investigation.py --capture`). **Result: 5/5 at recall 1.0** — which is the
problem, not the win. Reading the captured traces (`python/evals/golden_traces/*.json`) surfaced that
**the gate is too weak to be meaningful** and a real grounding gap:

- **GATE TOO WEAK (do first).** Each fixture requires only ~2 facts (`get_record` + one enrichment).
  A run that flails for 20 calls, guesses param names five times, and never stages a deliverable still
  scores 1.0. 5/5 passing tells us almost nothing. Strengthen per-fixture:
  - **Tool-budget ceiling** (e.g. ≤ 10 calls) so flailing fails — mirror `tool_budget` gate.
  - **Forbidden: same op retried >2× with different params** (the grounding-flail signature).
  - **c2 / mail_egress:** require the correlation pivot (search `incidents`), not just one enrichment.
  - **containment-capable cases:** require a concrete deliverable — `emit_action_card` OR
    `emit_choice_card` + capability-gap noted. (On THIS box `find_containment_actions(ip/host)` returns
    count=0 — no containment connector configured — so `emit_choice_card` IS the correct ending; the
    gate must credit that, not demand a card that can't exist here.)
- **PARAM-GROUNDING FLAIL (real, = deferred half of 1.6).** `invest_excessive_mail_egress` burned
  6 `find_operation` + 2 `get_op_schema` + repeated `run_op` retries cycling `ip`→`ip_address`,
  `indicator`±`indicator_type`. `_validate_op_params` only checks against the OFFLINE store; when the
  op isn't catalogued it no-ops, so the agent discovers the real param names by trial-and-error live.
  Extend grounding to validate args against the **live op-schema** when the store is un-synced
  (the roadmap item flagged under 1.6 / TODO next-step #4).
- **NON-issues (checked, withdrawn):** `emit_choice_card` instead of `emit_action_card` is correct
  (no containment op configured). `confirm=true` clearing a failing read op is NOT a gate hole —
  `_validate_op_params` runs (tools_execution.py:751) BEFORE the confirm gate (:778); `threat_intel_
  search` is tier-2 but flagged not-auto-safe, so `requires_confirmation` → retry-with-confirm is the
  designed path.
- **Golden-trace caveat.** The 5 captured traces encode the flailing above, so they are NOT usable
  as-is as "known-good" golden fixtures for the intended offline (no-AI) regression test. Either
  hand-curate the minimal expected pivot sequence per fixture, or pair the snapshot with the
  strengthened quality assertions above before freezing.

**Offline-test goal (the cost lever):** one live-AI canary (`calibrate_investigation.py`, run by hand
when prompt/model/tools change) + everything else free & deterministic — scorer unit tests (exist),
a golden-trace replay through `_score_investigation` (new, blocked on the caveat above), tool-shape
tests via the connector contract harness. Keep the live loop OFF `make verify`.

#### Gate strengthening shipped — 2026-05-30
Recall is no longer the only gate. `scoring._score_investigation_quality(trace, quality)` adds three
deterministic per-fixture gates, threaded through `Task.investigation_quality` → `score()` → harness +
`calibrate_investigation.py`:
- **`investigation_tool_budget`** — tighter ceiling than the authoring `tool_budget` (default 12;
  env `EVAL_INVESTIGATION_TOOL_BUDGET_MAX`). The loose authoring `tool_budget` (20) is demoted to
  informational in investigation mode so it isn't double-counted.
- **`investigation_no_param_flail`** — fails when the same `(connector, op)` is invoked with > N
  distinct arg-sets (default 2), the grounding-flail signature (`ip`→`ip_address`→`indicator`). A
  retry that only adds `confirm:true` collapses to one arg-set (the designed confirm-gate path, not a
  guess).
- **`investigation_deliverable`** — requires staging a concrete deliverable for the analyst; **credits
  `emit_choice_card` / `emit_capability_gap_card`**, not just `emit_action_card`, so a box with no
  containment connector still passes. `require_deliverable:false` marks it skipped for restraint /
  correlation-verdict fixtures (27, 28).

Fixtures: 25/26 gained the correlation pivot (`search_module_records` on incidents) as a required
fact + `require_deliverable:true`; 29 `require_deliverable:true`; 27 tighter budget (8) +
`require_deliverable:false`; 28 `require_deliverable:false`. **Golden-trace replay through the
strengthened gates: 3/5 PASS** (down from the meaningless 5/5) — `invest_excessive_mail_egress`
fails on budget (19 calls), `invest_outbound_cleartext_c2` fails deliverable (ended after `run_op`
with nothing staged). The two failures are the genuinely-weak runs; the gate now has teeth.
Tests: 9 new in `test_evals_investigation_recall.py` (17 total, all green; full fast suite 753 green).
Remaining 1.4 follow-ups: ✅ param-level live grounding now done (see §1.6) + hand-curated golden
traces (the captured ones now correctly fail, so still not freezable as known-good).

### 1.9 Probe-latency fix — concurrent + scoped healthchecks  ·  HIGH · small  ·  ✅ DONE (2026-05-30)
Surfaced by the calibration run: a single `list_configured_connectors(probe=True)` took **~5 minutes**
— it healthchecked all ~45 configured connectors **serially**, with **no per-call timeout** on the
inline GET. This hits the live ANALYST triage loop identically, not just the eval.
- `list_configured_connectors` now fans healthchecks out **concurrently** (`_healthcheck_many` thread
  pool, reuses `tools_execution._live_healthcheck`'s `timeout=8`); added an internal `only=<names>`
  param to probe a subset.
- `find_containment_actions` now lists **unprobed** (cheap), narrows to the few connectors that carry
  a matching containment op via the store, then probes **only those** — not all 45.
- Live-verified: `find_containment_actions(ip)` went **5 min → 1.2 s**. Tests:
  `python/tests/test_probe_parallel_scoped.py` (concurrency + scoping + zero-probe). **Still needs
  re-vendor into the connector** (`scripts/build.sh` + version bump) before it's live on the box.

### 1.5 Align widget contract version  ·  CRITICAL · small  ·  ✅ DONE
Widget `WIDGET_CONTRACT_VERSION = '2.0.0'` vs connector `2.1.0` →
`view.controller.js:34` → `'2.1.0'`. Removes negotiation noise. (Low real severity — non-strict mode
only `console.warn`s — but trivial and noise-removing.)

---

### 🟢 Live-triage failure — `sess-uq31go5p` (2026-05-30, forticloud box, v0.3.28) — RESOLVED
Gap **A** closed by 1.6 (shared `validate_op_grounded` on the emit path), gap
**B** by 1.7 (self-healing resume), and the same-session token waste by 1.8
(`full=True` cleaned + capped). `make verify` green; re-vendor + connector
version bump still pending to ship live. Original analysis preserved below.


Captured in a real triage hunt (export: `fsr_all_widgets/widgets-src/fsrPlaybookBuilder/exports/
fsrpb-chat-sess-uq31go5p-…md`). Investigating the smithDesktop defense-evasion incident, the agent
emitted an `action_card` for **`virustotal.lookup_hash`**, the analyst approved it, and on resume the
execute returned `unknown_operation: operation 'lookup_hash' not found on connector 'virustotal'
(18 ops catalogued)`. The turn then **ended** with a templated "⚠️ … did not complete … contain
manually" message. Two independent defects, both trust-critical:

**A. A phantom op reached the analyst as an approval card (grounding-guarantee gap).**
The contract (`FSR_PLAYBOOK_BUILDER_CONNECTOR_CONTRACT.md` §"action_card / Grounding guarantee")
promises a hallucinated/typo'd op *never* reaches the widget as a card, validated against the
"offline reference store, **with a live connector-definition fallback**." Reality: `emit_action_card`
(`tools_emit.py:226`) calls only `_validate_op_exists` (offline store). That function **no-ops when
the connector has 0 ops catalogued** (`_shared.py:156`) — exactly the case for the un-synced
`virustotal` entry on this box. The **live fallback `_validate_op_live`** that would have caught it
is wired into `run_op` only (`tools_execution.py:690-693`, gated on `store_ops_count == 0`) and was
never added to `emit_action_card`. So the offline check passed vacuously at emit time, the card was
rendered, the human approved a phantom, and `run_op`'s live fallback only caught it post-approval.
This is *why* "it shouldn't be possible" yet happened: the guarantee's offline half shipped into
`emit_action_card`, its live half did not.

**B. The self-heal loop never ran after approval (deterministic one-shot dead-ends).**
`run_op` returned a well-formed `unknown_operation` envelope with `suggestions: [find_operation…,
get_op_schema…]` — the exact breadcrumbs for self-correction. They went nowhere.
`_resume_action_card_execute` (`operations.py:1528`) executes the approved op **once** via a direct
`dispatch("run_op", …)`, runs the result through `_summarize_exec` (templated text, no LLM), and
returns `stop_reason: end_turn`. It **never re-enters the provider loop**, so a *correctable* failure
(`unknown_operation` / `bad_params`) is handled identically to a genuine infra failure: apologize,
tell the human to "contain manually," stop. The deterministic path is deliberate (docstring: survive
an Anthropic outage; human already approved) but it conflates "this action can't be fixed" with "the
model named the wrong op and the error tells it how to fix it."

### 1.6 `emit_action_card` live op-existence fallback  ·  CRITICAL · medium  ·  ✅ DONE
**Shipped.** Factored `validate_op_grounded(connector, op, client=None)` into
`tools_execution.py` (offline `_validate_op_exists` → store-count gate → live
`_validate_op_live`, fail-open on any client/preflight/lookup hiccup). `run_op`'s
gated block and `emit_action_card` both call it; emit resolves a live client
lazily via `_live_client_for_grounding`. Tests: `tests/test_op_existence.py`
(live-fallback blocks phantom on un-synced connector, allows real, fails open
when live unavailable / raises).

**Param-level live grounding — ✅ DONE (2026-05-30).** The deferred half. The offline
`_validate_op_params` no-ops on an un-synced connector, so the agent discovered real param names by
trial and error live (`ip`→`ip_address`→`indicator`, the `invest_excessive_mail_egress` flail that
the strengthened §1.4 gate now catches). Closed at the source: `validate_op_grounded` gained a
`params` arg and now, on the un-synced (`store_ops_count == 0`) path, fetches the live op definition
**once** (`_fetch_live_op`) and grounds BOTH the op name (`_op_not_in_live`) and the argument names
(`_validate_op_params_live` — unknown-param typo detector + missing-required, loose by design;
select/type membership stays on the offline path). `run_op` passes `params=params`;
`emit_action_card` passes `params=args` so a card with a guessed param can't reach the analyst for an
un-synced connector. Fail-open throughout. 8 new tests in `test_op_existence.py` (18 total); `make
verify` green (41 + 111). **Needs re-vendor + connector bump to ship live** (offline-only until then).
Close gap **A**: make the emit-time grounding match `run_op`'s. In `emit_action_card`, after the
offline `_validate_op_exists` returns None *because the store had 0 ops for the connector* (not
because the op exists), fall back to the live connector definition before rendering the card.
- **Impl:** factor `run_op`'s gated block (`store_ops_count == 0` → `_preflight_connector` →
  `_validate_op_live`) into a shared helper (e.g. `_shared.validate_op_grounded(connector, op,
  client_factory)`), call it from both `run_op` and `emit_action_card`. `emit_action_card` has no
  client today → import `get_client` lazily (mirror `tools_execution`); on any client/preflight
  hiccup, **fail open** (return None) so a transient lookup never false-rejects a real op — same
  contract as `_validate_op_live`. Also extend `_validate_op_params` the same way once the live
  op-schema is fetched (arg-level grounding, the roadmap item the contract note flags).
- **Test:** `emit_action_card('virustotal','lookup_hash',…)` with an empty offline store but a live
  def exposing the real 18 ops → returns `unknown_operation` with near-matches; **no card emitted**.
  Real op (`virustotal`/`file_reputation` or whatever the live def lists) → card emitted. Live lookup
  raising → card still emitted (fail-open).

### 1.7 Self-healing resume on correctable execute failures  ·  CRITICAL · medium  ·  ✅ DONE
**Shipped** in `operations.py`. `_try_self_heal_resume` re-enters the provider
loop (via `_resume_conversation` with a `action_card_self_heal` resume tag) when
the post-approval execute fails with a code in `{unknown_operation, bad_params,
missing_required, bad_select_value}`; the agent self-corrects and emits a fresh,
human-re-gated card. Bounded to `_MAX_SELF_HEAL_PASSES = 2` per session.
**Review-gap closure:** the heal returns `None` (→ deterministic "contain
manually" + `end_turn`) on a non-correctable code, a spent budget, no provider,
**and on any provider error/outage during the heal** (the result carries an
`error`) — so the outage-survivable property the deterministic path protects is
preserved. Prompt reinforcement added (rule 3: never card an unconfirmed op).
Tests: `tests/test_chat_operations.py` (correctable→`awaiting_action_card`;
infra→deterministic `end_turn`).
Close gap **B**: when the post-approval execute fails with a *correctable* code, re-enter the agent
loop instead of dead-ending. In `_resume_action_card_execute`, after `dispatch("run_op", …)`:
- If `exec_result.ok` → keep today's deterministic summary + `end_turn` (T6 unchanged).
- Else if `exec_result.code in {"unknown_operation", "bad_params", "missing_required",
  "bad_select_value"}` (the validator-emitted, agent-fixable codes) → splice the `tool_use` +
  `is_error` `tool_result` (carrying `suggestions`/`near`) into the conversation and **resume the
  provider loop** so the agent runs `find_operation`/`get_op_schema` and emits a corrected
  `action_card` (a fresh `awaiting_action_card`, re-gated by the human). Bound it: at most 1–2
  self-heal passes, then fall through to the templated message so it can't spin.
- Else (transport/preflight/exec_dispatch_failed — genuine infra) → keep the deterministic "contain
  manually" message + `end_turn` (preserves the Anthropic-outage-survivable property).
- **Prompt reinforcement (secondary):** the triage prompt already says "never guess an op name";
  add that `emit_action_card` MUST be preceded by `get_op_schema(connector, op)` for any op the agent
  hasn't already confirmed this session. Structural fix 1.6 is the guarantee; this reduces the round-trips.
- **Test:** approve a card whose op is phantom → resume produces a `tool_result(is_error)` then a
  follow-up turn that calls `find_operation`/`get_op_schema` and emits a corrected card (not an
  `end_turn` apology). Approve a card whose connector is genuinely down → still the deterministic
  `end_turn` apology (no infinite resume).

### 1.8 Stop `get_record(full=True)` dumping the raw body into context  ·  HIGH · small  ·  ✅ DONE
**Shipped** in `tools_triage.py`. `full=True` no longer returns the raw body:
`_clean_full_record` strips null/empty + hydra/audit noise + `*SLA*` plumbing +
known boilerplate (`impactAssessments`, `escalation_rules`, …), then `_cap_json`
hard-caps to `_REC_FULL_MAX_BYTES = 8192` (head/tail truncation marker), with
`coerced_full=true` + a note flagged on the result. Docstring + triage prompt
(new rule 5) reinforce that `full=True` is forbidden in triage.
**Deviation from plan (a):** the intent-gated coercion isn't wired — there is no
active-intent signal reachable from `get_record` (tools are sliced by intent but
no contextvar is threaded). The structural half (clean + unconditional hard cap)
is intent-agnostic and is the real guarantee, so `full=True` is capped on every
path. Token-accounting under-count left as the separate audit the plan flags.
Tests: `tests/test_get_record_full_cap.py`.
Same session: the agent's very first tool call was `get_record(iri=…, full=True)`. `get_record`
defaults to a pruned ~5% triage projection (`tools_triage.py:50-51` — `_REC_MAX_STR=600`,
`_REC_MAX_REL=5`, indicator scalars + capped {iri,label} relationship index) **specifically** to
keep the per-turn token budget bounded; its own docstring says "`full=True` returns the raw ~100KB
hydrated body … do NOT set it during normal triage." The agent set it anyway. The raw incident body
— mostly `null` fields, the multi-paragraph `impactAssessments` boilerplate, `escalation_rules`, and
SLA plumbing, almost none of it useful for hunting/pivoting — then rides in `messages[]` and is
**re-sent to the model on every subsequent turn** of the session (and on the resume). Cost is real,
avoidable, and grows with session length. (Aside: the export's "1,143 input tokens" badly under-counts
this turn — the usage accounting is worth a separate audit, but the structural waste stands regardless
of the number.)
- **Impl (defense-in-depth, structural beats prompt):** (a) in `get_record`, when the active intent
  is `triage`, treat `full=True` as advisory — still return the pruned projection (or a "full-but-
  cleaned" body that drops `null`/empty fields, known-boilerplate prose, and `*SLA*`/`*Date` plumbing)
  and set a `coerced_full=false` flag + one-line note so the agent learns it didn't get the raw blob;
  (b) hard-cap any `full` body (e.g. ≤ ~8KB) with head/tail truncation so a single call can never dump
  100KB; (c) reinforce in the triage system prompt that `full=True` is forbidden and the pruned
  projection already has every pivotable field.
- **Test:** `get_record(full=True)` under `intent=triage` → returns pruned/cleaned body (no `null`
  spam, no `impactAssessments` wall), `summarized`/`coerced_full` flagged, total size under the cap;
  under a non-triage/debug path → raw body still available but size-capped.

---

## Phase 2 — Reliability & completeness

### 2.1 `get_record` / `get_related` tool  ·  HIGH · small  ·  ✅ DONE
The triage prompt tells the agent to pull event-level rows via `iri`/`module`/`uuid`, but no such
tool exists — it must construct blind `run_op` calls. Add `get_record(iri | module+uuid,
relationships=True)` wrapping crudhub GET (`/api/3/<module>/<uuid>?$relationships=true`) to
`SAFE_TOOLS` (tier 1, read-only). Closes the prompt↔tool gap behind the attack-timeline / blast-radius
quick actions. **Shipped** in `tools_triage.get_record`; tests `python/tests/test_get_record.py`.
Re-vendor into the connector still pending.

### 2.2 Stream timeout in the provider protocol  ·  HIGH · medium
`run_turn.py:230` `async for ev in provider.stream(...)` has no deadline → a hung API blocks the turn
forever. Wrap in `asyncio.timeout(300)` (or add `timeout_secs` to the `LLMProvider` protocol); emit
`ErrorEvent` then `DoneEvent` on timeout.

### 2.3 Surface skipped tools on partial-completion resume  ·  CRITICAL(loop) · medium
On approval mid-turn, the provider stubs `remaining_tool_calls` silently. Emit synthetic
`ToolUseEvent` + `ToolResultEvent` (flagged `synthetic`) so the transcript shows the interrupted
intent ("Tool X was not executed because approval was requested for Z").

### 2.4 Max-turn summary failure surfaces an error  ·  HIGH · medium
`anthropic_provider.py:443-497`: if the post-budget summary call throws, the loop still yields
`DoneEvent` — the agent looks finished. Retry once with small `max_tokens`, or emit an `ErrorEvent`
("hit max tool budget; summary failed — see history above").

### 2.5 Transient vs permanent failure in enrichment fan-out  ·  MEDIUM · medium
Classify `run_op` failures (`connector_not_configured`/`unhealthy` = permanent; timeout/5xx =
transient). On transient, return `connector_transient_failure` and prompt the agent to retry or
note the gap ("VirusTotal inconclusive due to timeout; proceeding with AbuseIPDB only") rather than
silently proceeding with no enrichment.

### 2.6 Cycle detection before predecessor use  ·  HIGH · medium
`validator.py`: run cycle detection *before* `_compute_predecessors`, so reachability analysis isn't
run on stale predecessor sets for cyclic graphs.

### 2.7 Text-coalescer `seq` alignment  ·  HIGH · medium
Increment `seq_in_turn` after `coalescer.flush()` (at tool boundaries), not on the first text append,
so transcript reconstruction by `seq` doesn't misalign.

### 2.8 Parallel read-only tool dispatch (hunt latency)  ·  HIGH · medium · ✅ DONE (2026-05-30)
Shipped in `anthropic_provider.stream`: the first tier-3+ call is the approval
boundary; every call before it (read-only, tier ≤ 2 by construction) fans out
via `asyncio.gather(asyncio.to_thread(dispatch, …))` capped at
`MAX_PARALLEL_TOOLS=8` (`_loop_helpers`), `tool_result` blocks emitted in
`tool_use` order, tier-3+ still suspends one-at-a-time as before. Test:
`fsr_core/tests/test_parallel_dispatch.py` (concurrency + order + mixed-tier
suspend). Live on connector 0.3.26+.

A live hunt's wall-clock is dominated by **sequential** tool round-trips: `anthropic_provider`'s tool
loop (`for i, (call_id, name, args) in enumerate(tool_calls): result = dispatch(...)`,
~line 366) awaits each call before the next, and every `run_op`/`get_record` waits on a slow upstream
(SIEM/TI/healthcheck). On the C2-scenario demo this was minutes, almost all of it I/O wait — not the
model. Claude already emits multiple `tool_use` blocks per turn; the initial gather (search
`alerts`/`incidents`/`assets`/`identities` for the record's indicators) and indicator enrichment
(one TI lookup per connector) are mutually independent.
- **Do:** in the provider tool loop, dispatch the **auto-tier (read-only, tier ≤ 2)** calls in a turn
  **concurrently** via `asyncio.gather(*[asyncio.to_thread(dispatch, name, args) …])`, preserving
  `tool_result` order (Anthropic requires one `tool_result` per `tool_use`, order-matched). Any
  **tier-3+** call still routes through the existing suspend/`pending_approval` path — those are
  staged one at a time, so leave the sequential path for them (e.g. if a turn mixes tiers, run the
  read-only ones in parallel first, then handle the first approval-needing call as today). Collapses
  fan-out latency from *sum* → *max*.
- **Caveat:** `dispatch`/`run_op` are sync and touch shared state (the connector `requests` session,
  in-process health/config caches in `tools_execution`, sqlite). Scope concurrency to read-only tiers;
  the caches are idempotent writes; keep a cap on max concurrent calls.
- **Already landed (prompt side, 2026-05-30):** `system_prompt_triage.md` now tells the agent to issue
  independent lookups together in one turn and to serialize only dependent pivots — so the model
  produces the parallel `tool_use` batches this item then executes concurrently. Also excluded
  `alienvault-otx` from enrichment (slow / frequent timeouts) in the same prompt edit.
- **Test:** a fake provider emitting 3 independent read-only calls in one turn → assert they run
  concurrently (wall-clock ≈ slowest, not sum) and `tool_result` blocks stay in `tool_use` order; a
  mixed read-only + tier-3 turn → read-only resolve, tier-3 still suspends.

---

## Phase 3 — Safety & auditability

- **3.1 HMAC-bind approvals** (HIGH, medium) · ✅ DONE (2026-05-30) — `approvals.bind()` binds
  `(approval_id, tool, args_hash, created_at)` under a server secret (`FSR_APPROVAL_HMAC_KEY`, else
  per-process random) at stash time; `AnthropicProvider.resume()` calls `approvals.verify()`
  (`hmac.compare_digest`) before re-dispatching and fails closed (`ErrorEvent` + `DoneEvent`
  `stop_reason=approval_unverified`) on mismatch. Closes store-tampering: swapped args change
  `args_hash`, so the token no longer matches. Surfaced to the widget as the new
  `approval_unverified` stop_reason (connector contract **2.2.0**). Tests: `test_approval_hmac.py` (7).
- **3.2 Persist suspended sessions** (MEDIUM, large) · ✅ DONE (2026-05-30) — `SqliteApprovalGateway`
  (sqlite + pickled `SuspendedSession`, TTL gc) in `fsr_core.llm.approvals`; module default gateway
  made swappable (`set_default_gateway`). Web backend installs one at startup (deferred from import
  so keyring isn't touched early) so both the provider stash side and the chat-route resolve side
  share one persisted store across a restart. Pins a stable `FSR_APPROVAL_HMAC_KEY` in the keyring
  secrets store so 3.1 tokens survive a restart (else fail closed). Tests:
  `test_approval_persistence.py` (5).
- **3.3 LM Studio provider approvals** (MEDIUM, large) · ⏸ DEFERRED post-MVP (2026-05-30) — per
  product direction the connector/widget run on Anthropic (Haiku) and won't use LM Studio, so its
  tier-3+ auto-execute gap is latent (only reachable from the Studio editor if an operator switches
  providers). Core keeps the provider. When resumed: give `LMStudioProvider` the same suspend/resume
  approval path as Anthropic in OpenAI message shape — **not** a refuse-guard (that would break
  legitimate Studio-editor LM Studio use).
- **3.4 Widen `args_hash` to full SHA-256** (LOW, small) and **mask + store args in `AUDIT_LOG`**
  (MEDIUM, small) for collision-resistance and readable forensics.
- **3.5 Approval gateway atomicity + polling rate-limit** (LOW, small each) — replace peek-then-pop
  with an atomic `pop() -> (found, session)`; rate-limit `chat_resume` `approval_id` lookups.
- **3.6 Validate eval policy at set-time** (MEDIUM, small) — reject unknown policy strings instead
  of silently reverting to `suspend`.

---

## Phase 4 — Investigation quality & state

- **4.1 Persist entity context across `chat_resume`** (MEDIUM, small) — today only the first turn is
  grounded; persist on first `chat_turn`, re-inject on resume (`_entity_context_block` /
  `_inject_entity_context` already exist in `operations.py`).
- **4.2 Structured case scratchpad** (from review §2) — give the agent a read/write working-memory
  object (entities seen, IOCs + verdicts, open/closed hypotheses) instead of relying on the chat
  transcript. Raises the ceiling on long hunts and makes the triage→build handoff lossless.
- **4.3 Preserve analyst edits to approved args** (MEDIUM, medium) — record original vs
  final-approved args + a diff note so future playbook runs don't silently use stale params and
  analysts can audit their own decisions.
- **4.4 Approval-correctness + outcome evals** (HIGH, medium each) — score unproductive escalations
  (e.g. VirusTotal on an internal IP) and assert dry-run *outputs* (summary contains scoped IOCs,
  severity matches), not just that the playbook executes.
- **4.5 Enrichment semantic-bounds validation** (HIGH, medium) — sanity-check TI results
  (e.g. VirusTotal verdict range) so hallucinated/corrupted enrichment isn't treated as ground truth.

---

## Post-MVP — deferred to 2.0.0 (not for MVP)

- **Live tool-call streaming to the widget** (MEDIUM, large) — **2.0.0 feature, explicitly out of
  MVP scope.** Today every tool call *is* surfaced: the providers yield a `ToolUseEvent` +
  `ToolResultEvent` per call (`anthropic_provider.py:367/411`, `lmstudio_provider.py:254/256`),
  `run_turn.py:400-422` persists them, and the connector's `_event_to_wire`/`_wire_transcript`
  (`operations.py:537`) include every one in the response envelope the widget renders. The gap is
  that delivery is **per-turn batched** — the widget gets the full transcript when `chat_turn`
  returns, not a live "agent is calling X…" feed mid-turn. Real-time streaming (token/event push
  while the turn runs) would need a streaming transport on the connector chat surface and an
  incremental render path in the Angular widget. MVP ships the batched transcript; live streaming is
  a 2.0.0 enhancement.

## Backlog (low, opportunistic)

Picklist-validation discovery tool · document operator type coercion · SetVariable nested-key
shadowing · step-name auto-fix loses original error · legacy `approval_request` serialization
cleanup · Jinja regex edge cases in `_VARS_STEPS_RE` · lax-code demotion should feed the agent a
note · corpus validator envelope coverage for non-allowlisted step types · resume payload
camelCase/snake_case normalization · `info_card` block-kind validation.

---

## Sequencing rationale

Phase 1 closes the four trust-breakers (argument grounding, error legibility, the mutating-op gate,
and proof-of-investigation) plus the one-line version fix. Phase 2 makes the loop robust under real
failure (timeouts, partial completion, transient connectors). Phase 3 makes approvals tamper-evident
and durable. Phase 4 raises investigation quality and gives the agent real state. Ship Phase 1
before any prompt tuning — otherwise we optimize behavior the structure doesn't yet guarantee.
