# fsr-playbook-framework — reorganization plan (separation of concerns)

**Goal:** make this repo cleanly separated by concern — a shippable authoring **library**
(`fsr_playbooks`) distinct from non-shipped **tooling** (probes/deploy/e2e/evals), **data**
(the reference cache), **investigation/triage** (which belongs to the SOC connector), and the
**web/ts** product surface.

**Hard constraint (governs everything below):** the FortiSOAR SOC connector
(`ConnectorsV2/.../connector-fsr-soc-assistant`) **consumes this library**. Today it vendors a
copy/symlink; soon it will `pip install fsr_playbooks`. So *every move of a module the connector
imports is a breaking change to the connector* until the connector is cut over. Refactor behind
a stable surface; coordinate the genuinely-breaking moves as paired library+connector commits.

Related plans: the public-package re-scope + extraction boundary lives in
`pyfsr/docs/plans/FOLLOWUPS.md` items 0/3/6 — this doc is the repo-layout execution of that.

---

## 0. The import contract (the safety foundation — do this analysis FIRST)

The connector's `operations.py` imports ~50 deep paths into the library. They split in two:

**A. STAYS in `fsr_playbooks` (authoring) — must remain importable at stable paths:**
- `fsr_playbooks.compiler.*` — `compile_yaml`, `parse_yaml`, `resolver.Resolver`, `typed_walker`,
  `validator`, `ir.{Collection,Playbook,Step}`, `render_paths`, `skill_compiler`, `skill_verify`,
  `parser._slugify`
- `fsr_playbooks.llm.*` generic runtime — `provider.{Message,UsageEvent}`, `run_turn.run_agent_turn`,
  `anthropic_provider`, `openai_provider`, `intents`, `approvals`, `tools.anthropic_tools`
- `fsr_playbooks.agent.skill_trace.*`, `fsr_playbooks.protocols.*`
- `fsr_playbooks.mcp_server` authoring tools — `tools_compile.build_playbook_from_trace`,
  `_sim_fixtures`, `_sim_client`, `_shared`

**B. MOVES to the connector (investigation/triage) — connector rewrites these imports to its
own new local home, NOT `fsr_playbooks.*`:**
- `fsr_playbooks.llm.triage_{normalize,scenarios,preflight,sources}` → connector
- `fsr_playbooks.llm.tools._tier_for_run_op` — ⚠️ `llm/tools.py` is **mixed** (authoring
  `anthropic_tools` STAYS, triage `_tier_for_run_op` MOVES) → a per-symbol split point
- `fsr_playbooks.mcp_server.{tools_execution,tools_agent,_live_crudhub}` → connector

**Action:** freeze surface A as the library's public contract (re-export the canonical names
from `fsr_playbooks/__init__.py` and each subpackage `__init__`, so internal file moves don't
change what the connector sees). Surface B is the coordinated-cutover set.

---

## Library sync strategy — DECIDED (2026-06-17): pin to the published package

**Problem this kills:** the connector currently vendors a *hand-maintained copy* of
`fsr_playbooks` that has drifted from canonical (health check: 11 files differ, connector
missing 4, stale-behind). A copy anyone can edit will always drift.

**Decision — Option A:** target appliances **have package-index access at install time**, so the
connector declares a **pinned dependency** and **deletes the vendored copy** entirely:
- `requirements.txt`: `fsr_playbooks[mcp]==<pinned>` (currently 0.3.65; aligns deps —
  pulls `jinja2`/`ruamel.yaml`/`mcp`, fixing today's incomplete requirements.txt).
- Remove `connector-fsr-soc-assistant/fsr_playbooks/` and `fsr_core.bak` from the repo.
- Appliance pip-installs the pinned version → **no second copy → drift structurally impossible.**
- Updating the library = bump one version string (review the changelog, re-run the mock gate).

**Why not git subtree/submodule:** they keep an editable in-repo copy — the very thing that
drifted. A pinned package is read-only-by-construction. (Revisit only if an appliance ever
loses index access → fall back to Option B: vendor the *published wheel* at build time, pinned,
with a CI check that the vendored tree == the pin. Never hand-copy.)

**Precondition (couples to Phase 1):** the connector must stop *owning/editing* library code
first. Today it imports+edits triage from `fsr_playbooks.llm.triage_*`. After Phase 1 carves
triage *into* the connector (connector-owned) and leaves compiler/authoring read-only upstream,
the pinned dependency covers only code the connector never edits. **Drift reconciliation is
trivial:** the health check shows the connector is purely stale-behind except ~7 conn-only lines
in `mcp_server/{tools_noc,_sim_fixtures}.py` — both in the carve-out cluster, so eyeball those 7
lines during Phase 1 and nothing is lost at cutover.

## Target layout

```
fsr-playbook-framework/
├── fsr_playbooks/              # THE LIBRARY (shippable; surface A only after Phase 1)
│   ├── compiler/               # authoring core — no LLM, no transport (already an island)
│   ├── llm/                    # generic LLM runtime + build-agent assist   [llm extra]
│   ├── agent/                  # build-agent prompts/trace (system_prompt_build.md)
│   ├── mcp_server/             # authoring MCP delivery (compile/emit/verify/jinja/...) [mcp extra]
│   └── protocols.py
├── tooling/                    # NON-shipped dev/ops (was python/ + root scripts)
│   ├── probes/                 # cache builder — needs a live appliance
│   ├── catalog/                # build_compile_catalog.py (slim-DB builder)
│   ├── deploy/                 # cli.py + pyfsr push/run glue
│   ├── e2e/  evals/            # harnesses
│   └── scratch/                # ad-hoc one-offs (_poll_*, demo_hunt, seed_noc_alert, ...) or delete
├── data/                       # was store/ — heavy artifacts, gitignored
│   └── slim/fsr_reference.db   # ~1 MB globally-stable cache (TRACKED, ships as package-data)
├── packaging/fsr_playbooks/    # the dist (exists)
├── web/  ts/                   # frontend product surface (separate concern)
├── docs/                       # consolidated (root *.md move here)
└── scripts/                    # build/publish shell only
```

---

## Phased plan (each phase ends at a GREEN GATE before the next starts)

### Phase 0 — Freeze the public surface (no behavior change, no risk to connector) — ✅ DONE (2026-06-17)
1. ✅ Inventory surface A precisely (the list above; re-grep the connector to confirm none added).
   Re-grepped `operations.py`+connector: surface A also includes
   `compiler.{samples,errors,decompiler,render_analyzer,mi_output_catalog}`,
   `llm.{usage_log,fake_provider,_loop_helpers}`, `mcp_server.tools_discovery` — all folded in.
2. ✅ Add re-exports so every surface-A name is reachable from a stable path
   (`compiler/__init__`: typed_walker/render_paths/skill_compiler/skill_verify/_slugify;
   `llm/__init__`: provider + Message/UsageEvent — kept `anthropic_provider`/`openai_provider`/
   `intents`/`approvals` LAZY because `anthropic_provider` builds the tool REGISTRY at import time
   and must load after the mcp_server discovery tools register; `agent/__init__`: skill_trace).
3. ✅ **Gate:** library suite green (445 passed, +48 new); `import fsr_playbooks` clean;
   vendored-copy surface-A import-smoke resolves (only optional `openai` absent). Full
   `import operations` needs the FortiSOAR `connectors` SDK (not installed locally) — deferred to
   the appliance smoke. Added `tests/test_public_surface_contract.py` as the standing safety net.
*This is the net that lets later internal moves be non-breaking.*

### Phase 1 — Carve out investigation/triage (surface B) — ✅ LIBRARY SIDE DONE (2026-06-17)

> **Scope decision (2026-06-17, owner):** the framework repo is to hold **only the playbook
> authoring/compilation library + the web frontend**. Investigation/triage (SIEM/FAZ search, alert
> records, NOC device diagnostics, live crudhub) is NOT authoring → removed from the library.
> The mental model that governs the cut: **"library makes playbooks; connector investigates
> incidents."** `tools_execution` (run/push/dry-run/healthcheck playbooks) is kept — running and
> deploying a playbook is part of the authoring lifecycle.
>
> **Done (library side, branch `reorg/phase-0-freeze-surface`):** removed 11 modules
> (`llm/triage_*`, `mcp_server/{tools_triage,tools_noc,_live_crudhub,_noc_scenarios,noc_scenarios.json}`,
> `agent/system_prompt_triage.md`) + 17 investigation tests; pruned `mcp_server/__init__.py` and
> `llm/tools.py` (SAFE_TOOLS/TOOL_TIERS) of investigation tools; severed the two authoring→investigation
> tendrils (`tools_jinja.render_jinja`'s `from_pb_execution`, `tools_recipe.assert_playbook_outcome`)
> to degrade gracefully. **Gate: import clean, suite 267 passed, surface-A contract 48 green.**
>
> **NOTE — connector unaffected:** the connector still vendors its own full copy of `fsr_playbooks`,
> so removing investigation from the *canonical* library does not break it. Connector absorption of
> the removed modules into a connector-owned home (+ `operations.py` import rewrite) and the pinned-
> package cutover remain — and can't be gated offline here (needs the FortiSOAR `connectors` SDK).
> The original surface-A/B "paired commit" framing below assumed the connector imported from the
> canonical library; it doesn't yet (it vendors), so library-first removal is safe.

<details><summary>Original surface-B carve-out steps (superseded by the scope decision above)</summary>
1. Split `llm/tools.py`: keep `anthropic_tools` (authoring) in the library; move
   `_tier_for_run_op` + triage helpers out.
2. Move surface-B modules (`llm/triage_*`, `mcp_server/tools_{execution,agent}`, `_live_crudhub`,
   `agent/system_prompt_triage.md`, `mcp_server/{tools_noc,tools_analysis,_noc_scenarios,noc_scenarios.json}`)
   into the connector (its new local home), per FOLLOWUPS item 0.
3. Prune `mcp_server/__init__.py`'s eager `from . import (...)` so the library imports clean
   with surface B gone.
4. Rewrite the connector's `operations.py` surface-B imports to the new local paths.
5. **Gate:** library tests green WITHOUT triage; connector tests green importing triage locally;
   `import fsr_playbooks.mcp_server` succeeds with no triage present. **Paired commit** (library
   removal + connector absorption land together).
</details>

**Remaining Phase 1 follow-up (connector side, separate session — can't gate offline):**
- [ ] Give the connector a connector-owned home for the removed modules (or rely on its vendored copy until the Phase 5 pinned-package cutover).
- [ ] Rewrite `operations.py` investigation imports off `fsr_playbooks.*` once that home exists.
- [ ] Live appliance smoke (see pyfsr memory: lab `10.99.249.159`, module box `10.99.249.205`).

### Phase 2 — Split library vs. tooling physically
1. `git mv python/ tooling/` (preserve history); regroup into `probes/ deploy/ e2e/ evals/`.
2. Sweep ad-hoc scripts (`python/_poll_*`, `demo_hunt`, `seed_noc_alert`, `_q1_*`, `_prove_*`) →
   `tooling/scratch/` or delete. Decide per-file; don't ship them anywhere.
3. Confirm `fsr_playbooks` imports nothing from `tooling/` (already clean post-Phase-1 — the only
   leaks were the surface-B execution/recipe tools, now gone).
4. Update root `pyproject.toml` (`fsrpb` dist) package-dir/packages for the `python/`→`tooling/` move.
5. **Gate:** both test suites green; `fsrpb` CLI still runs.

### Phase 3 — Data / reference-cache reorg (resolves FOLLOWUPS item 6)
1. `store/` → `data/`; gitignore the heavy artifacts (65 MB `fsr_reference.db`, drafts, runs).
2. Add `tooling/catalog/build_compile_catalog.py`: filter the probed DB to the **globally-stable**
   tables only (step_types/handlers, jinja_*), strip connector icons → `data/slim/fsr_reference.db`
   (~1 MB, **tracked**). Instance-specific UUIDs (picklists/connectors/modules) are deliberately
   excluded — they're warmed from the target SOAR, not shipped (see item 6 + the cache analysis).
3. Wire `packaging/fsr_playbooks/pyproject.toml` to ship `data/slim/fsr_reference.db` as package-data.
4. **Verify the cache-miss fallback:** confirm the resolver degrades to a live lookup on a miss
   rather than hard-erroring (determines whether an un-warmed off-platform compile is graceful).
5. **Gate:** wheel `unzip -l` shows the ~1 MB slim DB + NO 65 MB / triage; clean-venv compile of a
   sample playbook works against the slim DB.

### Phase 4 — Docs / web / ts (cosmetic, low risk, do anytime after Phase 0)
1. Root `*.md` (ARCHITECTURE/AUTHORING/CAPABILITIES/DEMO/PRESENTATION/…) → `docs/`, leaving
   README + CLAUDE.md at root.
2. Confirm `web/` + `ts/` are import-decoupled from the library (separate product surface); if so,
   leave in place or split to their own repo later — not blocking.

### Phase 5 — Connector cutover to the pinned package (Option A — see sync strategy)
1. Add `fsr_playbooks[mcp]==<pinned>` to the connector `requirements.txt` (fixes the missing
   `jinja2`/`ruamel.yaml`/`mcp` deps in one move).
2. **Delete** `connector-fsr-soc-assistant/fsr_playbooks/` (vendored copy) and `fsr_core.bak`.
3. Confirm the carved-out triage now lives in the connector's own module (Phase 1), imported
   locally — NOT from the pinned package.
4. **Gate:** mock fixture replay diff-clean against the pinned package; then live smoke on a lab
   appliance (compile + `warmup` + a `chat_turn` + `push_playbook`).
5. Thereafter, library updates = bump the pinned version, review changelog, re-run the gate.

---

## Connector operations must keep working — and stay testable (the real acceptance bar)

The point of every gate is: **the connector's operations still run.** There's already a harness
for this — use it, don't invent one.

**Offline regression (no appliance) — the per-phase gate:**
- The connector dispatches all ops through one `operations` map (`operations.py:4496`,
  wrapped `_sim_aware`/`_mock_aware`). With `params["mode"] == "mock"`, `mock_replay.py` replays
  the 28 `fixtures/*.json` scenarios through the *same* dispatch.
- So after each phase, run the connector ops against the fixtures and assert unchanged output:
  `compile_yaml` (happy_path, compile_failure, validate_errors), `chat_turn`/`chat_resume`
  (incident_smtp_intrusion, multi_tool, approval_*), `push_playbook` (push_failure), etc.
- This exercises the surface-A imports (compiler/llm/agent) and, pre-Phase-1, the surface-B
  triage path — so a broken move shows up immediately as a fixture diff. **Capture a baseline
  fixture-run BEFORE Phase 0** and diff against it after every phase.

**Live verification (appliance) — after Phase 1 and Phase 5:**
- The ops that can't be mocked are the live ones: `warmup` (crudhub `/api/3/connectors/` ingest),
  `push_playbook`/`dry_run_playbook` (real workflow create/run). Smoke these on a lab appliance
  (see pyfsr memory: FortiAI lab `10.99.249.159`, module box `10.99.249.205`) once after the
  triage carve-out (Phase 1) and again after the package cutover (Phase 5).

**Build into the gates:** each phase's GREEN GATE = library suite + connector suite +
**`mode=mock` fixture replay diff-clean** + `import fsr_playbooks` + connector import-smoke.
Add a `make connector-mock-check` (or a `tooling/` script) wrapping the fixture replay so the
gate is one command and runnable after every move.

## Careful-refactor rules (because the connector consumes the library)
- **Never** move/rename a **surface-A** module without the Phase-0 re-export in place. The
  connector must keep importing the same names.
- **Surface-B** moves are the *only* connector-breaking changes — land each as a **paired
  library+connector commit**, never library-first.
- Use `git mv` and keep renames in commits **separate** from content edits (clean history/blame).
- Every phase ends at its GREEN GATE: library suite + connector suite + `import fsr_playbooks`
  + connector import-smoke. Do not start the next phase red.
- Sequence is intentional: **0 → 1 → 2 → 3**; 4 is parallelizable; 5 is last (needs 1+3 done).
- The `fsr_core → fsr_playbooks` rename (FOLLOWUPS 3b) is already done, so the connector already
  imports `fsr_playbooks.*` — that de-risks Phase 0 (no name churn, just re-export hardening).

## Open verifications (cheap, do before the phase that depends on them)
- [ ] Re-grep connector for any surface-A import not in the list above (Phase 0).
- [ ] Confirm `llm/tools.py` is the only mixed authoring/triage module (Phase 1 split scope).
- [ ] Confirm resolver cache-miss → live-lookup fallback exists (Phase 3 step 4).
- [ ] Confirm picklist/connector/module UUIDs are truly per-install (justifies excluding them
      from the slim DB — Phase 3 step 2).
