# Agent tool registry + dead-weight remediation plan

**Status:** 2026-05-28 — proposed, not started.
**Motivation:** session 2026-05-28 audit revealed that the system prompt mandates 10 tools the agent literally cannot call because they are absent from `SAFE_TOOLS` in `fsr_playbooks/llm/tools.py`. This is the root cause of the "playbook AI creation is broken" symptom: the agent has no way to validate, no way to analyze, no way to push, no way to triage. It falls back to raw generation, the editor's YAML extractor finds nothing, and the user sees an empty assistant bubble.

This plan also bundles the smaller dead-weight findings so we close them in one sweep rather than leaving them as drift.

---

## Phase 0 — Stop the bleeding (P0, ~30 min)

The agent's authoring loop is broken until `SAFE_TOOLS` reflects what the prompt actually mentions. Ship this first.

### 0.1 Add the four pure-compute tools the prompt mandates

Edit `fsr_playbooks/llm/tools.py`:
- Append to `SAFE_TOOLS`: `validate_yaml`, `compile_yaml`, `analyze_playbook`, `find_step_recipe`.
- Add to `TOOL_TIERS` as tier 0 (local compute, no FSR I/O, no side effects).

**Done when:** `fsr_playbooks.llm.tools.REGISTRY` contains all four; a quick `python -c "from fsr_playbooks.llm.tools import REGISTRY; print(sorted(REGISTRY))"` shows them.

### 0.2 Smoke-test the loop

Run `python -m uvicorn ...` against the dev frontend (separate port, e.g. :47831, per session feedback — do NOT touch the user's `:47821`/`:47822`). Send the same prompt that failed at the start of this session ("create a playbook to list fortimanager devices…"). Confirm:
- `validate_yaml` / `compile_yaml` fire and `yaml_text` arrives at the frontend.
- `analyze_playbook` fires after the validate gate.
- The editor receives the YAML.

### 0.3 Re-check the YAML-bearing tool extractor

`web/frontend/src/lib/components/Chat.svelte` already includes `validate_yaml` + `compile_yaml` in its forward-compat extractor (we widened it earlier this session). Verify nothing else regressed.

---

## Phase 1 — Wire the latent high-ROI tools (P1, ~1 hr)

These exist, the prompt references them, and they enable concrete demo flows the product needs.

### 1.1 Catalog / authoring helpers (tier 0)

Add to `SAFE_TOOLS` and tier them at 0:
- `propose_http_fallback` — HTTP fallback step shape for unmapped vendors. Big unlock for connector coverage.

### 1.2 Live triage (tier 1)

Read-only FSR API. Add to `SAFE_TOOLS`, tier 1:
- `why_did_playbook_fail` — agent can postmortem a failed run.
- `get_run_env` — agent can inspect the `vars.*` snapshot from a real run.
- `list_playbook_runs` — used as the predecessor to `why_did_playbook_fail`; add if not already there.

### 1.3 Side-effecting execution (tier-dynamic / tier 3)

These need HITL approval gates. Add to `SAFE_TOOLS`, tier `-1` (dynamic) so the wrapper resolves per-call:
- `push_playbook` — writes to FSR. Should require approval card.
- `run_playbook` — triggers a live execution. Should require approval card.
- `assert_playbook_outcome` — read-mostly but binds to a specific run; tier 1 is fine.

**Risk:** `_resolve_tier` currently special-cases `run_op`, `step_through_playbook`, `dry_run_playbook`. Need to extend the per-call logic for `push_playbook` / `run_playbook` or default them to tier 3. Confirm by reading `tools.py:_resolve_tier`.

### 1.4 Update prompt with what's available

Once the registry catches up, scan `python/agent/system_prompt.md` for tools it mentions that **still** aren't registered (the audit said zero remaining, but verify after 1.1–1.3 land). Anything stale gets removed from the prompt to save tokens.

---

## Phase 2 — Demo-route polish (P2, ~30 min)

Audit cleared `/capabilities`, `/inventory`, `/docs`, `/history`, `/settings`, `/browse` as real product surfaces. But two routes are explicit retirement stubs:

- `web/frontend/src/routes/run/+page.svelte`
- `web/frontend/src/routes/edit/+page.svelte`

**Action:** check git for the original retirement commit. If the redirect is older than ~3 months and no error logs show traffic, delete them. Otherwise leave the redirect.

Also: `web/frontend/src/lib/components/HealthPill.svelte` has zero importers. Delete unless `git log` shows recent work-in-progress intent.

---

## Phase 3 — Validate the integrated flow (P1, ~30 min)

End-to-end test the upgraded agent against three representative prompts:

1. **From scratch**: "create a playbook to enumerate fortimanager devices then block an IP." Expect `find_step_recipe` → `validate_yaml` → `analyze_playbook` → ready-to-push YAML.
2. **Live triage**: "playbook run 1234 failed, what happened?" Expect `why_did_playbook_fail` → `get_run_env` → diagnosis text.
3. **HTTP fallback**: "build a step for vendor X that has no FSR connector." Expect `propose_http_fallback` → resulting YAML.

Each one is a demo we can show the team. Save the transcripts.

---

## Out of scope (parked)

- The MCP catalog / API-example tools (`find_api_example`, `find_api_fixture`, `find_api_product`, `search_api_examples`, `synthesize_http_step`) — useful but the catalog isn't visible from chat yet. Park until Phase 3 demos succeed and we know which gap to fill.
- Session introspection tools (`review_chat_session`, `review_recent_thumbs_down`) — admin / eval tools, not authoring. Park.
- Backend `/api/llm/health` cache layer — currently runs `count_tokens` fresh each call (sub-second). If chat-page mount perf becomes a complaint, cache for 60s.

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Adding `push_playbook` to SAFE_TOOLS lets the agent push without an approval gate | Tier as dynamic, confirm `_resolve_tier` returns 3+ so the HITL card fires |
| `analyze_playbook` is slow when it runs the render-path walker | Already gated to "after validate is clean"; measure first turn, defer optimization |
| Adding 9 new tools bloats the system prompt's tool roster | Tools register their docstrings; ensure docstrings are tight (one-line description). Audit any over-long ones. |
| Frontend YAML extractor still misses YAML from new tools | Already handled — the extractor recognizes any tool call with `yaml_text` or `after_yaml` since this session's fix |

---

## Definition of done

- All 10 tools in §0.1 + §1 appear in `REGISTRY` with correct tiers.
- The three demo prompts in §3 each produce a complete YAML with no manual prodding.
- `pytest python/tests/ web/backend --ignore=python/tests/integration` and `pnpm test` both green.
- `HealthPill.svelte` either deleted or has a tracked owner / next step.
- Prompt no longer references any tool that isn't registered.
