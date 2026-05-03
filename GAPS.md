# FSRPB — Live-instance information gaps

Tracking what we still need to confirm against a live FortiSOAR instance
before the reference store can be considered trustworthy. Everything sourced
from local files is **untested by default** — only `live_*` or `playbook_e2e`
verification methods promote an entity to `is_trusted = 1` in
`v_verification_state`.

If a gap stays open, the worst-case fallback is to read the relevant PHP
controller from `/opt/cyops-api/src/` on the FSR backend (Symfony / API
Platform). The "Where to look on the box" column lists the likely path.

## Status legend

- 🟢 confirmed live — endpoint hit successfully on a real instance
- 🟡 documented but unverified — present in dashboard FORTISOAR_API.md or Insomnia, not yet tried
- 🔴 unknown — needs discovery

---

## 1. Connectors

| What | Endpoint | Status | Where to look on the box |
|---|---|---|---|
| List installed connectors | `GET /api/3/connectors` | 🟡 | `/opt/cyops-api/src/Entity/Connector*.php`, `/opt/cyops-api/src/Controller/*Connector*` |
| Single connector full config | `GET /api/3/connectors/{uuid}` | 🟡 | same |
| Connector ops + params (machine truth) | embedded in connector record's `config`/`info` JSON field — names tbd | 🔴 | inspect `Connector` entity attributes |
| **Execute an operation** (for `live_op_exec` verification) | `POST /api/integration/execute/?name=<connector>` (compiled `.so`, no PHP source) | 🟡 | uWSGI / cyops-integrations — log-tail to confirm shape |
| Connector health check | `POST /api/integration/...` health pattern | 🔴 | grep `cyops-integrations` access log |

**Open question for Dylan**: Is there a single endpoint that returns each
connector's `info.json` verbatim, or do we need to GET the connector record
and read a nested field?

## 2. Modules / fields

| What | Endpoint | Status | Where to look |
|---|---|---|---|
| List modules + field defs | `GET /api/3/model_metadatas` | 🟡 | `/opt/cyops-api/src/Entity/ModelMetadata.php` |
| Single module | `GET /api/3/model_metadatas/{uuid}` | 🟡 | same |
| Attribute defs | `GET /api/3/attribute_metadatas` | 🟢 | confirmed 2026-05-03; 1233 entries; richer than `module_fields` — adds `formType / validation / visibility / dataSource / bulkAction / encrypted / searchable / recommend`. Worth a future probe to enrich `module_fields`. |
| Picklist hydration | `model_metadatas` does NOT inline picklist values | 🟢 | confirmed 2026-05-03; embeds `dataSource: {model:'picklists', query:{filters:[{field:'listName__name',value:'<picklist name>'}]}}`. Current `staging_model_metadatas`+`picklist_names` ingest path is correct. |
| Picklist values | `GET /api/3/picklists/{uuid}` | 🟢 (in big API doc) | — |
| Picklist taxonomy | `GET /api/3/picklist_names/{uuid}` | 🟢 | — |

**Open question**: does `model_metadatas` include picklist UUIDs inline, or
do fields just reference picklist UUIDs that we then have to hydrate?

## 3. Step types + playbook patterns

User confirmed (2026-05-02) the following endpoints + query patterns
exist on this instance. **All flagged 🟡 until probe_step_types and
probe_playbook_patterns actually hit them.**

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /api/3/workflow_step_types/` | The step-type catalog (UUID + name + label). Replaces `fsr-schema.ts` as truth. | 🟡 |
| `GET /api/3/workflow_steps?$relationships=true` | Every step instance across all playbooks with stepType + args expanded. Use for mining real argument shapes and frequency counts. | 🟡 |
| `GET /api/3/workflows?$limit=1500&$fields=uuid,name,steps` | Bulk playbook dump (use `$fields` to keep payload small). Source for probe_playbook_patterns recipes. | 🟡 |
| `GET /api/3/workflows?triggerStep.stepType.name=cybersponse.post_create` | Filter by trigger type via nested dot notation. | 🟡 |
| `GET /api/3/workflows?triggerStep.stepType.name=cybersponse.post_create&isActive=true&triggerStep.arguments.resources$exists=alerts` | Same plus `$exists` array-containment on the trigger's resources list. | 🟡 |

**Powerful query patterns documented separately** in
`soar-reporting-dashboard-cl/docs/FORTISOAR_API.md` →
"Power-user query options for /api/3/* (API Platform)". Covers
nested-dot filters, `$fields=` projection, `$exists=` on array
relationships, and `$relationships=true` for inlining. These are the
primitives any dashboard work will lean on.

**Local fallback** if any of the above don't work:
`FSRPlaybookConversion/fsr-schema.ts` for step types
(`schema_ts`, `seen` only); `pb_examples/all_fsr_evoke_playbooks.json`
for patterns.

**Open: 2 step types reference handlers not in `workflow.eval.FUNCTION_MAP`**
(captured via `scripts/dump_function_map.py`, 2026-05-02):
- ~~`workflow_reference`~~ — handled in the compiler explicitly via
  per-step-type validation (resolver matches `target: <name>` against
  collection playbooks; emitter rewrites to IRI). Runtime dispatch on
  FSR likely goes through `call` or `remote_workflow_reference`, but
  that's irrelevant for the compiler.
- `map` — possibly a list-mapping wrapper; not yet located.
- `fetch_email_and_explode` — likely registered by a connector or addon;
  search workflow.builtins.* and contrib.* for late-binding registration.

To close: enumerate `workflow.eval.FUNCTION_MAP` after a full Django
worker boot (some keys may be added at runtime by addon imports), or
grep `/opt/cyops-workflow/sealab/workflow/builtins/__pycache__/*.pyc`
for the symbol names.

## 4. Workflow collections / playbooks

| What | Endpoint | Status | Notes |
|---|---|---|---|
| List collections | `GET /api/3/workflow_collections` | 🟡 | dashboard doc cites `workflows`, `playbooks` collection names |
| List individual playbooks | `GET /api/3/workflows` | 🟢 | confirmed via Hydra root 2026-05-03 |
| Filter collection by name | `GET /api/3/workflow_collections?name=<urlencoded>` | 🟢 | exact match works after URL-encoding (e.g. `&` → `%26`). Django-style `name__exact` / `name__contains` do **not** work on `/api/3/`. Body filter on `POST /api/query/workflow_collections` also works. |
| **Filtered query** (user mentioned this works) | `POST /api/query/workflows` with body `{ "logic": "AND", "filters": [...] }` | 🟡 | confirmed pattern in dashboard doc for any model |
| Import a collection | `POST /api/3/import_jobs` (envelope, **upsert**) — or `POST /api/3/workflow_collections` (entity, strict create) | 🟢 | verified 2026-05-02 by `probe_playbook_constraints`; details in FORTISOAR_API.md |
| Export a collection | `POST /api/3/export_jobs/` + `PUT /api/export?...` | 🟢 (big API doc) | — |
| Trigger a playbook | `POST /api/triggers/1/<trigger_uuid>` | 🟡 | confirmed pattern, exact path tbd |
| Execution status | `GET /api/3/workflow_logs/{uuid}` ? | 🔴 | needs discovery |

**Where to look**: `/opt/cyops-api/src/Entity/Workflow*.php`,
`WorkflowCollection.php`, plus `/opt/cyops-api/src/Controller/` for any
`*Import*` controllers.

## 5. Jinja  (largely closed — see notes)

Render endpoint, filter catalog, and per-filter output-type observation
are now in place. Remaining open items below.



| What | Endpoint / source | Status | Notes |
|---|---|---|---|
| Render a template | `POST /api/wf/api/jinja-editor/?format=json` | 🟢 | confirmed live; widget calls this via `dynamicValueService.evaluateJinja({template, values})` |
| Filter catalog (names + docs) | `widget-jinja-editor/widget/widgetAssets/js/constants/jinjaFilters.constants.js` (49) + Playbooks Guide pp. 207-214 (141 unique) | 🟢 | merged into `jinja_macros`; 99/144 verified live as `tested_pass`, 45 fail on string input (need specific shapes) |
| Per-filter output type | observed via `{{ value \| <filter> \| type_debug }}` | 🟢 | stored in `jinja_macros.output_type_observed`; surfaces 7 generator-returning filters that need `\| list` before re-iteration |
| Per-filter input-type contract | not exposed; widget constants don't include it | 🟡 | TODO: per-filter probe with multiple input shapes (str, list, dict, int) so input_type_hint becomes data-driven instead of guesswork |
| Param shape (name/type/required) for non-widget filters | only widget constants ship structured `parameters` arrays; PDF descriptions are prose | 🟡 | TODO: parse "filter(arg1, arg2=default)" signatures out of PDF prose for ~95 filters that came from the guide only |
| List context vars (`vars.input`, `vars.steps`, `vars.records`) | not exposed | 🟡 | seed table by hand from playbook examples, then verify each via render |
| List custom macros (org-specific) | not exposed | 🔴 | grep `pb_examples` for `{% macro %}` and `{% from ... import %}` |
| YAQL filters | exposed as Jinja filter `yaql` via `/api/wf/api/jinja-editor/` | 🟢 | confirmed 2026-05-03 via `scripts/probe_yaql_smoke.py`. 6/6 probes pass: identity / where / select / len / dict-pluck / type_debug. Output type: `list`. Shape: `{{ value \| yaql("$.where($ > 1)") }}` — `$` refers to piped value. |
| Custom org macros | `globalVars.<NAME>` namespace | 🟢 | confirmed 2026-05-03 via corpus grep. FSR "macros" are scalar globals, not Jinja `{% macro %}`. Accessed as `{{ globalVars.NAME }}` (122 ref occurrences across pb_examples). Defined per-collection with `name / value / default_value`. Values are themselves jinja templates (e.g. `Current_Date={{arrow.utcnow().timestamp}}`). |

**Plan for `probe_jinja`**:
1. Ingest `jinjaFilters.constants.js` → `jinja_macros` rows, all `seen` only
   via `widget_constants` method.
2. For each filter, build a tiny `{{ value | filter }}` probe template,
   call the (TBD) render endpoint, record `live_api_render` status.
3. Filters that render successfully become trusted; failures land as
   `tested_fail` with the error in `notes`.

## 6. Generic "PHP source" fallback

If you can SSH onto the FSR box, the most useful files for filling these
gaps without trial-and-error are:

| Need | Path on box |
|---|---|
| Which `/api/3/*` entities exist | `/opt/cyops-api/config/api_platform/*.yaml` (full Hydra exposure) |
| Custom (non-CRUD) routes | `/opt/cyops-api/config/routes/` + `/opt/cyops-api/src/Controller/` |
| Model field shapes | `/opt/cyops-api/src/Entity/*.php` |
| Jinja-render controller | `grep -rn "Jinja\|render" /opt/cyops-api/src/Controller/` |
| Workflow import flow | `grep -rn "WorkflowCollection\|import" /opt/cyops-api/src/Controller/` |

A 30-second `find /opt/cyops-api/config/api_platform -name '*.yaml' | xargs grep -l Workflow` would resolve most of section 4.

---

## How to close a gap

1. Hit the candidate endpoint with `pyfsr` (or `curl -k` against `.env`'s URL).
2. If it works: add a dedicated method to pyfsr (with a unit test), call it
   from the relevant probe, record `verifications(method='live_api_get', status='tested_pass')`.
3. If it 404s / 405s: try the next candidate; if all fail, escalate to PHP
   source inspection.
4. Update this file: change 🔴/🟡 → 🟢, append the confirmed path to
   `pdf_conversion/pdfs/FortiSOAR API Guide REDUCED_CLEAN.md` Section 4.x.
