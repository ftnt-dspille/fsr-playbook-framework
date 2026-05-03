# FSRPlaybookYaml — TODO / resume state

**Last touched**: 2026-05-02. Live FSR target: `https://10.99.249.205` (label `dev`).

## Where we are

All five static probes operational against the live instance:

| Probe | What it captures | Trusted rows |
|---|---|---|
| `probe_api_endpoints` | Hydra root + dashboard FORTISOAR_API.md inventory | 10 / 856 endpoints |
| `probe_connectors` | `/api/integration/connectors/` (installed) + `/api/query/solutionpacks` (catalog) | 70 installed + 644 catalog = 714 connectors, 6749 ops, 4753 params |
| `probe_modules` | `/api/3/staging_model_metadatas?$relationships=true` + `/api/3/picklist_names` | 62 modules, 1233 fields, 124 with picklist values |
| `probe_playbooks` | `/api/3/workflow_step_types/`, `workflow_steps?$relationships=true`, `workflows` | 43 step types, 7092 steps mined, 1664 playbooks, 6 trigger recipes |
| `probe_jinja` | Widget constants + Playbooks Guide PDF + live `type_debug` rendering | 99 filters tested_pass with observed types, 144 cataloged |
| `probe_jinja_backend` | **Backend introspection** via `inspect.signature()` on `sealab.jinja` Environment | 170 filters, 15 globals, 39 tests with canonical signatures |

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

### 3. Live-instance probes (Phase 5)
Workflow collection import + playbook execute + assert + cleanup probes
for end-to-end compiler validation. Needs `FSR_ALLOW_E2E=true` in `.env`
plus a confirmed import endpoint (currently 🔴 in `GAPS.md` — discovery
recipe is `php bin/console debug:router | grep import` on the box).
pyfsr enhancement: `client.workflow_collections.import_(payload)`,
`client.playbooks.run(trigger_uuid, body)`, `client.records.create_bulk`.

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

### 5a. `fsrpb push` — re-push UNBLOCKED 2026-05-03
**Resolution**: Symfony route dump (recon_20260503-122258) found two routes
that close §5.0:

- **`POST /api/3/bulkupsert/workflow_collections`** — true upsert. Per
  `UpsertController.php:89-90`, when the body sets `deletedAt: null` it
  resurrects soft-deleted records, which removes the UUID-conflict failure
  mode entirely. **This is the canonical re-push path** — replaces the
  POST→409→DELETE→409 dance.
- **`DELETE /api/3/{resource}/{uuid}?$hardDelete=true`** — confirmed via
  `MqMessagebroadcastSubscriber.php:147`. Bypasses soft-delete on a single
  record. Useful for cleanup probes that need to fully purge test artifacts.
- **`DELETE /api/3/delete-with-query/{resource}?$showDeleted=true`** with
  body `{logic, filters}` — bulk hard-purge. Already used by built-in
  scheduler playbooks (DataFixtures/SchedulerSystemWorkflow).

To wire up:
1. Replace `cmd_push --mode replace` PUT/POST fallback with a single call to
   `POST /api/3/bulkupsert/workflow_collections` (body = same unwrapped
   entity already used for first-create POST, plus `deletedAt: null` if the
   target is in the recycle bin).
2. Add `cmd_push --mode purge-and-create` for the rare case where bulkupsert
   semantics aren't right (e.g. you want a clean slate without keeping
   audit/comment history): `DELETE …?$hardDelete=true` then `POST`.
3. Backup paranoia from §5.0 still applies for first run, but the
   bulkupsert path doesn't destroy data — it merges.

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

### 5. MCP server v1 (new — depends on #4)
Wraps the compiler + reference store as MCP tools so any agent (Claude
Code, IDEs, the widget) can author playbooks via tool use without
hand-rolling lookups. See `ARCHITECTURE.md §3` for the tool table.
First cut is read-only + validate/compile (no e2e). `dry_run_playbook`
gets added after TODO #3 lands.

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
