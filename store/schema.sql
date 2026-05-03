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
    info_json         TEXT                   -- full blob, fallback / debug only (icons stripped)
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
    PRIMARY KEY (connector_name, op_name, parent_param_name, condition_value, param_name),
    FOREIGN KEY (connector_name, op_name)
        REFERENCES operations(connector_name, op_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_op_params_op ON operation_params(connector_name, op_name);

CREATE TABLE IF NOT EXISTS operation_examples (
    connector_name  TEXT NOT NULL,
    op_name         TEXT NOT NULL,
    source          TEXT NOT NULL,       -- 'pb_examples' | 'connector_lifecycle' | 'docs'
    example_kind    TEXT NOT NULL,       -- 'yaml' | 'json' | 'python'
    snippet         TEXT NOT NULL,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_op_examples ON operation_examples(connector_name, op_name);

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
    PRIMARY KEY (module_name, field_name)
);

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
