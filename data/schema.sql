-- fsr_reference.db schema
-- One source of truth for everything an agent or compiler needs to author a
-- FortiSOAR playbook. Everything queryable; no JSON grepping in the agent path.
-- Probes drop+recreate their owned tables on each run, then write _probe_runs.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------- Connectors ----------
CREATE TABLE IF NOT EXISTS connectors (
    name              TEXT PRIMARY KEY,
    version           TEXT NOT NULL,
    label             TEXT,
    category          TEXT,                  -- joined comma-separated list
    description       TEXT,
    publisher         TEXT,
    contributor       TEXT,
    active            INTEGER DEFAULT 1,     -- live: connector is enabled on instance
    system            INTEGER DEFAULT 0,     -- live: shipped with FSR (vs. installed)
    cs_approved       INTEGER DEFAULT 0,
    cs_compatible     INTEGER DEFAULT 0,
    ingestion_supported INTEGER DEFAULT 0,
    tags_json         TEXT,                  -- JSON array
    config_schema_json TEXT,                 -- connection-level config fields
    source            TEXT NOT NULL,         -- 'live_api_get' | 'rpm_info_json' | ...
    source_path       TEXT,                  -- when local: path to info.json
    info_json         TEXT,                  -- full blob, fallback / debug only (icons stripped)
    source_code       TEXT,                  -- connector.py + operations.py concatenated, populated lazily by mcp get_connector_source
    rpm_fingerprint   TEXT                   -- "<rpm_full_name>:<size_bytes>" — set by repo_rpm tier; lets re-runs skip already-ingested connectors
);

CREATE TABLE IF NOT EXISTS operations (
    connector_name              TEXT NOT NULL REFERENCES connectors(name) ON DELETE CASCADE,
    op_name                     TEXT NOT NULL,    -- the "operation" key (machine name)
    title                       TEXT,
    annotation                  TEXT,
    category                    TEXT,
    description                 TEXT,
    visible                     INTEGER DEFAULT 1,
    enabled                     INTEGER DEFAULT 1,
    output_schema_json          TEXT,
    conditional_output_schema_json TEXT,
    PRIMARY KEY (connector_name, op_name)
);

CREATE INDEX IF NOT EXISTS idx_ops_op ON operations(op_name);

-- Per-op safety classification. Populated by probes.probe_op_safety
-- using a layered classifier (HTTP method, name prefix, category bias).
-- `verify_playbook` reads this to decide which connector_ops are safe
-- to live-probe with `run_op` for output-shape synthesis.
CREATE TABLE IF NOT EXISTS op_safety (
    connector_name      TEXT NOT NULL,
    op_name             TEXT NOT NULL,
    safety              TEXT NOT NULL CHECK (safety IN ('safe','unsafe','unknown')),
    reason              TEXT,             -- one-line human explanation
    evidence            TEXT,             -- JSON: {method, matched_pattern, source}
    classifier_version  INTEGER NOT NULL DEFAULT 1,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (connector_name, op_name),
    FOREIGN KEY (connector_name, op_name)
        REFERENCES operations(connector_name, op_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_op_safety_safety ON op_safety(safety);

-- A param row models either a top-level param (parent_param_name IS NULL,
-- condition_value IS NULL) or a conditional sub-param that appears only when
-- its parent's value matches `condition_value` (per the connector's onchange
-- block). The (connector, op, parent, condition, name) tuple is unique.
CREATE TABLE IF NOT EXISTS operation_params (
    connector_name      TEXT NOT NULL,
    op_name             TEXT NOT NULL,
    parent_param_name   TEXT,                 -- NULL for top-level params
    condition_value     TEXT,                 -- the parent value that triggers this sub-param; NULL at top level
    param_name          TEXT NOT NULL,
    title               TEXT,
    type                TEXT,                 -- text|password|integer|select|checkbox|json|...
    required            INTEGER DEFAULT 0,
    default_value       TEXT,
    options_json        TEXT,                 -- JSON array of picklist options
    tooltip             TEXT,
    placeholder         TEXT,
    description         TEXT,
    visible             INTEGER DEFAULT 1,
    editable            INTEGER DEFAULT 1,
    ord                 INTEGER DEFAULT 0,
    -- Tier 2 static-type-validation columns. Populated by
    -- probes.probe_param_types. `observed_type` is the resolved type
    -- (int/float/bool/str/ipv4/url/iso8601/json_object/picklist/...);
    -- `coerces_from` is a comma-separated list of input forms the
    -- runtime accepts (e.g. "str,int"). Both NULL until probed.
    observed_type       TEXT,
    coerces_from        TEXT,
    PRIMARY KEY (connector_name, op_name, parent_param_name, condition_value, param_name),
    FOREIGN KEY (connector_name, op_name)
        REFERENCES operations(connector_name, op_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_op_params_op ON operation_params(connector_name, op_name);
CREATE INDEX IF NOT EXISTS idx_op_params_observed_type ON operation_params(observed_type);

CREATE TABLE IF NOT EXISTS operation_examples (
    connector_name  TEXT NOT NULL,
    op_name         TEXT NOT NULL,
    source          TEXT NOT NULL,       -- 'pb_examples' | 'connector_lifecycle' | 'docs'
    example_kind    TEXT NOT NULL,       -- 'yaml' | 'json' | 'python'
    snippet         TEXT NOT NULL,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_op_examples ON operation_examples(connector_name, op_name);

-- Warmup telemetry. One row per `warmup` run (connector operations.py), so a
-- slow catalog warm can be analyzed after the fact via query_store. Also
-- created defensively at runtime by `_record_warmup_run` so it exists on
-- reference DBs that predate this table.
CREATE TABLE IF NOT EXISTS warmup_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,          -- UTC ISO8601 of run completion
    forced          INTEGER NOT NULL DEFAULT 0,
    total_s         REAL,
    list_fetch_s    REAL,
    detail_loop_s   REAL,
    detail_calls    INTEGER,
    db_write_s      REAL,
    connectors      INTEGER,
    operations      INTEGER,
    operation_params INTEGER,
    op_safety       INTEGER,
    slowest_details TEXT,                   -- JSON: [{connector, s}, ...]
    timings_json    TEXT                    -- full timings dict, JSON
);

-- Tier 2.2 ledger. Each row is one (param, mutation) attempt against
-- the live FSR. Promotion to operation_params.observed_type requires
-- ≥3 corroborating rows (see probes.probe_param_types.promote). Kept
-- separate from operation_params so widget-only passes don't clobber
-- live-probe evidence and a re-run is incremental.
CREATE TABLE IF NOT EXISTS param_type_probes (
    connector_name      TEXT NOT NULL,
    op_name             TEXT NOT NULL,
    param_name          TEXT NOT NULL,
    mutation_input      TEXT NOT NULL,    -- repr() of the mutated value
    mutation_kind       TEXT NOT NULL,    -- 'string'|'int'|'list'|'dict'|'bool'|'enum_invalid'
    response_status     TEXT NOT NULL,    -- 'mutation_err'|'baseline_ok'|'baseline_fail'|'transport_err'
    error_message       TEXT,             -- raw FSR message, first 800 chars
    inferred_type       TEXT,             -- classify_error() result (NULL on no match)
    inferred_coerces    TEXT,
    classifier_version  INTEGER NOT NULL DEFAULT 1,
    probed_at           TEXT NOT NULL,
    PRIMARY KEY (connector_name, op_name, param_name, mutation_input),
    FOREIGN KEY (connector_name, op_name)
        REFERENCES operations(connector_name, op_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_param_probes_op
    ON param_type_probes(connector_name, op_name);
CREATE INDEX IF NOT EXISTS idx_param_probes_inferred
    ON param_type_probes(inferred_type);

-- ---------- Step types ----------
CREATE TABLE IF NOT EXISTS step_types (
    uuid             TEXT PRIMARY KEY,
    name             TEXT UNIQUE NOT NULL,    -- 'connector', 'set_variables', etc.
    label            TEXT,
    category         TEXT,
    description      TEXT,
    args_schema_json TEXT,                    -- JSON schema for the step's arguments
    occurrences      INTEGER DEFAULT 0,        -- count seen across pb_examples
    common_pitfalls  TEXT
);

-- Canonical step-handler signatures from workflow.eval.FUNCTION_MAP on the
-- live FSR appliance. Each step_type's args_schema_json.script ends in
-- /wf/workflow/tasks/<handler_name>, e.g. Decision -> 'cond',
-- SetVariable -> 'set_multiple', Connector -> 'connector'. This table
-- gives the canonical Python signature for each handler — the source of
-- truth for what `arguments` a step must provide.
CREATE TABLE IF NOT EXISTS step_handlers (
    name             TEXT PRIMARY KEY,         -- FUNCTION_MAP key, e.g. 'cond'
    signature        TEXT,                     -- inspect.signature() str
    parameters_json  TEXT,                     -- JSON [{name,kind,default,annotation}]
    qualname         TEXT,
    module           TEXT,
    source_file      TEXT,
    doc              TEXT
);

CREATE TABLE IF NOT EXISTS step_examples (
    step_type_name TEXT NOT NULL REFERENCES step_types(name) ON DELETE CASCADE,
    from_playbook  TEXT,
    snippet_json   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_step_examples_type ON step_examples(step_type_name);

-- Full per-step corpus, ingested from FSR playbook JSON exports (SP bundles,
-- store/incoming drops, live FSR pulls). Unlike step_examples (which is a
-- 3-row sampling per type used for quick LLM context), this table holds
-- EVERY step from EVERY playbook we've seen — used to mine real-world
-- argument shapes when tightening linting/validation.
--
-- step_type_name is denormalized at ingest time by joining stepType (an IRI
-- ending in a step_types.uuid) against step_types. Rows where the step type
-- can't be resolved get step_type_name=NULL and step_type_uuid populated.
CREATE TABLE IF NOT EXISTS playbook_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,            -- 'sp_export' | 'incoming' | 'live_fsr'
    source_path     TEXT NOT NULL,            -- file path or live-FSR base url
    collection      TEXT,
    playbook_name   TEXT,
    playbook_uuid   TEXT,
    step_uuid       TEXT,
    step_name       TEXT,
    step_type_uuid  TEXT,
    step_type_name  TEXT,                     -- resolved name e.g. 'ManualInput'
    arguments_json  TEXT NOT NULL,            -- raw step.arguments dict
    ingested_at     TEXT NOT NULL,
    UNIQUE (source, source_path, step_uuid)
);
CREATE INDEX IF NOT EXISTS idx_pbs_type ON playbook_steps(step_type_name);
CREATE INDEX IF NOT EXISTS idx_pbs_pb   ON playbook_steps(playbook_uuid);
CREATE INDEX IF NOT EXISTS idx_pbs_src  ON playbook_steps(source);

-- ---------- Modules ----------
CREATE TABLE IF NOT EXISTS modules (
    name        TEXT PRIMARY KEY,             -- 'threat_intel_feeds'
    label       TEXT,
    plural      TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS module_fields (
    module_name      TEXT NOT NULL REFERENCES modules(name) ON DELETE CASCADE,
    field_name       TEXT NOT NULL,
    title            TEXT,
    type             TEXT,
    required         INTEGER DEFAULT 0,
    picklist_options TEXT,
    tooltip          TEXT,
    picklist_name    TEXT,                -- listName of the bound picklist (e.g. 'AlertStatus'); NULL for non-picklist fields
    PRIMARY KEY (module_name, field_name)
);

-- Picklist items keyed by (listName, itemValue). Lets the resolver
-- map a friendly token in a record-write payload to the canonical
-- `/api/3/picklists/<uuid>` IRI without a live API call.
CREATE TABLE IF NOT EXISTS picklists (
    list_name   TEXT NOT NULL,            -- 'AlertStatus'
    item_value  TEXT NOT NULL,            -- 'Closed'
    item_iri    TEXT NOT NULL,            -- '/api/3/picklists/<uuid>'
    PRIMARY KEY (list_name, item_value)
);
CREATE INDEX IF NOT EXISTS idx_picklists_list ON picklists(list_name);

-- ---------- Jinja ----------
-- Filter type discipline matters when piping: a filter that returns a
-- generator (jinja2's `groupby`, `permutations`, `combinations`) will break
-- a downstream filter that expects a list unless wrapped in `| list`.
-- We track three views of the type per filter:
--   input_type_hint        — what the filter is *intended* to consume
--                             (e.g. "string", "list", "dict", "any")
--   output_type_declared   — what the widget constants / docs claim it returns
--   output_type_observed   — what `type_debug` reports when we render it live
--                             (the only one with status=tested_pass)
-- parameters_json holds the structured parameter list from widget constants
-- so agents can resolve arg names/types/required without re-parsing.
CREATE TABLE IF NOT EXISTS jinja_macros (
    name                  TEXT PRIMARY KEY,
    signature             TEXT,
    returns               TEXT,                 -- legacy single-value column; kept for back-compat
    description           TEXT,
    example               TEXT,
    parameters_json       TEXT,                 -- JSON [{name,type,description,required,default}, ...]
    input_type_hint       TEXT,
    output_type_declared  TEXT,
    output_type_observed  TEXT,
    aliases_csv           TEXT,                 -- e.g. count → length, e → escape
    -- Backend introspection (see scripts/dump_jinja_filters.py):
    qualname              TEXT,                 -- e.g. 'do_groupby'
    module                TEXT,                 -- e.g. 'jinja2.filters'
    source_file           TEXT                  -- absolute path on FSR box
);

-- Jinja globals are callables invoked as `name(args)` (no pipe), e.g.
-- `{{ arrow.get('2024-01-01') }}` or `{{ range(10) }}`.
CREATE TABLE IF NOT EXISTS jinja_globals (
    name              TEXT PRIMARY KEY,
    qualname          TEXT,
    module            TEXT,
    source_file       TEXT,
    signature         TEXT,
    parameters_json   TEXT,
    description       TEXT,             -- docstring
    output_type_observed TEXT
);

-- Jinja tests are invoked as `value is testname(args)`, e.g. `x is defined`.
CREATE TABLE IF NOT EXISTS jinja_tests (
    name              TEXT PRIMARY KEY,
    qualname          TEXT,
    module            TEXT,
    source_file       TEXT,
    signature         TEXT,
    parameters_json   TEXT,
    description       TEXT
);

CREATE TABLE IF NOT EXISTS jinja_context_vars (
    scope       TEXT NOT NULL,                -- 'vars', 'vars.steps', 'vars.input', ...
    var_name    TEXT NOT NULL,
    type        TEXT,
    description TEXT,
    PRIMARY KEY (scope, var_name)
);

-- ---------- Recipes / patterns ----------
CREATE TABLE IF NOT EXISTS recipes (
    name            TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,            -- 'feed_bundle' | 'upsert' | 'paged_loop' | ...
    when_to_use     TEXT,
    yaml_template   TEXT NOT NULL,
    source_playbook TEXT
);

-- ---------- FortiSOAR API endpoints ----------
-- Catalog of every reachable FortiSOAR HTTP endpoint we know about. Same
-- trust model as everything else: rows here are `seen` until exercised live.
-- Verifications kind: 'api_endpoint' (key = '{METHOD} {path_pattern}'),
--                     'api_endpoint_param' (key = '{METHOD} {path_pattern}#{param_name}').
CREATE TABLE IF NOT EXISTS api_endpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path_pattern    TEXT NOT NULL,           -- '/api/3/connectors/{uuid}'
    http_method     TEXT NOT NULL,           -- GET | POST | PUT | PATCH | DELETE | OPTIONS
    service         TEXT NOT NULL,           -- php | java_gateway | wf | rule | integration | auth | saml | postman
    controller      TEXT,                    -- e.g. 'app_gateway_get_audit_operations'
    php_class       TEXT,                    -- backend class for traceability
    summary         TEXT,
    response_kind   TEXT,                    -- 'hydra_collection' | 'hydra_member' | 'json' | 'binary' | 'other'
    auth_required   INTEGER DEFAULT 1,
    source          TEXT NOT NULL,           -- 'fortisoar_api_md' | 'hydra_root' | 'insomnia' | 'manual'
    notes           TEXT,
    UNIQUE (path_pattern, http_method)
);
CREATE INDEX IF NOT EXISTS idx_api_endpoints_method ON api_endpoints(http_method);
CREATE INDEX IF NOT EXISTS idx_api_endpoints_service ON api_endpoints(service);

CREATE TABLE IF NOT EXISTS api_endpoint_params (
    endpoint_id     INTEGER NOT NULL REFERENCES api_endpoints(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    location        TEXT NOT NULL,           -- 'path' | 'query' | 'body' | 'header'
    type            TEXT,                    -- 'string' | 'integer' | 'uuid' | 'object' | 'array' | ...
    required        INTEGER DEFAULT 0,
    default_value   TEXT,
    enum_options    TEXT,                    -- JSON array of allowed values when applicable
    description     TEXT,
    example         TEXT,
    PRIMARY KEY (endpoint_id, name, location)
);

-- Sample request/response payloads for an endpoint (filled by the live probe
-- when `tested_pass`, by the doc-parser when `seen`).
CREATE TABLE IF NOT EXISTS api_endpoint_examples (
    endpoint_id   INTEGER NOT NULL REFERENCES api_endpoints(id) ON DELETE CASCADE,
    direction     TEXT NOT NULL,             -- 'request' | 'response'
    status_code   INTEGER,                    -- response only
    payload       TEXT NOT NULL,             -- JSON or curl-equivalent body
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_examples ON api_endpoint_examples(endpoint_id);

-- ---------- Playbook inventory (pb_examples) ----------
CREATE TABLE IF NOT EXISTS playbooks_seen (
    collection           TEXT NOT NULL,
    workflow             TEXT NOT NULL,
    file                 TEXT NOT NULL,
    step_count           INTEGER,
    uses_connectors_csv  TEXT,
    PRIMARY KEY (collection, workflow, file)
);

-- ---------- Verification state ----------
-- Default for every entity in the store is UNTESTED — represented by the
-- absence of any row here. Probes never write rows that claim verification
-- they didn't perform. Verification is multi-method: a connector op might be
-- "seen" via /api/3/connectors (the deployed instance has it) but only
-- "tested_pass" once a compiled playbook actually executed it via
-- /api/integration/. Both rows are kept.
--
-- kind   — entity class. one of:
--          connector, operation, operation_param, step_type, module,
--          module_field, jinja_filter, jinja_macro, jinja_var, recipe
-- key    — canonical key for that kind, e.g.
--          'recorded-future-feed' (connector),
--          'recorded-future-feed:fetch_indicators' (operation),
--          'recorded-future-feed:fetch_indicators:api_key' (param),
--          'upper' (jinja_filter),
--          'threat_intel_feeds:source' (module_field).
-- method — how the verification was performed. one of:
--          live_api_get        — entity exists per a GET on a live FSR instance
--          live_api_render     — jinja template rendered successfully via API
--          live_op_exec        — connector op invoked successfully via /api/integration/
--          playbook_e2e        — used inside a playbook that ran end-to-end on live FSR
--          widget_constants    — appears in the jinja-editor widget constants file
--          schema_ts           — appears in fsr-schema.ts (step types)
--          schema_json         — appears in fortisoar/schema.json (modules)
--          rpm_info_json       — appears in a fortisoar-rpm-extracted info.json
--          manual              — human-asserted; lowest trust
-- status — tested_pass | tested_fail | seen
--          'seen' = catalogued from a source but not exercised. 'tested_pass'
--          requires the row to have been *exercised* (rendered, executed, etc).
CREATE TABLE IF NOT EXISTS verifications (
    kind    TEXT NOT NULL,
    key     TEXT NOT NULL,
    method  TEXT NOT NULL,
    status  TEXT NOT NULL CHECK (status IN ('tested_pass','tested_fail','seen')),
    ts      TEXT NOT NULL,
    notes   TEXT,
    PRIMARY KEY (kind, key, method)
);
CREATE INDEX IF NOT EXISTS idx_verif_kind_status ON verifications(kind, status);

-- Trust ladder. EVERYTHING IS UNTESTED BY DEFAULT (= no row in verifications).
-- Local sources (rpm_info_json, schema_json, schema_ts, widget_constants) only
-- ever produce status='seen' rows — they do NOT count as trusted. To become
-- trusted, an entity must be exercised on a live FSR instance via one of the
-- live_* methods or via playbook_e2e.
CREATE VIEW IF NOT EXISTS v_verification_state AS
WITH trusted_methods AS (
    SELECT 'live_api_get'    AS method UNION ALL
    SELECT 'live_api_render' UNION ALL
    SELECT 'live_op_exec'    UNION ALL
    SELECT 'playbook_e2e'
)
SELECT
    kind,
    key,
    MAX(CASE WHEN status = 'tested_pass'
                 AND method IN (SELECT method FROM trusted_methods)
             THEN 1 ELSE 0 END) AS is_trusted,
    MAX(CASE status WHEN 'tested_pass' THEN 3
                    WHEN 'tested_fail' THEN 2
                    WHEN 'seen'        THEN 1 END) AS rank,
    GROUP_CONCAT(method || ':' || status, ', ') AS methods_seen
FROM verifications
GROUP BY kind, key;

-- Counts of trusted / seen-only / (untested = anything in the entity tables
-- with no verifications row). Use in dashboards / `fsrpb status`.
CREATE VIEW IF NOT EXISTS v_trust_summary AS
SELECT kind,
       SUM(is_trusted)        AS trusted,
       SUM(1 - is_trusted)    AS seen_only
FROM v_verification_state
GROUP BY kind;

-- ---------- Connector configurations (Tier-2, per-install) ----------
-- Maps a connector + friendly config name to its per-instance config UUID.
-- These records are created out-of-band on each FSR box and are NOT portable,
-- so they're WARMED into this table (not shipped). The compiler reads it via
-- Resolver.resolve_config_id() — no live lookup, no dev-only `tooling/` import.
-- `config_name = '__default__'` holds the instance's default config for a
-- connector. Replaces the legacy data/connector_config_map.json cache.
CREATE TABLE IF NOT EXISTS connector_configs (
    connector   TEXT NOT NULL,
    config_name TEXT NOT NULL,                 -- friendly name, or '__default__'
    config_id   TEXT,                          -- per-instance UUID (NULL if none)
    is_default  INTEGER DEFAULT 0,
    PRIMARY KEY (connector, config_name)
);

-- ---------- Catalog provenance / freshness ----------
-- Single source of truth for WHERE and WHEN this catalog was warmed. Drives the
-- multi-instance guard (base_url_hash) and the two-level freshness check
-- (fsr_version, last_publish_time, count:<coll>, etag:<coll>). See
-- fsr_playbooks/_catalog_meta.py for the key vocabulary. Distinct from
-- _probe_runs (per-run audit log); this is the *current* state.
CREATE TABLE IF NOT EXISTS _catalog_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL                 -- ISO-8601 UTC
);

-- ---------- Audit ----------
CREATE TABLE IF NOT EXISTS _probe_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    probe_name   TEXT NOT NULL,
    ts           TEXT NOT NULL,                -- ISO-8601 UTC
    source_paths TEXT,                          -- JSON array
    row_counts   TEXT,                          -- JSON object {table: count}
    version      TEXT,
    notes        TEXT
);

-- ---------- JSON-key alias views ----------
-- Column names in the tables above use SQL-friendly names (op_name, *_json,
-- ord) that don't match the keys in the source info.json blobs. These views
-- expose every column under BOTH the table name AND the info.json key name,
-- so a query that guesses the column from the JSON shape ("operation",
-- "output_schema", "options", "order", "tags", "config_schema") still works.
-- Read-only; underlying tables are untouched.
DROP VIEW IF EXISTS v_connectors;
CREATE VIEW v_connectors AS
SELECT
    name, version, label, category, description, publisher, contributor,
    active, system, cs_approved, cs_compatible, ingestion_supported,
    tags_json, tags_json AS tags,
    config_schema_json, config_schema_json AS config_schema,
    source, source_path,
    info_json, info_json AS info,
    source_code, rpm_fingerprint
FROM connectors;

DROP VIEW IF EXISTS v_operations;
CREATE VIEW v_operations AS
SELECT
    connector_name,
    op_name, op_name AS operation,
    title, annotation, category, description, visible, enabled,
    output_schema_json, output_schema_json AS output_schema,
    conditional_output_schema_json,
    conditional_output_schema_json AS conditional_output_schema,
    output_schema_observed
FROM operations;

DROP VIEW IF EXISTS v_operation_params;
CREATE VIEW v_operation_params AS
SELECT
    connector_name,
    op_name, op_name AS operation,
    parent_param_name, condition_value,
    param_name, param_name AS name,
    title, type, required,
    default_value, default_value AS value,
    options_json, options_json AS options,
    tooltip, placeholder, description, visible, editable,
    ord, ord AS "order",
    observed_type, coerces_from
FROM operation_params;

DROP VIEW IF EXISTS v_module_fields;
CREATE VIEW v_module_fields AS
SELECT
    module_name,
    field_name, field_name AS name,
    title, type, required,
    picklist_options, picklist_options AS options,
    tooltip
FROM module_fields;

DROP VIEW IF EXISTS v_step_types;
CREATE VIEW v_step_types AS
SELECT
    uuid, name, label, category, description,
    args_schema_json, args_schema_json AS args_schema,
    occurrences, common_pitfalls
FROM step_types;

-- ---------- Full-text search ----------
-- Agents query this for "enrich indicator", "create incident", etc.
CREATE VIRTUAL TABLE IF NOT EXISTS fsr_fts USING fts5(
    kind,           -- 'operation' | 'step_type' | 'module_field' | 'recipe' | 'jinja_macro'
    key,            -- e.g. 'connector:op' or 'module:field'
    title,
    description,
    tooltip,
    content=''
);
