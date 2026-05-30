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

### 1.4 Investigation-quality eval family  ·  CRITICAL · large
Add 4–5 investigation-scope tasks scored on **recall** (`facts_fetched / required_facts`), not YAML
shape: phishing (email/URL/sender-IP pivots), lateral movement, data exfil, a **negative case**
(internal RFC1918 IP → refuse external TI), and **graceful partial failure** (TI timeout → flag the
gap distinctly from "no threats"). Gate: `investigation_recall >= 0.8`.
- **Test:** phishing task audit log shows the expected `get_record`/`run_op` pivots; computed recall
  meets gate.

### 1.5 Align widget contract version  ·  CRITICAL · small  ·  ✅ DONE
Widget `WIDGET_CONTRACT_VERSION = '2.0.0'` vs connector `2.1.0` →
`view.controller.js:34` → `'2.1.0'`. Removes negotiation noise. (Low real severity — non-strict mode
only `console.warn`s — but trivial and noise-removing.)

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
