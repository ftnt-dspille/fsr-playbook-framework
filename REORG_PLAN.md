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
| 3 | Reorg the reference-cache data (`store/` → `data/`, slim DB) | ☐ todo |
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
- [ ] Live appliance smoke (pyfsr memory: lab `10.99.249.159`, module box `10.99.249.205`).

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
1. `store/` → `data/`; gitignore the heavy artifacts (65 MB `fsr_reference.db`, drafts, runs).
2. `tooling/catalog/build_compile_catalog.py`: filter the probed DB to globally-stable tables only
   (step_types/handlers, jinja_*), strip connector icons → `data/slim/fsr_reference.db` (~1 MB,
   tracked). Instance-specific UUIDs (picklists/connectors/modules) are warmed from the target
   SOAR, not shipped.
3. Ship `data/slim/fsr_reference.db` as package-data via `packaging/fsr_playbooks/pyproject.toml`.
4. Verify the resolver degrades to a live lookup on a cache miss (graceful off-platform compile).
5. **Gate:** wheel `unzip -l` shows the ~1 MB slim DB and no 65 MB / no investigation; clean-venv
   compile of a sample playbook works against the slim DB.

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
- [ ] Confirm the resolver cache-miss → live-lookup fallback exists (Phase 3 step 4).
- [ ] Confirm picklist/connector/module UUIDs are truly per-install (justifies excluding them from
      the slim DB — Phase 3 step 2).
- [x] ~~Re-grep connector for surface-A imports not yet listed~~ (done in Phase 0).
- [x] ~~Confirm `llm/tools.py` split scope~~ — resolved: `_tier_for_run_op` is generic and STAYS;
      no split needed.
