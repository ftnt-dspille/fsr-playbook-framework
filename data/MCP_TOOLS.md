# MCP Tools — fsrpb agent surface

Auto-generated from `python/mcp_server.py` by `python/store/export_mcp_tools.py`. **Do not hand-edit.**

**26 tools** across **5 categories**.

## Index

- **Reference / lookup** — [`find_connector`](#find-connector), [`find_operation`](#find-operation), [`get_connector_source`](#get-connector-source), [`get_op_schema`](#get-op-schema), [`get_picklist`](#get-picklist), [`get_step_type`](#get-step-type), [`list_picklists`](#list-picklists), [`list_tags`](#list-tags), [`picklist_for_field`](#picklist-for-field), [`resolve_picklist_value`](#resolve-picklist-value), [`search_playbooks`](#search-playbooks)
- **Jinja** — [`find_jinja_filter`](#find-jinja-filter), [`find_jinja_pattern`](#find-jinja-pattern), [`get_filter_examples`](#get-filter-examples), [`render_jinja`](#render-jinja)
- **Compiler** — [`compile_yaml`](#compile-yaml), [`validate_yaml`](#validate-yaml)
- **Authoring loop** — [`dry_run_playbook`](#dry-run-playbook), [`get_run_env`](#get-run-env), [`list_playbook_runs`](#list-playbook-runs), [`list_recent_failed_runs`](#list-recent-failed-runs), [`push_playbook`](#push-playbook), [`run_playbook`](#run-playbook)
- **Live FSR** — [`healthcheck_connector`](#healthcheck-connector), [`list_configured_connectors`](#list-configured-connectors), [`run_op`](#run-op)

---

## Reference / lookup

### `find_connector`

```python
find_connector(q: str, limit: int = 15) -> list[dict[str, Any]]
```

Fuzzy-search connectors by name, label, category, or description.

Returns a list of matching connectors with name, label, category, and
description fields.  Use the `name` field as the connector identifier
in YAML steps.

### `find_operation`

```python
find_operation(connector: str, q: str = '', limit: int = 20) -> list[dict[str, Any]]
```

List or search operations for a connector.

Pass `connector` as the connector name (from find_connector).
`q` is an optional substring filter on op name, title, or description.
Returns op_name, title, description, annotation.

### `get_connector_source`

```python
get_connector_source(connector: str, file: str = 'operations.py') -> dict[str, Any]
```

Fetch the Python source code for a connector from the live FSR instance.

Returns the raw content of `operations.py` (or another file in the connector
package — `connector.py`, `info.json`, `release_notes.md`).

**Use this sparingly** — only when the op name and parameter schema are not
sufficient to understand what the connector actually does (e.g. undocumented
side effects, ambiguous return shape, or a newly added op with no description).

**How it works:**
FSR has no direct file-read API for installed connectors. This tool calls
`POST /api/integration/connector/development/entity/{id}/` with
`{edit_repo_connector: true}` to create a development copy, then reads the
file from that copy.  The result is cached in the local reference store so
subsequent calls return immediately without hitting the FSR instance again.

On success: `{ok: true, source: "...", cached: bool}`
On failure: `{ok: false, error: "..."}`

### `get_op_schema`

```python
get_op_schema(connector: str, op: str) -> dict[str, Any]
```

Return the full parameter schema for a connector operation.

Includes:
- `params` — input parameters with required/type/picklist info
- `output_schema_json` — static shape from the connector's info.json (may be
  absent or incomplete for many connectors)
- `output_schema_observed` — live-run inferred shape from a real FSR execution;
  populated by `run_op` the first time the op is exercised.  This is the most
  reliable source of truth for what the step actually returns.
- `output_schema_hint` — set to "run run_op to observe real output" when neither
  schema is available, so callers know to execute the op once.

### `get_picklist`

```python
get_picklist(name: str) -> dict[str, Any]
```

List items of a single picklist as [{itemValue, uuid, iri, ordinal}].

Args:
    name: picklist `listName.name` (e.g. 'AlertStatus', 'Severity').
          Use list_picklists() to discover.

### `get_step_type`

```python
get_step_type(name: str, verbose: bool = False) -> dict[str, Any]
```

Return schema and examples for a playbook step type.

`name` can be the friendly YAML short type (`manual_input`,
`set_variable`, `decision`, ...) or the canonical FSR name
(`ManualInput`, `SetVariable`, `Decision`). Friendly short names
map to their canonical form. The response includes a
`friendly_form` block with the YAML-author-facing schema (the
keys our compiler accepts) — prefer that over the wire-format
`args_schema_json` when authoring YAML.

By default the response is slim (~1–2 KB): the friendly_form
suffices for authoring and raw corpus examples are omitted. Pass
`verbose=True` for the full corpus dump (3 examples, no caps) —
only useful when debugging an unusual case the friendly_form
doesn't cover.

### `list_picklists`

```python
list_picklists() -> dict[str, Any]
```

List every picklist `listName.name` known to the FSR instance.

Use when the agent needs to discover what picklists exist (e.g.
'Severity', 'AlertStatus', 'Threat Type') before resolving a value
to an IRI. Live-fetched once per process and cached.

### `list_tags`

```python
list_tags(prefix: str | None = None, limit: int = 50) -> dict[str, Any]
```

List FortiSOAR tag names; use to discover tags before filtering runs by them.

Backed by `GET /api/3/tags?$export=true`. The instance can have 10k+ tags
(most are auto-generated from threat-intel data), so always pass a prefix
when looking for workflow-noise tags like "system" or "testing".

Args:
    prefix: case-insensitive tag prefix (uses `uuid$like=<prefix>%` —
        the tag entity's primary key IS the tag string). Pass None to
        page through everything.
    limit: max tag names to return.

Returns:
    {"total": <int>, "tags": [<name>, ...]}.

### `picklist_for_field`

```python
picklist_for_field(module: str, field: str) -> dict[str, Any]
```

Auto-discover the picklist behind a (module, field).

Returns the picklist_name plus the offline list of valid string
values pulled from the local module_fields cache. Tries heuristic
names first (e.g. 'AlertStatus' for alerts.status), then falls back
to a Jaccard-overlap match against all live picklist values. Result
persists to store/picklist_name_map.json.

Args:
    module: lowercase module name, e.g. 'alerts', 'incidents'.
    field:  field name, e.g. 'status', 'severity', 'type'.

### `resolve_picklist_value`

```python
resolve_picklist_value(value: str, picklist_name: str | None = None, module: str | None = None, field: str | None = None) -> dict[str, Any]
```

Resolve a friendly value (e.g. 'High') to a picklist IRI.

Provide either `picklist_name`, or both `module` + `field` to
auto-discover. Strings that already start with '/api/3/' pass
through unchanged. Returns close-match suggestions when the value
isn't an exact itemValue — useful when the LLM authored an invalid
value like 'In Progress' for AlertStatus (which only has Open,
Investigating, Pending, Closed, Active, Re-Opened).

### `search_playbooks`

```python
search_playbooks(q: str, limit: int = 10) -> list[dict[str, Any]]
```

Full-text search over playbook patterns seen in production.

Returns matching playbook names, collection names, and the connectors
they use — useful for 'how do others do X' pattern mining.

---

## Jinja

### `find_jinja_filter`

```python
find_jinja_filter(q: str, limit: int = 15) -> list[dict[str, Any]]
```

Search the Jinja filter catalog by name, description, or example.

Returns name, signature, description, example, output_type_observed,
is_trusted (1 = live-tested), corpus_uses (real-world occurrence count
in the live playbook corpus), and curated_doc when present (rich
long-form notes for complex filters like json_query, picklist,
fromIRI, resolveRange).

Use `get_filter_examples(name)` after this to pull more real-world
usages for a specific filter.

### `find_jinja_pattern`

```python
find_jinja_pattern(q: str, kind: str | None = None, limit: int = 12) -> list[dict[str, Any]]
```

Search the live-corpus Jinja-block catalog by substring + kind.

Use this when you want to learn FSR idioms — `{% set x = vars.steps.foo %}`,
`{% for r in vars.input.records %}`, conditional guards, etc — instead of
only looking up filters. The corpus contains ~7,800 unique blocks mined
from 1,669 live workflows.

Args:
    q: substring to match against the raw block, head, vars, or filter chain
    kind: optional — restrict to one block kind. Useful values:
        "expr"   — `{{ … }}` expression blocks (most common)
        "set"    — `{% set var = … %}` assignments
        "for"    — `{% for x in … %}` loops
        "if"     — `{% if cond %}` guards (`elif` is a separate kind)
        "macro"  — `{% macro name(args) %}` definitions
        (omit kind to search across all)
    limit: max results (default 12, ordered by occurrences desc)

Returns:
    list of {raw, kind, head, filters_csv, vars_csv, from_playbook,
             from_step, step_type, occurrences}

### `get_filter_examples`

```python
get_filter_examples(name: str, limit: int = 8) -> dict[str, Any]
```

Real-world usages of a Jinja filter, mined from the live playbook corpus.

Returns the filter's curated long-form doc (when present) plus the top
`limit` distinct expressions where it's used, ordered by frequency.
Each example is a full `{{ … }}` block from a real workflow so the
surrounding context (input shape, downstream chain) is visible.

Args:
    name: filter name (exact match, e.g. "json_query")
    limit: how many distinct expressions to return (default 8)

### `render_jinja`

```python
render_jinja(template: str, context: dict[str, Any] | None = None, from_pb_execution: str | None = None) -> dict[str, Any]
```

Render a Jinja template against the live FSR Jinja engine.

Uses the same engine as FSR's playbook runtime, so FSR-custom filters
(`| tojson`, `| b64encode`, `| yaql`, etc.) all work.

Args:
    template: Jinja source — e.g. `"{{ vars.steps.Get_org.records[0].id }}"`.
    context: dict of variable bindings (e.g. `{"value": [1, 2, 3]}`).
    from_pb_execution: optional workflow PK (string of digits) or task_id UUID.
        When set, the run's `{vars: {...env, steps: {<Name_us>: result}}}`
        is fetched and used as the base context. `context` is then merged
        on top so callers can override individual values for what-if tests.

Returns:
    `{output: <value>}` on success — value preserves its native type
    (str, int, float, bool, list, dict). `{error: str}` if the engine
    errored (template syntax issues, missing var, etc).

Typical use: after triggering a playbook via `run-playbook`, pass the
task_id here with the candidate Jinja for the NEXT step's argument to
confirm it resolves correctly before wiring it into the YAML.

---

## Compiler

### `compile_yaml`

```python
compile_yaml(yaml_text: str) -> dict[str, Any]
```

Compile a YAML playbook to FortiSOAR WorkflowCollection JSON.

Returns `{ok: true, json: "..."}` where `json` is the importable
FSR JSON string, or `{ok: false, errors: [...]}` with structured
compiler errors.

The returned JSON can be pushed to FSR via `fsrpb push` or imported
through the FSR UI (Administration → Import Wizard).

### `validate_yaml`

```python
validate_yaml(yaml_text: str) -> dict[str, Any]
```

Validate a YAML playbook without producing output JSON.

Runs the full compiler pipeline (parse → resolve → validate) and
returns structured errors.  Each error has: code, path, message,
suggestion (may be empty).

Returns `{ok: true}` when the playbook is valid.

---

## Authoring loop

### `dry_run_playbook`

```python
dry_run_playbook(yaml_text: str, playbook: str, input: dict[str, Any] | None = None, timeout_s: int = 180, cleanup: bool = True, use_mock_output: bool = False) -> dict[str, Any]
```

Compile + push + run + auto-cleanup. The agent's full E2E loop in one tool.

Args:
    yaml_text: full YAML source.
    playbook: workflow name to trigger after push (one playbook in the
        collection — the agent picks which one).
    input: trigger params (mapped to `vars.input.params.<k>`).
    timeout_s: poll timeout (default 180s).
    cleanup: hard-purge the collection after the run (default True).
        Set False to keep the collection on the instance for inspection.
    use_mock_output: run with each step's `arguments.mock_result` instead
        of live external calls.

Returns:
    {ok, status, task_id, wf_pk, collection_uuid, error_message?,
     failed_steps?, cleaned_up: bool}.

### `get_run_env`

```python
get_run_env(pb_execution: str) -> dict[str, Any]
```

Fetch the live Jinja context (`vars` + per-step results) of a past playbook execution.

The single most useful tool when building the NEXT step in a playbook
that consumes a prior step's output: it returns exactly what
`vars.steps.<step_name_underscored>.<field>` will resolve to at runtime.
Hits GET /api/wf/api/workflows/<pk>/?step_detail=true and rebuilds the
same shape FSR's widget builds (transform: `step.name.replace(" ", "_")`,
case preserved).

Args:
    pb_execution: workflow PK (integer string e.g. "676747") OR task_id UUID

Returns:
    {
      "status": "finished" | "failed" | ...,
      "name": "<workflow name>",
      "vars": {
        "<env field>": ...,
        "steps": {
          "<step name with spaces→_>": <step result>,
          ...
        }
      }
    }
    or {"error": "..."} on lookup failure.

### `list_playbook_runs`

```python
list_playbook_runs(playbook: str | None = None, playbook_uuid: str | None = None, limit: int = 20, include_finished: bool = False, modified_after: str | None = None, modified_before: str | None = None, tags_include: str | None = None, tags_exclude: str | None = 'system', user_iri: str | None = None) -> dict[str, Any]
```

List runs of a single playbook, server-filtered by template_iri.

Faster + more reliable than `list_recent_failed_runs(playbook=...)`
when you know which playbook you care about — the API uses
template_iri to do the filter on its side, so we don't waste a fetch
of irrelevant rows.

Args:
    playbook: playbook name (resolved live to uuid).
    playbook_uuid: skip the lookup if you already have the uuid.
    limit: max rows (default 20).
    include_finished: include finished runs too (default failures only).

Returns:
    {playbook_uuid, runs: [{task_id, name, status, error_message,
     modified, pk}]}.

### `list_recent_failed_runs`

```python
list_recent_failed_runs(limit: int = 20, playbook: str | None = None, include_finished: bool = False, modified_after: str | None = None, modified_before: str | None = None, tags_include: str | None = None, tags_exclude: str | None = 'system', user_iri: str | None = None) -> list[dict[str, Any]]
```

List recent workflow runs (default: failures only) for triage.

Use this when the user says "my playbook is broken" without naming
the playbook — fetches the most recently-modified failed/errored
runs across the instance from BOTH the live and historical workflow
tables (FSR purges live → historical every ~30-60 min).

Args:
    limit: max rows to return (default 20)
    playbook: optional name filter (client-side substring match)
    include_finished: include finished runs too (default False —
        failed/finished_with_error/terminated only)
    modified_after: ISO timestamp, e.g. "2026-05-01 05:00:00" (server-side)
    modified_before: ISO timestamp (server-side)
    tags_include: CSV of tag names to require (server-side)
    tags_exclude: CSV of tag names to exclude (default "system" to hide
        framework noise; pass "" to include them)
    user_iri: full IRI like "/api/3/people/<uuid>" — filter by triggering
        user (server-side)

Returns:
    List of {task_id, name, status, error_message, modified, uuid,
    pk, source} where source is "live" or "historical".

### `push_playbook`

```python
push_playbook(yaml_text: str) -> dict[str, Any]
```

Compile a YAML playbook and push it to the live FSR instance.

Idempotent: PUT first, POST on 404, hard-purge + POST on 409 (matches
`fsrpb push --mode replace`). Use after `validate_yaml` returns clean.

Returns:
    {ok: true, collection_uuid, collection_name, workflows: [{name, uuid}],
     action: "put"|"post"|"purge_post"} on success.
    {ok: false, errors: [...]} on compile failure.
    {ok: false, error: str} on push failure.

### `run_playbook`

```python
run_playbook(playbook: str, input: dict[str, Any] | None = None, collection: str | None = None, record: str | None = None, follow: bool = True, timeout_s: int = 180, use_mock_output: bool = False) -> dict[str, Any]
```

Trigger a deployed playbook and (optionally) poll until terminal.

Args:
    playbook: workflow name OR uuid OR `Collection:Name` shorthand
    input: trigger params; FSR maps these to `vars.input.params.<k>`
    collection: collection name to disambiguate duplicate workflow names
    record: "<module>:<uuid>" for record-context (cybersponse.action)
        triggers; omit for /notrigger style (designer Run button)
    follow: if True, poll until terminal status (default 180s timeout)
    timeout_s: poll timeout when follow=True
    use_mock_output: honor each step's `arguments.mock_result` instead
        of running live (good for dry-running without external API calls)

Returns:
    {ok, status, task_id, wf_uuid, wf_pk, error_message?, failed_steps?}.
    `ok` is True only when status == "finished"; "finished_with_error"
    and "failed" return ok=False with diagnostics.

---

## Live FSR

### `healthcheck_connector`

```python
healthcheck_connector(name: str, version: str | None = None, config: str | None = None) -> dict[str, Any]
```

Live-check whether a single connector configuration is reachable.

Use after `list_configured_connectors` to confirm the upstream service
is actually up before recommending an op to the user.

Args:
    name: connector name
    version: optional — when omitted, the first configured version is used
    config: optional config UUID — required when the connector has more
        than one configuration and you want a specific one

Returns:
    {status, message, name, version, config_id}
    status="Available" → green; "Disconnected" → connector configured but
    upstream is down; HTTP 404 → no configuration on this instance.

### `list_configured_connectors`

```python
list_configured_connectors(probe: bool = False) -> dict[str, Any]
```

List connectors that are configured AND active on the live FSR instance.

A connector with no configuration cannot be called — it'll fail at runtime
even if it appears in `find_connector`. Use this BEFORE picking which
connector to put in a playbook.

Args:
    probe: when True, also healthcheck each one (one HTTP call per
        connector — slower but gives live "Available"/"Disconnected"
        status). When False (default), just lists the configured set.

Returns:
    {configured: [{name, version, label, config_count, status}], probed: bool}
    With probe=True, status is "Available", "Disconnected", or an error.
    With probe=False, status comes from the listing endpoint
    ("Completed" = config saved successfully).

### `run_op`

```python
run_op(connector: str, op: str, params: dict[str, Any] | None = None, config: str = '', confirm: bool = False) -> dict[str, Any]
```

Execute a single connector operation on the live FSR instance and return
its real output.

This is the authoritative way to discover what a step produces when
info.json has no output_schema or the static schema is incomplete.

**Guardrails** — operations are classified by their `category` field:
- `query / investigation / utilities` → **safe**, runs automatically.
- `remediation / containment / management` → **destructive**, requires
  `confirm=True`.  The tool returns `{requires_confirmation: true}` when
  confirm is omitted so the caller (agent or user) can decide explicitly.
- Any other / unknown category → also requires `confirm=True`.

Pass `confirm=True` only after the user has approved the action or you are
certain it is a read-only probe with no side effects.

On success:
- Returns `{ok: true, data: <actual_output>, output_shape: <inferred_type_shape>}`
- Stores the inferred shape in `output_schema_observed` so `get_op_schema`
  returns it on all future calls without re-running the operation.
- Records a `live_op_exec / tested_pass` verification row.

On failure:
- Returns `{ok: false, status: <str>, message: <str>}` with the FSR error.
- Records `live_op_exec / tested_fail` so the store tracks the attempt.

`params` — dict of input parameter values for the operation.
`config` — optional connector config name (leave empty for the default config).
`confirm` — set True to execute operations that are not auto-safe.

---
