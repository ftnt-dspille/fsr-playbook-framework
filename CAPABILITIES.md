# What can I do with fsrpb?

A capabilities dashboard for users who are new to the toolchain. Find your goal in the left column, follow the entry-point in the middle, and you'll land on either a runnable command or a script the agent can follow end-to-end.

For exhaustive tool / step-type / connector / Jinja docs, see [`store/MCP_TOOLS.md`](store/MCP_TOOLS.md), [`store/STEP_TYPES.md`](store/STEP_TYPES.md), [`store/CONNECTORS.md`](store/CONNECTORS.md), [`store/FSR_CUSTOM_JINJA.md`](store/FSR_CUSTOM_JINJA.md).

---

## I want to…

### …generate a working playbook from scratch (recipes)

The fastest path. Recipes ship as ready-to-push YAML/JSON for two common patterns.

| What | Command | Output |
|---|---|---|
| Threat-feed ingestion (TAXII2-style — bulk feed → indicators) | `fsrpb generate-recipe --kind threat-feed --info-json <connector>/info.json` | full collection JSON, validates clean, push-ready |
| Data ingestion (alerts / incidents from a SIEM-style fetch op) | `fsrpb generate-recipe --kind data-ingest --info-json <connector>/info.json --target-module alerts` | full collection JSON |

Behind the scenes the generator queries the live FSR for picklist UUIDs, prechecks that the target connector is installed, and binds output to its matching ruleset for self-validation. See [`store/RECIPES.md`](store/RECIPES.md) for the structural patterns.

### …explore a sample playbook and adapt it

Working examples live in `examples/` — each has a `.yaml` source and a `.test.yaml` runner spec.

| Sample | What it shows |
|---|---|
| `demo_pure_logic` | Set / decision / no external calls — fastest smoke |
| `demo_record_create` | Create a record, capture its uuid |
| `demo_record_find_update` | Find a record, then update it |
| `demo_for_each` | Iterate over a list of records |
| `demo_decision_branch` | Multi-branch decision with default route |
| `demo_parent_child` | Parent calls child via `workflow_reference` |
| `demo_manual_input` | Pause for human input mid-flow |
| `demo_delay` | Sleep step |
| `demo_code_snippet` | Inline Python/Jinja transform |
| `demo_alert_on_create` | On-create trigger on the `alerts` module |
| `demo_alert_on_status_change` | Field-mutate trigger |
| `demo_alert_action` | Record-context "Execute" action button |
| `demo_virustotal_ip` | Real connector op with verdict logic |

Run any one end-to-end with: `fsrpb e2e run examples/<name>.test.yaml`.
Run all 11: `fsrpb e2e all`.

### …let an agent build it for me from a natural-language ask

The MCP server exposes 26 tools (see [`store/MCP_TOOLS.md`](store/MCP_TOOLS.md)) that an LLM uses to do the entire authoring loop.

Demo prompt:
> Build me a playbook that takes an IP, looks it up on VirusTotal, and tells me whether it's malicious or clean.

The agent typically: `find_connector` → `find_operation` → `get_op_schema` → emit YAML → `validate_yaml` → `dry_run_playbook` (compile + push + run + cleanup). No CLI hand-off.

Full scripted scenarios in [`DEMO.md`](DEMO.md).

### …troubleshoot a broken playbook

The killer demo. None of this loop is possible from the FSR Playbook Designer.

Agent flow:
1. `list_recent_failed_runs(limit=20)` — newest failures across the instance, **including historical** (FSR purges live → historical every ~30-60 min). Returns `task_id`, `name`, `status`, `error_message`, `source: live|historical`.
2. `get_run_env(<pk>)` — rebuilds the live `{vars: {…env, steps: {Step_Name: result}}}` Jinja context from a real run. The shape mismatch (e.g. `.records` vs `.data`) is now obvious.
3. `render_jinja('{{ vars.steps.X.field }}', from_pb_execution=<pk>)` — confirm the candidate fix resolves before committing.
4. `fsrpb pull "<name>"` → edit YAML → `validate_yaml` → `push_playbook` → `run_playbook --follow`.

Filter further with `modified_after`, `tags_include`, `tags_exclude="system"`, `user_iri="/api/3/people/<uuid>"` for noisy instances.

### …reverse-engineer or audit an existing playbook

| Goal | How |
|---|---|
| Pull a live playbook to YAML | `fsrpb pull "<name>"` |
| Pull a whole collection | `fsrpb pull-collection "<coll-name>"` |
| Diff your YAML against the live version | `fsrpb diff "<name>"` |
| Search across the corpus | MCP `search_playbooks(q)` — full-text over 1,669 live workflows |
| Decompile FSR JSON to YAML | `fsrpb decompile <coll.json>` |
| Round-trip-test the compiler | `fsrpb roundtrip <coll.json>` |

### …understand what a connector / op / step type / Jinja filter does

| Surface | Tool |
|---|---|
| Find connectors by keyword | `find_connector(q)` (CLI: `fsrpb find connector <q>`) |
| List operations on a connector | `find_operation(connector, q)` |
| Full op schema (params + observed output shape) | `get_op_schema(connector, op)` |
| Run an op live to observe real output | `run_op(connector, op, params, confirm=True)` |
| Step-type schema (start / decision / connector / etc) | `get_step_type(name)` |
| Find a Jinja filter | `find_jinja_filter(q)` (corpus_uses + curated_doc) |
| See real corpus expressions for a filter | `get_filter_examples(name)` |
| Search the corpus by block kind (`set`/`for`/`if`/`macro`/`expr`) | `find_jinja_pattern(q, kind)` |
| Render a template against a real past run | `render_jinja(tpl, from_pb_execution=<pk>)` |

### …verify a YAML draft before pushing

| Step | Tool |
|---|---|
| Catch typos and structural errors | `validate_yaml(yaml_text)` — structured errors with "did you mean…" suggestions for connector / op / param / step-id / Jinja path / picklist value |
| Convert to FSR JSON without pushing | `compile_yaml(yaml_text)` |
| End-to-end dry run with auto-cleanup | `dry_run_playbook(yaml_text, playbook=…, input=…)` |

### …discover what's configured / healthy on the live FSR

| Goal | Tool |
|---|---|
| List configured + active connectors | `list_configured_connectors(probe=True)` |
| Health-check one connector config | `healthcheck_connector(name, version, config)` |
| List picklists | `list_picklists()` |
| Map a field to its picklist | `picklist_for_field(module, field)` |
| Resolve a label to its IRI | `resolve_picklist_value("Critical", "Severity")` |
| Discover available tags (for filtering runs) | `list_tags(prefix="syst")` |

---

## Demo storyboards

Four scripted scenarios in [`DEMO.md`](DEMO.md), each ~3-5 minutes:

- **Demo A — Authoring from a vague ask**: connector discovery → op schema → YAML → validate → dry-run. Showcases the full loop without CLI hand-off.
- **Demo B — Iterating on a broken draft**: paste typo'd YAML, agent uses validator's "did you mean" + `render_jinja(from_pb_execution=…)` to fix without guessing.
- **Demo C — Triage and fix a broken playbook**: `list_recent_failed_runs` → `get_run_env` → spot shape mismatch → pull / edit / push / re-run. **Not possible in the FSR Designer.**
- **Demo D — Reverse-engineer an existing playbook**: pull → narrate steps in plain English → cross-reference idioms via `find_jinja_pattern`.

Pre-talk smoke: `fsrpb e2e all` runs all 11 demo fixtures end-to-end.

---

## Where to look next

- [`AUTHORING.md`](AUTHORING.md) — the agent's authoring guide; per-step output-shape table; the `vars.steps.<Underscored_Step_Name>` rule
- [`store/MCP_TOOLS.md`](store/MCP_TOOLS.md) — every MCP tool, auto-generated, with full signatures + docstrings
- [`store/STEP_TYPES.md`](store/STEP_TYPES.md) — all 43 FSR step types with arg shapes
- [`store/CONNECTORS.md`](store/CONNECTORS.md) — 714 connectors, 6,773 ops, signatures-as-cheatsheet
- [`store/FSR_CUSTOM_JINJA.md`](store/FSR_CUSTOM_JINJA.md) — the 32 FortiSOAR-custom Jinja capabilities (grep this first for FSR-flavored Jinja)
- [`store/JINJA_IDIOMS.md`](store/JINJA_IDIOMS.md) — 10 corpus-mined patterns
- [`store/RECIPES.md`](store/RECIPES.md) — multi-step composition templates
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the parser → resolver → validator → emitter pipeline
- [`PRESENTATION_OUTLINE.md`](PRESENTATION_OUTLINE.md) — slide deck for the talk
