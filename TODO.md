# FSRPlaybookYaml — TODO / resume state

**Last touched**: 2026-05-03. Live FSR target: `https://10.99.249.205` (label `dev`).

## Backlog (parked 2026-05-04)

Captured mid-session when we pivoted to the editor "save" problem. Each
item is a real follow-up grounded in something the session exposed.

1. **Apply the strict-whitelist pattern to the other resolver normalizers.**
   `manual_input` now hard-errors on unknown keys and on bad `type:` values
   (silent-drop trap fixed). The same trap still exists for `delay`,
   `code_snippet`, `start_on_create` / `start_on_update`, and the record
   CRUD trio (`create_record`, `update_record`, `find_record`). Add a
   per-handler accepted-keys check + fail-on-unknown the way
   `_normalize_manual_input_args` does. Template: `compiler/resolver.py`,
   the `_FRIENDLY` / `_CANONICAL` whitelists pattern. ~30 min.

2. **Slim the other big tools the way `get_step_type` was slimmed.**
   Token analyzer is built (`fsrpb chat-stats`, `web/backend/usage.jsonl`).
   Run it after a real chat session and trim whatever sits at the top of
   the tool-cost ranking. Likely candidates: `search_playbooks` (full
   snippet JSON × N), `validate_yaml` (returns the entire compiled
   collection), `decompile`. Pattern: add a `verbose: bool = False`
   parameter and a default cap, mirroring `get_step_type`. ~1 hr after
   seeing real data.

3. **Investigate the `--mode upsert` HTTP 400.** Every push to
   `/api/3/bulkupsert/workflow_collections` 500s with a generic
   `TypeError` from FSR. Replace mode works as a workaround. Either fix
   the payload shape or remove the `upsert` option from `cli.py:cmd_push`
   and document why. Reproduce with `fsrpb push --mode upsert <yaml>`.
   ~1 hr.

4. **Roundtrip test against the friendly-form examples.** Decompile →
   recompile may regress YAMLs from friendly form to canonical wire form
   after the recent friendly-form work. Run `fsrpb roundtrip` on the 11
   demo examples and confirm nothing diverges semantically. ~15 min smoke.

5. **Smoke test for the 9 examples without `.test.yaml` sidecars**
   (`decision_branch`, `find_and_update`, `hello_connector`,
   `ip_reputation_check`, `ip_reputation_check_abuseipdb`,
   `manual_input_then_act`, `parent_calls_child`, `test_complex_e2e`,
   `test_manual_input_e2e`). Some genuinely can't be run blind, but a
   "compile + push + check link 200" smoke per example would catch
   regressions like the URL-pattern bug we just fixed
   (`cli.py:cmd_push`'s post-push GET on `/api/3/workflows/<uuid>`).

6. **History tab (started, parked).** `web/backend/history.py` written
   with the schema (`pushes`, `push_workflows`, `chat_sessions`,
   `chat_turns`, `chat_tool_calls`) + writers, readers, YAML diff helper,
   chat↔push correlation via `~/.fsrpb/active_session`. **Not yet wired
   in** — `cli.py:cmd_push` and `web/backend/llm/anthropic_provider.py`
   still need to call `record_push()` / `record_chat_turn()`, and the
   `/api/history` FastAPI endpoints + Svelte `/history` page are TODO.
   Resume by importing `from history import …` in those two writers and
   adding the route handlers; reader functions are already shaped for
   the UI.


## Recent changes (most-recent first)

- **2026-05-03 — Jinja corpus mining**: new `probe_jinja_corpus` walks 1,669 live workflows, extracts every `{{…}}`/`{%…%}` block (19,305 total → 7,789 unique idioms), populates `jinja_expressions` (kind=expr/set/for/if/macro/…) and `jinja_filter_usage`. Most-used real example auto-promoted onto `jinja_macros.example`. New table column `jinja_macros.curated_doc` + 13 hand-written long-form filter docs (json_query JMESPath syntax breakdown, picklist, fromIRI, resolveRange, map, selectattr, regex_search, regex_replace, ternary, default, dict2items, flatten, from_json/to* family). New MCP tool `find_jinja_pattern(q, kind)` and enriched `find_jinja_filter` / `get_filter_examples`.
- **2026-05-03 — `store/JINJA_IDIOMS.md`** (new) — 10 corpus-mined patterns with occurrence counts.
- **2026-05-03 — Live e2e loop closed**: `fsrpb push` is idempotent (PUT → POST → PURGE+POST including child-workflow purge), `run-playbook --follow` auto-dumps step diagnostics on failure (fetches `?step_detail=true`), `fsrpb env <pb_execution>` rebuilds the live `{vars: {…env, steps: {Step_Name: result}}}` Jinja context, `fsrpb jinja '<tpl>' --from-pb-execution <id>` renders against it. MCP equivalents: `get_run_env`, `render_jinja(from_pb_execution=…)`.
- **2026-05-03 — Connector params 14 % → 90 %**: new RPM-based tier in `probe_connectors`. Downloads each connector's RPM from `repo.fortisoar.fortinet.com`, extracts `info.json`, ingests params. Fingerprint diff (`connectors.rpm_fingerprint`) so re-runs short-circuit. Cache at `store/rpm_cache/`.
- **2026-05-03 — Connector healthcheck**: `fsrpb health [name] [--probe] [--config <uuid>]`. Lists configured + active via `POST /api/integration/connector_details/?configured=true&active=true`; per-config probe via `GET /api/integration/connectors/healthcheck/{name}/{version}/?config=…`. MCP: `list_configured_connectors`, `healthcheck_connector`.
- **2026-05-03 — Compiler**: start step now emits `arguments.step_variables.input.params=[]` (was `{}`, caused runtime `pop expected at most 1 argument`).
- **2026-05-03 — `vars.steps.<step_id>` rule confirmed**: keyed off `step.name.replace(" ", "_")` (case **preserved**, not lowercased). Verified against the Jinja editor widget's `view.controller.js`. AUTHORING.md updated.



## Where we are

Compiler v1, reference store, live e2e (push/run/poll/env), MCP server (16 tools), and corpus-mined Jinja docs are all live. Open work: demo MVP, Phase 8 frontend research, `CONNECTORS.md` generation.

| Probe | What it captures | Status |
|---|---|---|
| `probe_api_endpoints` | Hydra root + dashboard endpoint inventory | live |
| `probe_connectors` | 3 tiers: live (installed) → solutionpacks (catalog) → **fortinet_repo_rpm** (RPM `info.json` from `repo.fortisoar.fortinet.com`, fingerprint diff so re-runs short-circuit) | 714 connectors, 6,762 ops, **6,097 with params (90%)** |
| `probe_modules` | `/api/3/staging_model_metadatas?$relationships=true` + `/api/3/picklist_names` | 62 modules, 1,233 fields |
| `probe_playbooks` | step types, playbook corpus, trigger recipes | 43 step types, 1,669 playbooks |
| `probe_jinja` | Widget constants + PDF + live `type_debug` rendering | 144 filters, 99 w/ observed types |
| `probe_jinja_backend` | Backend introspection via `inspect.signature()` | 170 filters, 15 globals, 39 tests |
| `probe_jinja_corpus` (NEW) | Mines every `{{…}}`/`{%…%}` block from live workflow args | 19,305 blocks → 7,789 unique idioms |
| `probe_step_handlers` | FUNCTION_MAP signatures | 100% coverage |
| `probe_playbook_constraints` | rule constraints | live |
| `probe_cleanup` | pattern-matched delete of test artifacts (gated on `FSR_ALLOW_E2E`) | live |

DB at `store/fsr_reference.db`, schema at `store/schema.sql`. All probes are
idempotent and re-runnable. `python/probes/_env.py` loads `.env` (already
populated; API key auth, SSL verify off).

## Trust model recap

- Local sources (rpm_info_json, schema_json, schema_ts, widget_constants,
  playbook_guide_pdf) are **always `seen` only** — never trusted.
- Live methods (live_api_get, live_api_render, live_op_exec, playbook_e2e)
  with `tested_pass` promote to `is_trusted=1` in `v_verification_state`.
- **`backend_introspect`** is the new highest-trust method (added today) —
  reads the actual Python objects on the FSR box.

## Open TODOs (priority order)

### 1. ~~Surface FSR-custom filter set explicitly~~ ✅ DONE 2026-05-02
Generated `store/FSR_CUSTOM_JINJA.md` (385 lines, 32 entries: 5 globals + 27
filters from `workflow.*` and `sealab.*`). Pointer added to
`FORTISOAR_RESOURCES_INDEX.md` so future agents grep it first.
Builder: `python/store/export_jinja_cheatsheet.py`. Re-run after any
`probe_jinja_backend` run.

### 2. ~~Backend introspection for workflow step types~~ ✅ DONE 2026-05-02
Found the canonical dispatcher: `workflow.eval.FUNCTION_MAP` (44 entries).
Each step type's `args_schema_json.script` ends in `/wf/workflow/tasks/<key>`
where `<key>` is a FUNCTION_MAP entry. Captured all 44 signatures via
`scripts/dump_function_map.py`; ingested by `probe_step_handlers` into
new `step_handlers` table. Bundled into `fsr_reference.json`.

Discovery path: celery tasks (`scripts/dump_step_types.py`) turned out
to be cleanup jobs, not step handlers — `workflow/builtins/*.so` houses
the actual handlers but they're dispatched by name through FUNCTION_MAP.
Three step types reference handlers not in FUNCTION_MAP:
`workflow_reference`, `map`, `fetch_email_and_explode` — flagged in
`GAPS.md`.

### 3. Live-instance probes (Phase 5) — ✅ DONE 2026-05-03
End-to-end via CLI: compile → push (idempotent w/ child-workflow purge)
→ trigger via `/api/triggers/1/notrigger/<wf>` → poll
`/api/wf/api/workflows/?task_id=` → on terminal, fetch `?step_detail=true`
and dump per-step status + top-level error inline. `fsrpb env <pk>` and
`fsrpb jinja '<tpl>' --from-pb-execution <pk>` close the loop for
authoring the next step against the previous run's real data.

### 4. Compiler v1 — vertical slice landed; widen coverage next
✅ Pipeline complete: parser → resolver → validator → emitter, plus
   decompiler and round-trip checker.
✅ Round-trip on `pb_examples/all_fsr_evoke_playbooks.json`:
   **1596/1596 (100%) semantic match** across every step type FSR uses
   in production. 1 skip is an empty-steps record.

✅ CLI: `fsrpb compile / validate / decompile / roundtrip / explain` (`python/cli.py`).
✅ Argument-shape validation (`python/compiler/arg_validator.py`):
   uses `step_handlers` signatures to enforce required params and
   reject unknown args on handlers without `**kwargs`. Framework-injected
   params (step, step_id, wf_id, env, …) are excluded from the
   "required" check.

Remaining for v1 → v1.1:
Reference store is rich enough to start. Phase 3 from
`Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md`. See `ARCHITECTURE.md` for how
this fits the bigger picture (it's the engine all three authoring
surfaces — CLI, MCP, visual editor — sit on top of). Targets:
- `python/compiler/parser.py` — YAML → IR
- `python/compiler/resolver.py` — connector/op/param/step/jinja-filter
  references resolve against the SQLite store
- `python/compiler/validator.py` — strict mode rejects unknown refs with
  Levenshtein "did you mean..." suggestions; **errors are structured
  objects with code/location/suggestion**, never bare strings (MCP needs
  machine-readable diagnostics)
- `python/compiler/emitter.py` — IR → FSR `WorkflowCollection` JSON
- Library-first; CLI is a thin wrapper around the same functions MCP
  and the widget will call.
- Acceptance: bambenek-feed YAML → JSON byte-equivalent (modulo UUIDs/ts)
  to the vendor original.

### 5a. `fsrpb push` — idempotent ✅ DONE 2026-05-03

The actually-shipped path: `cmd_push --mode replace` does PUT → POST →
PURGE+POST. The crucial fix that unblocked re-push was that **the
collection-level hard-purge does not cascade to its workflows** — orphaned
workflows from a prior failed import keep their UUIDs, which causes the
second POST to 409 on the workflow (not the collection). Solution: the
purge step now also deletes every child workflow UUID via
`DELETE /api/3/delete/workflows?$hardDelete=true {ids: [...]}`. Verified
by re-pushing `examples/hello_connector.yaml` twice — both succeed as
`PURGE+POST` with the same `uuid=3a892679`.

`bulkupsert` is documented but not wired — the PURGE+POST path works,
and bulkupsert had separate PHP-side bugs in `UpsertController.php` we
didn't want to depend on.

---

### 5a-archive. Original re-push parking notes (kept for context):

✅ **First-create** push works end-to-end.
`POST /api/3/workflow_collections` with the **unwrapped collection
entity body** (not the export envelope) is the right path. Cascade-persist
on the entity automatically writes nested `workflows[]` and their
steps/routes. Verified by `examples/hello_connector.yaml` deployed live
as `Compiler Demo` (collection visible in FSR UI; `pull` round-trips back
to the original YAML).

⏸️ **Re-push** is parked pending appliance backup. Root cause: FSR
soft-deletes (sets `deletedat=NOW()` rather than purging). After a DELETE,
the UUID is still owned by the soft-deleted record, so a subsequent POST
hits 409 `UniqueConstraintViolationException` — error message even names
the recycle bin.

Attempts and results:

| Approach | Result |
|---|---|
| POST first time | ✅ creates |
| POST after DELETE | ❌ 409 (UUID still owned by soft-deleted) |
| PUT `?$showDeleted=true` body `deletedAt:null` | ❌ 409 |
| `DELETE /api/3/delete-with-query/workflow_collections?$showDeleted=true` (with body, hard-purge — same path `PlaybookConfig.php` uses for replace-mode imports internally) | not yet attempted (deferred until backup exists) |

Earlier rabbit hole — `import_jobs` is the **multi-type configuration
bundle import** (Solution Pack format: collections + modules + connectors
+ fixtures + roles + …), not single-collection import. Verified from
`Service/ConfigExportImport/ImportService.php` (iterates `configTypes`)
and `Entity/Core/ImportJob.php` (no `data` column; `file` IRI field for
Solution Pack zip uploads). Documented in
`soar-reporting-dashboard-cl/docs/FORTISOAR_API.md` "Workflow collection
import" section.

Mode flags wired in `cli.py cmd_push`:
- `--mode replace` (default): try PUT first, fall back to POST on 404.
  Currently fails on existing soft-deleted records.
- `--mode create`: POST only; clean for first-create.
- `--mode update`: PUT in-place; no-op so far (entity expects path under
  `?$showDeleted=true`).

To unblock re-push when ready (after backup):
1. Ensure backup of `Compiler Demo` and any other test collections.
2. Try `DELETE /api/3/delete-with-query/workflow_collections?$showDeleted=true`
   with body `{logic:"AND", filters:[{field:"uuid", operator:"in", value:[<uuid>], type:"primitive"}]}` via pyfsr's authenticated session.
3. If that hard-purges, wire it as the prelude inside `cmd_push --mode replace`.
4. Alternative: tail nginx while clicking "Save" on an existing playbook
   in the FSR UI to see what the official client sends.

Workaround for now: use `--mode create` for first imports; for updates
go through the FSR UI, or compile to JSON and use `app:import:from:file`
on the appliance.

### 5. MCP server v1 — ✅ LIVE (16 tools)
`python/mcp_server.py` over stdio; `.claude/settings.json` registers it
as `fsrpb`. Tools (verified 2026-05-03): `find_connector`,
`find_operation`, `get_op_schema`, `get_connector_source`, `run_op`
(w/ confirm guardrails + risk classification), `get_step_type`,
`find_jinja_filter` (returns `corpus_uses` + `curated_doc`),
`find_jinja_pattern` (search corpus by block kind), `get_filter_examples`,
`render_jinja` (w/ `from_pb_execution`), `search_playbooks`,
`validate_yaml`, `compile_yaml`, `get_run_env`,
`list_configured_connectors`, `healthcheck_connector`.

**Open follow-ups:**
- `dry_run_playbook` — sandbox-execute compiled JSON without persisting.
- Bug: `render_jinja` doesn't unwrap non-string scalar results (returns
  `{"output": '{"result": 5}'}` instead of `{"output": "5"}`).

### Read-only probes landed 2026-05-03

- ✅ **CONNECTORS.md** generated (13,595 lines, 714 connectors / 6,749 ops / 4,753 params, grouped by 85 categories). Builder: `python/store/export_connectors.py`.
- ✅ **RECIPES.md** generated (355 lines: 5 hand-curated patterns + trigger frequency table + top-25 connector orchestrations). Builder: `python/store/export_recipes.py`.
- ✅ **YAQL filter probe** — confirmed `yaql` is a live Jinja filter via `/api/wf/api/jinja-editor/`. 6/6 probes pass; output type `list`; shape `{{ v | yaql("$.where($ > 1)") }}`. Recorded into `verifications` and `jinja_macros.output_type_observed`. Script: `scripts/probe_yaql_smoke.py`.
- ✅ **Custom-macro corpus grep** — FSR "macros" are scalar globals accessed via `{{ globalVars.NAME }}` (NOT Jinja `{% macro %}`). 12 defined in pb_examples; 122 ref occurrences. Recorded into `jinja_context_vars` (`scope='globalVars'`).
- ✅ **GlobalVars / macros endpoint** — `GET /api/wf/api/dynamic-variable/` confirmed live 2026-05-03. Schema `{id, name, value, default_value}`. Full CRUD via `/{pk}/`. UI capture #14 closed without needing capture.
- ✅ **historical-workflows record shape** — confirmed via live fetch. Per-run record: `@id, name, result.{data,status,message}, template_iri, created, modified, env.{wf_id, step_id, task_id, lastPullTime,...}, status, tags, metadata.{routes, groups}`. Use top-level `status` for completion polling, `result.status` for pass/fail.
- ✅/⚠️ **Bulkupsert characterized** — `POST /api/3/bulkupsert/workflow_collections` body = single workflow_collection object. **Works only for fresh creates with no existing match** (live or soft-deleted). Two FSR-side PHP 8 bugs confirmed via `prod.log`:
  - `UpsertController.php:89` — `array_key_exists()` on `stdClass` (the json-decoded body). Crashes when an existing soft-deleted record matches by uuid/name, blocking the resurrect path.
  - `UpsertController.php:258` (`upsertWorkflowCollections`) — `['workflows']` array-index access on stdClass when called via the bulk list path. Crashes during update.
  - `BulkRequestService.php:70` — `count()` on stdClass.

  Bottom line: bulkupsert can't update existing records. Kept as `--mode upsert` opt-in for never-seen UUIDs only.

- ✅ **Canonical UI delete endpoints** (from user UI capture 2026-05-03):
  - Soft-delete: `DELETE /api/3/delete/workflow_collections` body `{ids:[<uuid>]}`
  - Hard-delete: `DELETE /api/3/delete/workflow_collections?$hardDelete=true` body `{ids:[<uuid>]}`
  - These work on records visible to the caller. They do NOT reach into the recycle bin — for that, the `delete-with-query` path with `?$showDeleted=true` is the right tool.

- ✅ **`fsrpb push --mode replace`** wired up for the success path (PUT → POST → on 409 PURGE+POST). Soft-delete recovery path requires the recycle-bin scope, but a once-soft-deleted UUID with sub-entity wedge can still 409 — manual cleanup of that record needed for fully clean re-push idempotency.
- ✅ **`?name=` filter** — works as exact match after URL-encoding (`&`→`%26`). Django suffix variants (`name__exact`, `name__contains`) do NOT work on `/api/3/`. `POST /api/query/workflow_collections` body filter also works. Earlier failure was a URL-encoding bug.
- ✅ **`attribute_metadatas`** — 1233 entries; richer per-field metadata than `module_fields`. Worth a follow-up probe but not blocking compiler v1.
- ✅ **Picklist hydration** — confirmed: `model_metadatas` embeds `dataSource: {model:'picklists', query: …}` rather than inlining values. Current ingest path correct.

### Live-instance gaps still pending (need backend recon)

`scripts/fsr_recon.sh` is a single-shot read-only recon script for `csadmin@10.99.249.205`. Outputs to `/home/csadmin/fsrpb_recon/<ts>/` + a tarball next to it. Covers:
- Symfony route table + filtered views (workflow / trigger / purge / import).
- Workflow Django app `urls.py` + `/api/wf/runs/` view code (the 403 endpoint).
- Live `workflow.eval.FUNCTION_MAP` dump (resolves missing `map`, `fetch_email_and_explode` handlers).
- `PlaybookConfig.php` delete logic for soft-delete purge unblocking.
- `cyops-integrations` log tail for connector op execution shape.
- `nginx` confs (so we know which `/api/*` prefix maps to which service).
- Copies of `api_platform/`, `routes/`, `Entity/Workflow/`, `Controller/`.

Once the tarball is back: extract under `store/incoming/recon_<ts>/` and write `probe_recon.py` to ingest the diffs.

### 5b. Pull / diff / status — local-only, working
- ✅ `fsrpb pull <name|uuid> [-o out.yaml]` — fetch live collection,
  decompile to YAML. Verified end-to-end except: API Platform `?name=`
  filter on `/api/3/workflow_collections` returns 0 hits; need a
  different filter syntax (see "Open" below).
- ✅ `fsrpb diff <yaml> [-c name]` — semantic diff between local YAML
  (compiled) and live collection (pulled).
- ✅ `fsrpb status [-n N]` — list recent `import_jobs` with state.
  Confirmed working.

Open (cheap fixes):
- `fsrpb pull "<name>"` doesn't find any collections because `?name=`
  exact-match filter isn't honored. Workaround: pull by UUID. Real fix:
  use `?name__exact=<value>` or `$filter=name=<value>` per the
  power-user query options doc, or fetch all and filter client-side.

### 5c. Backlog (parked, scope sketches preserved here)
The following are unblocked locally and can be picked up without user
intervention. Listed in rough priority order:

1. **MCP server v1** — wraps compiler + store + (eventual) push as
   agent tools. See ARCHITECTURE.md §3 for tool table. Read-only first
   (`find_connector`, `get_op_schema`, `find_step_type`, `find_handler`,
   `find_jinja_filter`, `search_playbooks`), then validate/compile/
   decompile, then `render_jinja` (live). `dry_run_playbook` blocks on
   §3 e2e probes.
2. **More example YAMLs** — decision branches, `manual_input`,
   `find_record`+`update_record`, parallel paths. Each example doubles
   as agent grounding (LLMs benefit from more curated examples) and a
   round-trip regression fixture.
3. **TS compiler port skeleton** — `ts/src/compiler/` with the same IR
   shape so the future widget surface isn't an afterthought. Same tests
   can be ported via vitest.
4. **`fsrpb explain` extensions** — `explain jinja_filter <name>`,
   `explain module <name>`, `explain recipe <trigger_type>`. Currently
   only `connector`/`step`/`handler` are wired.
5. **AUTHORING.md** — single doc explaining the YAML shape with
   copy-pastable snippets pulled from `step_examples`. Should describe
   the connector/decision/set_variable/find_record/update_record/
   workflow_reference patterns, plus jinja idioms.
6. **YAQL probe** — Playbooks Guide pp.218-220, currently 0% covered.
   Likely has its own render endpoint similar to jinja-editor.
7. **Per-filter input-type contract probe** — sweep each of 144 jinja
   filters with str/list/dict/int inputs to populate `input_type_hint`
   data-driven (currently NULL).
8. **Cleanup probe** — find/delete `*__fsrpb_probe__*` and
   `Compiler Demo*` collections so e2e probes don't leave residue.
9. **`probe_workflow_runtime`** — exercise `wf/workflow/tasks/<func>/`
   for a few simple FUNCTION_MAP entries (`no_op`, `add`,
   `set_multiple`) to confirm direct dispatch surface and capture
   response shape — needed for the future `dry_run_playbook` MCP tool.

### 6. Smaller wishes
- Rerun `probe_jinja` after `probe_jinja_backend` so the type_debug
  observed types overlay onto the backend-canonical signatures (they're
  in different columns; just want to make sure both are present per
  filter).
- Multi-version connector support — switch primary key from `name` to
  `(name, version)` if multi-version coverage starts mattering. Currently
  `INSERT OR REPLACE` collapses versions; 760 catalog entries → 95 unique
  names.
- YAQL filter language probe (separate from Jinja; Playbooks Guide
  pp.218-220).
- Per-filter input-type contract — multi-shape probe (str / list / dict /
  int) so `input_type_hint` becomes data-driven instead of NULL.
- Param shape inference for the 26 jinja filters whose `tested_fail`
  message wasn't a "missing N required" pattern. The backend introspect
  dump fixes most of these but worth diffing.
- TS compiler port (`ts/src/`) once Python compiler v1 stabilizes.
- ~~`build_reference_json()` end-to-end~~ ✅ DONE 2026-05-02 —
  `store/fsr_reference.json` (5.9 MB) now contains all probe data
  including api_endpoints + jinja.globals + jinja.tests.
- ~~`store/STEP_TYPES.md` cheatsheet~~ ✅ DONE 2026-05-02 —
  92 KB, 43 step types frequency-ordered with 3 examples each.

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
- Open gaps: `FSRPlaybookYaml/GAPS.md`
- API truth: `soar-reporting-dashboard-cl/docs/FORTISOAR_API.md`
- Schema: `store/schema.sql`
- Probes: `python/probes/probe_*.py`
- Backend dump scripts: `scripts/dump_jinja_filters.py`
  (next: `scripts/dump_step_types.py`)
- Incoming backend dumps: `store/incoming/filters.json` (170 filters
  introspected from `/opt/cyops-workflow/sealab/.../sealab.jinja`)
