# fsrpb CLI reference

_Auto-generated from `cli.build_parser()` -- re-run `python3 scripts/external/dump_cli_docs.py` after touching the CLI.

## Commands

- [`fsrpb agent-stats`](#fsrpb-agent-stats) -- Phase-1 analyzer for AGENT_QUALITY_PLAN.md.
- [`fsrpb agreement`](#fsrpb-agreement) -- 
- [`fsrpb analyze`](#fsrpb-analyze) -- 
- [`fsrpb assert`](#fsrpb-assert) -- 
- [`fsrpb audit-shapes`](#fsrpb-audit-shapes) -- 
- [`fsrpb canvas-check`](#fsrpb-canvas-check) -- 
- [`fsrpb chat-drive`](#fsrpb-chat-drive) -- 
- [`fsrpb chat-review`](#fsrpb-chat-review) -- 
- [`fsrpb chat-stats`](#fsrpb-chat-stats) -- 
- [`fsrpb chat-transcript`](#fsrpb-chat-transcript) -- 
- [`fsrpb compile`](#fsrpb-compile) -- 
- [`fsrpb decompile`](#fsrpb-decompile) -- 
- [`fsrpb demo`](#fsrpb-demo) -- 
  - [`fsrpb demo prep`](#fsrpb-demo-prep)
- [`fsrpb diagnose`](#fsrpb-diagnose) -- 
- [`fsrpb diff`](#fsrpb-diff) -- 
- [`fsrpb doctor`](#fsrpb-doctor) -- 
- [`fsrpb dump-step-params`](#fsrpb-dump-step-params) -- 
- [`fsrpb e2e`](#fsrpb-e2e) -- Run a .test.yaml end-to-end: compile → push → trigger → poll → assert → cleanup.
  - [`fsrpb e2e all`](#fsrpb-e2e-all)
  - [`fsrpb e2e cleanup`](#fsrpb-e2e-cleanup)
  - [`fsrpb e2e run`](#fsrpb-e2e-run)
- [`fsrpb env`](#fsrpb-env) -- 
- [`fsrpb evals`](#fsrpb-evals) -- 
- [`fsrpb explain`](#fsrpb-explain) -- 
- [`fsrpb find`](#fsrpb-find) -- 
- [`fsrpb find-step-examples`](#fsrpb-find-step-examples) -- 
- [`fsrpb generate-recipe`](#fsrpb-generate-recipe) -- 
- [`fsrpb graph`](#fsrpb-graph) -- 
- [`fsrpb health`](#fsrpb-health) -- 
- [`fsrpb hub`](#fsrpb-hub) -- Search or browse the FortiSOAR Content Hub (solutionpacks catalog).
  - [`fsrpb hub list`](#fsrpb-hub-list)
  - [`fsrpb hub search`](#fsrpb-hub-search)
  - [`fsrpb hub show`](#fsrpb-hub-show)
- [`fsrpb inputs`](#fsrpb-inputs) -- 
  - [`fsrpb inputs list`](#fsrpb-inputs-list)
  - [`fsrpb inputs respond`](#fsrpb-inputs-respond)
  - [`fsrpb inputs show`](#fsrpb-inputs-show)
- [`fsrpb inspect`](#fsrpb-inspect) -- 
- [`fsrpb inventory`](#fsrpb-inventory) -- 
  - [`fsrpb inventory api-examples`](#fsrpb-inventory-api-examples)
  - [`fsrpb inventory connectors`](#fsrpb-inventory-connectors)
  - [`fsrpb inventory search`](#fsrpb-inventory-search)
  - [`fsrpb inventory stale`](#fsrpb-inventory-stale)
  - [`fsrpb inventory summary`](#fsrpb-inventory-summary)
- [`fsrpb jinja`](#fsrpb-jinja) -- 
- [`fsrpb jinja-filter`](#fsrpb-jinja-filter) -- 
- [`fsrpb matrix`](#fsrpb-matrix) -- 
- [`fsrpb mcp`](#fsrpb-mcp) -- 
- [`fsrpb migrate`](#fsrpb-migrate) -- Migrate playbook YAMLs to the current friendly authoring surface.
- [`fsrpb picklist`](#fsrpb-picklist) -- 
  - [`fsrpb picklist for-field`](#fsrpb-picklist-for-field)
  - [`fsrpb picklist list`](#fsrpb-picklist-list)
  - [`fsrpb picklist resolve`](#fsrpb-picklist-resolve)
  - [`fsrpb picklist show`](#fsrpb-picklist-show)
- [`fsrpb probe`](#fsrpb-probe) -- Run one or more reference-store probes against the live FSR instance.
- [`fsrpb provision`](#fsrpb-provision) -- Teach the reference store about a single connector.
- [`fsrpb pull`](#fsrpb-pull) -- 
- [`fsrpb pull-collection`](#fsrpb-pull-collection) -- 
- [`fsrpb purge`](#fsrpb-purge) -- 
- [`fsrpb push`](#fsrpb-push) -- 
- [`fsrpb recipe`](#fsrpb-recipe) -- 
  - [`fsrpb recipe find`](#fsrpb-recipe-find)
  - [`fsrpb recipe show`](#fsrpb-recipe-show)
- [`fsrpb recover-deleted-playbooks`](#fsrpb-recover-deleted-playbooks) -- 
- [`fsrpb refresh`](#fsrpb-refresh) -- 
- [`fsrpb resolve`](#fsrpb-resolve) -- 
- [`fsrpb roundtrip`](#fsrpb-roundtrip) -- 
- [`fsrpb routes`](#fsrpb-routes) -- 
- [`fsrpb run-op`](#fsrpb-run-op) -- 
- [`fsrpb run-playbook`](#fsrpb-run-playbook) -- 
- [`fsrpb runs`](#fsrpb-runs) -- 
- [`fsrpb search`](#fsrpb-search) -- 
- [`fsrpb status`](#fsrpb-status) -- 
- [`fsrpb steps`](#fsrpb-steps) -- 
- [`fsrpb triggers`](#fsrpb-triggers) -- 
- [`fsrpb validate`](#fsrpb-validate) -- 
- [`fsrpb validate-ingestion`](#fsrpb-validate-ingestion) -- 
- [`fsrpb verify`](#fsrpb-verify) -- 

## `fsrpb`

| arg | help | meta |
| --- | --- | --- |
| `--db` | path to fsr_reference.db | default: `/Users/dylanspille/PycharmProjects/fsr-playbook-framework/data/fsr_reference.db` |

### `agent-stats`

Phase-1 analyzer for AGENT_QUALITY_PLAN.md.

Scans `web/backend/history.db` and writes three artifacts:
  - docs/AGENT_TOOL_USAGE.md       per-tool census
  - docs/AGENT_DATA_GAPS.md        empty/repeated lookup needles
  - docs/AGENT_PROMPT_ADHERENCE.md structural prompt-rule checks
Read-only against history.db.

| arg | help | meta |
| --- | --- | --- |
| `--out-dir` | docs output dir (default: <repo>/docs) | -- |
| `--history-db` | history.db path (default: web/backend/history.db) | -- |

### `agreement`

| arg | help | meta |
| --- | --- | --- |
| `--screen` | archived --repeat run for side A (any lane; conventionally the cheaper one) | -- |
| `--confirm` | archived --repeat run for side B, naming a DIFFERENT lane. Pair it with `attribute` on either side to blame a disagreement on the model or the substrate rather than both at once. | -- |
| `--list-screens` | list archived --repeat runs and exit | -- |
| `--json` | emit the agreement report as JSON | -- |

### `analyze`

| arg | help | meta |
| --- | --- | --- |
| `input` | playbook YAML file | -- |
| `--playbook` | name of the workflow within the YAML (default: first one) | -- |
| `--trigger-input` | JSON for vars.input.params (e.g. '{"alert_id":7}') | -- |
| `--branch-choices` | JSON map of {step_id: branch_label} pinning decision routes | -- |
| `--manual-choices` | JSON map of {step_id: option_label} pinning manual_input choices | -- |
| `--execute-safe-ops` | run read-only connector ops live for real outputs (default: pure offline) | -- |
| `--json` | emit the full analyzer payload as JSON to stdout | -- |

### `assert`

| arg | help | meta |
| --- | --- | --- |
| `input` | path to JSON file with a list of assertions, '-' for stdin, or an inline JSON array | -- |
| `--json` | emit full result as JSON on stdout | -- |

### `audit-shapes`

| arg | help | meta |
| --- | --- | --- |
| `--out` |  | default: `docs/corpus_audit` |
| `--db` |  | default: `/Users/dylanspille/PycharmProjects/fsr-playbook-framework/data/fsr_reference.db` |
| `--type` | filter to one step_type_name (e.g. ManualInput) | -- |

### `canvas-check`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | -- |
| `--json` |  | -- |

### `chat-drive`

| arg | help | meta |
| --- | --- | --- |
| `--task` | existing investigation task fixture name (e.g. invest_outbound_cleartext_c2) | -- |
| `--message` | ad-hoc scenario message (no fixture scoring) | -- |
| `--intent` | triage \| build | default: `triage` |
| `--record` | optional record context: JSON string or path | -- |
| `--version` | deployed connector version to drive | default: `0.3.116` |
| `--config` | connector config name | default: `fsrpb-live` |
| `--capture-fixture` | (A2) propose a tasks/*.json + golden trace from this run for review (ad-hoc --message runs only) | -- |
| `--json` | also emit the full run summary as JSON | -- |

### `chat-review`

| arg | help | meta |
| --- | --- | --- |
| `session_id` | chat session id (from /api/history/sessions or the History tab) | -- |
| `--history-db` | path to web/backend/history.db (defaults to STUDIO_HISTORY_DB env or the standard location) | -- |
| `--json` | emit structured report as JSON on stdout | -- |

### `chat-stats`

| arg | help | meta |
| --- | --- | --- |
| `path` | path to usage JSONL (defaults to $STUDIO_USAGE_LOG or web/backend/usage.jsonl) | -- |
| `--session` | filter to one session id | -- |
| `--top` | rows to show in tool-cost ranking (default 10) | default: `10` |

### `chat-transcript`

| arg | help | meta |
| --- | --- | --- |
| `session_id` | chat session id (from /api/history/sessions or the History tab) | -- |
| `--history-db` | path to web/backend/history.db (defaults to STUDIO_HISTORY_DB env or the standard location) | -- |
| `--json` | emit structured transcript as JSON on stdout | -- |
| `--full` | don't truncate tool args / results (default caps at 280 chars) | -- |

### `compile`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `-o`, `--output` |  | required |
| `--lax` | demote unknown_param/unknown_connector to warnings (use for round-trip Path B on decompiled playbooks) | -- |

### `decompile`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `-o`, `--output` |  | -- |
| `-w`, `--workflow` | filter to a single workflow by exact name | -- |
| `--no-layout` | drop step positions and uuids (top/left/uuid): easier to read, still compiles | -- |
| `--raw` | the old internal dump (iris, resolved routes) instead of the authoring YAML | -- |

### `demo`

#### `demo prep`

| arg | help | meta |
| --- | --- | --- |
| `--pattern` | extra glob to purge (repeatable) | default: `[]` |

### `diagnose`

| arg | help | meta |
| --- | --- | --- |
| `yaml` | path to the playbook YAML | -- |
| `pb_execution` | workflow PK or task_id of the run | -- |
| `--json` |  | -- |

### `diff`

| arg | help | meta |
| --- | --- | --- |
| `input` | local YAML | -- |
| `-c`, `--collection` | live collection name (defaults to YAML's collection name) | -- |

### `doctor`

| arg | help | meta |
| --- | --- | --- |
| `connector` | connector name (use `find_connector` to discover) | -- |
| `--op` | filter to ops whose name contains this substring | -- |
| `--json` | emit the table as JSON on stdout | -- |

### `dump-step-params`

| arg | help | meta |
| --- | --- | --- |
| `--out` | output directory (default: docs/step_params) | default: `docs/step_params` |
| `--db` | reference DB path | default: `/Users/dylanspille/PycharmProjects/fsr-playbook-framework/data/fsr_reference.db` |

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
| `--dir` | search dir for *.test.yaml (default: examples/) | -- |
| `--keep` | leave deployed collections in place after each run | -- |
| `--no-cleanup` | skip the pre-pass purge of stale demo/test collections | -- |
| `--json` | emit machine-readable per-test results to stdout | -- |
| `--verbose` | show per-step run output for each test (default: summary only) | -- |

#### `e2e cleanup`

| arg | help | meta |
| --- | --- | --- |
| `patterns` | name glob(s); defaults to FSRPB Demo* / Compiler Demo* / *__fsrpb_probe__* | -- |

#### `e2e run`

| arg | help | meta |
| --- | --- | --- |
| `test` | path to <fixture>.test.yaml | -- |
| `--keep` | leave the deployed collection in place after the run | -- |

### `env`

| arg | help | meta |
| --- | --- | --- |
| `pb_execution` | workflow PK (integer) or task_id (UUID) | -- |
| `--task-id` | force UUID-as-task_id resolution (rarely needed; auto-detected) | -- |
| `--summary` | print a one-line-per-key index instead of full JSON | -- |

### `evals`

| arg | help | meta |
| --- | --- | --- |
| `--models` | comma-separated provider names. NOTE: only gold and echo are truly box-free. Every agentic_* provider runs a REAL tool loop, and those tools call a live appliance (connector healthcheck, record reads) -- so a slow or degraded box shows up as lower scores and reads as an agent regression. Trust `mode=tool_selection` fixtures (appliance-light, see `make tool-gate`); treat `mode=investigation` scores as suspect unless the box is known healthy. Set FSR_TIMEOUT to bound the appliance calls. DEFAULT: agentic_frank -- free, GLM 5.2 on the Fortilab gateway, and a real tool loop, so it is the only free provider that can score tool_selection. FREE, no LLM: gold, echo -- but these only generate YAML, so they score 0/0 on tool_selection fixtures; ask for them explicitly when you want the compiler path alone. Other free tool loop: agentic_lmstudio (needs LM Studio on :1234). PAID: anthropic, openai, agentic_anthropic, agentic_openai_api (= the production gpt-4.1-mini; use only when the question is about that model). | default: `agentic_frank` |
| `--repeat` | run the matrix N times and print a per-model consistency screen instead of one matrix; a model is 'consistent' only if every fixture passes every repeat | default: `1` |
| `--tasks` | comma-separated task names; default = all | -- |
| `--live` | enable live Runs gate (resolve + dry-run) against the live FSR | -- |
| `--offline` | bind the agent's tools to the simulated client and strip the FSR_* credentials (= EVAL_OFFLINE=1). A degrading box otherwise scores as agent regression. | -- |
| `--bundle` | serve the offline record surface (/api/3, /api/query) from a fixture bundle instead of empty-but-ok (= EVAL_FIXTURE_BUNDLE). `soc_invest_surface` covers the invest_* fixtures; without it they triage a box holding no records. | -- |
| `--json` | emit the full matrix as JSON on stdout | -- |
| `--save` | archive matrix.json + report.md under data/eval_runs/<run_id>/ (auto-implied by --baseline) | -- |
| `--replay` | re-score an archived run with today's graders -- no model call, sub-second. Grading and generation are separate problems and only one needs a model. Use this to iterate on gates/ir_assertions; it CANNOT measure a prompt or tool-description change, because the agent's behavior is frozen at capture time. | -- |
| `--baseline` | prior run id to diff against; prints a per-cell delta table after the matrix | -- |
| `--list-runs` | list archived eval run ids and exit | -- |

### `explain`

| arg | help | meta |
| --- | --- | --- |
| `kind` |  | choices: `connector`, `step`, `handler`, `filter`, `module`, `recipe` |
| `name` |  | -- |

### `find`

| arg | help | meta |
| --- | --- | --- |
| `--step-type` | WorkflowStepType name (Connectors, ManualInput, Decision, …) | -- |
| `--connector` | connector name in any step's arguments.connector | -- |
| `--operation` | operation name in any step's arguments.operation | -- |
| `--calls` | playbooks that workflow_reference this name/uuid | -- |
| `--text` | any substring in any step's serialized arguments | -- |
| `--collection` | restrict to one collection (name) | -- |
| `--active` | only isActive=true | -- |
| `--triggered-by` | playbooks listening to this record-event (requires --module) | choices: `on-create`, `on-update`, `on-delete`, `pre-create`, `pre-update`, `pre-delete` |
| `--module` | module name (alerts, incidents, …) -- used with --triggered-by | -- |
| `--writes-to` | playbooks with create_record / update_record / approval against this module | -- |
| `--json` | emit JSON | -- |

### `find-step-examples`

| arg | help | meta |
| --- | --- | --- |
| `step_type` | step_types.name e.g. ManualInput, Decision, SetVariable | -- |
| `--contains` | optional substring that must appear in arguments_json (e.g. 'ipv4', 'formType":"lookup', 'default":true') | -- |
| `--limit` |  | default: `20` |
| `--json` |  | -- |

### `generate-recipe`

| arg | help | meta |
| --- | --- | --- |
| `--kind` | recipe kind | choices: `threat-feed`, `data-ingest` · required |
| `--info-json` | path to connector info.json | required |
| `--config-uuid` | FSR connector instance UUID; user replaces post-import if omitted | default: `REPLACE_WITH_CONFIG_UUID` |
| `-o`, `--output` | write FSR JSON to this path; otherwise stdout | -- |
| `--target-module` | (data-ingest) module IRI segment, e.g. 'alerts' or 'incidents' (default: alerts) | default: `alerts` |
| `--fetch-op` | (data-ingest) override fetch op name when auto-detect picks the wrong one | -- |
| `--dedup-field` | (data-ingest) vendor field used as sourceId for dedup (auto-detected from op output_schema) | -- |
| `--severity-field` | (data-ingest) field on each item carrying the vendor severity enum | default: `severity` |
| `--status-field` | (data-ingest) field on each item carrying the vendor status enum | default: `status` |
| `--severity-enum` | (data-ingest) comma-separated vendor severity values, e.g. 'CRITICAL,HIGH,MEDIUM,LOW' | -- |
| `--status-enum` | (data-ingest) comma-separated vendor status values, e.g. 'Open,Investigating,Closed' | -- |
| `--skip-prechecks` | skip live-FSR prechecks (connector installed, picklist values resolvable). Use offline. | -- |

### `graph`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `--json` | emit the graphs as JSON | -- |

### `health`

| arg | help | meta |
| --- | --- | --- |
| `connector` | connector name (omit to list all configured); single-name always probes | -- |
| `--version` | connector version (default: looked up live) | -- |
| `--config` | config UUID to test (when a connector has multiple configurations) | -- |
| `--probe` | when listing all, also healthcheck each one (one extra round-trip per connector) | -- |
| `--json` | emit JSON instead of grouped tables | -- |

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
| `--category` | filter by category (partial match) | -- |

#### `hub search`

| arg | help | meta |
| --- | --- | --- |
| `query` | search term | -- |

#### `hub show`

| arg | help | meta |
| --- | --- | --- |
| `name` | connector name (e.g. abuseipdb) | -- |

### `inputs`

#### `inputs list`

| arg | help | meta |
| --- | --- | --- |
| `--json` |  | -- |

#### `inputs respond`

| arg | help | meta |
| --- | --- | --- |
| `id` | manual-wf-input pk (from `inputs list`) | -- |
| `--option` | button label to pick (default: primary option) | -- |
| `--vars` | JSON dict of inputVariable values | -- |
| `--task-id` | task_id from the original trigger (helps resolve wf pk) | -- |
| `--json` |  | -- |

#### `inputs show`

| arg | help | meta |
| --- | --- | --- |
| `id` | manual-wf-input pk | -- |
| `--json` |  | -- |

### `inspect`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | -- |
| `--json` | JSON output (default) | -- |
| `--table` | human-readable two-table layout instead of JSON | -- |
| `--task` | overlay execution status from this task_id (historical-steps); marks each route TRAVERSED if both endpoints executed in the run | -- |

### `inventory`

#### `inventory api-examples`

| arg | help | meta |
| --- | --- | --- |
| `-q` | filter substring | -- |
| `--limit` |  | default: `50` |

#### `inventory connectors`

| arg | help | meta |
| --- | --- | --- |
| `-q` | filter substring | -- |
| `--limit` |  | default: `50` |

#### `inventory search`

| arg | help | meta |
| --- | --- | --- |
| `q` | search needle | -- |
| `--limit` | per-table result cap | default: `5` |

#### `inventory stale`

| arg | help | meta |
| --- | --- | --- |
| `--days` |  | default: `7` |

#### `inventory summary`

### `jinja`

| arg | help | meta |
| --- | --- | --- |
| `template` | Jinja template string, e.g. '{{ vars.steps.Get_org.records[0].id }}' | -- |
| `--from-pb-execution` | seed context from a past run (workflow PK or task_id) | -- |
| `--input` | JSON file path or inline JSON to merge into context | -- |
| `--bind` | KEY=VALUE override (repeatable; dotted keys nest under vars). Value is JSON-parsed if possible, else plain string | default: `[]` |

### `jinja-filter`

| arg | help | meta |
| --- | --- | --- |
| `query` | filter name or substring | -- |
| `--examples` | show real corpus expressions instead of hits | -- |
| `--limit` |  | default: `8` |

### `matrix`

| arg | help | meta |
| --- | --- | --- |
| `--lane` | screen (DEFAULT): agentic_frank/GLM-5.2, offline, soc_invest_surface bundle -- free and box-free, run it on every change. confirm: agentic_openai_api against a live appliance -- costs credits, needs --live-ok, and exists to answer one question at milestones: does the free lane still predict the paid one? attribute: the paid model on the FREE substrate -- costs credits but touches no box, and exists so a screen-vs-confirm disagreement can be pinned on the model or the substrate instead of guessed at | choices: `screen`, `confirm`, `attribute` · default: `screen` |
| `--mode` | corpus slice, taken from each fixture's own `mode` field: all (default), routing, invest, enhance, repair, refuse, authoring -- plus `gate`, the five name-pinned fixtures `make tool-gate` diffs against its baseline | default: `all` |
| `--tasks` | explicit comma-separated task names; overrides --mode | -- |
| `--repeat` | run N times and print the consistency screen; a single run lies (auto-memory: model screening doctrine). Milestones only -- it is N times the wall clock and, on the confirm lane, N times the bill. | default: `1` |
| `--baseline` | prior run id to diff against. The differ refuses when the lanes/substrates/scorer disagree. | -- |
| `--live-ok` | deliberate opt-in required by any lane that spends money or reaches a box | -- |
| `--json` | emit the full matrix as JSON on stdout | -- |

### `mcp`

### `migrate`

Migrate playbook YAMLs to the current friendly authoring surface.

Text-based (preserves comments + formatting). Idempotent: running twice
produces no changes the second time. Point at a file or directory:

    fsrpb migrate examples/
    fsrpb migrate examples/demo_alert_on_create.yaml --dry-run

Transforms (applied in order, all are safe on already-migrated files):

1.  ``type: insert_record`` → ``type: create_record``
    The legacy alias was removed; it now hard-errors.

2.  ``arguments:`` wrapper removed -- children hoisted to step level.
    Phase G dropped the ``arguments:`` wrapper on every step type.

3.  ``collection:`` on ``update_record`` → ``record:``
    ``collection:`` on update was the record IRI but collided with
    create_record's module-IRI ``collection`` (the #1 record-CRUD footgun).

3b. ``collection: /api/3/<m>`` on ``create_record`` → ``module: <m>``
    ``collection: /api/3/upsert/<m>`` → ``module: <m>`` + ``is_upsert: true``.
    Non-``/api/3/`` collections pass through (canonical escape hatch).

4.  ``resource:`` on ``create_record``/``update_record`` → ``fields:``
    ``fields:`` is the friendly alias; ``resource:`` was an FSR API term.

5.  ``type: CyopsUtilices`` → ``type: utilities`` (if present).
    The editor's raw canonical is never the friendly surface.

6.  Wire-internal default fields stripped (``step_variables: []``,
    ``fieldOperation: []``, ``tagsOperation: Overwrite``, ``__recommend: []``,
    ``_showJson: false``, default ``owner_detail``/``email_notification``).

7.  ``query:`` on ``find_record`` → ``filters:``/``limit:``/``logic:``.
    Default ``logic: AND`` / ``limit: 30`` and ``__selectFields`` are skipped.

8.  Wire ``owner_detail:`` on ``manual_input`` → friendly ``assign_to:``
    (``assignedToTeam`` → ``team:``, ``assignedToPerson`` → ``person:``).
    Wire ``email_notification:`` → friendly ``email:``
    (``smtpParameters[0]`` → ``recipients``/``subject``/``body``/``from``).
    Defaults (``isAssigned: false`` / ``enabled: false``) already stripped
    by step 6; only real assignment/email data is converted here.

| arg | help | meta |
| --- | --- | --- |
| `path` | file or directory to migrate | -- |
| `--dry-run` | show what would change without writing | -- |

### `picklist`

#### `picklist for-field`

| arg | help | meta |
| --- | --- | --- |
| `module` |  | -- |
| `field` |  | -- |

#### `picklist list`

#### `picklist resolve`

| arg | help | meta |
| --- | --- | --- |
| `value` |  | -- |
| `--name` | picklist listName.name (overrides discovery) | -- |
| `--module` |  | -- |
| `--field` |  | -- |

#### `picklist show`

| arg | help | meta |
| --- | --- | --- |
| `name` |  | -- |

### `probe`

Run one or more reference-store probes against the live FSR instance.

Each probe fetches a slice of FSR's metadata and writes it into
data/fsr_reference.db.  All probes are idempotent -- re-running them
updates the store in place without destroying existing data.

Examples:
  fsrpb probe connectors            # refresh connector / op / param data
  fsrpb probe jinja jinja-backend   # refresh both Jinja probes
  fsrpb probe --all                 # run every probe in sequence
  fsrpb probe --list                # show available probes

| arg | help | meta |
| --- | --- | --- |
| `probes` | probe name(s) to run (omit with --all) | -- |
| `--all` | run all probes in order | -- |
| `--list` | list available probes and exit | -- |
| `--live` | pass through to probes that support a live-FSR mode (currently: playbook-steps) | -- |
| `--conditional-refetch` | opt-in Tier-2 freshness: the wired probes fetch via conditional_refetch (TTL + If-None-Match) and only rewrite changed collections. Default off = always re-pull. Live-validate ETags on a box before relying on this. | -- |

### `provision`

Teach the reference store about a single connector.

`fsrpb refresh` rebuilds the whole catalog from every probe, which is far too
big a hammer when the only thing that changed is "I just wrote a new connector"
or "I just installed one on the box". Until the catalog knows it, the compiler
rejects every step that references it:

    [unknown_connector] playbooks[0].steps[1].arguments.connector:
        unknown connector: 'fortinet-fortisiemv2'
        -> did you mean 'fortinet-fortisiem'?

...and `fsrpb validate` / `push` refuse to run. This module warms exactly one
connector, from either of the two places a connector can exist:

  * **local** -- a connector source directory (or its ``info.json``). This is
    the case the compiler cannot recover from on its own: a connector being
    developed has never been installed anywhere, so no live probe can see it.

  * **instance** -- installed on the configured FortiSOAR. Pulls the same
    operation/parameter definitions the appliance reports.

The compiler reads SQLite directly (``resolver/catalog.py``), so an upsert here
takes effect on the very next compile -- there is no JSON snapshot to
regenerate.

Usage:
    fsrpb provision ~/src/fortinet-fortisiemv2      # from local source
    fsrpb provision --from-instance fortinet-fortisiemv2
    fsrpb provision --check fortinet-fortisiemv2    # what does the store know?

| arg | help | meta |
| --- | --- | --- |
| `path` | connector source directory, or a path to its info.json | -- |
| `--from-instance` | pull NAME's definition from the configured FortiSOAR instead | -- |
| `--check` | report what the catalog knows about NAME and exit | -- |
| `--db` | reference-store path (default: the configured store) | -- |
| `--force` | re-provision even when the same version is already present | -- |
| `--dry-run` | report what would be written without writing | -- |
| `--json` | machine-readable output | -- |

### `pull`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name or UUID | -- |
| `-o`, `--output` |  | -- |

### `pull-collection`

| arg | help | meta |
| --- | --- | --- |
| `collection` | collection name or UUID | -- |
| `-o`, `--output` |  | -- |

### `purge`

| arg | help | meta |
| --- | --- | --- |
| `target` | workflow name(s) or UUID(s) | -- |
| `--dry-run` | show counts without deleting | -- |

### `push`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `--url` | FortiSOAR base URL (overrides FSR_BASE_URL / .env) | -- |
| `--user` | FortiSOAR username (overrides FSR_USERNAME / .env) | -- |
| `--password` | FortiSOAR password (overrides FSR_PASSWORD / .env) | -- |
| `--mode` | safe (default): preflight + restore recycled rows, then PUT or POST. No hard-delete on this path. create: POST only (409 on UUID/name collision). update: PUT in-place (preserves unmodeled fields). replace: hard-purge then POST -- gated on FSR_ALLOW_HARD_DELETE; use only for recovery. | choices: `safe`, `replace`, `create`, `update`, `upsert` · default: `safe` |
| `--json` | print response JSON to stdout | -- |
| `--no-activate` | push workflows exactly as authored (keep an isActive: false recipe inactive). Default: push activates the workflows it writes -- an inactive push looks like a successful deploy until the first run dies with CS-WF-1 (referenced playbook non-existent or Inactive). | -- |
| `--force-large-purge` | replace mode: bypass the >50-workflow / >500-step safety cap. Required only when an intentional purge exceeds the cap. | -- |
| `--allow-foreign-loss` | safe mode: proceed even if the target collection contains workflows not in this YAML. Bulkupsert will cascade-remove them. Use only when you intentionally want to drop them. | -- |
| `--confirm-overwrite` | replace mode: proceed even when the target collection contains out-of-band workflows (added via the FSR UI after your last pull). Without this flag, replace mode refuses to purge when drift is detected, preventing a silent clobber of UI edits. | -- |
| `--skip-connector-check` | skip the live connector-installation preflight (warnings only by default). Use when pushing to a box that will have connectors installed later. | -- |

### `recipe`

#### `recipe find`

| arg | help | meta |
| --- | --- | --- |
| `query` |  | default: `` |
| `--kind` | threat_feed \| data_ingest | -- |
| `--limit` |  | default: `10` |
| `--yaml` | print just the yaml_template if exactly one hit | -- |

#### `recipe show`

| arg | help | meta |
| --- | --- | --- |
| `name` |  | -- |
| `--yaml` | print yaml_template only | -- |

### `recover-deleted-playbooks`

| arg | help | meta |
| --- | --- | --- |
| `--since` | Start date (YYYY-MM-DD or ISO-8601) | required |
| `--until` | End date (default: now) | -- |
| `--limit` | Max audit entries to scan (default 500) | default: `500` |
| `--apply` | Actually restore. Without this flag, dry-run only. | -- |
| `--overwrite` | Restore even if a live workflow with the same name exists with different content. Default: skip diffs to avoid clobbering edits you've made since the deletion. | -- |
| `--show-diffs` | Print step-level diff for every workflow flagged as 'live differs' (additions / removals vs. the audit snapshot). Helps decide whether to --overwrite. | -- |
| `--max` | Cap the number of restores actually performed (0 = no cap). Useful for smoke-testing: --max 3. | -- |
| `--only-name` | Only restore workflows whose name matches this string (repeatable). Substring match, case-insensitive. E.g. --only-name 'Get Users'. | default: `[]` |
| `--include-all-sources` | Do not filter by source IP; consider every Delete event | -- |
| `--only-source` | Restrict to deletes from this source IP (e.g. 10.100.4.143 for the 2026-05-08 probe rig) | -- |
| `--json-out` | Write the restore plan to this JSON file | -- |
| `--refresh` | Bypass the 48-hour disk cache and re-fetch live workflows + per-record hydration from FSR. | -- |
| `-v`, `--verbose` |  | -- |
| `--reorganize` | Post-pass: move workflows from per-workflow '<wfname>-Restored' (or '<wfname>') collections into their original parent collection (read from the workflow's audited `collection` IRI), then delete the empty junk collections. Dry-run unless combined with --apply. | -- |

### `refresh`

| arg | help | meta |
| --- | --- | --- |
| `--conditional-refetch` | opt-in Tier-2 freshness: probes fetch via conditional_refetch (TTL + If-None-Match) and only rewrite changed collections. Default off = always re-pull. Live-validate ETags on a box before relying on this. | -- |

### `resolve`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `--json` | emit full result as JSON on stdout | -- |

### `roundtrip`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |

### `routes`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | -- |
| `--json` |  | -- |

### `run-op`

| arg | help | meta |
| --- | --- | --- |
| `connector` |  | -- |
| `operation` |  | -- |
| `--params` | JSON string or path to a JSON file | -- |
| `--version` | override connector version (default: store) | -- |
| `--config` | connector config name | -- |

### `run-playbook`

| arg | help | meta |
| --- | --- | --- |
| `playbook` | workflow name, UUID, or 'Collection:Name' | -- |
| `--collection` | restrict name lookup to this collection (disambiguates duplicates) | -- |
| `--input` | JSON string or path to a JSON file (designer-run mode) | -- |
| `--record` | fire as record-context Execute (cybersponse.action triggers); e.g. alerts:db7afbf7-... | -- |
| `--follow` | poll task status until terminal (finished/failed/terminated/skipped) | -- |
| `--follow-interval` | seconds between polls (default 3) | default: `3` |
| `--follow-timeout` | give up after N seconds (default 300) | default: `300` |
| `--mock` | trigger with useMockOutput=true / globalMock=true so each step returns its arguments.mock_result instead of executing live; useful for validating playbook plumbing when the target connector is not yet configured. Default: off. | -- |

### `runs`

| arg | help | meta |
| --- | --- | --- |
| `--all` | include successful runs (default: failed/errored only) | -- |
| `--status` | explicit status filter (comma-separated, e.g. 'failed,finished_with_error,terminated') | -- |
| `--limit` |  | default: `20` |
| `--json` |  | -- |

### `search`

| arg | help | meta |
| --- | --- | --- |
| `query` |  | -- |
| `--limit` |  | default: `10` |
| `--json` |  | -- |

### `status`

| arg | help | meta |
| --- | --- | --- |
| `-n`, `--limit` |  | default: `10` |

### `steps`

| arg | help | meta |
| --- | --- | --- |
| `task_id` | task_id from `run-playbook` output | -- |
| `-v`, `--verbose` | dump each step's args/input/result JSON | -- |
| `--json` |  | -- |

### `triggers`

| arg | help | meta |
| --- | --- | --- |
| `module` | module name (alerts, incidents, indicators, …); omit for all | -- |
| `--inactive` | include unpublished playbooks (isActive=false) | -- |
| `--json` | emit raw JSON | -- |

### `validate`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `--json` | emit errors as JSON on stdout | -- |

### `validate-ingestion`

| arg | help | meta |
| --- | --- | --- |
| `input` | path to FSR workflow_collections JSON | -- |
| `--rulesets` | comma list: data-ingest, feed-ingest, or 'auto' (detect from tags+steps). Default: auto | default: `auto` |
| `--json` | emit issues as JSON on stdout | -- |
| `--info-json` | connector info.json path (auto-detected next to or above the playbook file if omitted) | -- |

### `verify`

| arg | help | meta |
| --- | --- | --- |
| `input` |  | -- |
| `--playbook` | which playbook to verify (default: first in collection) | -- |
| `--live-probe` | probe safe ops via run_op for true output shapes | -- |
| `--verbose` | include full typed_walk + per-step shapes in evidence | -- |
| `--json` | emit raw result as JSON on stdout | -- |
