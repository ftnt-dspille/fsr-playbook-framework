---
title: Authoring Playbooks in YAML
category: playbook-authoring
status: reference
source: hand-written
topics:
- yaml-syntax
- step-types
- playbook-structure
- variables
- branching
canonical: true
summary: 'Guide for writing playbooks in YAML. Covers step types, variables,
  branching, looping, and all available fields.'
---

# Authoring playbooks in YAML

## Quick orientation

```
fsrpb compile in.yaml -o out.json    # YAML → JSON (offline)
fsrpb validate in.yaml               # check refs, "did you mean…"
fsrpb push in.yaml                   # deploy to appliance
fsrpb pull <name|uuid>               # fetch a live playbook as YAML
fsrpb diff in.yaml                   # local YAML vs live
fsrpb run-op <connector> <op>        # fire a single connector op
fsrpb run-playbook <name|uuid>       # trigger a deployed playbook
fsrpb explain {connector|step|filter|module|recipe} <name>
```

## Top-level shape

```yaml
collection: My Collection
description: optional
visible: true

playbooks:
  - name: Unique Name
    description: optional
    tag: optional
    is_active: true                    # default true; set false for a disabled draft
    owners: [TeamA, TeamB]            # restrict who can run it (optional)
    parameters: [hostname, severity]  # input params; read as vars.input.params.<name>
    steps:
      - name: Start
        type: start
        next: Do Lookup
      - name: Do Lookup
        type: connector
        connector: virustotal
        operation: query_ip
        params:
          ip: "{{ vars.input.params.hostname }}"
        next: Done
      - name: Done
        type: end
    annotations:                      # optional canvas notes/blocks
      - id: setup_phase
        kind: block
        title: Setup
        contains: [Start, Do Lookup]
```

**Rules:**
- `collection` name must be globally unique on the appliance
- `name` must be unique within a collection
- Each playbook needs exactly one trigger step (`start`, `start_on_create`, `start_on_update`, `start_on_delete`, or `api_endpoint`)
- Steps are identified by `name:` (not `id:`). Use `name:` in `next:` and `branches:` references.

## Step types

| `type:` | Description | Key arguments |
|---|---|---|
| `start` | Manual trigger (Run button). Add `module:` to make it a record-action trigger. | `module`, `button_label`, `requires_record`, `run_mode` |
| `start_on_create` | Fires when a record is created. | `module`, `when: {logic, filters: [{field, op, value}]}` |
| `start_on_update` | Fires when a record is updated. | `module`, `when: …` (supports `op: changed`) |
| `start_on_delete` | Fires when a record is deleted. | `module`, `when: …` |
| `api_endpoint` | Exposes the playbook as an HTTP endpoint. | `route`, `authentication_methods` (optional, defaults to token) |
| `set_variable` | Sets variables for downstream use. | `vars: {name: value, …}` |
| `decision` | Branches based on conditions. | `conditions: [{display, when, next}]`, `default: <step>` |
| `connector` | Calls a connector operation. | `connector`, `operation`, `params`, `config` |
| `find_record` | Queries records from a module. | `module`, `filters: [{field, operator, value}]`, `limit`, `logic`, `sort`, `select`, `relationships`, `max_relations` |
| `create_record` | Creates a new record. | `module` (required), `fields: {field: value}`, `operation`, `is_upsert` |
| `update_record` | Updates an existing record. | `record` (IRI), `module` (required), `fields: {field: value}`, `link:`/`unlink: {rel: [uuid]}` (append/detach), `operation` |
| `delete_record` | Deletes a record. | `record:`, or `module:` + `record_id:`, or `module:` + `filters:` (bulk); `show_deleted:` |
| `manual_input` | Pauses for human input (form or buttons). | `title`, `description`, `options`, `inputs`, `email`, `assign_to`, `is_approval` |
| `delay` | Waits for a duration or event. | `seconds` (or `minutes`/`hours`/`days`) |
| `code_snippet` | Runs inline Python. | `code: \|...`, `config` (optional) |
| `send_email` | Sends an email. | `to`, `subject`, `body`, `from`, `cc`, `bcc` |
| `approval` | Creates an approval request. | `resource: {assignedTo, owners, userOwners, approvaldescription}`, `timeout` |
| `create_task` | Creates a manual task. | `resource: {name, status, priority, …}` |
| `set_api_keys` | Sets API keys for the appliance. | `public_key`, `private_key` |
| `workflow_reference` | Calls another playbook in the same collection. | `target` (name) or `workflowReference` (IRI), `arguments` |
| `stop` / `end` | Terminal step (no-op). | (none) |
| `utilities` | No-op utility step. | (none) |
| `ingest_bulk_feed` | Bulk-ingest records via a feed. | `module`, `fields`, `feed_config` |

## Universal step keys

These keys can be added to any step:

```yaml
- name: Block IP
  type: connector
  when: "{{ vars.score > 70 }}"                        # conditional execution
  retry: {times: 3, delay: 5, until: "{{ vars.done }}"} # retry loop
  ignore_errors: true                                  # continue on failure
  apply_async: true                                     # fire-and-forget
  on_remote: pick_from_record                            # route to remote agent
  for_each: {item: "{{ vars.ips }}"}                   # loop over a list
  mock_result: {data: {score: 0}}                       # mock output for testing
  set: {last_lookup_at: "{{ now() }}"}                  # stamp vars after step
  with:                                                  # alias deep Jinja paths
    info: "{{ vars.steps.Enrich.data.code_output }}"
  post_comment: "auto-added by triage"                   # post a comment on the record
  comment: "blocks egress to the C2 IP"                  # canvas sticky-note
  description: "Free-form detail pane text"              # step description
```

| Key | Meaning |
|-----|---------|
| `when:` | Jinja boolean -- the step runs only when truthy. On `start_on_create`/`start_on_update`: a field-based trigger filter (`{logic, filters: [{field, op, value}]}`). |
| `retry:` | Retry the step until a condition holds. Keys: `times`, `delay` (seconds), `until` (Jinja condition). |
| `ignore_errors:` | Boolean. When `true`, a step failure doesn't halt the playbook. |
| `apply_async:` | Boolean. Fire-and-forget execution. |
| `on_remote:` | Route execution to a remote/tenant agent. `pick_from_record` or an agent name. |
| `for_each:` | Loop the step over a list. See [Looping](#looping-a-step-over-a-list-for_each). |
| `mock_result:` | The payload `--mock` runs return for this step. |
| `set:` | Inline vars stamped after the step runs. Read as `vars.<name>` downstream. |
| `with:` | Jinja path binding -- alias a long `vars.steps.X.data.Y` path for the step's scope. See [with: binding](#with-jinja-path-binding). |
| `post_comment:` | Post a collaboration comment to the record. Sugar for `message: {content: "…"}`. |
| `comment:` | A canvas sticky-note for humans; does not affect execution. |
| `description:` | Free-form text shown in the step's detail pane. |

### `with:` -- Jinja path binding

When a step references the same deep Jinja path many times, `with:`
aliases it for the step's scope:

```yaml
- name: FMG Ensure Vendor Address
  type: connector
  with:
    info: "{{ vars.steps.Enrich_Host.data.code_output }}"
  connector: fortinet-fortimanager-json-rpc
  operation: get_address
  params:
    url: "/pm/config/adom/{{ vars.info.adom }}/obj/firewall/address/{{ vars.info.src_addr_name }}"
```

- Binding names must be valid identifiers (letter/underscore start).
- Values can be `{{ }}`-wrapped or bare Jinja expressions.
- Word-boundary matching: `vars.info` matches in `{{ vars.info.adom }}`
  but **not** in `{{ vars.information }}`.

### `message:` -- posting a comment to the record

Works on any step type except `delay` and `set_api_keys`:

```yaml
- name: Block IP
  type: connector
  message:
    content: "Blocked {{ vars.src_ip }} on FortiGate."
    record: "{{ vars.input.records[0]['@id'] }}"   # omit when triggered on a record
    tags: [containment]                             # optional
    thread: false                                   # optional, default false
  connector: fortigate-firewall
  operation: block_ip
  params: {ip: "{{ vars.src_ip }}"}
```

## Variables and Jinja

| Expression | What it gives you |
|---|---|
| `{{ vars.input.records[0] }}` | the trigger record |
| `{{ vars.input.params.<name> }}` | input param declared in `parameters:` |
| `{{ vars.steps.<step_name>.<field> }}` | output of a previous step (name with spaces → underscores) |
| `{{ vars.<name> }}` | a variable set via `set_variable` or `set:` |
| `{{ vars.env.<key> }}` | env-level variables (organization, user, …) |
| `{{ vars.item }}` | current element in a `for_each` loop |

### Reading a previous step's output

The `vars.steps.<key>` namespace uses the step's **name** with spaces
converted to underscores (case preserved):

```yaml
- name: Get organization
  type: connector
  connector: fortinet-fortisiem
  operation: get_org_name_by_org_id
  next: Route

- name: Route
  type: decision
  conditions:
    - display: found
      when: "{{ vars.steps.Get_organization.records[0].id is defined }}"
      next: Take Action
```

### Per-step-type output shapes

| Step type | Where the output lands |
|---|---|
| `connector` | `vars.steps.<name>.data` (or `.records` per op output schema) |
| `find_record` | `vars.steps.<name>.records[]` (each is a full module record) |
| `set_variable` | variables go directly to `vars.<var_name>` (not under `vars.steps`) |
| `manual_input` | `vars.steps.<name>.input.<field>` (after the operator submits) |
| `code_snippet` | whatever the snippet `return`s, at `vars.steps.<name>` |
| `workflow_reference` | child output at `vars.steps.<name>.<key>` |

### Setting variables

**On a `set_variable` step** -- use `vars:` at the step level:

```yaml
- name: Capture
  type: set_variable
  vars:
    severity_label: "{{ vars.input.records[0].severity }}"
    indicator_count: "{{ vars.steps.Fetch.indicators | length }}"
    next_action: "escalate"
```

**On any other step** -- use `set:` to stamp vars after the step runs:

```yaml
- name: Fetch
  type: connector
  connector: my-connector
  operation: list_things
  params:
    since: "{{ vars.lastPullTime }}"
  set:
    fetched_at: "{{ now() }}"
    pull_window: "{{ vars.lastPullTime }}"
```

## Routing

**Linear flow** -- one step → next:

```yaml
- name: Step A
  type: set_variable
  vars: {x: 1}
  next: Step B
- name: Step B
  type: end
```

**Branching** -- a decision routes to N possibilities:

```yaml
- name: Branch
  type: decision
  conditions:
    - display: yes
      when: "{{ vars.severity == 'high' }}"
      next: Escalate
    - display: no
      when: "{{ vars.severity != 'high' }}"
      next: Log Only
  default: Log Only           # optional implicit else
```

**Manual input branching** -- each option routes to a different step:

```yaml
- name: Approve Action?
  type: manual_input
  title: Approve blocking?
  options:
    - display: Approve
      primary: true
      next: Block IP
    - display: Reject
      next: End
```

## Looping a step over a list (`for_each`)

Any step can run once per element of a list:

```yaml
- name: Create Alerts
  type: create_record
  module: alerts
  fields:
    name: "{{ vars.item.name }}"
    severity: "{{ vars.item.severity | default('Medium') }}"
  for_each:
    item: "{{ vars.steps.fetch.records }}"   # required: Jinja list expression
    parallel: false                           # optional, default false
    condition: ""                             # optional Jinja filter
    max_parallel: 5                           # optional; cap concurrent iterations
    # __bulk: true                             # bypass on-create triggers (high-volume feeds)
    # batch_size: 100                          # only with __bulk
    # break_loop: ""                            # optional; truthy stops the loop
```

- `for_each.item` is **required** and must evaluate to a list.
- The current element is always `vars.item` (object items expose fields as `vars.item.<field>`).
- `parallel: true` runs iterations concurrently -- only safe with no shared state.
- `__bulk: true` bypasses on-create/on-update playbook triggers. Use for high-volume feeds only.

## Step type details

### `connector`

```yaml
- name: Lookup IP
  type: connector
  connector: virustotal           # required
  operation: query_ip            # required
  config: "my-vt-config"         # config name or UUID; omit for default
  params:
    ip: "{{ vars.input.params.hostname }}"
```

### `find_record`

```yaml
- name: Find Alert
  type: find_record
  module: alerts
  filters:
    - field: severity
      operator: eq
      value: High
  limit: 200                      # see note below -- rides on the module
  logic: AND
  sort:                           # optional
    - field: createDate
      direction: DESC             # ASC (default) | DESC
  select: [name, status]          # optional field projection
  relationships: true             # optional; include related records
  max_relations: 100              # optional; cap per relationship
  partial: true                   # optional; return first page only
```

**`limit:` is emitted onto the module, not just the query.** The compiler
writes `module: alerts?$limit=200` alongside `query.limit`, because the
platform reads the page size from the query string and ignores the body value.
Authored as above this is handled for you -- but if you hand-write a raw
`query:` envelope with only `limit` inside it, the step silently returns **30
rows** and reports success. Every shipped Solution Pack find step carries the
suffix.

`max_relations:` becomes `$fsr_max_relation_count=N` and only bites alongside
`relationships: true`. Worth setting: expanding relationships uncapped on a
busy module can pull an unbounded child set.

### `create_record` / `update_record`

`module:` is **required** on both.

```yaml
- name: Create Alert
  type: create_record
  module: alerts
  fields:
    name: "Suspicious IP detected"
    severity: High
  operation: Overwrite
  is_upsert: false                # optional

- name: Update Alert
  type: update_record
  record: "{{ vars.steps.Find.records[0]['@id'] }}"
  module: alerts
  fields:
    status: Investigating
    description: "Updated by triage playbook"
  operation: Replace
```

#### Writing a multi-value field REPLACES it

A `fields:` write to a collection field (`recordTags`, `indicators`, `assets`,
any relationship) **discards whatever was already there**. To add without
disturbing existing values, use `link:`:

```yaml
- name: Attach indicator
  type: update_record
  module: alerts
  record: "{{ vars.item['@id'] }}"
  link:                           # appends -- compiles to resource.__link
    indicators: ["{{ vars.new_indicator_uuid }}"]
  fields:                         # scalars can be written in the same step
    status: /api/3/picklists/...
```

Measured on live 7.x and 8.0 appliances: seeding an alert with 2 indicators and
writing 1 via `fields:` leaves **1**; linking 1 via `link:` leaves **3**, with
unrelated tags untouched. `__link` is the same primitive the platform's own
escalation engine uses to attach alerts and assets to a case.

**`operation:` / `field_operations:` / `tags_operation:` do NOT control this.**
They map to the wire keys `operation` / `fieldOperation` / `tagsOperation`,
which 349 of 370 live update steps set -- but 15 combinations were tested across
both versions and both field types (`Append`, `Overwrite`, `Replace`,
per-field overrides, `OverwriteTags`, `AppendTags`, and omitting them entirely)
and **every one replaced the collection**. The keys are accepted for wire
fidelity; do not rely on them to preserve data. Use `link:`.

To REMOVE a related record, use `unlink:` -- the same primitive in reverse
(measured: 2 linked indicators, unlink 1, leaves 1):

```yaml
- name: Detach indicator
  type: update_record
  module: alerts
  record: "{{ vars.item['@id'] }}"
  unlink:
    indicators: ["<uuid>"]
  fields:
    description: written in the same step
```

`link:` and `unlink:` can appear in one step -- both ride in the same `resource`
payload, so attaching and detaching is a single PUT, not two steps. The wire
keys (`__link` / `__unlink`) are still accepted under `fields:` if you prefer
to write them out.

Reach for `unlink:` rather than rewriting the collection by hand: detaching via
`fields:` means reading the current list, dropping one entry and writing the
rest back, which races anything else touching that record and silently discards
the difference if the read comes back short.

### `delete_record`

```yaml
- name: Delete Record
  type: delete_record
  record: "{{ vars.steps.Find.records[0]['@id'] }}"
  # or by module + ID:
  # module: alerts
  # record_id: "123"
  # or bulk by filters -- NOTE: these go inside a `query:` envelope on this
  # step (unlike find_record, `filters:`/`logic:` at step level are rejected):
  # module: alerts
  # query:
  #   logic: AND
  #   filters: [{type: primitive, field: status, operator: eq, _operator: eq, value: Closed}]
  show_deleted: false             # optional
```

**Bulk delete is not row-capped** -- 45 matching records were deleted in one
run, with and without a `?$limit=` suffix. Unlike `find_record`, there is no
30-row ceiling to work around.

**A filter the platform rejects deletes nothing and still reports success.** A
raw `contains` filter on `alerts.name` errors server-side on this platform; the
step swallowed it, deleted 0 of 45, and the run finished green. Fail-safe in
direction, but silent -- verify the count after a bulk delete rather than
trusting the run status.

### Substring filters: write `contains`, get `like`

`/api/query/<module>` has no scalar `contains` -- sending one returns a 500, and
so do `startswith` and `sw`. The only substring match it honours is `like` with
an explicit `%` in the value. So on `find_record` and `delete_record` filters
the compiler rewrites for you (with a warning), exactly as it already did for
trigger `when:` conditions:

| authored | compiled |
|---|---|
| `operator: contains`, `value: test` | `operator: like`, `value: %test%` |
| `operator: startswith`, `value: test` | `operator: like`, `value: test%` |
| `operator: endswith`, `value: test` | `operator: like`, `value: %test` |
| `operator: notcontains`, `value: test` | `operator: notlike`, `value: %test%` |

A value you wildcard yourself (`%already%`) is passed through untouched, so you
can still write your own pattern. Both `operator` and `_operator` are set -- the
platform reads the first and the designer reads the second, and a step where
they disagree renders with the wrong operator selected.

### `manual_input`

```yaml
- name: Approve Action?
  type: manual_input
  title: "Approve blocking?"
  description: "Review the alert and choose an action."
  options:
    - display: Approve
      primary: true
      next: Block IP
    - display: Reject
      next: End
  inputs:                          # optional form fields
    - name: comment
      kind: textarea
      label: "Comment"
      required: true
    - name: severity
      kind: select
      label: "Severity"
      options: [Low, Medium, High]
  email:                           # optional email notification
    enabled: true
    subject: "Action required"
    recipients:
      - alice@example.com
    body: "Please review this alert"
  assign_to:                       # optional assignment
    person: "admin"                # or: team: "Tier 1"  or: record_field: true
  is_approval: false               # set true for an approval gate
```

`inputs[]` per-field keys: `name`, `kind`, `label`, `tooltip`, `required`,
`default`, `options`. Supported `kind:` values: `text, textarea, richtext,
html, email, url, password, integer, number, checkbox, boolean, select,
datetime, json`. `kind: select` needs `options:`.

After the operator submits, form fields are read at
`vars.steps.<step_name>.input.<name>`.

### `delay`

```yaml
- name: Wait
  type: delay
  seconds: 30
  # or: minutes: 5  /  hours: 1  /  days: 1
```

### `code_snippet`

```yaml
- name: Run Script
  type: code_snippet
  code: |
    result = {"ip": vars.input.params.ip, "blocked": True}
    return result
  config: "python-runner"    # optional
```

### `send_email`

```yaml
- name: Notify Team
  type: send_email
  to:
    - alice@example.com
    - bob@example.com
  subject: "Alert: {{ vars.input.records[0].name }}"
  body: "Please review this alert."
  from: soc@example.com        # optional
  cc: [lead@example.com]       # optional
  bcc: []                       # optional
```

### `approval`

```yaml
- name: Get Approval
  type: approval
  resource:
    assignedTo: ["admin"]
    owners: ["TeamA"]
    userOwners: ["analyst@example.com"]
    approvaldescription: "Please approve the containment action."
  timeout:                     # optional
    days: 1
    hours: 0
    minutes: 0
```

### `workflow_reference`

```yaml
- name: Call Child
  type: workflow_reference
  target: Resolve Hostname      # name of another playbook in this collection
  arguments:
    hostname: "{{ vars.input.params.hostname }}"
    dns_server: "8.8.8.8"
  apply_async: false
  pass_input_record: false
```

For cross-collection references, use the IRI directly:
```yaml
  workflowReference: /api/3/workflows/<uuid>
  arguments: {hostname: "fsr-1"}
```

### `api_endpoint`

```yaml
- name: Start
  type: api_endpoint
  route: lookup_ip              # → /api/triggers/1/lookup_ip
```

Defaults to token-based authentication. To use a different auth mode:
```yaml
  authentication_methods: ["anonymous"]   # No Authentication
  # or
  authentication_methods: ["Basic"]      # HTTP Basic
```

The inbound HTTP body and query params are available at
`vars.steps.<step_name>.input.params.api_body` and `.api_params`.

### `create_task`

```yaml
- name: Create Task
  type: create_task
  resource:
    name: "Review suspicious IP"
    status: "Open"
    priority: "High"
```

### `set_api_keys`

```yaml
- name: Set Keys
  type: set_api_keys
  public_key: "{{ vars.env.API_PUBLIC_KEY }}"
  private_key: "{{ vars.env.API_PRIVATE_KEY }}"
```

## Playbook ownership

By default a playbook is public -- any team can run it. Restrict it:

```yaml
playbooks:
  - name: Lookup IP
    owners: ["TeamA", "TeamB"]
    steps: [...]
```

`owners:` accepts team names (resolved to IRIs via the warmed reference
table) or full team IRIs. An unknown team name is a hard error with a
suggestion.

## Picklist values

Picklist-typed fields accept the friendly display value directly:

```yaml
fields:
  severity: High           # not a picklist IRI
  status: Investigating
  type: Phishing
```

## Comments and annotations

**`comment:`** -- sticky-note explaining a single step:
```yaml
- name: Find Alert
  type: find_record
  comment: |
    Pulls the matching alert before we mutate it.
  module: alerts
  filters: [{field: uuid, operator: eq, value: "{{ vars.input.params.id }}"}]
```

**`annotations:`** -- free-floating notes or grouping blocks:
```yaml
annotations:
  - id: explainer
    kind: note
    title: "Why we re-queue here"
    body: "The async output is checked every minute."
  - id: setup
    kind: block
    title: Setup phase
    contains: [Start, Prep, Lookup]
```

## Common errors

| Code | Cause | Fix |
|---|---|---|
| `parse_error` | invalid YAML | check indentation |
| `missing_field` | required argument not present | add it; `fsrpb explain step <name>` shows what's required |
| `unknown_step_type` | typo in `type:` | use a name from the step type table |
| `unknown_connector` | typo in connector name | `fsrpb explain connector <name>` to verify |
| `unknown_operation` | op not on the connector | `fsrpb explain connector <name>` lists ops |
| `unknown_param` | param not on the operation | check `fsrpb explain` output |
| `bad_value` | wrong shape, bad Jinja, invalid enum value | message includes specifics |
| `no_trigger` | no trigger step | add exactly one `start`/`start_on_*`/`api_endpoint` |

## Worked examples

All under `examples/` and validated by tests on every commit:

| File | Pattern |
|---|---|
| `hello_connector.yaml` | start → set_variable → connector -- minimum useful playbook |
| `decision_branch.yaml` | start → set_variable → decision → two branches |
| `find_and_update.yaml` | start → find_record → update_record |
| `manual_input_then_act.yaml` | start → manual_input → decision → branched action |
| `parent_calls_child.yaml` | two playbooks; parent invokes child via `target:` with input params |
