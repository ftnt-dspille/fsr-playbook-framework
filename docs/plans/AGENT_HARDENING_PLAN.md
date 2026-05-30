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

---

## Phase 1 — Trust-critical (do first)

### 1.1 Argument validation against the operation schema  ·  HIGH · medium
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

### 1.2 Tool errors marked `is_error`  ·  CRITICAL · small
`anthropic_provider.py:398-404` builds `tool_result` with content only. Add
`"is_error": isinstance(result, dict) and "error" in result` (also recognize the `{ok: false}`
envelope). Without it the self-repair loop is guessing.
- **Test:** mock a transient connector 500 → next loop escalates/alternates instead of blindly
  retrying; error logged as `is_error`.

### 1.3 Structural gate on mutating ops in `run_op`  ·  HIGH · medium
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

### 1.5 Align widget contract version  ·  CRITICAL · small
Widget `WIDGET_CONTRACT_VERSION = '2.0.0'` vs connector `2.1.0` →
`view.controller.js:34` → `'2.1.0'`. Removes negotiation noise. (Low real severity — non-strict mode
only `console.warn`s — but trivial and noise-removing.)

---

## Phase 2 — Reliability & completeness

### 2.1 `get_record` / `get_related` tool  ·  HIGH · small
The triage prompt tells the agent to pull event-level rows via `iri`/`module`/`uuid`, but no such
tool exists — it must construct blind `run_op` calls. Add `get_record(iri | module+uuid,
relationships=True)` wrapping crudhub GET (`/api/3/<module>/<uuid>?$relationships=true`) to
`SAFE_TOOLS` (tier 1, read-only). Closes the prompt↔tool gap behind the attack-timeline / blast-radius
quick actions.

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

---

## Phase 3 — Safety & auditability

- **3.1 HMAC-bind approvals** (HIGH, medium) — bind `approval_id + tool + args_hash + ts` with an
  HMAC token (HITL plan Phase 0); validate on resume via `secrets.compare_digest`. Closes argument
  substitution if the session store leaks.
- **3.2 Persist suspended sessions** (MEDIUM, large) — the in-memory gateway loses all pending
  approvals on worker restart. Back it with the session store.
- **3.3 LM Studio provider approvals** (MEDIUM, large) — it currently auto-executes tier-3+ tools;
  route them through the same suspend/resume path as Anthropic, or refuse tier-3+ under it.
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
