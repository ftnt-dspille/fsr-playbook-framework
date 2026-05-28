# FSRPlaybookYaml — TODO / resume state

**Last touched**: 2026-05-26. Live FSR target: `https://10.99.249.205` (label `dev`).

This file is the master backlog + resume state. Deep multi-phase plans
live under `docs/plans/`; frozen research/audit snapshots under
`docs/research/`; superseded plans under `docs/archive/`.

## Plan index

**Active plans** (`docs/plans/`) — open these for phase-level detail; this file links to them rather than restating their content.

| Plan | Scope | Status |
|---|---|---|
| [`VERIFY_PLAYBOOK_PLAN.md`](docs/archive/VERIFY_PLAYBOOK_PLAN.md) | Single `verify_playbook` forcing-function tool that gates "done" for the agent loop. Trust audit + tool consolidation. | ✅ complete (2026-05-25). Re-baseline `20260525T165836Z`: agentic_anthropic 36/40 (90%) on verify-relevant subset. `verify_runs` history table + `session_verify_stats` reader shipped. Follow-up: `live_tested`-gate `no_dry_run_target` bug — separate ticket. |
| [`VISUAL_EDITOR_PLAN.md`](docs/plans/VISUAL_EDITOR_PLAN.md) | Toggle yaml ↔ visual editor; drag/drop palette; flowchart canvas; per-step inspector wired to every MCP tool; debug runner. | Phases 1–4 + 4.5 shipped. **Phase 5 server-side pause/resume ✅** 2026-05-25 (5 new MCP tools + `mcp_server/debug_session.py` + DebugPanel rewire + 12 tests). **Debug + Inspector UX polish ✅** 2026-05-26: `_normalize_friendly_steps` fixes friendly-YAML decision branching + MI option routing in the simulator; `as_status()` now returns full trace (fixes "0 steps walked yet" bug); 3-button toolbar (▶ Run / ⏭ Step / ⏹ Stop) where Run creates + continues end-to-end; Stop → ↺ Restart label; Step auto-skips trigger entry. Inspector consolidation: Simulate → Samples (now applies to any mockable step — manual_input sidecar + connector mock_result); Verify tab collapsed from 5 sections to 1 (one ▶ Run this step button + auto-loaded issues banner + one-line history); MI Samples tab gets a prompt-wireframe preview (title + description + inputs + option buttons). 11 e2e tests against real `examples/*.yaml` (caught 3 latent bugs in the simulator). Remaining: 5.4 branch chooser UI / 5.5 watch panel UI / 5.7 trigger payload editor UI (all server-side ready); canvas breakpoint gutter; Phase 6 toolbar gaps (6.2 Resolve, 6.3 Dry-run, 6.4 Assert, 6.6 Recipe export); Phase 6.5 Variable picker side panel (G27/G28); G11 pane-click create-step popover; **manual browser smoke of the new debug + inspector UX (never verified end-to-end live)**. |
| [`RENDER_PATH_VALIDATOR_PLAN.md`](docs/plans/RENDER_PATH_VALIDATOR_PLAN.md) | Local render-path trace + heuristic checks → red badges on failing steps before push. Powers editor preview. | Phases 1–3 + Phase 6.1 shipped. **Phase 5 complete ✅** 2026-05-25 (C6 index-into-non-list / C7 decision-references-unset-path / C8 MI mode/output mismatch / C9 for-each loop-var leak / C10 dead step; C5 superseded by Tier 3). Remaining: 6.2/6.3 fix-apply + bulk-fix, 4.1-4.7 visual-editor surfacing pass, 7.3 agent fail-fast on skipped authoring tools. |
| [`AGENT_QUALITY_PLAN.md`](docs/plans/AGENT_QUALITY_PLAN.md) | Evidence base for agent tuning: what the agent actually looks up, data-store gaps, prompt-adherence baseline. | Phase 1A/B/C shipped (`fsrpb agent-stats`); Phase 2/3 pending |
| [`CONNECTOR_INTEGRATION_PLAN.md`](docs/plans/CONNECTOR_INTEGRATION_PLAN.md) | Catalog-grounded HTTP-shaped authoring: `find_api_*` + `propose_http_fallback` so the agent can ground "do X with vendor Y" requests in real OpenAPI fixtures (36k fixtures, 6.9k products). Supersedes TODO D3 + HTTP-virtual-connector items. | **Phases 0 / 0.5 / 0.6 done** (2026-05-18). Path fix to `fortisoar/corpus_builder/catalog.sqlite` + `FSRPB_API_CATALOG` env + intent-aware fixture ranking (auth-prelude demotion + intent-token overlap + verb-method tie-break). Phases 1-3 **descoped** — validator/replay are connector-author tools, different audience; toolkit stays where it lives. Phase 4 (editor "use http fallback" affordance) + Phase 5 (connector-lifecycle mining) still viable as separate follow-ups. |
| [`AGENT_LOOP_REFINEMENT_PLAN.md`](docs/plans/AGENT_LOOP_REFINEMENT_PLAN.md) | Three orthogonal refinements: (A) static reference data into the prompt cache, (B) constrained generation for hot shapes via `emit_*` tools, (C) separate "enhance" path from "build" path with `verify_enhancement` + intent-tagged metrics. | **Refinement A done** (commit `18adb53` — 14.9 KB cached prefix). B + C pending. |
| [`HITL_GUARDRAILS_PLAN.md`](docs/plans/HITL_GUARDRAILS_PLAN.md) | Tier-based human-in-the-loop approvals for every tier-3+ tool call (FSR writes, third-party side effects). Approval cards with rendered preview + masked secrets; conversation transcript as audit log; eval-harness policy + `appropriate_approval_requests` gate. | **✅ Complete** (2026-05-18). All 5 phases shipped: tier-aware dispatch, loop suspend + `/api/approvals/{id}` resume, frontend approval card, audit pane, eval policy + gate, server-side step-up, `step_through_playbook` unsafe placeholder. `run_op` / `step_through_playbook` / `dry_run_playbook` / `diagnose_yaml_against_pb_execution` surfaced into `SAFE_TOOLS` behind the gate. |
| [`STATIC_TYPE_VALIDATION_PLAN.md`](docs/archive/STATIC_TYPE_VALIDATION_PLAN.md) | Static value-level type checking for connector params + Jinja flow typing. Tier 1 ships compile-time enum / int / decimal / bool / picklist diagnostics via the resolver. Tier 2 adds probe-derived `observed_type` (ipv4 / url / iri / epoch) for `text`-typed params. Tier 3 propagates types forward through Jinja filter chains so `{{ x \| int }}` satisfies an integer-typed param statically. | **✅ complete** (2026-05-25). All tiers landed; 12,317 / 26,093 connector params typed (47%); Tier 3 chain validation across resolver + walker with re-baseline showing agents self-correct via `bad_jinja_filter_chain` in the verify loop (3-iteration recovery on `jinja_chain_json_payload`). `fsrpb doctor` CLI for connector authors. |

**Frozen research / audits** (`docs/research/`) — snapshots, not updated:

- [`GAPS.md`](docs/research/GAPS.md) — live-instance information gaps (endpoints we still need to confirm).
- [`SURFACE_AUDIT.md`](docs/research/SURFACE_AUDIT.md) — Phase 0 feeder for `VERIFY_PLAYBOOK_PLAN`: every MCP tool / route / prompt directive / CLI verb tagged keep|wire|delete.
- [`MI_DECISION_VALIDATION_AUDIT.md`](docs/research/MI_DECISION_VALIDATION_AUDIT.md) — 2026-05-06 audit of ManualInput + Decision rules against the corpus.
- [`RECIPE_EXPANSION_RESEARCH.md`](docs/research/RECIPE_EXPANSION_RESEARCH.md) — 2026-05-06 archetype assessment beyond threat-feed / data-ingest recipes.

**Archived / superseded** (`docs/archive/`):

- [`CHAT_APP_PLAN.md`](docs/archive/CHAT_APP_PLAN.md) — Phase 2 LLM-agnostic chat shim. UI/shipping superseded by `web/PLAN.md` (SvelteKit + FastAPI); LLM-context strategy still inherited from this doc.

**Cross-project**:

- [`Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md`](../Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md) — original cross-project plan; referenced from global `~/.claude/CLAUDE.md`.

## Next steps (resume state, 2026-05-26)

Ordered roughly by leverage. Pick from this list when restarting; each
points to deeper detail in its plan.

**A. Verify the recent UX work in a real browser** (do this FIRST).
The debug runner + inspector consolidation shipped 2026-05-26 with
408 frontend tests + 682 backend tests passing, but **was never
opened in an actual browser**. Smoke-walk:

   - Open a playbook (e.g. one of `examples/*.yaml`).
   - In the debug drawer: click ▶ Run (one click — should walk
     end-to-end). Click Stop → Restart should appear. Run again with
     a shift-clicked breakpoint to confirm pause behavior.
   - Click a manual_input step → Inspector → **Samples** tab.
     Confirm the prompt-preview wireframe shows title + description
     + input field labels + option buttons (any of approve / reject /
     etc).
   - Click a connector step → Inspector → **Samples** tab. Confirm
     the `mock_result` JSON editor renders. Save a mock, switch to
     **Verify** tab, click ▶ Run this step, confirm result panel.
   - Confirm the **Verify** tab is one tight box (issues banner only
     if there ARE issues; one Run button; one-line history). No
     "What this step resolves to" details.
   - If anything is off, the work is in `web/frontend/src/lib/
     components/{DebugPanel,StepInspector,StepInspectorVerifyTab,
     StepInspectorSimulateTab}.svelte`.

**B. Strategic anchor (H2 lever):**
1. **Solution Pack research kickoff.** Open
   `docs/research/SOLUTION_PACKS.md` (currently missing — create it).
   Crack open one Fortinet marketplace pack (recommend
   SOC-Automation or Phishing-Triage), un-archive it, write the
   structural map: manifest schema, module ↔ playbook ↔ connector
   ↔ picklist dependency graph, lifecycle (install/uninstall/version).
   This is the spec a pack-generation agent has to be able to author.
   Cross-ref: `Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md` 2026-05-20
   strategic block. Park condition is now satisfied
   (verify_playbook + Tier 2/3 + render-path v2 all firm).

**C. Debug-runner UI tail** (server-side ready, just needs UI):
2. **5.4 Branch chooser modal** — when execution pauses at a Decision
   step, pop a small modal asking which branch to take. Server
   already accepts `branch_choice_override` on `step_debug_session`.
   ~30 min — pure frontend.
3. **5.5 Watch panel** — pin specific `vars.steps.X.Y` paths; the
   panel polls `get_debug_session` (which already returns `vars_keys`)
   and resolves each pinned path. ~1 hr.
4. **5.7 Trigger payload editor** — form built from
   `module_fields` for the playbook's trigger module; binds to the
   `input` arg on `start_debug_session`. ~2 hr.
5. **Canvas-gutter breakpoint UI** — current breakpoint toggle is
   only on the trace tape. Add a small dot indicator on canvas nodes
   too. ~1 hr.

**D. Debug-runner performance** (surfaced 2026-05-26):
6. **Batch `render_jinja` calls server-side.** The simulator's
   `_render_walk` posts ONE HTTP request per templated string. For
   a step with N templated args against a live FSR, latency is N ×
   200-1000ms. Batch the renders into a single endpoint call (or
   short-circuit aggressively when no `{{` is present — already
   does this client-side, verify it's tight on the server too).

**E. Render-path tail** (Phase 5 complete; just remainders):
7. **6.2/6.3 fix-apply + bulk-fix** in `analyze_playbook` → click a
   diagnostic to apply its suggested fix; bulk for many.
8. **4.1-4.7 visual-editor diagnostic surfacing pass** —
   render-path warnings should show up on canvas nodes too, not just
   the inspector.
9. **7.3 Agent fail-fast on skipped authoring tools** — if the agent
   bypasses a tier-1 tool, surface as a hard error.
10. **Tier 3 corpus mining for long-tail filters** — the 90-entry
    curated map covers the dominant filters; corpus-mining the
    remainder would lift coverage on niche `workflow.jinja` macros.
    Lowest priority since the agent loop has the curated set.

**F. Visual editor surface polish:**
11. **Phase 6 toolbar gaps** — Resolve (6.2), Dry-run (6.3), Assert
    (6.4) buttons; Recipe export (6.6). Mostly thin frontend wrappers
    over existing MCP tools.
12. **G11 pane-click create-step popover** — corpus-driven next-step
    suggestions mining `playbook_steps` for what usually follows the
    selected anchor.
13. **G19/T3 Jinja Test modal** — currently a stub button; port
    logic from `WebstormProjects/widget-jinja-editor/`.
14. **G27/G28 Variable picker side panel** — Input/Output + Functions
    + Global Variables tabs; click to insert at the focused arg's caret.

**G. Eval / agent-quality tail:**
15. **AGENT_QUALITY_PLAN Phase 2/3** — phases past `fsrpb agent-stats`.
16. **AGENT_LOOP_REFINEMENT B + C** — DEPRIORITIZED per global
    memory (`priority_agent_loop_deprioritized.md`).

**H. Carry-over polish:**
17. **Eval scoring fix #0** at the top of "Backlog (open)" —
    `no_dry_run_target` is already fixed (commit `5393510`). Stale
    line; remove on the next TODO sweep.

**I. Smaller items not yet on a plan:**
18. **Live Jinja resolve in MI prompt preview** — current preview shows
    `{{ ... }}` raw. Could call `render_jinja` against saved samples
    to show resolved title/description. ~30 min if added.
19. **Consolidate the two simulator implementations** —
    `tools_analysis.step_through_playbook` and
    `debug_session._execute_one_step` both loop step-by-step, sharing
    only helpers. Tracked as tech debt in
    `mcp_server/debug_session.py` docstring; safe to keep parallel
    while debug runner is still maturing.
20. **Future Tier 3.5: typed-walker also reports terminal-type
    mismatches** (resolver does this only for connector_op params;
    walker only does chain validation). Symmetric coverage so that
    a `set_variable.vars` field of type "string" can be checked
    against `{{ ... | length }}`. Lower priority since set_variable
    fields aren't widget-typed.

---

**Working-tree carry-overs** (changes not yet committed because the
files had pre-existing WIP from other sessions):

- `python/agent/system_prompt.md` — gains:
  - top-of-file pointer to the cached static grammar block (Refinement A).
  - "Latent capabilities" section listing 22 wire-up tools.
  - `propose_http_fallback` rule under "Latent capabilities"
    (CONNECTOR_INTEGRATION_PLAN Phase 0.5).
- `web/frontend/src/lib/api.ts` — `listRecentFailedRuns`,
  `whyDidPlaybookFail` helpers for `FailedRunsPanel`.
- `web/frontend/src/routes/history/+page.svelte` — tab nav into the
  failed-runs panel.

Pull these into whichever next commit touches those files.

---

## Strategic — Solution Pack generation (added 2026-05-20)

**Premise:** Playbook generation in isolation produces curiosities, not
value. The unit of customer-deliverable work in FortiSOAR is the
*solution pack* — a bundle that ships custom modules (ORM-mapped
PostgreSQL tables, the actual data substrate), connectors, playbooks,
dashboards, roles, and pre-seeded picklists/views. A solution pack is
an application; an island playbook is a snippet. Everything we've
built so far (compiler, type validation, verify_playbook, the agent
loop) makes the snippet-author faster — useful, but linear leverage.

**Why this is the exponential lever:** if an agent can design a coherent
*solution pack* — choose the data model, design the modules that map
to it, wire the connectors that populate the data, write the playbooks
that act on it, and bundle the result for distribution — the agent
moves from "generates one step better than a human" to "generates an
entire SOC use-case end-to-end." That's the difference between
"helpful tool" and "platform multiplier." The playbooks in a solution
pack also have **lifecycle**: triggered by module events, mutate
module records, hand off between each other — they're a system, not
an island. Type-flow, ownership, and idempotency questions all gain
real stakes in this context.

**What we'd need to learn / build (deep dive when we get here):**

1. **Solution-pack export format.** What is the manifest schema? How
   are module → playbook → connector dependencies expressed? How does
   FortiSOAR install / uninstall / version one? Reverse the export
   pipeline from the UI; sample real packs from the Fortinet
   marketplace; document the canonical structure under
   `docs/research/SOLUTION_PACKS.md`.
2. **Module schema as ORM.** Modules in FSR are Doctrine entities over
   PostgreSQL — picklists are FKs to a picklist table, lookups are
   joins. Understanding this maps directly onto the static-type
   validation work: an agent that designs a module knows the column
   types, so playbook-vs-module type checks become a free byproduct.
3. **Picklist + view + role coupling.** Every module carries a default
   set of picklists, list views, detail layouts, and role permissions.
   These are what make a pack feel like an application. Need a
   `module_design` tool that proposes the full bundle from a use-case
   prompt, not just the entity.
4. **Trigger / lifecycle graph.** Solution-pack playbooks are wired
   into module-event triggers (`onCreate`, `onUpdate`, status-change).
   A pack is best modeled as a *graph* of (modules, triggers,
   playbooks, connectors). Generation has to satisfy the whole graph.
5. **Validation upgrade.** Today verify_playbook validates one
   playbook in isolation. Solution-pack validation needs cross-
   playbook checks: do the triggered playbooks actually exist? Are
   module fields referenced in playbooks still present? Are picklist
   values referenced statically still in the bundled picklist?

**Why-park-this-now:** the foundations (typed resolver, run_op,
catalog, op_safety) need to be solid before we layer pack-level
generation on top. Tier 2.2 / 2.3 + render-path validator + verify_
playbook all earn their keep regardless of whether we go pack-scale
next, *and* they are prerequisites for any credible solution-pack
agent. So: finish those, then open `SOLUTION_PACK_PLAN.md` and treat
it as the strategic anchor for 2026-H2.

**Concrete first move when we pick this up:** crack open one
non-trivial Fortinet marketplace pack (e.g. SOC-Automation or
Phishing-Triage), un-archive it, and write the structural map. That
becomes the spec for what the agent has to be able to author.

---

## Live-FSR round-trip probe

`python/probes/probe_round_trip.py` synthesises a YAML playbook per
scenario, compiles + pushes via the real resolver/runner pipeline,
pulls back the canonical JSON, and asserts structural claims survived
FSR's normalisation. **18/18 scenarios green** as of 2026-05-15.

Positive scenarios (push + structural check):
`two_triggers` (negative compile-rejection), `on_create_nested_filter`,
`on_update_changed`, `find_record_correlated`, `decision_three_way`,
`manual_input`, `workflow_reference`, `ingest_bulk_feed`,
`update_record_picklist` (exercises picklist friendly-token NFR),
`find_record_sort`, `on_create_fires_and_completes` (live-fire).

Negative / lint scenarios (compile-only):
`neg_unreachable`, `neg_dup_name`, `neg_dangling_next`,
`neg_no_trigger`, `neg_two_defaults`, `neg_norway_branch`,
`neg_unknown_type`, `neg_unknown_picklist`.

Gotchas:
- Each scenario MUST use a unique collection name. FSR retains
  deleted UUIDs in a recycle layer that doesn't expose a clean
  hard-purge endpoint on 7.6.x; reusing a name produces 409
  UniqueConstraintViolation on the second push because the resolver
  mints deterministic uuid5 from the collection name. Probe uses
  `_fsrpb_rt_<scenario>` prefix + per-scenario purge.

Open follow-ups:
- Inline `is_active` toggle in inspector (today users edit YAML
  directly; requires extending `from_visual`'s diff path to cover
  playbook-level keys).
- ✅ Compiler-rule guards in canvas — `PlaybookGuards.svelte`.

## Step-type authoring polish — open items

(All other items in this section landed 2026-05-08; see git log + the
visual-editor inspector tabs. Two still active:)

- **`workflow_reference` Args UI.** Target playbook picker
  (cross-collection, surface from the playbook list); per-parameter
  input mapping editor (graph predecessor outputs → target inputs);
  "open nested playbook" jump button.
- **Filter-leaf value editors by type.** Picklist values should
  auto-resolve to IRIs when `type: object` is selected (precheck via
  `precheck_picklist_value` MCP, same flow used in connector_op
  params). Datetime should accept either ISO or epoch ms with a
  picker.

(Already-shipped follow-ups intentionally trimmed; one-liners only.)
- ✅ Picklist friendly-token round-trip — server-side now: resolver
  rewrites `resource.<picklistField>: "Label"` → IRI for
  create/insert/update_record. Code: `python/compiler/resolver.py`
  `_resolve_picklist_friendly_tokens`. Round-trip:
  `update_record_picklist` scenario in `probe_round_trip.py`. Negative:
  `neg_unknown_picklist`. Shipped 2026-05-15.
- ✅ code_snippet Monaco editor — `web/frontend/src/lib/components/MonacoCode.svelte`.
- ✅ Ingest Bulk Feed authoring block (see `StepInspectorArgsTab.svelte`).
- ✅ Decision condition Jinja path picker (`VarPathPicker.svelte`, 7 tests).
- ✅ Find Record correlated-records wire shape (URL-param round-trip,
  see `find_record_correlated` round-trip scenario).
- ✅ Related-module sub-query auto-scoping (`FilterTreeEditor.svelte`).
- ✅ `changed` + `in_all` operators (corpus-verified; on_update_changed
  round-trip scenario).

## Step-type Examples + AI builder

(Both shipped 2026-05-08.)

- ✅ E1 Corpus-mined Examples tab — `web/backend/step_examples.py`
  (15 tests); `GET /api/ref/step-examples/<step_type>`. Inspector
  tab renders clustered skeletons + deterministic English summaries.
- ✅ E2 AI step builder — `web/backend/step_drafter.py` (13 tests).
  `POST /api/visual/draft-step`. ✨ Describe button on inspector
  header. Inline validator pass shows compiler diagnostics in the
  modal.

Open follow-ups from E2: tool-using variant where the model calls
`list_picklists` / `find_step_examples` mid-turn instead of relying
on pre-loaded prompt; step_drafter UsageEvent telemetry dashboard
(data is recorded, read-side queued).

## Pending — distributability & user personalization (added 2026-05-07)

These two are about turning fsrpb from a personal tool into something
others can install and shape to their environment.

D1. **Distribution: thin base image + `fsrpb train` ingestion command**.
    Today `store/fsr_reference.db` is checked in pre-populated (58 MB)
    with every connector, operation, op param, picklist and playbook
    from the dev FSR — that's customer-specific data and blocks open
    distribution. Three SQLite files exist on this machine; plan
    handles each:

    **`store/fsr_reference.db` (58 MB)** — split the tables:
    - SHIP IN BASE IMAGE (environment-agnostic, broadly useful):
      `step_types`, `step_examples`, `step_handlers`, `jinja_macros`,
      `jinja_globals`, `jinja_tests`, `jinja_context_vars`,
      `jinja_filter_usage`, `jinja_expressions`, `api_endpoints`,
      `api_endpoint_params`, `api_endpoint_examples`, `recipes` (the
      generator + step recipe metadata, not playbooks_seen).
    - POPULATE VIA `fsrpb train` (tenant-specific):
      `connectors`, `operations`, `operation_params` (incl.
      parent_param_name/condition_value visibility rules — load-bearing
      for `param_groups_by_select`), `modules`, `module_fields`,
      `playbooks_seen`, `playbook_steps`, `verifications`, `_probe_runs`,
      and the FTS shadow tables (`fsr_fts*`) which rebuild from
      playbooks_seen anyway.
    - The 3rd-party API tables (`api_endpoints*`) are gold for custom
      HTTP connector authoring and have NO tenant linkage — keep them
      shipped.

    **`web/backend/history.db` (692 KB)** — per-user runtime state
    (chat_sessions, chat_turns, chat_tool_calls, chat_messages,
    chat_feedback, pushes, push_workflows). Never ship populated.
    Initialize empty on first run; document path override via env
    (`FSRPB_HISTORY_DB` already partially supported — verify).

    **`store/store.db` and `python/store/playbooks.db`** — both 0
    bytes. Stale stubs from earlier iterations; just delete them
    and remove any code paths still pointing at them.

    **`Miscellaneous/api_examples_catalog/catalog.sqlite` (339 MB,
    6,927 products / 207,419 entries with FTS)** — generic 3rd-party
    API command catalog. Environment-agnostic and high-value for
    custom HTTP connector authoring (Splunk, ServiceNow, AWS,
    Crowdstrike, …). Currently NOT wired into fsrpb — sitting in a
    sibling project. Distribution options:
    - Ship a slimmed `catalog.base.sqlite` in the base image (top
      products only, e.g. the ~500 with the most entries) — keeps
      the package small, covers the long tail via on-demand fetch.
    - OR keep the full 339 MB as an *optional* sidecar download
      gated behind `fsrpb train --with-api-catalog` so users who
      don't author HTTP connectors don't pay for it.
    - Either way, define a stable schema-versioned download URL so
      the catalog can be refreshed independently of the fsrpb
      release. See D3 for the integration work.

    Action items:
    - New `fsrpb train` (or `fsrpb learn`) verb that points at a
      configured FSR and populates the tenant tables above. Reuse
      probes under `python/probes/`; goal is one verb that
      orchestrates connectors → operations → operation_params →
      modules → playbooks_seen → playbook_steps in dependency order.
    - Build script that produces the base-image db: copy the schema
      from the current store, retain only the SHIP-tagged tables'
      rows, vacuum, and emit `store/fsr_reference.base.db`. Lives in
      `python/probes/build_base_image.py`.
    - Make data dirs configurable via env (`FSRPB_DB`, `FSRPB_CACHE_DIR`,
      `FSRPB_HISTORY_DB`) so hosted/ephemeral installs aren't forced
      to write into the package.
    - `.gitignore` the populated `store/fsr_reference.db`; check in
      only the base image. First-time users run `fsrpb train` once.
    - Bonus: `fsrpb train --since <ts>` incremental refresh so reruns
      aren't full rescans.

D2. **User context preferences that influence every chat session**.
    Per-user (or per-workspace) preferences the agent reads at the
    top of every chat so it doesn't re-derive house style each time.
    Examples the user called out:
    - "When we block on an endpoint, we use CrowdStrike + endpoint
      quarantine."
    - "Default ticketing system is ServiceNow incidents."
    - "All approvals route through the SOC analyst queue."
    Plan:
    - Storage: a `user_preferences` table (or YAML file under the
      user's profile dir) with rows like `{scope, intent_pattern,
      preferred_connector, preferred_operation, notes}`. Free-form
      `notes` field too — anything the user wants the agent to know.
    - Surface: prepend a compact preferences block to the system
      prompt at chat start (cap size; cache-friendly so this doesn't
      blow the prompt cache).
    - Hookpoints: when the agent calls `find_step_recipe` /
      `find_connector` / `find_operation`, post-filter or up-rank
      results that match the user's preferences. (E.g. "block ip on
      endpoint" should surface CrowdStrike before the alphabetical
      first match.)
    - UI: simple settings page under the History tab to add/edit/
      delete preferences; CLI `fsrpb prefs` mirror.
    - Test: an eval harness scenario that runs the same prompt
      with/without a preference and asserts the right connector got
      selected.

D3. ~~**Wire `api_examples_catalog/catalog.sqlite` into fsrpb as a
    first-class lookup**.~~ ✅ Superseded by
    [`CONNECTOR_INTEGRATION_PLAN.md`](docs/plans/CONNECTOR_INTEGRATION_PLAN.md)
    Phases 0 + 0.5 (commit `b4ad73d`). The catalog is now ATTACHed and
    surfaced via `find_api_product`, `find_api_example` (FTS5), and
    `find_api_fixture` (with response/parameters schemas). The bigger
    `propose_http_fallback` story — native op → connector `api_call`
    escape hatch → http fixture → `no_grounded_shape` — also landed.
    Still open from the original D3 plan, deferred to D1 sidecar
    decision:
    - Distribution of the 437 MB catalog (slim vs full sidecar).
    - D2 user-pref tie-in (auto-call when "block on endpoint → CrowdStrike"
      preference matches).

## Chat-review landings follow-ups (session c44c6e36)

✅ Regression tests landed — `python/tests/test_chat_review_landings.py`
(12 cases).

Open:

1. **Eval re-baseline** — re-run agentic_anthropic + agentic_lmstudio
   on the "Confirm Before Block" task; compare to c44c6e36 transcript.

Shipped 2026-05-16:
- ✅ `get_op_schema` flat `visibility: {always, when}` block alongside
  `param_groups_by_select` — `tools_discovery.py:_build_visibility_block`.
- ✅ `get_step_type(set_variable)/friendly_form` surfaces `message_block`
  with per-key docs (content/tags/type/thread/record/records).
- ✅ Live picklist resolution for `message.type` — resolver queries
  `picklists` table for `'Comment Type'` first; falls back to hardcoded
  IRI map. Warning lists live options.
- ✅ `message.tags` live verification — new `tags(name, iri)` table
  hydrated by `probe_modules` from `/api/3/tags`; resolver warns when
  a friendly tag isn't found *and* the table is populated.
- ✅ Linter parity: `rule_connector_param_visibility` in
  `rulesets/_shared.py`, registered on both data-ingest and feed-ingest.

## Pending — agentic eval re-baseline (2026-05-07)

Track A landed the agentic provider + scoring gates (tool_budget /
no_spiral / adherence) but the actual baseline run was deferred — it
costs API calls. Run when ready:

```
ANTHROPIC_API_KEY=… fsrpb evals --models gold,agentic_anthropic --save
LMSTUDIO_BASE_URL=… fsrpb evals --models gold,agentic_lmstudio --save
fsrpb evals --baseline 20260507T132623Z   # delta vs the gold-only smoke
```

Compare cells to see whether the Track-B slimming + Track-C auto-fixes
moved the agentic providers' p95 tool count / spiral counts. Archive
under `store/eval_runs/`; if regressions appear, the gates will surface
them per-cell.

**Since 2026-05-07** several refinements have landed that should also
show up in the re-baseline delta:

- Refinement A (cached static grammar block, commit `18adb53`) —
  expect `get_step_type` / `find_jinja_filter` call counts to drop.
- 22 latent MCP tools surfaced in `system_prompt.md` (commit `9ca5a36`
  era, in working tree) — expect non-zero call counts on
  `propose_http_fallback`, `why_did_playbook_fail`, picklist discovery.
- Connector Phase 0 + 0.5 (commit `b4ad73d`) — eval task #21
  (`soc_http_fallback_no_native_op`) is the dedicated probe for
  whether the agent reaches for `propose_http_fallback` vs dead-ending.
- 5 new SOC/NOC/ITOps/DevOps eval tasks (17–21) added.

The pre-2026-05-07 baseline (`20260507T132623Z`) is therefore stale
as a single comparison; consider running fresh with **all** current
gates and using *that* run as the baseline going forward.

## Success ladder + LLM-agnostic groundwork

All 11 items shipped 2026-05-06. Strategy in
`docs/archive/CHAT_APP_PLAN.md` "Success ladder + LLM-agnostic strategy".

| # | Item | Code |
|---|---|---|
| I1+I2 | Picklist + connector prechecks | `python/recipes/prechecks.py`; MCP `precheck_connector_installed`, `precheck_picklist_value` |
| 2 | `resolve_yaml` MCP tool + `fsrpb resolve` CLI | `python/mcp_server.py`, `python/cli.py` |
| 3 | `run_op` returns `output_top_keys` / `output_is_list` / `schema_cached` | `python/mcp_server.py` |
| 4 | Variable-reachability ruleset (`_compute_predecessors` + `_check_jinja_paths`) | `python/compiler/validator.py` |
| 5 | `step_through_playbook` MCP — DAG walk + live Jinja render + safe-op exec | `python/mcp_server.py` |
| 6 | `assert_playbook_outcome` MCP + `fsrpb assert` CLI (3 assertion kinds) | `python/tests/test_assert_outcome.py` |
| 7 | External system prompt + structured tool I/O envelopes | `python/agent/system_prompt.md`, `python/mcp_server.py:_err` |
| 8 | LLM evaluation harness (`fsrpb evals`) | `python/evals/` |
| 9 | `diagnose_yaml_against_pb_execution` MCP tool | `python/tests/test_diagnose.py` |
| 10 | Demo reset (`fsrpb demo prep`) + full transcript capture | `web/backend/history.py:chat_messages` |
| 11 | Inventory web dashboard | `web/backend/routes/ref.py`, `web/frontend/src/routes/inventory/` |

Open follow-ups: per-step-type handler taxonomy for full I10 stepper;
token-budget audit on remaining tools (default `verbose=False` everywhere).

## Step-corpus + branch-validator follow-ups

Context: `playbook_steps` table + `probe_playbook_steps` ingester +
`fsrpb find-step-examples`. Live FSR corpus: 1,690 workflows / 7,122
steps; full per-type breakdown previously inlined here was historical
trivia — query the DB instead.

| Item | Status | Note / code |
|---|---|---|
| I12 Live-FSR ingestion path for `playbook_steps` | ✅ 2026-05-06 | `fsrpb probe playbook-steps --live`; `python/probes/probe_playbook_steps.py` |
| I15 Shared branch-validator helper | ✅ refined | Decision + ManualInput branch checks in `python/compiler/validator.py` |
| I17 Full formType catalog (ipv4/ipv6/domain/phone/filehash/picklist/…) | ✅ 2026-05-06 | `resolver._INPUT_FIELD_KINDS` |
| I20 Mode-aware co-presence checker for ManualInput | ✅ 2026-05-06 | `resolver._check_manual_input_modes` |
| I21 Accept `type: DecisionBased` (button-only flows) | ✅ 2026-05-06 | resolver |
| I22 Per-option `next:` lifted into branches; primary auto-promotion logic | ✅ 2026-05-06 | resolver |
| I23 `kind: lookup` requires `module:`; `kind: picklist` requires `picklist:` | ✅ 2026-05-06 | resolver |
| I26 Hover docs for `arguments:` per step type | ✅ 2026-05-06 | `web/backend/step_args_help.py`, `yamlHover.ts` |
| I27 History tab: chat replay + thumb up/down + review summary | ✅ 2026-05-06 | `web/backend/routes/history.py`, `web/frontend/src/routes/history/` |
| I28–I32 Feedback-driven hardening (set_variable typo, UUID step-id lint, next_fix, terse find_*, system-prompt rules) | ✅ 2026-05-06 | resolver + linter + `mcp_server.py` |
| I34 Session replay into Design page | ✅ 2026-05-06 | `sessionReplay.ts`, Design `?session=` |
| I35 Bias fix (placeholder YAML not sent) + draft revisions | ✅ 2026-05-06 | `routes/chat.py:_is_meaningful_yaml`, `yamlStore.svelte.ts` |
| I36 Chat-review tool — 8 pattern detectors | ✅ 2026-05-06 | `python/chat_review.py`, `fsrpb chat-review` |
| I37 Detect "agent didn't add the playbook to the UI" failure | ✅ 2026-05-06 | chat_review detectors `no_editor_update`, `yaml_in_wrong_fence` |
| I16 Per-option `next:` on manual_input | ✅ shipped | resolver `_normalize_manual_input_args` lifts into `step.branches` |
| I18 Did-you-mean on unknown `kind:` | ✅ 2026-05-16 | alias map + difflib in `_expand_input_variables` |
| I25 Friendly `default: <step_id>` on decision | ✅ 2026-05-16 | parser synthesizes Else default-condition row |

I24 (MI form-builder round-trip) **deprioritized** — UI-cosmetic keys
confirmed.

### Open

- ✅ I13 Corpus shape audit — 2026-05-16; `probe_corpus_audit.py` +
  `fsrpb audit-shapes`. Initial run surfaced cross-step universal keys
  (`when`, `for_each`, `do_until`, `ignore_errors`, `message`, `name`)
  that resolver normalizers reject when they shouldn't; follow-up to
  promote these to step-level fields (see "Refine the YAML grammar"
  backlog item).
- ✅ I14 `_INPUT_FIELD_KINDS` drift audit — 2026-05-16; reframed from
  "auto-derive" to drift check, since friendly kind names have no
  in-corpus signal. Audit flags corpus tuples no kind projects to. Open:
  add a `text` variant with `templateUrl=None` (48 MI rows use it) and a
  `textarea_json` kind (`textarea/text/string/.../json.html`, 11 rows).
- ✅ I19 `why_did_playbook_fail` MCP tool — 2026-05-16;
  `tools_recipe.why_did_playbook_fail`. Accepts a playbook name OR
  workflow PK / task_id UUID; when no yaml_text is supplied it
  pulls the live playbook + decompiles via the CLI helpers.
- **I33 Richer "did you mean" mining for empty searches.** Partly
  covered by I32's difflib pass; revisit when more thumbs-down rows
  arrive.

## Architecture review findings

Project structure is sound: compiler + SQLite reference store + MCP
server with deterministic lookups; LLM authors YAML and sequences
tools, doesn't drive resolution. **Invariants to preserve**:
- SQLite is the single source of truth.
- Compiler is a library — no `print()`, all errors are structured.
- `is_trusted=1` only when source ∈ {live_api_get, backend_introspect}
  AND `verifications` row says `tested_pass`.
- LLM doesn't resolve references.

Shipped from this review:
- ✅ I1 picklist precheck — `python/recipes/prechecks.py`,
  `precheck_picklist_value` MCP. (Server-side resolution in
  record-write payloads landed 2026-05-15 too — see Foundations.)
- ✅ I2 connector-installed precheck — `precheck_connector_installed`.
- ✅ I3 recipe persistence + `generate_recipe` / `find_recipe` MCP.
- ✅ Linter v1 core 3 (Norway / step-name charset / mock_result) —
  `python/compiler/linter.py`.
- ✅ I10 stepper skeleton — `step_through_playbook` MCP.
- ✅ `diagnose_yaml_against_pb_execution` MCP.
- ✅ `run_op` returns shape inline; tool-result envelopes (`{ok, code,
  suggestions[]}`).
- ✅ Inventory dashboard — `python/inventory.py`, `fsrpb inventory`,
  `/api/ref/inventory`.

Open follow-ups:

- **Tool-result cap audit in `web/backend/routes/chat.py`** — 4000-char
  truncation is too aggressive for `get_op_schema` / `search_playbooks`.
  Either stream or raise the cap per tool category.
- **SQLite efficiency wins (low-pri):**
  - FTS5 on `connectors`/`operations` (today `find_connector` uses LIKE).
  - `param_options(connector, op, param, label, value, iri)` table so
    SQL — not Python JSON-decode — filters picklist options.
  - Move `connector_config_map.json` into a `connector_configs` SQLite
    table populated by `probe_connectors` tier 1.
  - Widen `playbooks_seen` FTS to index Jinja exprs / step args /
    connector calls so agents can search by intent.
- **Freshness sync** — probes are on-demand. For 24/7 agent use, add a
  background sync (hourly or change-notification driven). Also picks up
  picklist edits so the friendly-token NFR doesn't drift.
- **Multi-provider cost tracking** — stamp `model` into every
  `UsageEvent` (`web/backend/llm/provider.py`) so per-turn pricing
  works across mid-chat provider switches.

### HTTP virtual-connector + `api_examples_catalog`

Mostly subsumed by
[`CONNECTOR_INTEGRATION_PLAN.md`](docs/plans/CONNECTOR_INTEGRATION_PLAN.md).
Status:

- ✅ Catalog ATTACHed + queryable (`find_api_product`,
  `find_api_example` FTS5 join, `find_api_fixture` with schemas).
- ✅ `propose_http_fallback` decision tree (native op → connector
  `api_call` → http fixture → `no_grounded_shape`) emits a
  ready-to-paste `http` connector step with auth-wiring warnings.
- ✅ `synthesize_http_step` MCP (entry → step) — already shipped
  earlier; pair it with `find_api_fixture` for OpenAPI-grounded
  shapes.
- ⏳ **HTTP v2.0.0 not in DB** — re-run `probe_connectors` against
  `Miscellaneous/connector_building/http` (adds `http_paginate`,
  `fetch_records`).
- ⏳ **`http-virtual-connector` recipe kind** — when no native
  connector, emit a *whole* playbook seeded from catalog request
  shape (not just one step). Different surface than
  `propose_http_fallback`; multi-step pattern.
- ⏳ **`connector_catalog_map(connector_name, catalog_product_id,
  confidence)`** cross-link — would let the agent skip the fuzzy
  match for vendors with stable mappings. Low priority; the runtime
  match works.
- ⏳ **Pagination + auth taxonomy mapping to HTTP connector enums** —
  today `propose_http_fallback` emits header hints; an authoritative
  mapping per FSR HTTP-connector auth enum would tighten it up.

## Ingestion recipe + validator follow-ups

Threat-feed + data-ingest recipe generators
(`python/recipes/generator.py`, `fsrpb generate-recipe`) + validator
rulesets (`python/compiler/rulesets/`) are live.

Shipped:
- ✅ I1/I2 picklist + connector prechecks → see Success ladder.
- ✅ I3 recipe persistence + `generate_recipe`/`find_recipe` MCP.
- ✅ I4 `generate_recipe` MCP wrapper.
- ✅ I7 recipe gold-standard test fixtures (`test_recipe_gold.py`).
- ✅ I10 stepper skeleton (`step_through_playbook` MCP).
- ✅ I5 `compile --lax` flag — 2026-05-16; `compile_yaml(lax_codes=…)`
  + CLI `--lax` demotes `unknown_param`/`unknown_connector` to warnings.

Open:

- **I6 Extract + index RPM-bundled playbooks.** `store/rpm_cache/` holds
  RPMs; each contains a `playbooks/playbooks.json`. We ingest connector
  metadata but not the playbooks. New `python/probes/probe_rpm_playbooks.py`.
- **I8 Use connector-provided sample data in env_setup branch.** Today's
  `Return Sample Data` step emits a hardcoded 2-record placeholder.
  Synthesize from `output_schema` or use `sample_response` field if the
  connector ships one. ~1.5 hr.
- **I9 Live-probe sample data via `run_op` during recipe generation.**
  Stronger I8: call `run_op(connector, op, {limit: 1, ...})` and embed
  the captured response as sample data; walk it to suggest mappings;
  render-check picklist Jinja calls against captured values. ~3 hr.
- **Full I10 per-step-type handler taxonomy** for the stepper. Reuses
  `run_op`, `fsrpb env`, `render_jinja`, compiler IR, destructive-op
  confirm guard.

## Backlog (open)

Each item is grounded in something a recent session exposed; estimates
assume the patterns established in 2026-05-03/04 are followed.

0. **Eval scoring bug — `live_tested` gate `no_dry_run_target`** (surfaced 2026-05-25 by re-baseline run `20260525T165836Z`). Every YAML-emitting task in the re-baseline lost 1 point because the eval's `dry_run_kwargs` is built without a `playbook` name. Fix is in `python/evals/scoring.py` (or wherever the `live_tested` level constructs the dry-run call) — populate `playbook` from the compiled IR's first playbook name. ~30 min.

1. **Slim the other big tools the way `get_step_type` was slimmed.**
   Token analyzer + history db are built (`fsrpb chat-stats`,
   `web/backend/usage.jsonl`, `history.cost_by_playbook()`). Run a real
   chat session and trim whatever sits at the top of the tool-cost
   ranking. Likely candidates: `search_playbooks` (full snippet JSON × N),
   `validate_yaml` (returns the entire compiled collection), `decompile`.
   Pattern: add a `verbose: bool = False` parameter + default cap,
   mirroring `get_step_type`. ~1 hr after seeing real data.

3. **Investigate the `--mode upsert` HTTP 400.** Every push to
   `/api/3/bulkupsert/workflow_collections` 500s with a generic
   `TypeError` from FSR. Replace mode works as a workaround. Either fix
   the payload shape or remove the `upsert` option from `cli.py:cmd_push`
   and document why. Reproduce with `fsrpb push --mode upsert <yaml>`.
   ~1 hr.

4. ~~Roundtrip test against the friendly-form examples.~~ ✅ 2026-05-16
   22/22 examples green (compile → decompile → recompile).

5. **Smoke test for the 9 examples without `.test.yaml` sidecars**
   (`decision_branch`, `find_and_update`, `hello_connector`,
   `ip_reputation_check`, `ip_reputation_check_abuseipdb`,
   `manual_input_then_act`, `parent_calls_child`, `test_complex_e2e`,
   `test_manual_input_e2e`). A "compile + push + check link 200" smoke
   per example would catch regressions like the URL-pattern bug fixed
   2026-05-04 (`cli.py:cmd_push`'s post-push GET on
   `/api/3/workflows/<uuid>`).

6. **History tab UI** — backend done (see 2026-05-04 changes); UI still
   parked. Need: `GET /api/history?type=push|chat`, `GET /api/history/push/<id>`,
   `GET /api/history/push/<id>/diff?against=<id>` (use `history.yaml_diff`),
   `GET /api/history/cost-by-playbook`. Frontend `/history` route already
   exists as a stub in `web/frontend/src/routes/history/+page.svelte`.
   Reader fns in `web/backend/history.py` already shaped for the UI:
   `timeline()`, `list_pushes()`, `get_push()`, `previous_push()`,
   `list_chat_sessions()`, `get_chat_session()`, `cost_by_playbook()`.

7. **Promote drafts to backend (optional)**. Editor drafts live in
   localStorage today (`web/frontend/src/lib/yamlStore.svelte.ts`). Once
   #6 lands, drafts can be persisted into `history.db` for cross-browser
   sync + cross-reference with pushes. Not blocking.

8. **Push overwrite safeguard for imported playbooks.** `pull` /
   decompile already lets users import playbooks from a live FSR. The
   risk is the inverse direction: `fsrpb push --mode replace` does PUT →
   POST → PURGE+POST, which will silently clobber any out-of-band edits
   made on the FSR side after the pull. Add a drift-detection step
   (compare local IR vs. live collection's current state) and require an
   explicit `--confirm-overwrite` (or interactive y/N) when drift is
   detected. Goal: a user who pulled a playbook, then pushed back days
   later, can never lose someone else's UI edits without acknowledging
   them. Pure import (collection doesn't exist yet) needs no confirm.

9. **Refine the YAML grammar + linter for agent/human ergonomics.**
   Mostly landed via `python/compiler/linter.py` + `validator.py` +
   strict-whitelist normalizers in `resolver.py`. Negative round-trip
   scenarios in `probe_round_trip.py` (neg_norway_branch,
   neg_dup_name, neg_no_trigger, neg_dangling_next, neg_unreachable,
   neg_two_defaults, neg_unknown_type, neg_unknown_picklist) prove
   each rule fires.

   ✅ Already in place:
   - Strict-whitelist `_FRIENDLY`/`_CANONICAL` per step type.
   - Norway problem (`linter._scan_norway`).
   - Step name charset `[A-Za-z0-9 _]` (`linter._check_step_name`, auto-renames).
   - Jinja paths against upstream output schema (`validator._check_jinja_paths`).
   - Missing `mock_result` on Fetch + IngestBulkFeed (`linter._check_mock_result`).

   Still open:
   - Promote `for_each` / `when` / `mock_result` / `step_variables`
     to first-class step-level fields (siblings of `arguments`).
   - Friendlier shapes: shorthand decision conditions, sugar for
     `resource:` blocks, single `set:` for inline-vars.
   - **Mocked-runs failure-branch lint** — `cyops_utilities.raise_exception`
     honors `useMockOutput=true` and returns null. Recipes that route
     to a Raise Exception failure branch report `finished` under
     `--mock` even though the failure path was taken. Lint should warn.
   - Updated `AUTHORING.md` + `fsrpb lint <file>` subcommand surface.


## Where we are

Compiler v1, reference store, live e2e (push/run/poll/env), MCP server
(16 tools), corpus-mined Jinja docs, visual editor with inspector
authoring, picklist friendly-token NFR, and an 18-scenario round-trip
probe are all live.

| Probe | Captures | Status |
|---|---|---|
| `probe_api_endpoints` | Hydra root + dashboard inventory | live |
| `probe_connectors` | 3 tiers (live → solutionpacks → fortinet RPM, fingerprint diff) | 714 connectors / 6,762 ops / 6,097 w/ params (90%) |
| `probe_modules` | `staging_model_metadatas` + `picklist_names` + picklist IRI map | 62 modules / 1,233 fields / 710 picklist items |
| `probe_playbooks` + `probe_playbook_steps` | Step types + corpus + recipes | 43 step types / 1,669 playbooks / 7,122 steps |
| `probe_jinja` + `probe_jinja_backend` + `probe_jinja_corpus` | Filter catalog + backend introspection + corpus idioms | 170 filters / 19,305 blocks → 7,789 unique idioms |
| `probe_step_handlers` | FUNCTION_MAP signatures | 100% |
| `probe_round_trip` | YAML → push → pull → assert (18 scenarios incl. negatives) | 18/18 green |

DB at `store/fsr_reference.db`, schema at `store/schema.sql`. All probes
idempotent; `python/probes/_env.py` loads `.env`.

## Trust model

- Local sources (rpm_info_json, schema_json, schema_ts, widget_constants,
  playbook_guide_pdf) → always `seen` only, never trusted.
- Live methods (live_api_get, live_api_render, live_op_exec, playbook_e2e)
  with `tested_pass` → `is_trusted=1` in `v_verification_state`.
- `backend_introspect` is the highest-trust method — reads Python
  objects on the FSR box.

## Foundations (all shipped — kept as a one-glance summary)

| Capability | Status | Code |
|---|---|---|
| FSR-custom Jinja filter cheatsheet | ✅ 2026-05-02 | `store/FSR_CUSTOM_JINJA.md`, `python/store/export_jinja_cheatsheet.py` |
| Step-type backend introspection (`FUNCTION_MAP`, 44 handlers) | ✅ 2026-05-02 | `store/fsr_reference.db` → `step_handlers` |
| Live-instance e2e probes (compile→push→trigger→poll) | ✅ 2026-05-03 | `python/cli.py`, `python/probes/probe_round_trip.py` |
| Compiler v1 pipeline (parse → resolve → validate → emit + decompile + roundtrip) | ✅ 1596/1596 corpus match | `python/compiler/` |
| Argument-shape validation against `step_handlers` | ✅ | `python/compiler/arg_validator.py` |
| Idempotent `fsrpb push --mode replace` (PUT → POST → PURGE+POST w/ child-workflow purge) | ✅ 2026-05-03 | `python/cli.py:cmd_push` |
| MCP server v1 (16 tools over stdio) | ✅ 2026-05-03 | `python/mcp_server.py` |
| Read-only probes: CONNECTORS.md, RECIPES.md, YAQL, globalVars, bulkupsert, delete endpoints, picklist hydration | ✅ 2026-05-03 | `python/store/`, `python/probes/` |
| `fsrpb pull / diff / status` | ✅ 2026-05-03 | `python/cli.py` |
| `dry_run_playbook` + `step_through_playbook` + `assert_playbook_outcome` MCP tools | ✅ 2026-05-06 | `python/mcp_server.py` |
| `fsrpb push` re-push parking (see git history if you need the recycle-bin notes) | — | archived 2026-05-15 |

### Open follow-ups carried forward

- ✅ `render_jinja` non-string scalar bug — 2026-05-16,
  `python/mcp_server/tools_jinja.py` now JSON-decodes string-wrapped
  bodies before unwrapping `result`/`output`/…
- **`fsrpb pull "<name>"`** filter — `?name=` exact-match returned 0
  hits historically (URL-encoding workaround documented in docs/research/GAPS.md
  §4). Verify the fix landed in `python/cli.py:cmd_pull` or apply.
- **`--mode upsert` HTTP 400** — `POST /api/3/bulkupsert/workflow_collections`
  500s with PHP-side bugs in `UpsertController.php`. Either remove
  the option or wait for FSR-side fix; not blocking.
- **Backend recon ingestion** — `scripts/fsr_recon.sh` tarball
  unpacks under `store/incoming/recon_<ts>/`; needs a `probe_recon.py`
  ingester.
- **Cross-project doc updates** — add `POST /api/integration/connectors/{name}/{version}/?format=json`
  to FORTISOAR_API.md; note `/api/3/connectors` is a Hydra ghost (404s).

### Parked backlog (still listed; pick up as needed)

- More example YAMLs (decision_branch, parallel paths — many landed; audit).
- TS compiler port skeleton (`ts/src/compiler/`).
- `fsrpb explain jinja_filter | module | recipe` (only `connector`/`step`/`handler` wired today).
- AUTHORING.md single-source doc.
- YAQL filter language probe (separate from Jinja).
- Per-filter input-type contract probe (str/list/dict/int → `input_type_hint`).
- Multi-version connector support (PK from `name` → `(name, version)`).
- `probe_workflow_runtime` — exercise `wf/workflow/tasks/<func>/` for `no_op`, `add`, `set_multiple`.
- Rerun `probe_jinja` after `probe_jinja_backend` to overlay observed types.

## Cross-project doc updates pending

Already updated `soar-reporting-dashboard-cl/docs/FORTISOAR_API.md` with:
- "Endpoints used by `fsrpb`" section
- Power-user `/api/3/*` query options (dot notation, `$fields=`, `$exists=`,
  `$relationships=true`)
- `/api/query/*` pagination quirk (use `?$limit&$page`, body params ignored)
- Jinja render endpoint + filter catalog + type discipline + generator-list

Should still update:
- Add `POST /api/integration/connectors/{name}/{version}/?format=json` as a
  confirmed-live entry (it's working but not yet in the API doc).
- Note that `/api/3/connectors` is a Hydra ghost (advertises but 404s).

## Key files / paths

- Live plan: `Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md`
- Open gaps: `docs/research/GAPS.md`
- API truth: `soar-reporting-dashboard-cl/docs/FORTISOAR_API.md`
- Schema: `store/schema.sql`
- Probes: `python/probes/probe_*.py`
- Backend dump scripts: `scripts/dump_jinja_filters.py`
  (next: `scripts/dump_step_types.py`)
- Incoming backend dumps: `store/incoming/filters.json` (170 filters
  introspected from `/opt/cyops-workflow/sealab/.../sealab.jinja`)
