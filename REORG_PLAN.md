# fsr-playbook-framework — reorganization plan

## The goal (one line)

**This repo should hold only two things: the playbook *authoring* library (`fsr_playbooks`)
and the *web frontend*.** Everything else either moves out or is clearly marked non-shipped.

The mental model that decides every boundary call:

> **The library makes playbooks. The connector investigates incidents.**

So: compile / author / build / run / deploy a playbook → **library**. Search SIEM logs, pull
alert records, diagnose NOC devices, hit the live crudhub → **connector** (investigation/triage).

---

## Status at a glance

| Phase | What | State |
|------|------|-------|
| 0 | Freeze the library's public surface (re-exports + contract test) | ✅ done (`20db683`) |
| 1 | Remove investigation/triage from the library | ✅ library side done (`c040744`) |
| 1b | Connector absorbs the removed code; rewrite its imports | ⏳ separate session (needs FortiSOAR SDK) |
| 2 | Physically split non-shipped tooling (`python/` → `tooling/`) | ✅ rename + scratch sweep done; themed-subdir regroup deferred |
| 3 | Reorg the reference-cache data (`store/` → `data/`, slim DB) | ✅ done (3a rename + 3b slim DB shipped) |
| 4 | Move root docs into `docs/`; confirm `web/`+`ts/` decoupled | ☐ todo (low risk) |
| 5 | Connector cutover to a pinned `fsr_playbooks` package | ☐ last (needs 1b + 3) |

Work so far is on branch `reorg/phase-0-freeze-surface` (2 commits). Library gate is green:
`import fsr_playbooks` clean, library suite **267 passed**, surface contract **48 passed**.

---

## Target layout

```
fsr-playbook-framework/
├── fsr_playbooks/              # THE LIBRARY (authoring only) — shippable
│   ├── compiler/               # authoring core — no LLM, no transport (an island)
│   ├── llm/                    # generic LLM runtime + build-agent assist   [llm extra]
│   ├── agent/                  # build-agent prompts/trace (system_prompt_build.md)
│   ├── mcp_server/             # authoring MCP delivery (compile/emit/verify/jinja/debug/…) [mcp extra]
│   └── protocols.py
├── web/  ts/                   # the frontend product surface  ← the other thing that stays
├── tooling/                    # NON-shipped dev/ops (was python/ + root scripts)   [Phase 2]
│   ├── probes/ catalog/ deploy/ e2e/ evals/
│   └── scratch/                # ad-hoc one-offs (or delete)
├── data/                       # was store/ — heavy artifacts, gitignored             [Phase 3]
│   └── slim/fsr_reference.db   # ~1 MB globally-stable cache (TRACKED, ships as package-data)
├── packaging/fsr_playbooks/    # the dist (exists)
├── docs/                       # consolidated (root *.md move here)                   [Phase 4]
└── scripts/                    # build/publish shell only
```

---

## What "authoring only" means in practice (the boundary, decided 2026-06-17)

**STAYS — library (authoring lifecycle):**
- `compiler/*` — the whole YAML→FSR pipeline.
- `llm/*` generic runtime — provider protocol, `run_agent_turn`, anthropic/openai providers,
  intents, approvals, `tools.anthropic_tools` + the generic tier logic (`_tier_for_run_op`).
- `agent/skill_trace` + `system_prompt_build.md`; `protocols.py`.
- `mcp_server/*` authoring tools — compile, discovery, emit, jinja, verify, catalog, corpus,
  picklists, recipe, **analysis/debug** (step-through/debug-session: debugging a playbook you
  authored), the **build-agent loop** (`tools_agent`), `_shared`, `_sim_client`, `_sim_fixtures`.
- **`tools_execution`** — run / push / dry-run / healthcheck a playbook. Running and deploying
  is part of authoring, so it stays even though the connector also uses it.

**LEFT — investigation (removed from the library in Phase 1):**
- `llm/triage_{normalize,preflight,prompt,scenarios,sources}.py`
- `mcp_server/{tools_triage, tools_noc, _live_crudhub, _noc_scenarios, noc_scenarios.json}`
- `agent/system_prompt_triage.md`

**Severed tendrils (authoring tools that *optionally* reached into investigation):** these now
degrade with a clear error instead of crashing when the investigation tools are absent —
`tools_jinja.render_jinja(from_pb_execution=…)`, and `tools_recipe`'s live-run diagnostics
(`assert_playbook_outcome`, `why_did_playbook_fail`, `diagnose_yaml_against_pb_execution`) via
the `_tools_triage_or_err()` guard.

---

## Phase 0 — Freeze the public surface ✅

Added re-exports so every name the connector imports is reachable at a stable path, plus
`tests/test_public_surface_contract.py` (48 checks) as a standing safety net — if a later move
drops a path, this goes red in the library suite first.

Note: `anthropic_provider` / `openai_provider` / `intents` / `approvals` are re-exported **lazily**
(left as submodule paths, not eager `__init__` imports): `anthropic_provider` builds the tool
REGISTRY at import time and must load *after* the mcp_server discovery tools register; `openai_provider`
carries the optional `openai` dep.

## Phase 1 — Remove investigation from the library ✅ (library side)

Removed the 11 investigation modules above + 23 investigation tests (17 library, 6 `python/`
tooling); pruned `mcp_server/__init__.py` and `llm/tools.py` (`SAFE_TOOLS`/`TOOL_TIERS`); severed
the tendrils. **Gate green** (267 + 48).

**Why this was safe to land library-first:** the connector still **vendors its own full copy** of
`fsr_playbooks`, so removing investigation from the *canonical* library does not break it. (The
original plan's "paired library+connector commit" rule assumed the connector imported from the
canonical library — it doesn't yet.)

### Phase 1b — connector side (separate session; cannot be gated offline)
The connector currently imports the now-removed modules from its vendored copy. Before the Phase 5
cutover it must own them itself:
- [ ] Give the connector a connector-owned home for the investigation modules.
- [ ] Rewrite `operations.py` investigation imports off `fsr_playbooks.*` to that home.
- [ ] Eyeball the ~7 connector-only lines in `mcp_server/{tools_noc,_sim_fixtures}.py` so nothing
      is lost at cutover.
- [ ] Live appliance smoke (pyfsr memory: lab `<your-fortisoar-host>`, module box `<your-fortisoar-host>`).

> Blocked offline: a full connector run needs the FortiSOAR `connectors` SDK, which isn't installed
> here. Verify on an appliance.

## Phase 2 — Split library vs. non-shipped tooling ✅ (rename; regroup deferred)
1. ✅ `git mv python/ tooling/` (history preserved — 204 renames). Path refs rewired:
   `fsrpb_main.py` sys.path bootstrap, `pyproject.toml` `package-dir`, `pytest.ini` `testpaths`,
   `Makefile`, `.gitlab-ci.yml`, `CLAUDE.md`, `AGENTLESS.md`, plus every functional `/ "python"`
   sys.path/cwd construction in `tooling/**` and `web/backend/**`.
2. ✅ Ad-hoc one-offs swept to `tooling/scratch/`: the 3 Phase-1 orphans
   (`gen_fs_recipes,seed_noc_alert,demo_hunt`, tracked) + 5 untracked `_*.py` probes
   (`tooling/scratch/_*.py`, now gitignored). `tooling/scratch` excluded from ruff.
3. ✅ Confirmed `fsr_playbooks` imports nothing from `tooling/` (clean).
4. ✅ `pyproject.toml` `fsrpb` dist updated (`package-dir` → `tooling/{probes,store,e2e}`).
5. ✅ **Gate:** tooling suite **806 passed** (unchanged from baseline), `import fsr_playbooks`
   clean, `fsrpb` CLI runs, ruff green.

**Deferred — themed-subdir regroup** (`probes/ catalog/ deploy/ e2e/ evals/`): the flat top-level
modules (`cli`, `recover`, `picklists`, `preflight`, `inventory`, `connector_configs`,
`chat_review`, `agent_stats`, `fsr_{read,deploy}_mcp`) import each other and are imported by name
off `tooling/` on sys.path; moving them into subpackages breaks those flat imports for zero gate
value. Do it only if/when the `tooling/` layout itself needs the structure. `probes/ evals/ e2e/`
already exist as subdirs; `catalog/ deploy/` were never created.

## Phase 3 — Reference-cache data reorg
**Revised 2026-06-18** after verifying there is NO cache-miss → live-lookup fallback (see Open
verifications). Decision: *accept the limit* — ship the stable catalog, no new resolver feature.
A slim-DB compile of a stable-only playbook succeeds; a playbook referencing a live connector
op/picklist/module fails with a clear `CompileError` until `warmup` fills those tables.

Done in two commits — **3a rename** (mechanical) then **3b slim DB** (the substantive win).

### 3a — `store/` → `data/` rename
1. `mv store data` (the 65 MB `fsr_reference.db`, 134 MB `rpm_cache/` are already gitignored;
   `**/fsr_reference.db` covers the new path). Rewire the 8 hardcoded `store/` path constants:
   library `mcp_server/_shared.py`, `tooling/{cli,picklists,probes/common}.py`,
   `web/backend/{routes/ref,routes/yaml_routes,step_drafter}.py`.
2. gitignore: retarget the `store/…` rules to `data/…`; drop the now-dead `/python/_[a-z]*.py` rule.
3. **Gate:** tooling suite green; `fsrpb compile` of a sample still works against `data/fsr_reference.db`.

### 3b — slim DB builder + ship as package-data ✅
4. ✅ NEW `tooling/catalog/build_compile_catalog.py`: copies the **full schema** (so every table the
   resolver may touch exists → missing connector = clean `CompileError`, not "no such table") but
   populates ONLY the stable tables — `step_types, step_handlers, step_examples, jinja_macros,
   jinja_globals, jinja_tests, jinja_context_vars, recipes, connector_op_defs` — then VACUUMs.
   **Output landed inside the package** at `fsr_playbooks/_data/fsr_reference.db` (not repo-root
   `data/slim/`): the packaging build uses `where=../..` + `include=["fsr_playbooks*"]`, so
   package-data must live under the package tree. **0.59 MB, tracked** (gitignore negation
   `!fsr_playbooks/_data/fsr_reference.db`). Deliberately *excluded* though stable: the authoring-hint
   corpus (`jinja_expressions` ~7.8k, `jinja_filter_usage` ~1.7k) and the REST catalog
   (`api_endpoints*` ~1.2k) — the compiler reads none of them; only `tools_jinja` does, and it
   degrades to "no suggestions". Including them ballooned the DB to ~4 MB.
5. ✅ New `fsr_playbooks/_db.py` centralizes DB resolution (`default_db_path()` + `PACKAGED_SLIM_DB`
   / `REPO_PROBED_DB`): `$FSRPB_DB` → repo `data/fsr_reference.db` (dev) → packaged slim. Wired the
   6 library sites (`mcp_server/_shared`, `compiler/{validator,rulesets/_shared}`,
   `llm/{tools,_loop_helpers}`). Shipped as package-data via `"fsr_playbooks" = ["_data/*.db"]` in
   `packaging/fsr_playbooks/pyproject.toml`.
6. ✅ **Gate (no live fallback):** wheel `unzip -l` shows the 0.59 MB slim DB, no 65 MB, no
   investigation modules. **Fresh-venv install proof** (no repo `data/`): `default_db_path()` →
   the in-package slim DB; `compile_yaml(decision_branch)` → ok; `compile_yaml(virustotal)` →
   `ok=False`, blocking `unknown connector: 'virustotal'`. Pinned by
   `fsr_playbooks/tests/test_slim_catalog.py` (3 tests).

## Phase 4 — Docs / web / ts (low risk, anytime)
1. Root `*.md` (ARCHITECTURE/AUTHORING/CAPABILITIES/DEMO/PRESENTATION/…) → `docs/`, leaving
   README + CLAUDE.md at root.
2. Confirm `web/` + `ts/` are import-decoupled from the library (separate product surface).

## Phase 5 — Connector cutover to a pinned package
**Sync strategy (decided 2026-06-17): pin to the published package, delete the vendored copy.**
The connector's vendored copy drifts (a copy anyone can edit always will). Target appliances have
package-index access at install time, so:
1. Connector `requirements.txt`: `fsr_playbooks[mcp]==<pinned>` (also fixes the missing
   `jinja2`/`ruamel.yaml`/`mcp` deps).
2. **Delete** `connector-fsr-soc-assistant/fsr_playbooks/` (vendored) and `fsr_core.bak`.
3. Confirm the carved-out investigation lives in the connector's own module (Phase 1b), imported
   locally — NOT from the pinned package.
4. **Gate:** mock fixture replay diff-clean against the pinned package; then live appliance smoke
   (compile + `warmup` + `chat_turn` + `push_playbook`).
5. Thereafter: library update = bump the pinned version, review changelog, re-run the gate.

> Not git subtree/submodule: those keep an editable in-repo copy — the thing that drifted. A pinned
> package is read-only by construction. Fallback if an appliance loses index access: vendor the
> *published wheel* at build time, pinned, with a CI check that the vendored tree == the pin.

---

## The connector acceptance bar (for Phases 1b / 5)

The real test of any change is **the connector's operations still run.** A harness already exists —
use it:

- **Offline regression:** the connector dispatches all ops through one `operations` map
  (`operations.py`, wrapped `_sim_aware`/`_mock_aware`). With `params["mode"] == "mock"`,
  `mock_replay.py` replays the 28 `fixtures/*.json` scenarios through the same dispatch. Run the
  ops against the fixtures and assert unchanged output (`compile_yaml`, `chat_turn`/`chat_resume`,
  `push_playbook`, …). Capture a baseline once, diff after each connector-side change.
- **Live (appliance only):** `warmup` (crudhub ingest), `push_playbook`/`dry_run_playbook` can't be
  mocked — smoke them on a lab appliance after Phase 1b and again after Phase 5.

---

## Open verifications (cheap; do before the phase that needs them)
- [x] ~~Confirm the resolver cache-miss → live-lookup fallback exists~~ — **it does NOT.** The
      resolver hard-fails: a missing step_type/connector/op/picklist row makes `_resolve_step`
      (`fsr_playbooks/compiler/resolver/normalizers.py:22–55`) append a `CompileError` and return —
      no live lookup, anywhere. So Phase 3 step 4's "degrades to a live lookup" premise is **false**;
      a slim DB means *off-platform compile only works for playbooks that reference solely the
      shipped stable tables* (step_types/handlers/jinja_*/recipes). Anything touching a live
      connector op / picklist / module needs `warmup` against a real SOAR first. (See revised Phase 3.)
- [x] ~~Confirm picklist/connector/module UUIDs are truly per-install~~ — **yes, confirmed.** Probed
      live per appliance (`tooling/probes/probe_modules.py` reads `/api/3/staging_model_metadatas`
      + `/api/3/picklist_names`); warmed via `warmup`, never shipped. Justifies excluding
      connectors/operations/operation_params/op_safety/modules/module_fields/picklists from the slim DB.
- [x] ~~Re-grep connector for surface-A imports not yet listed~~ (done in Phase 0).
- [x] ~~Confirm `llm/tools.py` split scope~~ — resolved: `_tier_for_run_op` is generic and STAYS;
      no split needed.
