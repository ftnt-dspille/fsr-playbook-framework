# fsr-playbook-framework — architecture & end state

**Status**: living doc. Last updated 2026-05-03. Compiler v1, reference store, live e2e (push/run/poll/env), MCP server (16 tools), and corpus-mined Jinja docs are all live. Open: demo MVP + Phase 8 frontend research (Monaco YAML editor + LLM chat).

## North star

FortiSOAR is the execution engine. Everything we build emits a valid FSR
`WorkflowCollection` JSON in the end. What changes is *who* authors the
upstream representation and *how* they get feedback while doing it.

There are three authoring surfaces, all targeting the same compiler:

```
   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
   │  Human (CLI)     │    │  Agent (MCP)     │    │  Human (visual)  │
   │  writes YAML     │    │  writes YAML     │    │  drags blocks    │
   └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    ▼
                       ┌────────────────────────┐
                       │   Simplified YAML IR   │
                       └───────────┬────────────┘
                                   ▼
                       ┌────────────────────────┐
                       │  Compiler (parser →    │
                       │  resolver → validator  │
                       │  → emitter)            │
                       └───────────┬────────────┘
                                   ▼
                       ┌────────────────────────┐
                       │  FSR WorkflowCollection│
                       │  JSON (importable)     │
                       └───────────┬────────────┘
                                   ▼
                              FortiSOAR
```

The reference store (`store/fsr_reference.db` + `.json`) is the brain: it
is what the resolver/validator consult, what MCP tools query, and what the
visual editor renders pickers from.

## The two LLM flows

### Flow A — deterministic compile, no LLM at compile-time
Human (or any tool) writes simplified YAML → `fsrpb compile` → FSR JSON.
Reproducible, diff-able, version-controllable. This is the foundation.
Compiler v1 (TODO #4) targets this.

### Flow B — agent-in-the-loop authoring
LLM writes the YAML, calls validation/testing tools, iterates. The LLM
never writes FSR JSON directly — it writes YAML and trusts the compiler.
The MCP server is the interface that makes this loop work.

We are **not planning to fine-tune** a model. With a good MCP toolset and
the cheatsheets already built (`FSR_CUSTOM_JINJA.md`, `STEP_TYPES.md`),
frontier-class models should author correctly via tool use. Revisit only
if tool-use authoring plateaus.

## Components

### 1. Reference store (built — Phase 1-2 complete)
SQLite + bundled JSON snapshot. Trust-tracked. Source of truth for every
"does this exist / what shape" question.

### 2. Compiler (TODO #4 — next)
- `parser.py` — YAML → IR
- `resolver.py` — connector/op/param/step/jinja-ref lookups against store
- `validator.py` — strict mode, "did you mean…" suggestions
- `emitter.py` — IR → FSR JSON
- **Returns structured error objects, not stderr strings** — MCP needs
  machine-readable diagnostics.
- Acceptance: bambenek-feed YAML → JSON byte-equivalent (modulo
  UUIDs/timestamps) to vendor original.

### 3. MCP server (new — after compiler v1)
Wraps compiler + reference store + live FSR. Exposes tools any
MCP-capable agent (Claude Code, IDE plugins, the widget) can call:

| Tool | Backed by | Purpose |
|---|---|---|
| `find_connector(q)` | SQLite FTS | fuzzy search 714 connectors |
| `find_operation(connector, q)` | SQLite | list ops + fuzzy search |
| `get_op_schema(connector, op)` | SQLite | params, types, required, picklists |
| `get_connector_source(connector)` | live FSR | fetch operations.py source |
| `run_op(connector, op, params)` | live `/wf/workflow/tasks/connector` | one-shot op exec; caches output shape |
| `get_step_type(name)` | SQLite + STEP_TYPES.md | schema + 3 real examples |
| `find_jinja_filter(q)` | SQLite | filter sig + observed type |
| `find_jinja_pattern(q, kind)` | SQLite | global/macro/test catalog |
| `get_filter_examples(name)` | SQLite | real corpus uses of a filter |
| `render_jinja(template, ctx)` | live `/api/wf/api/jinja-editor/` | runtime check |
| `search_playbooks(q)` | FTS over `playbooks_seen` | "how do others do X" |
| `validate_yaml(yaml)` | compiler dry-run | structured errors |
| `compile_yaml(yaml)` | compiler | YAML → FSR JSON |
| `get_run_env(pb_execution)` | live | dump a run's `vars` env for triage |
| `list_configured_connectors(probe)` | live | connector configs + health probe |
| `healthcheck_connector(name)` | live | invoke connector's health_check op |
| `list_recent_failed_runs(...)` | live | triage list for "my playbook is broken" |
| `list_picklists()` | live | every `listName.name` on the instance |
| `get_picklist(name)` | live | items: `{itemValue, uuid, iri}` |
| `picklist_for_field(module, field)` | live + cached | auto-discover picklist_name |
| `resolve_picklist_value(value, ...)` | live + cached | friendly value → IRI, with close-match suggestions |

### 4. End-user interfaces (longer-term)
All sit on top of the compiler + MCP, none reinvent the engine.

- **CLI** (`fsrpb`) — power-user path. `fsrpb compile`, `fsrpb validate`,
  `fsrpb push`, `fsrpb diff`. Already scaffolded.
- **Visual editor** — drag-and-drop block authoring for non-CLI users.
  Renders pickers from the reference store. Same compiler under the hood,
  so visual output is interoperable with hand-written YAML.
- **FortiSOAR widget** — TS port of compiler runs in-browser inside
  FSR. Same reference JSON snapshot, same emitter. Lets users author
  inside FSR without leaving the appliance.

The invariant: **all three surfaces produce the same simplified YAML IR**,
which goes through the same compiler. A YAML authored visually opens
correctly in the CLI editor and vice versa.

## Roadmap (ordered)

1. ~~Reference store (probes + cheatsheets + JSON bundle)~~ ✅
2. **Compiler v1** — TODO #4. Build with MCP as explicit consumer:
   structured errors, programmatic API, no `print()` side effects.
3. **MCP server v1** — read-only tools first (find_*, get_*, render_jinja,
   validate_yaml, compile). Ship before e2e is wired.
4. **Phase 5 e2e probes** — TODO #3. Becomes `dry_run_playbook` MCP tool.
5. **TS compiler port** — for the widget surface.
6. **Visual editor** — only after CLI + MCP are stable; consumes same IR.

## FortiSOAR backend reference (step-env API)

The `GET /api/wf/api/workflows/{pk}/?step_detail=true` endpoint (and its
historical-workflow twin) is served by Django/DRF in
`/opt/cyops-workflow/sealab/workflow/` on the FSR host. The source is
Cython-compiled (`.so`); build path `/br/BUILD/cyops-workflow-7.6.5-5662/`.

Pipeline for a single step's env + result:

- `workflow.eval.__update_env_and_args` assembles the per-step env from:
  `input`, `request` (incl. `headers`), `currentUser`, `auth_info`,
  `task_id`, `debug`, `resources`, `globalMock`, `useMockOutput`,
  `mockPlaybookId`, `step_variables`, and prior `steps[*].result`.
- `workflow.eval.clean_result` / `sanitize_value` /
  `filter_result_and_skip` sanitize the step output **at execution time**
  before `save_step_detail` persists it. The API later returns the
  already-sanitized record — replaying a stored `result` will not match
  the raw step output.
- `workflow.serializers.StepDetailSerializer.to_representation` calls
  `workflow.utility.mask_authorization_header`, which replaces
  `request.headers.authorization` with `MASKING_CHARACTER` (the `*******`
  seen in responses). The real auth value is unrecoverable from the API.
- `constants.EXCLUDED_FROM_MOCK_OUTPUT` drives field exclusion in mock
  paths; `DAS_SECRET_KEY` (referenced in `eval.so`) suggests encryption
  of certain stored fields.

When fixturing step-env responses for the validator or compiler tests,
treat `authorization` as permanently masked and treat `result` as
already-sanitized output, not raw connector output.

### Daily action limit

Enforcement of the per-day action cap (the "1000 actions" license limit)
lives in `workflow.utility` (`is_action_limit_enabled`,
`is_action_count_breached`, `update_action_count`, `REMAINING_ACTIONS`),
called from `eval.so` before each step dispatch.

State is stored in Postgres in `workflow_config`, section `license`:

- `daily_action_limit` (int) — the cap
- `remaining_actions` (int) — running counter
- `reset_time` (int) — when the counter resets
- `last_update_time` (float)

All four values are encrypted on disk; decryption uses `DAS_SECRET_KEY`
at runtime. Initial values are seeded by `workflow/fixtures/Config.json`
and rewritten by Fortinet license activation. Hand-editing the row
won't work — the decryptor rejects plaintext.

Master switch: `ACTION_LIMIT_ENABLED` in `sealab/settings.py`. The dev
host (`fsr`) has this set to `False`, so the limit isn't enforced there
regardless of DB state. On licensed hosts it's `True` and the cap is
license-bound.

#### How the cap is actually protected

The encryption is not the boundary — FDN sync is. Concretely:

1. **Encryption is symmetric and the key is on disk in plaintext.**
   `DAS_SECRET_KEY` is read from `/opt/cyops/configs/database/db_config.yml`
   under `verification_key.das` by
   `sealab/settings.py:309`. The `encrypt` / `decrypt` callables come
   from `fsr_utilities.manage_passwords`, which wraps
   `/opt/cyops/scripts/.lib/PasswordModule.so` (`pm.encrypt(data)` /
   `pm.decrypt(data)`). Anything with file-read access to the config
   yaml can round-trip values.
2. **Authoritative refresh runs in the background.**
   `cyops-auth` schedules `fdn_sync` via APScheduler
   (`BackgroundScheduler`, configured by `INTERVAL` /
   `INTERVAL_DEFAULT_VALUE` constants in
   `/opt/cyops-auth/handlerworkers/fdnclient.so`). On each tick it pulls
   license details from FDN and writes them back into
   `workflow_config`. Any local edit to `daily_action_limit` /
   `remaining_actions` gets overwritten on the next sync.
3. **There is no row-level signature.** The `workflow_config` schema is
   just `section/key/value/type`; integrity is whatever AEAD
   `PasswordModule` provides on the ciphertext itself, nothing extra.

### Cache layers that affect execution-history reads

`/api/wf/api/historical-workflows/` and `/api/wf/api/historical-steps/`
pass through multiple caches. The ones that can actually cause stale
or wrong responses, ordered by likelihood:

**1. PHP/Symfony team-membership cache (`cyops-api`, APCu).**
`App\Service\AccessibleTeamIdsProvider` caches two keys per user via the
`TagAwareCacheInterface` (APCu adapter, `config/packages/cache.yaml`):

- `_accessible_teams_<username>` — tagged `user_accessible_teams`
- `_parent_teams_<team_uuid>` — tagged `user_parent_teams`

`wfProxyRouteAction` injects these IRIs as `__TEAMS` into every POST
body before forwarding to Django (`src/Controller/ProxyController.php`).
If a user's team membership changes and the tag isn't invalidated, the
historical list silently filters with the **old** team set — runs that
should be visible disappear or vice-versa. Symptom: per-user
inconsistency, not global staleness.

Clear via the localhost-only endpoint:

```
curl -X POST http://localhost/api/3/cache_util \
  -H 'Content-Type: application/json' \
  -d '{"operation":"invalidate-tag","tags":["user_accessible_teams","user_parent_teams"]}'
```

Or nuclear: `{"operation":"clear-cache"}` (resets opcache + APCu).
Constants: `App\Constants\CacheConstants::ACCESSIBLE_CHILD_TEAMS` /
`ACCESSIBLE_PARENT_TEAMS`.

**2. Secondary-storage routing cache (Django, `CACHE_SECONDARY_STORAGE`).**
`workflow.secondary_storage.data_movement_task.secondary_storage_movement_job`
moves aged `historical_workflow` / `historical_step` rows from the
primary tables to a partitioned secondary table. After each move it
calls `update_job_status_cache`, which writes to the
`CACHE_SECONDARY_STORAGE` key tracking *which physical table holds which
run*. If that cache is stale (mid-move, or the job crashed after moving
rows but before updating the key), historical reads target the wrong
table and the run looks missing. Toggle:
`ENABLE_SECONDARY_STORAGE` in `[secondary_storage]` of the appliance
config (`sealab/settings.py:109`). Recovery: re-run
`secondary_storage_movement_job` or restart `cyops-workflow` to force a
fresh cache build.

**3. Django `DatabaseCache` (`workflow_cache` table).**
Configured at `sealab/settings.py:290–294`. Used for short-TTL
aggregates (counts, metrics, ES-recommendation criteria via
`workflow.utility.refresh_cache_for_es_recommendation_criteria`) and
view-level caching governed by the `CACHE_SECONDS` constant in
`views.so`. Stale symptoms here are dashboard tiles / `/count/`,
`/metrics/`, `/statuslist/` lagging the underlying data — not the
detail responses themselves. Clear:

```sql
TRUNCATE workflow_cache;
```

**4. `historical_step.env` spill to disk.** Large env values aren't
stored inline in the JSONB column; `workflow.eval.update_env_for_files`
writes them to disk and stores a pointer. `workflow.tasks.clean_env_files`
reaps the files on a retention schedule (`CLEAN_WF_SECONDARY_TABLES` in
`settings.py:108`). If the file is reaped while the row survives, the
API returns the pointer shell — env appears empty/truncated. Not
strictly a "cache" but presents identically. Not retroactively
recoverable; only fixed by re-running the playbook or extending the
retention window before the run of interest.

**5. Symfony build-time caches (`var/cache/prod/`).** Doctrine metadata,
route map, annotations, serialization. These only go stale on deploy /
metadata change, not at runtime. Clear:

```
sudo -u nginx php /opt/cyops-api/bin/console cache:clear --env=prod
sudo systemctl restart php-fpm nginx
```

**What's *not* a cache** despite looking like one:
`__pyx_code_cache` / `__pyx_dict_cached_value.*` in every `.so` are
Cython interpreter internals (constant interning), not application
caches. `_prefetched_objects_cache` is Django ORM per-request prefetch,
scoped to one request. Don't chase these.

**Diagnostic recipe** for "history endpoint returns wrong/stale data":

1. Reproduce with a curl that bypasses the UI. If the bug reproduces,
   it's server-side; if not, it's browser cache.
2. Hit the Django service directly (port 8001/8002 on the appliance,
   bypassing nginx + cyops-api). If the bug disappears, the PHP layer
   (likely #1 team cache) is the culprit. If it persists, it's Django
   (#2–#4).
3. For Django-side, query the row directly with `psql` and compare to
   the API response. A pointer-shaped `env` JSONB with no on-disk file
   confirms #4. Row missing from primary but present in secondary table
   (or vice versa) confirms #2.
4. Per-user inconsistency (one account sees it, another doesn't) almost
   always means #1.

#### So how *could* the action cap be raised

On a host where you control the box and accept it's unsupported:

```python
# as the sealab user, with the key from db_config.yml
from fsr_utilities import encrypt
new_val = encrypt("99999999")
```

```sql
UPDATE workflow_config
   SET value = '<new_val>'
 WHERE section = 'license'
   AND key IN ('daily_action_limit', 'remaining_actions');
```

…then restart the workflow service (or invalidate its in-memory cache).
To make it *stick*, you also need to prevent FDN from overwriting it:
either block outbound to the FDN host at the network layer or stop the
`fdn_sync` scheduler in `cyops-auth`. Otherwise the next interval reverts
the row.

The clean dev-lab equivalent — and what this host already does — is
flipping `ACTION_LIMIT_ENABLED = False` in `sealab/settings.py` and
restarting; that short-circuits `is_action_count_breached` without
touching the DB or fighting FDN. Use this for dev environments; do not
do either on a licensed deployment.

## Design rules

- **Compiler is library-first, CLI is a thin wrapper.** Anything the CLI
  does, MCP and the widget can do too, by importing the same functions.
- **Errors are data, not strings.** Every validator failure has a code,
  location (line/col), suggested fix.
- **Reference store is the single source of truth.** Compiler never
  hardcodes connector/op/step-type knowledge — always resolves through
  the store. Probes refresh the store; the compiler stays stable.
- **Never trust local-only data for correctness.** Existing trust ladder
  stays: `live_*` + `tested_pass` ⇒ `is_trusted=1`; everything else is
  `seen` and surfaces with a warning.
- **Same IR across surfaces.** CLI YAML, MCP-authored YAML, and visual
  editor output are the same shape. A round-trip (compile → decompile)
  should be lossless modulo formatting.
