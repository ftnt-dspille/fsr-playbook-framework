# Agentic IR&R Architecture Review — FSR Playbook Builder

**Date:** 2026-05-30 · **Method:** 8-way read-only multi-agent review (agent loop, tool
surface/grounding, HITL guardrails, storage/session, eval harness, compiler, investigation
capability, widget↔contract conformance) + synthesis. 61 findings (4 critical, 15 high, 27
medium, 15 low).

> This is a **durable reference**, not a changelog. The actionable, ordered work derived from it
> lives in [`plans/AGENT_HARDENING_PLAN.md`](plans/AGENT_HARDENING_PLAN.md). Update this doc when
> the architecture changes; update the plan as items ship.

The system under review: the **connector is the brain** (LLM agent loop + MCP tool registry +
platform calls + session storage + HITL pause/resume); the **widget is a thin chat front-end**.
Canonical source of `fsr_playbooks` is `fsr-playbook-framework/fsr_playbooks` — the connector at
`ConnectorsV2/fsr-playbook-builder` **vendors** it via `scripts/build.sh` (which `rm -rf`s and
re-copies the vendored tree, so **all `fsr_playbooks` edits must land here, not in the connector copy**).

---

## 1. Verdict

**The spine is sound; it is not yet SOC-deployable without hardening.** The design makes the right
foundational bets — a real agentic loop (not a single prompt), tiered human-in-the-loop autonomy,
deterministic playbook compilation, and a grounded tool catalogue. What separates it from
"an analyst trusts this unattended" is a cluster of gaps where **validation is deferred to runtime**
and **safety-relevant behavior is enforced by prompt rather than structure**.

### What's solid (the spine)

- **Event-driven agent loop with prompt caching + HITL gating.** `tool_use → dispatch →
  tool_result → loop`, bounded by `MAX_TOOL_TURNS`, with a self-repair loop for compiler errors
  (capped at `MAX_SELF_REPAIR_TURNS`). Ephemeral cache on the tool schema preserves ~90% cache-hit
  savings across turns (`anthropic_provider.py:182-190`).
- **Tiered approval model.** Tiers 0–2 auto-run; tier 3+ suspend for human approval; unknown
  category escalates. Policy (`TOOL_TIERS`) is separated from dispatch logic (`tools.py`), DB-backed
  by `op_safety`. This is the single most important design decision for IR, and the default fails
  toward asking.
- **Deterministic compilation.** Multi-stage pipeline (parse → lint → resolve → arg/corpus → graph
  → emit) with UUID v5 for round-trip stability; predecessor analysis catches cycles and
  unreachable steps.
- **Connector-as-integration-spine.** Pre-execution health checks (4h/5m TTL cache), op-existence
  validation against the offline store **and** the live connector definition, and result
  field-pruning for large enrichment blobs.
- **Transcript as source of truth.** Sessions persist after every turn; approval chains stash
  history (10-min TTL); resume correctness is tested at the block level.

### What breaks trust (the critical gaps)

1. **No argument validation against the operation schema.** The op *name* is now validated (see
   §3), but params are not: required-field presence, type conformance, and select-option membership
   are all deferred to the live FSR execute call. Analysts approve incomplete/invalid action cards;
   ops fail *after* approval with opaque errors.
2. **Investigation phase has no structural gate.** The triage prompt forbids mutating ops via
   `run_op(confirm=True)` in *prose only* — there is no runtime check. Model drift or prompt
   injection bypasses it. Mutating actions are gated by convention, not code.
3. **Tool-error feedback is lossy.** Failures are wrapped as `{error: ...}` strings without the
   Anthropic `is_error: true` flag (`anthropic_provider.py:398-404`), so the model cannot reliably
   distinguish a failed tool call from a successful one — degrading the self-repair loop the whole
   design depends on.
4. **No investigation-quality evaluation.** The eval harness scores YAML *shape*, not whether the
   agent scoped the incident correctly (recall of affected assets/IOCs), asked the right questions,
   or avoided unproductive escalations. We can't prove the agent investigates like a human.

---

## 2. Cross-cutting themes

| Theme | Evidence | Impact |
|---|---|---|
| **Validation deferred to runtime** | Tool args, op params, and Jinja refs are validated at FSR execution, not at build/compile time. | Analysts approve actions that fail at the last moment. Erodes trust. |
| **Prompt-enforced safety vs structural gates** | Triage forbids `run_op` mutations; investigation forbids LLM self-approval — both rely on model compliance. | HITL gates are aspirational where they should be enforced. Drift/injection bypasses them. |
| **Opaque error feedback** | Tool errors are stringified without `is_error`; transient vs permanent failures are not distinguished; lax-code demotion silently masks issues. | Agent can't self-repair intelligently; analysts see unhelpful errors; logs are weak for forensics. |
| **Evals measure authoring, not operational readiness** | Harness grades YAML, not incident handling. No recall/precision, no graceful-degradation tasks. | Ships authoring-correct but operationally naive agents. |
| **Approval architecture incomplete** | HMAC token binding (HITL plan Phase 0) unimplemented; args not cryptographically bound to `approval_id`; `args_hash` is 64-bit; in-memory gateway loses sessions on restart. | Argument substitution is possible if the session store leaks; approvals don't survive a worker restart. |
| **State lives only in the transcript** | No structured case object (entities, IOCs, verdicts, hypotheses); entity context is not persisted across `chat_resume`; analyst edits to approved args leave no audit trail. | Long hunts degrade; triage→build handoff is lossy; analysts can't audit their own decisions. |

---

## 3. Status of the op-existence fix (2026-05-30)

The "agent proposed a VirusTotal op that doesn't exist" bug is **fixed** and serves as the template
for the argument-validation work that should follow it:

- `_shared._validate_op_exists(connector, op)` — offline store check; rejects a phantom op with
  `unknown_operation` + near-matches, **only** when the connector has ops catalogued (no false
  reject on an empty store).
- `tools_execution._validate_op_live(client, connector, op)` — live fallback when the store has no
  ops for the connector; validates against the live connector definition; never blocks on a lookup
  failure.
- `run_op` calls the offline check before the risk gate and the live check after preflight;
  `emit_action_card` calls the offline check before rendering. The triage prompt now forbids
  guessing op names.

The errors flow back as `tool_result` blocks and the agent self-corrects within the same turn (no
human round-trip). **The next gap is the symmetric one: validate the op's *arguments*, not just its
name** — see Phase 1 of the hardening plan.

---

## 4. Full findings appendix

61 findings across 7 reviewed subsystems (the storage/session reviewer failed to emit structured
output; its core concerns — in-memory gateway loses sessions on restart, entity context not
persisted across resume — were independently surfaced by the agent-loop and tool-surface
reviewers and are captured below). Ordered by severity.

### Critical (4)

| Finding | Area | Effort |
|---|---|---|
| No investigation-recall eval (agent never scored on scoping/IOC recall) | Eval harness | large |
| Resume on partial tool completion silently skips remaining tool calls (no feedback/event) | Agent loop | medium |
| Tool errors not marked `is_error` in `tool_result`; LLM can't tell success from failure | Agent loop | small |
| Widget declares contract `2.0.0`; connector emits `2.1.0` (negotiation noise) | Contract | small |

### High (15)

| Finding | Area | Effort |
|---|---|---|
| **Missing argument validation against op schema** (required/type/options) | Tool registry | medium |
| Missing `get_record`/`get_related` tool for entity-timeline grounding (prompt assumes it exists) | Tool registry | small |
| Missing end-to-end outcome validation in evals (dry-run doesn't assert results) | Eval harness | medium |
| No approval-correctness measurement beyond tier counts (unproductive escalations unscored) | Eval harness | medium |
| No prompt-adherence coverage for investigation patterns | Eval harness | medium |
| `provider.stream()` can hang indefinitely; no timeout in the provider protocol | Agent loop | medium |
| Max-turn summary call failure falls through silently (agent looks finished when it stalled) | Agent loop | medium |
| Text-coalescer `seq` off-by-one (transcript reconstruction by seq misaligns) | Agent loop | medium |
| No cryptographic binding between `approval_id` and execute arguments | HITL | medium |
| No structural validation that enrichment results are real (semantic bounds) | Investigation | medium |
| Prompt-only enforcement of "never run mutating ops via `run_op`" | Investigation | medium |
| Jinja-syntax errors in `render_paths` silently fail with empty result | Compiler | small |
| Predecessor computation used before acyclicity is validated | Compiler | medium |
| Step output-schema detection: 100% fallback failure on unknown step types | Compiler | small |
| Widget still handles legacy `approval_required` stop_reason the connector no longer emits | Contract | small |

### Medium (27) — selected

| Finding | Area | Effort |
|---|---|---|
| In-memory approval gateway loses all sessions on worker restart; no persistence | Agent loop / session | large |
| LM Studio provider does not emit approvals; tier-3+ tools auto-execute | Agent loop | large |
| Persist entity context across `chat_resume` turns (today only first turn is grounded) | Tool registry / session | small |
| Triage→build handoff may not preserve analyst edits to approved args (no audit trail) | Investigation | medium |
| Hunt loop doesn't distinguish transient from permanent failures in fan-out enrichment | Investigation | medium |
| Corpus validator only checks allowlisted step types; ~60% of steps bypass envelope validation | Compiler | medium |
| Resume payload field-name drift (snake_case vs camelCase) between contract and widget | Contract | medium |
| `info_card` block vocabulary has no validation; unknown kinds silently degrade to rows | Contract | small |
| Args not masked in `AUDIT_LOG`; secrets risk + weak forensics | HITL | small |
| Tier resolution for unknown op defaults to tier-3, but op existence is checked after the tier gate | HITL | small |
| `max_tokens` cap (4096) can truncate large compiler-error feedback | Agent loop | small |
| `shrink_history()` dedup leaves stale `yaml_sha` tags when older validations are stubbed | Agent loop | medium |
| Render-path analyzer downgrades missing-key errors to warnings without a confidence threshold | Compiler | medium |
| Eval-policy typos silently revert to production `suspend` behavior | Eval harness | small |
| Live-test blocker heuristics incomplete (slow ops can time out the runner) | Eval harness | small |

*(Remaining medium/low findings — approval polling rate-limit, `args_hash` width, peek/pop
atomicity, picklist discovery tool, operator type-coercion docs, reserved-var shadowing, and
others — are enumerated in the hardening plan backlog.)*

### Low (15)

Minor UX/robustness items: negative-case investigation task, narrower agentic eval tool coverage,
no picklist-validation discovery tool, implicit operator type coercion undocumented, approval
gateway peek/pop race, eval-policy bypass surface, `args_hash` width, entity lookup-key
pre-validation, `emit_action_card` completeness enforcement, Jinja regex edge cases, SetVariable
nested-key shadowing, step-name auto-fix loses original error, legacy `approval_request`
serialization confusion. See the plan backlog for the full list.

---

## 5. How to use this document

- **Architecture changed?** Update §1–§2 here.
- **Picking up work?** Go to [`plans/AGENT_HARDENING_PLAN.md`](plans/AGENT_HARDENING_PLAN.md) — it
  orders these findings into shippable phases with call sites and tests.
- **Cross-references:** wire shape →
  `fortisoar-widget-harness/FSR_PLAYBOOK_BUILDER_CONNECTOR_CONTRACT.md`; HITL design →
  `docs/plans/HITL_GUARDRAILS_PLAN.md`; agent quality/evals → `docs/plans/AGENT_QUALITY_PLAN.md`.
