# fsrpb → pyfsr migration plan

**Date:** 2026-06-08 · **Author:** Dylan Spille
**Goal:** stop re-implementing FortiSOAR REST access in fsr-playbook-framework (fsrpb)
and consume the `pyfsr` SDK (v0.3.x, on PyPI) for all live-FSR I/O. Delete the
duplicated transport / parsing / resolution logic once pyfsr covers the gaps below.

This plan is the result of a capability gap analysis: every place fsrpb talks to a
FortiSOAR appliance was inventoried and mapped against pyfsr's public API.

---

## TL;DR

- fsrpb currently uses pyfsr **only as a dumb transport** — `from pyfsr import FortiSOAR`
  in `python/probes/_env.py:98`, then raw `.get/.post/.put/.delete/.session.*`. Everything
  else (Hydra parsing, pagination, IRI normalization, picklist resolution, record
  projection, query building, connector execution, workflow history) is hand-rolled.
- pyfsr's high-level surface **already covers most of it**. The migration is mostly
  *delete fsrpb code and call the SDK*.
- **Five real gaps** remain in pyfsr (§3) that must land first, plus one architectural
  decision about on-platform execution (§4).

---

## 1. What pyfsr already covers (adopt directly — no pyfsr change needed)

| fsrpb capability (current location) | pyfsr replacement |
|---|---|
| Connection/auth (`_env.EnvConfig`, manual `/auth/authenticate`) | `FortiSOAR(base_url, auth, verify_ssl, port, timeout, max_retries)` + `pyfsr.config.EnvConfig.from_env()` |
| Record CRUD (`cli.py`, probes: GET/POST/PUT `/api/3/{m}[/{uuid}]`) | `client.records(module).get/list/search/query/iterate/create/update` |
| Soft/hard delete (`/api/3/delete/{m}?$hardDelete=true`) | `RecordSet.delete(ref, hard=True)` (+ `restore`) |
| Hydra envelope parsing (40+ `.get("hydra:member")` sites) | `HydraPage` (`.members/.total/.has_next`), returned by `list()` |
| Pagination loops (`$limit`/`$page`) | `RecordSet.iterate()` / `pyfsr.pagination.paginate` |
| Record-ref normalization (uuid / `module:uuid` / IRI) | built into every `RecordSet` method + `BaseRecord.iri` / `.picklist_uuid()` |
| Query DSL incl. **relationship dot-walk** (`"alerts.name eq …"`) | `Query().where("alerts.name", "eq", …)` — field is a free dotted string; server treats `.`==`__`. **Not a gap.** |
| Picklist resolution (`picklists.py` 3-tier cache→DB→Jaccard) | `client.picklists.for_field/values/resolve/resolve_record_fields` (reads `staging_model_metadatas` live — the Jaccard heuristic becomes dead code) |
| Record projection / triage-shrink (`tools_triage.py` ~300 LOC) | `pyfsr.projection.project_record(rec, summary=True)` or `RecordSet.get(..., summary=True)` |
| Connector list / execute / healthcheck | `client.connectors.list_configured/execute/healthcheck/resolve_config` |
| Connector configured-instance lookup (`connector_details`) | `client.connectors.list_configured()` / `configurations()` |
| Module metadata (`staging_model_metadatas`, contexts) | `client.modules.list()/describe()` |
| Content/packs/widgets | `client.content_hub.*`, `client.records("widgets")` |
| Agents / import_jobs / generic modules | `client.records("agents")`, `client.records("import_jobs")` |
| Playbook run history (live + historical merge) | `client.playbooks.runs()/get()/resume()` |
| Structured errors (status→exception) | `pyfsr.exceptions.*` (Validation/Auth/Permission/NotFound/APIError) |
| Agent tool surface (if fsrpb wants a generic one) | `pyfsr.tools` registry + `pyfsr.mcp` |

---

## 2. Migration phases

Ordered so nothing breaks mid-flight. Each phase is independently shippable.

### Phase A — collapse the connection layer (no pyfsr change)
1. Make `_env.get_client()` the single source of a `pyfsr.FortiSOAR`. Map fsrpb's
   `FSR_*` env vars onto `pyfsr.config.EnvConfig.from_env()` (pyfsr already reads
   `FSR_BASE_URL/FSR_API_KEY/FSR_USERNAME/FSR_PASSWORD/FSR_VERIFY_SSL/FSR_PORT`).
2. Keep `_env`'s `http://`-scheme restoration shim (pyfsr auto-prepends https).
3. **Done when** every probe/tool obtains its client from `_env.get_client()` and no
   code constructs `requests.Session` or calls `/auth/authenticate` directly.

### Phase B — records & queries (no pyfsr change)
1. Replace direct `/api/3/{module}` GET/POST/PUT and `/api/query/{module}` POST calls
   with `client.records(module).*` and `pyfsr.Query`.
2. Delete fsrpb's Hydra-member extraction, `$limit/$page` loops, and IRI-prefix checks.
3. Replace `picklists.py` resolution with `client.picklists.*`; delete the
   cache→DB→Jaccard discovery once parity is confirmed against the dev box.
4. Replace `tools_triage` record-shrinking with `projection.project_record(summary=True)`;
   keep only fsrpb-specific noise rules that pyfsr's SUMMARY_FIELDS doesn't cover (audit
   the diff — SLA/escalation/impact-assessment dropping may need a custom field list).
5. **Done when** `python/picklists.py`, `python/connector_configs.py`, and the
   Hydra/pagination helpers are deleted or thin shims over pyfsr.

### Phase C — connectors & playbooks (needs pyfsr gaps #2, #3)
1. Connector *execution* → `client.connectors.execute()` (available now).
2. Connector *schema / operation-definition* fetch and *source files* → blocked on
   pyfsr gap #3.
3. Playbook *run history* → `client.playbooks.runs()/get()` (available now).
4. Playbook *step-by-step trace + jinja run-env* (`tools_triage.get_run_env`) → blocked
   on pyfsr gap #2.

### Phase D — authoring write-path (needs pyfsr gap #1)
1. Playbook/collection push (`bulkupsert/workflow_collections`, `upsert/{module}`) →
   blocked on pyfsr gap #1 (upsert/bulkupsert verbs).
2. `workflow_steps` / `workflow_step_types` CRUD already works via generic
   `client.records(...)`.

### Phase E — jinja & dynamic-variable tooling (needs pyfsr gap #4)
1. `cli.py`/`tools_jinja.py` Jinja rendering (`/api/wf/api/jinja-editor/`) and
   `dynamic-variable` → blocked on pyfsr gap #4.

### Phase F — on-platform execution (needs §4 decision)
1. Reconcile `fsr_core/mcp_server/_live_crudhub.CrudhubLiveClient` with pyfsr (see §4).

---

## 3. Gaps to add to pyfsr FIRST (blocking)

These are the only things fsrpb needs that pyfsr does not yet provide. Each should be a
small PR to pyfsr (it already has the test harness + dev-box integration suite).

1. **Upsert / bulk verbs on `RecordSet`.**
   - Add `RecordSet.upsert(data, *, match=...)` → `POST /api/3/upsert/{module}` and
     `RecordSet.bulk_upsert(rows)` → `POST /api/3/bulkupsert/{module}`.
   - Needed for playbook-collection push. pyfsr today has "deliberately no bulk path"
     (records.py) — that guard is about *delete*; upsert is safe to add.
   - Mind the 207 multi-status response shape.

2. **Playbook execution step trace + run-env.**
   - Extend `PlaybooksAPI.get(run_pk, *, step_detail=False)` to pass `?step_detail=true`.
   - Add `PlaybooksAPI.run_env(run_pk)` returning the per-step jinja context dict
     (mirrors `tools_triage.get_run_env`).

3. **Connector schema / operation-definition + source files.**
   - Add `ConnectorsAPI.definition(connector, *, version=None)` →
     `POST /api/integration/connectors/{c}/{v}/?format=json` (operation catalog).
   - Add `ConnectorsAPI.files(dev_id)` → `GET /api/integration/connector/{id}/files/`
     (dev/source fetch) — lower priority, dev-only.

4. **Jinja render + dynamic-variable helpers.**
   - Add `client.render_jinja(template, context)` → `POST /api/wf/api/jinja-editor/`.
   - Add `client.dynamic_variable(...)` → `/api/wf/api/dynamic-variable/`.
   - Could live on a new small `WfToolsAPI` accessor to keep the client tidy.

5. **`changed` / `in_all` query operators.**
   - Add both to `pyfsr.query.OPERATORS`. They're trigger-condition operators
     (see Miscellaneous memory `reference_visual_editor_wire_shapes`). One-line change
     + a unit test; lowest effort.

**Priority order for the pyfsr PRs:** #5 (trivial) → #1 (write-path unblocks Phase D)
→ #2 (triage) → #3 → #4. Ship each, cut a pyfsr patch release, then bump fsrpb's pin.

---

## 4. Architectural decision: on-platform / crudhub transport

fsrpb runs in two worlds:
- **Off-platform** (CLI/studio/dev): HTTP to a remote FSR — pyfsr fits perfectly.
- **On-platform** (inside a FortiSOAR connector): it bridges to
  `integrations.crudhub.make_request` via `fsr_core/mcp_server/_live_crudhub.CrudhubLiveClient`,
  which mimics the pyfsr surface (`get/post/put/delete`, `.session`, `.base_url`).

pyfsr is `requests`-only and assumes a network endpoint. Two options:

- **Option A (recommended): pluggable transport in pyfsr.** Extract pyfsr's HTTP calls
  behind a `Transport` protocol (`request(method, path, params, data) -> dict`). Default
  = the current requests transport; on-platform = a crudhub transport. fsrpb then always
  uses the *real* pyfsr client (high-level RecordSet/Picklists/etc.) regardless of world.
  Biggest payoff — fsrpb deletes `_live_crudhub.py` entirely and gets the high-level API
  on-platform too.
- **Option B (cheaper): keep `CrudhubLiveClient` in fsrpb** as an alternate low-level
  client, but only use it for raw calls; high-level pyfsr APIs that take a `client` arg
  must accept the crudhub shim. This is fragile (the shim must track pyfsr's internals)
  and is what fsrpb does today.

Recommend Option A as a follow-up pyfsr enhancement; it's the clean long-term shape and
lets fsrpb collapse to a single code path.

---

## 5. Validation strategy

- pyfsr already has a live dev-box integration suite (`tests/integration`, gated behind
  `-m integration`, creds in `examples/config.toml`). Add integration tests for each new
  gap method (#1–#5) against the dev box before fsrpb depends on them.
- For each fsrpb call site migrated, keep the old code path behind a flag for one cycle
  and diff outputs against the dev box (especially picklist resolution and record
  projection, where fsrpb's heuristics differ from pyfsr's).
- Pin fsrpb to an exact pyfsr version; bump only after the dependent gap PR is released.

---

## 6. Estimated deletion (what fsrpb sheds)

From the inventory, consuming pyfsr removes ~1,200 LOC of duplicated access logic:
Hydra parsing (~200), pagination (~150), IRI normalization (~100), record projection
(~300), session/auth (~200), picklist resolution (~150), query building (~100), plus the
scattered `verify=`/`timeout=` plumbing (~50). `python/picklists.py`,
`python/connector_configs.py`, and most of `_env.py`'s manual session handling go away;
`_live_crudhub.py` goes away too under Option A.
