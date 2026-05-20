# fsrpb CLI reference

_Auto-generated from `cli.build_parser()` — re-run `python3 scripts/external/dump_cli_docs.py` after touching the CLI.

## Commands

- [`fsrpb assert`](#fsrpb-assert) — 
- [`fsrpb canvas-check`](#fsrpb-canvas-check) — 
- [`fsrpb chat-review`](#fsrpb-chat-review) — 
- [`fsrpb chat-stats`](#fsrpb-chat-stats) — 
- [`fsrpb chat-transcript`](#fsrpb-chat-transcript) — 
- [`fsrpb compile`](#fsrpb-compile) — 
- [`fsrpb decompile`](#fsrpb-decompile) — 
- [`fsrpb demo`](#fsrpb-demo) — 
  - [`fsrpb demo prep`](#fsrpb-demo-prep)
- [`fsrpb diagnose`](#fsrpb-diagnose) — 
- [`fsrpb diff`](#fsrpb-diff) — 
- [`fsrpb e2e`](#fsrpb-e2e) — Run a .test.yaml end-to-end: compile → push → trigger → poll → assert → cleanup.
  - [`fsrpb e2e all`](#fsrpb-e2e-all)
  - [`fsrpb e2e cleanup`](#fsrpb-e2e-cleanup)
  - [`fsrpb e2e run`](#fsrpb-e2e-run)
- [`fsrpb env`](#fsrpb-env) — 
- [`fsrpb evals`](#fsrpb-evals) — 
- [`fsrpb explain`](#fsrpb-explain) — 
- [`fsrpb find`](#fsrpb-find) — 
- [`fsrpb find-step-examples`](#fsrpb-find-step-examples) — 
- [`fsrpb generate-recipe`](#fsrpb-generate-recipe) — 
- [`fsrpb health`](#fsrpb-health) — 
- [`fsrpb hub`](#fsrpb-hub) — Search or browse the FortiSOAR Content Hub (solutionpacks catalog).
  - [`fsrpb hub list`](#fsrpb-hub-list)
  - [`fsrpb hub search`](#fsrpb-hub-search)
  - [`fsrpb hub show`](#fsrpb-hub-show)
- [`fsrpb inputs`](#fsrpb-inputs) — 
  - [`fsrpb inputs list`](#fsrpb-inputs-list)
  - [`fsrpb inputs respond`](#fsrpb-inputs-respond)
  - [`fsrpb inputs show`](#fsrpb-inputs-show)
- [`fsrpb inspect`](#fsrpb-inspect) — 
- [`fsrpb inventory`](#fsrpb-inventory) — 
  - [`fsrpb inventory api-examples`](#fsrpb-inventory-api-examples)
  - [`fsrpb inventory connectors`](#fsrpb-inventory-connectors)
  - [`fsrpb inventory search`](#fsrpb-inventory-search)
  - [`fsrpb inventory stale`](#fsrpb-inventory-stale)
  - [`fsrpb inventory summary`](#fsrpb-inventory-summary)
- [`fsrpb jinja`](#fsrpb-jinja) — 
- [`fsrpb jinja-filter`](#fsrpb-jinja-filter) — 
- [`fsrpb mcp`](#fsrpb-mcp) — 
- [`fsrpb picklist`](#fsrpb-picklist) — 
  - [`fsrpb picklist for-field`](#fsrpb-picklist-for-field)
  - [`fsrpb picklist list`](#fsrpb-picklist-list)
  - [`fsrpb picklist resolve`](#fsrpb-picklist-resolve)
  - [`fsrpb picklist show`](#fsrpb-picklist-show)
- [`fsrpb probe`](#fsrpb-probe) — Run one or more reference-store probes against the live FSR instance.
- [`fsrpb pull`](#fsrpb-pull) — 
- [`fsrpb pull-collection`](#fsrpb-pull-collection) — 
- [`fsrpb purge`](#fsrpb-purge) — 
- [`fsrpb push`](#fsrpb-push) — 
- [`fsrpb recipe`](#fsrpb-recipe) — 
  - [`fsrpb recipe find`](#fsrpb-recipe-find)
  - [`fsrpb recipe show`](#fsrpb-recipe-show)
- [`fsrpb refresh`](#fsrpb-refresh) — 
- [`fsrpb resolve`](#fsrpb-resolve) — 
- [`fsrpb roundtrip`](#fsrpb-roundtrip) — 
- [`fsrpb routes`](#fsrpb-routes) — 
- [`fsrpb run-op`](#fsrpb-run-op) — 
- [`fsrpb run-playbook`](#fsrpb-run-playbook) — 
- [`fsrpb runs`](#fsrpb-runs) — 
- [`fsrpb search`](#fsrpb-search) — 
- [`fsrpb status`](#fsrpb-status) — 
- [`fsrpb steps`](#fsrpb-steps) — 
- [`fsrpb triggers`](#fsrpb-triggers) — 
- [`fsrpb validate`](#fsrpb-validate) — 
- [`fsrpb validate-ingestion`](#fsrpb-validate-ingestion) — 

## `fsrpb`

| arg | help | meta |
| --- | --- | --- |
| `--db` | path to fsr_reference.db | default: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/store/fsr_reference.db` |

### `assert`

| arg | help | meta |
| --- | --- | --- |
| `input` | path to JSON file with a list of assertions, '-' for stdin, or an inline JSON array | — |
| `--json` | emit full result as JSON on stdout | — |

### `canvas-check`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | — |
| `--json` |  | — |

### `chat-review`

| arg | help | meta |
| --- | --- | --- |
| `session_id` | chat session id (from /api/history/sessions or the History tab) | — |
| `--history-db` | path to web/backend/history.db (defaults to STUDIO_HISTORY_DB env or the standard location) | — |
| `--json` | emit structured report as JSON on stdout | — |

### `chat-stats`

| arg | help | meta |
| --- | --- | --- |
| `path` | path to usage JSONL (defaults to $STUDIO_USAGE_LOG or web/backend/usage.jsonl) | — |
| `--session` | filter to one session id | — |
| `--top` | rows to show in tool-cost ranking (default 10) | default: `10` |

### `chat-transcript`

| arg | help | meta |
| --- | --- | --- |
| `session_id` | chat session id (from /api/history/sessions or the History tab) | — |
| `--history-db` | path to web/backend/history.db (defaults to STUDIO_HISTORY_DB env or the standard location) | — |
| `--json` | emit structured transcript as JSON on stdout | — |
| `--full` | don't truncate tool args / results (default caps at 280 chars) | — |

### `compile`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | — |
| `-o`, `--output` |  | required |

### `decompile`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | — |
| `-o`, `--output` |  | — |
| `-w`, `--workflow` | filter to a single workflow by exact name | — |

### `demo`

#### `demo prep`

| arg | help | meta |
| --- | --- | --- |
| `--pattern` | extra glob to purge (repeatable) | default: `[]` |

### `diagnose`

| arg | help | meta |
| --- | --- | --- |
| `yaml` | path to the playbook YAML | — |
| `pb_execution` | workflow PK or task_id of the run | — |
| `--json` |  | — |

### `diff`

| arg | help | meta |
| --- | --- | --- |
| `input` | local YAML | — |
| `-c`, `--collection` | live collection name (defaults to YAML's collection name) | — |

### `e2e`

Run a .test.yaml end-to-end: compile → push → trigger → poll → assert → cleanup.

Subcommands:
  run <test.yaml>    Run a single test sidecar against the live instance.
  cleanup [PATTERN]  Hard-purge collections whose name matches glob(s).
                     Default patterns: 'FSRPB Demo*', 'Compiler Demo*',
                     '*__fsrpb_probe__*'. Override with one or more args.

#### `e2e all`

| arg | help | meta |
| --- | --- | --- |
| `--dir` | search dir for *.test.yaml (default: examples/) | — |
| `--keep` | leave deployed collections in place after each run | — |
| `--no-cleanup` | skip the pre-pass purge of stale demo/test collections | — |
| `--json` | emit machine-readable per-test results to stdout | — |
| `--verbose` | show per-step run output for each test (default: summary only) | — |

#### `e2e cleanup`

| arg | help | meta |
| --- | --- | --- |
| `patterns` | name glob(s); defaults to FSRPB Demo* / Compiler Demo* / *__fsrpb_probe__* | — |

#### `e2e run`

| arg | help | meta |
| --- | --- | --- |
| `test` | path to <fixture>.test.yaml | — |
| `--keep` | leave the deployed collection in place after the run | — |

### `env`

| arg | help | meta |
| --- | --- | --- |
| `pb_execution` | workflow PK (integer) or task_id (UUID) | — |
| `--task-id` | force UUID-as-task_id resolution (rarely needed; auto-detected) | — |
| `--summary` | print a one-line-per-key index instead of full JSON | — |

### `evals`

| arg | help | meta |
| --- | --- | --- |
| `--models` | comma-separated provider names (gold, echo, anthropic, openai, lmstudio) | default: `gold,echo` |
| `--tasks` | comma-separated task names; default = all | — |
| `--live` | enable live Runs gate (resolve + dry-run) against the live FSR | — |
| `--json` | emit the full matrix as JSON on stdout | — |

### `explain`

| arg | help | meta |
| --- | --- | --- |
| `kind` |  | choices: `connector`, `step`, `handler`, `filter`, `module`, `recipe` |
| `name` |  | — |

### `find`

| arg | help | meta |
| --- | --- | --- |
| `--step-type` | WorkflowStepType name (Connectors, ManualInput, Decision, …) | — |
| `--connector` | connector name in any step's arguments.connector | — |
| `--operation` | operation name in any step's arguments.operation | — |
| `--calls` | playbooks that workflow_reference this name/uuid | — |
| `--text` | any substring in any step's serialized arguments | — |
| `--collection` | restrict to one collection (name) | — |
| `--active` | only isActive=true | — |
| `--triggered-by` | playbooks listening to this record-event (requires --module) | choices: `on-create`, `on-update`, `on-delete`, `pre-create`, `pre-update`, `pre-delete` |
| `--module` | module name (alerts, incidents, …) — used with --triggered-by | — |
| `--writes-to` | playbooks with insert_record / update_record / approval against this module | — |
| `--json` | emit JSON | — |

### `find-step-examples`

| arg | help | meta |
| --- | --- | --- |
| `step_type` | step_types.name e.g. ManualInput, Decision, SetVariable | — |
| `--contains` | optional substring that must appear in arguments_json (e.g. 'ipv4', 'formType":"lookup', 'default":true') | — |
| `--limit` |  | default: `20` |
| `--json` |  | — |

### `generate-recipe`

| arg | help | meta |
| --- | --- | --- |
| `--kind` | recipe kind | choices: `threat-feed`, `data-ingest` · required |
| `--info-json` | path to connector info.json | required |
| `--config-uuid` | FSR connector instance UUID; user replaces post-import if omitted | default: `REPLACE_WITH_CONFIG_UUID` |
| `-o`, `--output` | write FSR JSON to this path; otherwise stdout | — |
| `--target-module` | (data-ingest) module IRI segment, e.g. 'alerts' or 'incidents' (default: alerts) | default: `alerts` |
| `--fetch-op` | (data-ingest) override fetch op name when auto-detect picks the wrong one | — |
| `--dedup-field` | (data-ingest) vendor field used as sourceId for dedup (auto-detected from op output_schema) | — |
| `--severity-field` | (data-ingest) field on each item carrying the vendor severity enum | default: `severity` |
| `--status-field` | (data-ingest) field on each item carrying the vendor status enum | default: `status` |
| `--severity-enum` | (data-ingest) comma-separated vendor severity values, e.g. 'CRITICAL,HIGH,MEDIUM,LOW' | — |
| `--status-enum` | (data-ingest) comma-separated vendor status values, e.g. 'Open,Investigating,Closed' | — |
| `--skip-prechecks` | skip live-FSR prechecks (connector installed, picklist values resolvable). Use offline. | — |

### `health`

| arg | help | meta |
| --- | --- | --- |
| `connector` | connector name (omit to list all configured); single-name always probes | — |
| `--version` | connector version (default: looked up live) | — |
| `--config` | config UUID to test (when a connector has multiple configurations) | — |
| `--probe` | when listing all, also healthcheck each one (one extra round-trip per connector) | — |
| `--json` | emit JSON instead of grouped tables | — |

### `hub`

Search or browse the FortiSOAR Content Hub (solutionpacks catalog).

Examples:
  fsrpb hub search virustotal          # find connectors matching a query
  fsrpb hub search "threat intel"      # multi-word search
  fsrpb hub show abuseipdb             # show full ops + params for a connector
  fsrpb hub list --category "Threat Intelligence"  # list by category

#### `hub list`

| arg | help | meta |
| --- | --- | --- |
| `--category` | filter by category (partial match) | — |

#### `hub search`

| arg | help | meta |
| --- | --- | --- |
| `query` | search term | — |

#### `hub show`

| arg | help | meta |
| --- | --- | --- |
| `name` | connector name (e.g. abuseipdb) | — |

### `inputs`

#### `inputs list`

| arg | help | meta |
| --- | --- | --- |
| `--json` |  | — |

#### `inputs respond`

| arg | help | meta |
| --- | --- | --- |
| `id` | manual-wf-input pk (from `inputs list`) | — |
| `--option` | button label to pick (default: primary option) | — |
| `--vars` | JSON dict of inputVariable values | — |
| `--task-id` | task_id from the original trigger (helps resolve wf pk) | — |
| `--json` |  | — |

#### `inputs show`

| arg | help | meta |
| --- | --- | --- |
| `id` | manual-wf-input pk | — |
| `--json` |  | — |

### `inspect`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | — |
| `--json` | JSON output (default) | — |
| `--table` | human-readable two-table layout instead of JSON | — |
| `--task` | overlay execution status from this task_id (historical-steps); marks each route TRAVERSED if both endpoints executed in the run | — |

### `inventory`

#### `inventory api-examples`

| arg | help | meta |
| --- | --- | --- |
| `-q` | filter substring | — |
| `--limit` |  | default: `50` |

#### `inventory connectors`

| arg | help | meta |
| --- | --- | --- |
| `-q` | filter substring | — |
| `--limit` |  | default: `50` |

#### `inventory search`

| arg | help | meta |
| --- | --- | --- |
| `q` | search needle | — |
| `--limit` | per-table result cap | default: `5` |

#### `inventory stale`

| arg | help | meta |
| --- | --- | --- |
| `--days` |  | default: `7` |

#### `inventory summary`

### `jinja`

| arg | help | meta |
| --- | --- | --- |
| `template` | Jinja template string, e.g. '{{ vars.steps.Get_org.records[0].id }}' | — |
| `--from-pb-execution` | seed context from a past run (workflow PK or task_id) | — |
| `--input` | JSON file path or inline JSON to merge into context | — |
| `--bind` | KEY=VALUE override (repeatable; dotted keys nest under vars). Value is JSON-parsed if possible, else plain string | default: `[]` |

### `jinja-filter`

| arg | help | meta |
| --- | --- | --- |
| `query` | filter name or substring | — |
| `--examples` | show real corpus expressions instead of hits | — |
| `--limit` |  | default: `8` |

### `mcp`

### `picklist`

#### `picklist for-field`

| arg | help | meta |
| --- | --- | --- |
| `module` |  | — |
| `field` |  | — |

#### `picklist list`

#### `picklist resolve`

| arg | help | meta |
| --- | --- | --- |
| `value` |  | — |
| `--name` | picklist listName.name (overrides discovery) | — |
| `--module` |  | — |
| `--field` |  | — |

#### `picklist show`

| arg | help | meta |
| --- | --- | --- |
| `name` |  | — |

### `probe`

Run one or more reference-store probes against the live FSR instance.

Each probe fetches a slice of FSR's metadata and writes it into
store/fsr_reference.db.  All probes are idempotent — re-running them
updates the store in place without destroying existing data.

Examples:
  fsrpb probe connectors            # refresh connector / op / param data
  fsrpb probe jinja jinja-backend   # refresh both Jinja probes
  fsrpb probe --all                 # run every probe in sequence
  fsrpb probe --list                # show available probes

| arg | help | meta |
| --- | --- | --- |
| `probes` | probe name(s) to run (omit with --all) | — |
| `--all` | run all probes in order | — |
| `--list` | list available probes and exit | — |
| `--live` | pass through to probes that support a live-FSR mode (currently: playbook-steps) | — |

### `pull`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name or UUID | — |
| `-o`, `--output` |  | — |

### `pull-collection`

| arg | help | meta |
| --- | --- | --- |
| `collection` | collection name or UUID | — |
| `-o`, `--output` |  | — |

### `purge`

| arg | help | meta |
| --- | --- | --- |
| `target` | workflow name(s) or UUID(s) | — |
| `--dry-run` | show counts without deleting | — |

### `push`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | — |
| `--mode` | replace (default): DELETE+POST clean-slate update. create: POST only (409 on UUID/name collision). update: PUT in-place (preserves unmodeled fields). | choices: `replace`, `create`, `update`, `upsert` · default: `replace` |
| `--json` | print response JSON to stdout | — |

### `recipe`

#### `recipe find`

| arg | help | meta |
| --- | --- | --- |
| `query` |  | default: `` |
| `--kind` | threat_feed \| data_ingest | — |
| `--limit` |  | default: `10` |
| `--yaml` | print just the yaml_template if exactly one hit | — |

#### `recipe show`

| arg | help | meta |
| --- | --- | --- |
| `name` |  | — |
| `--yaml` | print yaml_template only | — |

### `refresh`

### `resolve`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | — |
| `--json` | emit full result as JSON on stdout | — |

### `roundtrip`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | — |

### `routes`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | — |
| `--json` |  | — |

### `run-op`

| arg | help | meta |
| --- | --- | --- |
| `connector` |  | — |
| `operation` |  | — |
| `--params` | JSON string or path to a JSON file | — |
| `--version` | override connector version (default: store) | — |
| `--config` | connector config name | — |

### `run-playbook`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | — |
| `--collection` | restrict name lookup to this collection (disambiguates duplicates) | — |
| `--input` | JSON string or path to a JSON file (designer-run mode) | — |
| `--record` | fire as record-context Execute (cybersponse.action triggers); e.g. alerts:db7afbf7-... | — |
| `--follow` | poll task status until terminal (finished/failed/terminated/skipped) | — |
| `--follow-interval` | seconds between polls (default 3) | default: `3` |
| `--follow-timeout` | give up after N seconds (default 300) | default: `300` |
| `--mock` | trigger with useMockOutput=true / globalMock=true so each step returns its arguments.mock_result instead of executing live; useful for validating playbook plumbing when the target connector is not yet configured. Default: off. | — |

### `runs`

| arg | help | meta |
| --- | --- | --- |
| `--all` | include successful runs (default: failed/errored only) | — |
| `--status` | explicit status filter (comma-separated, e.g. 'failed,finished_with_error,terminated') | — |
| `--limit` |  | default: `20` |
| `--json` |  | — |

### `search`

| arg | help | meta |
| --- | --- | --- |
| `query` |  | — |
| `--limit` |  | default: `10` |
| `--json` |  | — |

### `status`

| arg | help | meta |
| --- | --- | --- |
| `-n`, `--limit` |  | default: `10` |

### `steps`

| arg | help | meta |
| --- | --- | --- |
| `task_id` | task_id from `run-playbook` output | — |
| `-v`, `--verbose` | dump each step's args/input/result JSON | — |
| `--json` |  | — |

### `triggers`

| arg | help | meta |
| --- | --- | --- |
| `module` | module name (alerts, incidents, indicators, …); omit for all | — |
| `--inactive` | include unpublished playbooks (isActive=false) | — |
| `--json` | emit raw JSON | — |

### `validate`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | — |
| `--json` | emit errors as JSON on stdout | — |

### `validate-ingestion`

| arg | help | meta |
| --- | --- | --- |
| `input` | path to FSR workflow_collections JSON | — |
| `--rulesets` | comma list: data-ingest, feed-ingest, or 'auto' (detect from tags+steps). Default: auto | default: `auto` |
| `--json` | emit issues as JSON on stdout | — |
| `--info-json` | connector info.json path (auto-detected next to or above the playbook file if omitted) | — |
