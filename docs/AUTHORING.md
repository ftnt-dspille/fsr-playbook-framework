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
summary: 'Working guide for simplified YAML syntax the compiler accepts: playbook
  shape, step types, parameter binding, trigger patterns.'
---

# Authoring playbooks in YAML

This is the working guide for writing FortiSOAR playbooks in the simplified
YAML the compiler accepts. For the bigger picture (compiler internals,
roadmap, MCP integration) see `ARCHITECTURE.md`. For source-of-truth API
details see `soar-reporting-dashboard-cl/docs/FORTISOAR_API.md`.

## Quick orientation

```
fsrpb compile in.yaml -o out.json    # YAML → FSR JSON
fsrpb validate in.yaml               # check refs, "did you mean…"
fsrpb decompile fsr.json             # FSR JSON → YAML (read existing playbooks)
fsrpb pull <name|uuid>               # fetch a live collection as YAML
fsrpb diff in.yaml [-c name]         # local YAML vs live collection
fsrpb status                         # recent import_jobs and their state
fsrpb explain {connector|step|handler|filter|module|recipe} <name>
fsrpb push in.yaml                   # first create works; re-push parked
fsrpb run-op <connector> <op>        # fire a single connector op via wf/workflow/tasks/connector/
fsrpb run-playbook <name|uuid>       # manually trigger a deployed playbook
```

The compiler is fully offline. `pull`, `diff`, `status`, `push` need
`.env` credentials.

## Top-level shape

```yaml
collection: My Collection
description: optional
visible: true

playbooks:
  - name: <unique within this collection>
    description: optional
    tag: optional
    is_active: true          # defaults to true (active); set false to ship a disabled draft
    owners: [optional, list, of, team, names, or, IRIs]  # restricts who can run it; see "Playbook ownership"
    is_private: true        # optional, DERIVED from owners — set owners: rather than this
    parameters: [optional, list, of, names]    # input params; read inside as vars.input.params.<name>
    steps:
      - id: start          # short ref (slug); used for routing
        type: start        # see "Step types" below
        next: <next-id>
        # branches: {label: target-id}      # for decision steps
        # comment: |                        # optional explanation
        #   Why this step exists / what it does.
        #   Auto-rendered as a sticky-note next to the step on the canvas.
      - ...
    annotations:           # optional: notes and blocks on the canvas
      - id: setup_phase
        kind: block         # note (sticky comment) | block (grouping) | custom
        title: Setup
        contains: [start, prep, lookup]   # block-only: which steps it wraps
```

**Constraints the compiler checks at compile time** (verified from FSR's
Doctrine entity definitions, see API doc):
- `collection.name` must be globally unique on the appliance
- `playbook.name` must be unique **within a collection**
- Each playbook needs exactly one `start` step
- `step.id` must be unique within a playbook
- Connector / operation / param names must exist in the reference store

## Step types

The short names you write in `type:` map to canonical FSR step types.
Run `fsrpb explain step <name>` for the canonical handler signature.

| YAML `type` | FSR step type | Handler | Common arguments |
|---|---|---|---|
| `start` | `cybersponse.abstract_trigger` (or `cybersponse.action` when `module:` present) | (trigger) | `module`, `button_label`, `requires_record`, `run_mode` (record-context only) |
| `start_on_create` | `cybersponse.post_create` | (trigger) | `module`, `when: {logic, filters: [{field, op, value}]}` |
| `start_on_update` | `cybersponse.post_update` | (trigger) | `module`, `when: …` (supports `op: changed`) |
| `start_on_delete` | `cybersponse.post_delete` | (trigger) | `module`, `when: …` (matches pre-delete state); deleted record(s) at `vars.input.records` |
| `api_endpoint` | `cybersponse.api_call` | (trigger) | `route`, `authentication_methods` (optional — defaults to token-based; see [API-Endpoint triggers](#api-endpoint-triggers-api_endpoint) below) |
| `set_variable` | `SetVariable` | `set_multiple` | `arg_list: [{name, value}, …]` or flat `{name: value}` |
| `decision` | `Decision` | `cond` | `conditions: [{option, condition}]` + `branches:` |
| `connector` | `Connectors` | `connector` | `connector, operation, params, version, config, step_variables` |
| `stop` / `end` | `Connectors` (cyops_utilities `no_op`) | `connector` | (no args — synthesized as Utils: No Operation) |
| `delete_record` | `Connectors` (cyops_utilities `make_cyops_request`, `method: DELETE`) | `connector` | one of: `record:` (IRI/`@id`), `module:`+`record_id:`, or `module:`+`query:` (bulk `delete-with-query`); optional `show_deleted:` — FSR has no dedicated delete step type |
| `find_record` | `FindRecords` | `find_data` | `module, query, partial` |
| `create_record` | `InsertData` | `insert_data` | `module` (→ `collection`), `resource`, `operation` |
| `update_record` | `UpdateRecord` | `update_data` | `collection` (record IRI), `module` (→ `collectionType`), `resource`, `operation` |
| `insert_record` | `InsertData` | `insert_data` | legacy alias for `create_record` |
| `delay` | `Delay` | `delay` | `seconds` (or `minutes`/`hours`/`days`) |
| `manual_input` | `ManualInput` | `manual_input` | `title, description, options: [...], inputs: []` |
| `code_snippet` | `CodeSnippet` | `connector` | `code: |...`, optional `config: <friendly-name>` |
| `approval` | `Approval` | `approval` | `resource: {assignedTo / owners / userOwners, approvaldescription}`, optional `response_mapping`, `timeout` (`collection` defaults to `approvals`) |
| `send_email` | `SendEmail` | `send_email` | `to: [...]`, `subject`, `body` (→ `content`), optional `from` (→ `from_str`), `cc`, `bcc` |
| `create_task` | `ManualTask` | `create_task` | `resource: {name, status, priority, …}` (`collection` defaults to `tasks`) |
| `set_api_keys` | `SetAPIKeys` | `set_api_keys` | `public_key`, `private_key` (both jinja-capable) |
| `workflow_reference` | `WorkflowReference` | (per-type validator) | `target` (local name) or `workflowReference` (IRI) + `arguments` |

> Removed: `record_action` short alias is gone — fold into `start` with a `module:` arg. `requires_record: false` is the same as the old "no record context" form.

Other FSR step types (`cybersponse.action`, `RestApi`, `RunScript`,
`ParallelExecution`, `MapPlaybook`, `FetchEmail`) round-trip
correctly through the compiler — they just don't have a friendly short
alias yet. Use the canonical name in `type:` when you need them.

## Connector step fields

```yaml
- id: lookup
  type: connector
  arguments:
    connector: fortinet-fortisiem      # required
    operation: get_org_name_by_org_id  # required
    config: dans fortisiem             # name OR uuid; "" = use connector's default config
    params: { domain_id: "Fortinet" }
    # version: auto-stamped from the store
    # step_variables: defaults to {} — set keys to capture step output as a variable
```

`config:` accepts either the friendly config name (as shown in the FSR
Connectors UI) or the config uuid. Empty string tells FSR to use the
connector's saved default. The compiler passes it through unchanged —
FSR resolves it at runtime.

`step_variables:` lets a step expose its output under a named variable
(`{{ vars.<name> }}`) for downstream steps. Recommended practice is to
use a separate `set_variable` step instead — `step_variables` on a
connector step is invisible from the canvas, and a downstream reader
can't tell where the variable came from.

## Comments and annotations

Two ways to leave human-readable notes on the canvas. Both round-trip
losslessly through the compiler.

**`step.comment` — preferred for explaining a single step.**
```yaml
- id: lookup_alert
  type: find_record
  comment: |
    Pulls the matching alert before we mutate it. Don't merge with
    update_record — that loses the audit trail.
  arguments: { module: alerts, query: "id={{vars.input.id}}" }
```
The compiler emits a sticky-note (`type: note`, title `Note`) positioned
to the right of the step. On round-trip the note is folded back into
`step.comment` so the YAML stays clean. Title defaults to `Note` if you
don't set one.

**`playbook.annotations` — for free-floating notes or grouping blocks.**
```yaml
annotations:
  - id: explainer
    kind: note
    title: "Why we re-queue here"     # defaults to "Note"
    body: |
      The async output is checked every minute.
    position: { top: 240, left: 800, width: 500, height: 160 }
  - id: setup
    kind: block
    title: Setup phase
    contains: [start, prep, lookup]   # block: each listed step gets group=this
```
Blocks visually wrap their `contains:` steps and set each step's `group`
field on the FSR side. Notes are positional only — they sit at the
canvas coordinates you give them (or the compiler picks coords near the
first contained step).

## Routing: linear vs branching

**Linear flow** — one step → next step:

```yaml
- id: a
  type: set_variable
  next: b
- id: b
  type: connector
  ...
```

**Branching** — a decision routes to N possibilities:

```yaml
- id: branch
  type: decision
  arguments:
    conditions:
      - option: yes
        condition: "{{ vars.severity == 'high' }}"
  branches:
    yes: escalate
    no: log_only            # last branch with no condition is the implicit else
```

The compiler synthesizes a `WorkflowRoute` per `next` and per `branches`
entry — labels become FSR's edge labels. Empty-string labels are
normalized to null on round-trip.

## The universal step envelope (siblings of `arguments:`)

A consistent set of cross-cutting concepts applies across step types and
can be written at the **step level** instead of buried under `arguments:`.
This is the one envelope to learn — the same keys mean the same thing on
every step. The compiler folds them into the canonical wire shape; both
forms are accepted, but setting the same value at the step level *and*
under `arguments:` is an error so you don't end up with two values.

```yaml
- name: Block IP
  type: connector
  when: "{{ vars.score > 70 }}"          # run this step only if truthy
  retry: { times: 3, delay: 5, until: "{{ vars.done }}" }  # → do_until
  ignore_errors: true                    # keep the playbook running on failure
  apply_async: true                      # fire-and-forget execution
  on_remote: pick_from_record            # route to a remote / tenant agent
  for_each: { item: "{{ vars.ips }}" }   # loop config (full reference below)
  mock_result: { data: { score: 0 } }    # used by --mock runs
  set: { last_lookup_at: "{{ now() }}" } # inline vars stamped after the step
  post_comment: "auto-added by triage"   # → message block (comment on record)
  comment: "blocks egress to the C2 IP" # canvas sticky-note for humans
  arguments:
    connector: fortigate-firewall
    operation: block_ip
    params: { ip: "{{ vars.item }}" }
```

| Step key | Wire key | Meaning |
|----------|----------|---------|
| `when:` | `when` | On a step: a Jinja boolean — the step runs only when it evaluates truthy. On `start_on_create`/`start_on_update`: a field-based trigger filter (`{logic: AND\|OR, filters: [{field, op, value?}]}`). |
| `retry:` | `do_until` | Retry the step until a condition holds or the budget is spent. Keys: `times`→`retries`, `delay` (seconds between attempts), `until`→`condition`. Write `do_until:` directly for the raw shape — setting both is an error. |
| `ignore_errors:` | `ignore_errors` | Boolean. When `true`, a step failure doesn't halt the playbook. |
| `apply_async:` | `apply_async` | Boolean. Fire-and-forget execution (connector / `workflow_reference`). |
| `on_remote:` | `agent` + `pickFromTenant` | Route execution to a remote/tenant agent. `on_remote: pick_from_record` → `agent: "Pick From Record Ownership"`, `pickFromTenant: true`; any other string → that agent name with `pickFromTenant: false`. Write `agent:` directly for the raw value — setting both is an error. |
| `for_each:` | `for_each` | Loop the step over a list (full reference below). |
| `mock_result:` | `mock_result` | The payload `--mock` runs return for this step. |
| `set:` | `step_variables` | Inline vars stamped after the step. Same spelling whether the step is `set_variable` (where it's `vars:`) or anything else. |
| `post_comment:` | `message` | Post a collaboration comment to the record. Sugar for `message: {content: "…"}`; use the `message:` block (below) for tags/record/thread. Setting both is an error. |
| `comment:` | (annotation) | A canvas sticky-note for humans; does not affect execution. |
| `description:` | `description` | Free-form text shown in the step's detail pane (FSR's per-step `description`, distinct from the `comment:` sticky-note). Round-trips verbatim on pull. |

### `message:` / `post_comment:` — posting a comment to the record

The `message:` block tells FSR to post a collaboration comment on the
associated record after the step completes. It works on any step type
(connector, set_variable, create_record, find_record, decision, etc.)
except `delay` and `set_api_keys`.

```yaml
- name: Block IP
  type: connector
  message:
    content: "Blocked {{ vars.src_ip }} on FortiGate."
    record: "{{ vars.input.records[0]['@id'] }}"   # omit when triggered on a record
    tags: [containment]                             # optional; names auto-resolved
    thread: false                                   # optional; default false
  arguments:
    connector: fortigate-firewall
    operation: block_ip
    params: { ip: "{{ vars.src_ip }}" }
```

| Field | Required | Notes |
|-------|----------|-------|
| `content` | yes | Comment text. Jinja supported. Plain text is auto-wrapped in `<p>…</p>`; raw HTML passes through. |
| `record` | situational | IRI of the record to attach the comment to. **Omit when the playbook runs on a triggered record** — FSR attaches it automatically. Use `records:` for a Jinja expression. |
| `records` | situational | Jinja expression resolving to a record IRI. Alternative to `record:` when you need dynamic resolution. |
| `tags` | no | List of tag names. Unknown names are auto-created on first use. |
| `thread` | no | Boolean, default `false`. |

The `type:` field is omitted intentionally — all comments use the
standard Comment type (`/api/3/picklists/ff599189-…`). Do not set it.

## Setting variables: where they go under `arguments`

Two distinct cases — easy to confuse, and the wrong shape silently
emits one variable literally named `step_variables`:

**On a `set_variable` step → flat keys directly under `arguments`.**
The whole point of the step is to set variables; the entire arguments
dict IS the var bucket. No wrapper, no list-of-`{name, value}`.

```yaml
- id: capture
  type: set_variable
  arguments:
    severity_label: "{{ vars.input.records[0].severity }}"
    indicator_count: "{{ vars.steps.Fetch.indicators | length }}"
    next_action: "escalate"
```

**On any other step that supports inline-stamping vars (`start`,
`connector`, `create_record`, `find_record`, `update_record`, …) →
`step_variables` dict, sitting alongside the step's normal args.**
Here `arguments` is a mixed bag (step config + inline vars), so the
labeled bucket is needed to tell them apart. Always a **dict**
(`{name: value, ...}`), never a list of `{name, value}`.

```yaml
- id: fetch
  type: connector
  arguments:
    connector: my-connector
    operation: list_things
    config: ""
    params:
      since: "{{ vars.lastPullTime }}"
    step_variables:                 # vars stamped after the step runs
      fetched_at: "{{ now() }}"
      pull_window: "{{ vars.lastPullTime }}"
```

On `start` (`cybersponse.abstract_trigger`), `step_variables` is also a
dict; the canonical key `input.params: []` lives there. Inline vars go
alongside it. The compiler auto-fills the canonical default if you
leave it off.

Anti-pattern that silently breaks rendering:

```yaml
# DON'T — `step_variables: [...]` on a set_variable step gets emitted
# as ONE variable literally named "step_variables" whose value is the
# list. FSR's UI shows "step_variables = [object Object],[object Object]".
arguments:
  step_variables:
    - { name: foo, value: bar }
```

## Variables and Jinja

Inside a playbook you read state via Jinja templates:

| Expression | What it gives you |
|---|---|
| `{{ vars.input.records[0] }}` | the trigger record (alert/incident/etc.) |
| `{{ vars.input.params.<name> }}` | input param declared in `parameters:` |
| `{{ vars.steps.<step_name_underscored>.<field> }}` | output of a previous step (see note below) |
| `{{ vars.<name> }}` | a variable set via `set_variable` |
| `{{ vars.env.<key> }}` | env-level variables (organization, user, …) |

### Reading a previous step's output

The Jinja namespace `vars.steps.<key>` keys off the step's **display name**
with spaces converted to underscores (case preserved) — NOT the YAML `id:`
field, NOT the step UUID. The transform is exactly
`step.name.replace(" ", "_")` (verified against the Jinja editor widget's
`view.controller.js`). Authoring rule of thumb:

```yaml
- id: lookup                     # YAML-internal — used for `next:` / `branches:` only
  type: connector
  name: Get organization         # ← spaces→_, case preserved → "Get_organization"
  arguments: { … }
  next: route

- id: route
  type: decision
  arguments:
    conditions:
      - option: ok
        condition: "{{ vars.steps.Get_organization.records[0].id is defined }}"
        # ↑ keys off the previous step's NAME (Get_organization), not its id (lookup)
```

Per step-type output shape (observed; for connector ops the canonical
shape lives in the operation's `output_schema` plus any cached observed
shape from `mcp run_op`):

| Step type | Where the output lands |
|---|---|
| connector  | `vars.steps.<name>.data` (or `.records` / `.<custom>` per op `output_schema`) |
| find_record | `vars.steps.<name>.records[]` (each is a full module record) |
| set_variable | the variables themselves go to top-level `vars.<var_name>` (not under `vars.steps`) |
| manual_input (after resume) | `vars.steps.<name>.input.<field>` |
| code_snippet | whatever the snippet `return`s, at `vars.steps.<name>` |
| workflow_reference | child output at `vars.steps.<call_step_name>.<key>` — child vars do NOT auto-merge into parent's top-level `vars` |

If you reference a step output with a key that doesn't match any step
name in the playbook, the compiler flags it with a difflib-suggested
correction (see "What the compiler validates" below).

Use `fsrpb explain filter <name>` to see canonical filter signatures
and observed return types. Examples:

- `{{ value | regex_replace('foo', 'bar') }}`
- `{{ list_value | length }}`
- `{{ dict_value | toJson }}`
- `{{ value | type_debug }}` — shows the runtime type (helpful for debugging
  pipelines where a generator vs list vs string can break the next filter)

The reference store has 170 backend-introspected filters with canonical
signatures plus 144 documented in the widget catalog. FSR-custom
extensions live under `workflow.*` and `sealab.*` modules — see
`store/FSR_CUSTOM_JINJA.md`.

## Looping a step over a list (`for_each`)

Any step can run once per element of a list by adding a `for_each:`
mapping at the step level (sibling of `arguments`). Inside the step,
the current element is bound to **`{{ vars.item }}`** (object items
expose fields as `{{ vars.item.<field> }}`).

```yaml
- id: create_alerts
  type: create_record
  for_each:
    item: "{{ vars.steps.fetch.records }}"   # required: Jinja list expression
    parallel: false                          # optional, default false
    condition: ""                            # optional Jinja filter; empty = run every iteration
    # max_parallel: 5     # optional (FSR 8.0); cap concurrent iterations on a parallel loop
    # __bulk: true        # optional; bypasses on-create playbook triggers (use only for feeds)
    # batch_size: 100     # optional; only relevant with __bulk
    # break_loop: ""      # optional Jinja; truthy stops the loop early
  arguments:
    module: alerts
    resource:
      name: "{{ vars.item.name }}"
      severity: "{{ vars.item.severity | default('Medium') }}"
      description: "{{ vars.item.description }}"
```

Rules:

- `for_each.item` is **required** and must be a Jinja expression that
  evaluates to a list. The compiler hard-errors if it's missing.
- The runtime variable is always `vars.item`, regardless of how `item`
  is named in YAML — they're separate concepts (the YAML key names the
  *iterable*, FSR exposes each *element* under the fixed name `vars.item`).
- `parallel: true` runs iterations concurrently — only safe if the body
  has no shared state. Default is sequential.
- `max_parallel: N` (FSR 8.0; alias `concurrency_count`) caps how many
  iterations run at once on a **parallel** loop. It compiles to the wire
  pair `concurrency: true` + `concurrencyCount: N` (the designer's
  "Configure concurrency level" / "maximum parallel limit"). The engine
  minimum is 2. On a sequential loop the cap is ignored (the compiler
  warns); on a pre-8.0 appliance the engine has no notion of it and the
  loop fans out unbounded.
- `__bulk: true` is the **trigger-bypass** flag — the body's writes do
  not fire on-create / on-update playbooks. Use it for high-volume
  threat-feed ingestion where per-record triggers would melt the system.
  **Do not** use `__bulk` when ingesting Alerts — you want triggers to
  fire for enrichment / escalation / dedupe.
- `batch_size` only affects `__bulk: true` runs (how many records the
  bulk POST sends per request).
- `break_loop` evaluates each iteration; a truthy result stops further
  iterations.

Unknown keys under `for_each:` are rejected by the compiler.

## Calling another playbook

```yaml
playbooks:
  - name: Resolve Hostname              # the callee
    parameters: [hostname, dns_server]
    steps: [...]

  - name: My Caller                     # the caller
    steps:
      - id: call
        type: workflow_reference
        arguments:
          target: Resolve Hostname      # local-name reference
          arguments:
            hostname: fsr-1
            dns_server: 8.8.8.8
          apply_async: false
          pass_input_record: false
          step_variables: []
```

The compiler:
- Validates `target` exists in the same collection
- Validates the caller's `arguments` keys against the callee's `parameters`
- Rewrites `target: <name>` to `workflowReference: /api/3/workflows/<uuid>` at emit time, using deterministic UUIDs

For cross-collection refs, write the IRI directly:

```yaml
arguments:
  workflowReference: /api/3/workflows/<uuid>
  arguments: {...}
```

Cross-collection UUIDs aren't stable through FSR's importer — it
re-rolls them. For durable cross-collection refs, use `aliasName`
(not yet wired into the compiler — see TODO).

## API-Endpoint triggers (`api_endpoint`)

An `api_endpoint` trigger exposes the playbook as an invokable HTTP
endpoint at `POST /api/triggers/1/<route>` — external systems POST to it
(webhook-style). It's the trigger to use when something outside FSR needs
to *call* the playbook on demand, as opposed to `start` (manual, from the
designer/UI) or `start_on_create`/`start_on_update` (event-driven).

```yaml
- name: Start
  type: api_endpoint
  arguments:
    route: lookup_ip          # the URL path segment → /api/triggers/1/lookup_ip
```

That's the whole clean form. The compiler fills in sensible defaults so
you don't have to spell FSR's wire-internal fields:

- **`authentication_methods`** defaults to **token-based** (`[""]` on the
  wire). This is the only mode that exposes the route at
  `/api/triggers/1/<route>` (no `deferred/` prefix) — i.e. the one you
  almost always want. The empty-string wire value is awkward to write and
  read, so it's the default; **omit `authentication_methods` entirely**
  rather than writing `[""]`.
- The trigger infrastructure fields (`__triggerLimit`, `triggerOnSource`,
  `triggerOnReplicate`, `step_variables`) are auto-filled to the canonical
  shape FSR's designer emits. The inbound HTTP body and query params are
  exposed to the playbook at `vars.steps.<step_name>.input.params.api_body`
  and `.api_params`.

To opt into a different auth mode, set `authentication_methods` explicitly
— both of these route at `deferred/<route>` (NOT invokable at the clean
`/api/triggers/1/<route>` path, by FSR design):

```yaml
arguments:
  route: lookup_ip
  authentication_methods: ["anonymous"]   # No Authentication
  # or
  authentication_methods: ["Basic"]       # HTTP Basic
```

| `authentication_methods` | FSR mode | Route | Invokable at `/api/triggers/1/<route>`? |
|---|---|---|---|
| *(omit)* → defaults to `[""]` | Token Based | `<route>` | yes |
| `["anonymous"]` | No Authentication | `deferred/<route>` | no |
| `["Basic"]` | Basic | `deferred/<route>` | no |

`route` is the one required argument — it's the public URL path segment,
so it has no sane default. A playbook has exactly one trigger step;
`api_endpoint` counts, so don't also add a `start`.

## Playbook ownership (`owners` / `is_private`)

By default a playbook is **public** — any team can run it. Restrict it to
specific teams by listing owner team **names** (or team IRIs):

```yaml
playbooks:
  - name: Lookup IP
    owners: ["TeamA", "TeamB"]      # only these teams can run/trigger it
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
```

- `owners:` accepts friendly team **names** (resolved to
  `/api/3/teams/<uuid>` IRIs via the warmed `teams` reference table — run
  `fsrpb probe modules` / `pyfsr` warmup against the target SOAR first) or
  full team IRIs (which pass through offline, no warmup needed). An
  unknown or misspelled team name is a hard error with a did-you-mean
  suggestion; a bare name against an unwired catalog tells you to warm up.
- **`is_private` is derived from `owners`**, mirroring FSR's invariant:
  owners present → private; no owners → public. You usually don't write
  `is_private:` at all. Writing `is_private: true` with no `owners:` is a
  warning (private requires owners) and emits a public playbook.

This is the access-control knob that matters for `api_endpoint` triggers:
a token-based API key for a team that is **not** an owner *should* be
denied when it POSTs to the route (owner-team scoping). See the
private-playbook API-trigger access repro for the live behavior.

## Worked examples

All under `examples/` and validated by tests on every commit:

| File | Pattern |
|---|---|
| `hello_connector.yaml` | start → set_variable → connector — minimum useful playbook |
| `decision_branch.yaml` | start → set_variable → decision → two branches |
| `find_and_update.yaml` | start → find_record → update_record |
| `manual_input_then_act.yaml` | start → manual_input → decision → branched action |
| `parent_calls_child.yaml` | two playbooks; parent invokes child via `target:` with input params |

## Common errors and what they mean

The compiler returns structured errors. CLI shows them like:

```
[unknown_connector] playbooks[0].steps[1].arguments.connector: unknown connector: 'fortimanger'
    -> did you mean 'fortinet-fortimanager'?
```

Codes you'll see most often:

| Code | Cause | Fix |
|---|---|---|
| `parse_error` | invalid YAML or wrong top-level shape | check indentation; top must be a mapping |
| `missing_field` | required arg/key not present | add it; `fsrpb explain handler <name>` shows what's required |
| `unknown_step_type` | typo in `type:` | use a name from the table above; suggestion shown |
| `unknown_connector` | typo in connector name | `fsrpb explain connector <name>` to verify |
| `unknown_operation` | op not in the connector | `fsrpb explain connector <name>` lists ops |
| `unknown_param` | param not in op definition | check `fsrpb explain` output; suggestion shown |
| `unknown_next_step` | `next:` or `branches:` target doesn't match a step id | typo in step ids |
| `duplicate_step_id` | two steps share an id | ids must be unique within a playbook |
| `bad_value` | wrong shape, cycles, unreachable steps, reserved-name collisions, bad Jinja paths | message includes the specific cause |
| `no_trigger` | no trigger step in a playbook | every playbook needs exactly one `start`, `start_on_create`, `start_on_update`, or `api_endpoint` |

## Re-importing existing playbooks

`fsrpb push` works for **first creates** — it POSTs the unwrapped
collection entity to `/api/3/workflow_collections` and the cascade-persist
on the FSR entity creates the workflows + steps + routes:

```bash
fsrpb compile examples/hello_connector.yaml -o /tmp/x.json   # offline check
fsrpb push examples/hello_connector.yaml                     # → 200 created
```

**Re-push (updating an already-deployed collection) is parked** pending
an appliance backup — FSR soft-deletes (sets `deletedat`) rather than
purging, and the UUID stays owned by the soft-deleted record, so POST
collides on the second push. The path forward (after backup) is the
internal-FSR hard-purge endpoint `DELETE /api/3/delete-with-query/
workflow_collections?$showDeleted=true`. See TODO §5a for the full
state.

Until re-push is unblocked:

```bash
# Update an existing playbook
fsrpb compile myplaybook.yaml -o /tmp/x.json
# Then in FSR UI: Automation → Playbooks → Edit → paste/upload x.json
# Or on the appliance: app:import:from:file --file-path /tmp/x.json
```

The eventual dev loop (post-fix):

```bash
fsrpb pull "Original Collection" -o local.yaml   # one-time clone
# ...edit local.yaml...
fsrpb diff local.yaml                             # see what would change
fsrpb push local.yaml                             # in-place update via PUT
```

## Running a single op or playbook (no re-import needed)

For smoke-testing without going through `push`:

```bash
fsrpb run-op fortinet-fortisiem get_org_name_by_org_id \
  --params '{"domain_id": "Fortinet"}'
# → POST /api/wf/workflow/tasks/connector/ with the canonical body shape
# Returns the connector op's response inline.

fsrpb run-playbook "Some Active Playbook" \
  --input '{"records": [...]}'
# ⚠ endpoint discovery still pending (route file not yet captured).
# Workaround: trigger from the FSR UI's "Run Manually" button.
```

Both bypass the playbook *deploy* path entirely. `run-op` lets you
verify a connector op works in isolation; `run-playbook` triggers an
already-deployed playbook (one that's in FSR via UI import or
`fsrpb push --mode create`).

## Round-trip guarantee

Every playbook in the bundled corpus (`pb_examples/all_fsr_evoke_playbooks.json`,
1596 workflows across 119 collections) round-trips byte-for-byte through
`decompile → compile`. If you `pull` a real playbook and re-`compile`,
the output is semantically identical to what FSR would have exported.
This is the regression gate — `pytest -m slow` runs it.

## What the compiler validates

Beyond per-step argument shape, the validator runs cross-cutting checks:

**Graph-level**
- Cycles (back-edges in `next:` / `branches:`).
- Unreachable steps (warning — FSR tolerates them but they're dead code).
- Dangling decision branches: every `conditions[].option` needs a
  `branches[]` entry or a default `next:`. Stale branch labels (typos)
  are flagged as warnings.

**Reserved names**
- SetVariable arg names that shadow runtime vars: `input, steps, task_id,
  env, result, vars, globalVars, globals, parent_wf, self`.
- Step names that aren't valid Jinja identifiers (Python/Jinja keywords
  like `for`, `class`; identifiers starting with digits).
- Playbook `parameters:` that collide with `records`.

**Jinja paths**
- `{{ vars.steps.<key>... }}` references where `<key>` doesn't match any
  step's name (with spaces→underscores). Suggests the closest match via
  difflib.
- For connector ops with a known `output_schema_json`, the first
  attribute after the step key is checked against the declared output
  keys (warning).

## What the compiler does NOT validate (yet)

- **Full Jinja flow-typing** — we check the first attribute after
  `vars.steps.<name>`, not the full chain.
- **`do_until` semantics** — accepted as opaque mappings.
- **`for_each.item` expression typing** — the compiler checks that
  `item` is a non-empty string but does not statically verify it
  evaluates to a list at runtime. (Accepted keys and required fields
  *are* validated — see the `for_each` section above.)
- **Permission checks** — the compiler trusts you have RBAC on the
  modules / connectors you reference.
- **Schedule definitions** — `schedules:` on a playbook isn't yet
  modeled in the IR.

## Picklist values are friendly strings

Picklist-typed fields (e.g. alerts.severity, alerts.status, indicators.
reputation) accept the friendly display value:

```yaml
arguments:
  resource:
    severity: High           # not /api/3/picklists/<uuid>
    status: Investigating
    type: Phishing
```

Auto-resolution lives in `python/picklists.py` (used by the e2e runner
+ MCP `resolve_picklist_value` tool). The (module, field)→picklist_name
map is discovered live and persisted to `store/picklist_name_map.json`.

> **Foot-gun for trigger filters**: a stored picklist value is the IRI,
> not the display string. So `start_on_create` / `start_on_update` with
> `when: {field: severity, op: like, value: "High"}` will never match.
> Filter on string fields (`name`, `description`) or use `op: changed`
> on post_update.

## Friendly argument expansions

Several step types have a friendly authoring shape that expands to FSR's
canonical argument blob.

**`delay`**
```yaml
- type: delay
  arguments: {seconds: 5}        # or minutes / hours / days
```
Expands to a `TimeBased` rule with the instance-wide `resume_playbook`
channel.

**`code_snippet`**
```yaml
- type: code_snippet
  arguments:
    code: |
      print("hi")
    config: test                  # optional connector-config name
```
Expands to a `connector: code-snippet, operation:
python_inline_code_editor` step. Config UUID resolved live + cached at
`store/connector_config_map.json`.

**`manual_input`**

Friendly form (compiler expands to FSR's canonical InputBased shape).
**Top-level keys are strictly whitelisted**: `title`, `description`,
`options`, `inputs`. Anything else is a hard error — silent-drop trap
verified in the field.

```yaml
- type: manual_input
  arguments:
    title: "Approve action?"
    description: "Click approve to continue."
    options:
      - {option: approve, primary: true}
      - {option: reject}
    inputs:                         # optional InputBased fields
      - {name: comment,  kind: textarea, label: "Comment", required: true}
      - {name: severity, kind: select,   label: "Severity",
         options: [Low, Medium, High]}
      - {name: notify,   kind: checkbox, label: "Notify lead?", default: false}
  branches:
    approve: do_thing
    reject: bail
```

`inputs[]` per-field accepted keys: `name`, `kind`, `label`, `tooltip`,
`required`, `default`, `options` (only). Supported `kind:` values:
`text, textarea, richtext, html, email, url, password, integer,
number, checkbox, boolean, select, datetime, json`. `kind: select`
needs `options:` (list of strings or jinja → list).

After the operator submits, fields are read at
`vars.steps.<step_name>.input.<name>` (step name = display name with
spaces → underscores).

**DO NOT USE** (rejected by the compiler):
- `type: textarea` / `type: single-select` — there is no such FSR
  dispatch; `type:` may only be `InputBased` or omitted.
- `label`, `message` at the top level — not valid keys; use
  `title` / `description` instead, or move into `inputs[]`.
- `timeout` — silently ignored by FSR at runtime.
- `vars.steps.<id>.input.choice` — does not exist; the chosen option
  drives `branches:`, not a variable on the step output.

**`create_record` / `update_record`**
```yaml
- type: create_record
  arguments:
    module: alerts                # → collection: /api/3/alerts
    resource: {name: "...", severity: High}

- type: update_record
  arguments:
    collection: "{{ vars.steps.Find.records[0]['@id'] }}"  # the record IRI
    module: alerts                # → collectionType: /api/3/alerts
    resource: {description: "..."}
    operation: Replace
```

<!-- BEGIN GENERATED STEP REFERENCE (fsr_playbooks.tests.step_reference_gen) -->

<!-- Generated from docs/STEP_WIRE_SHAPES.json — do not edit by hand.
     Regenerate: python -m fsr_playbooks.tests.step_reference_gen --write -->

### Per-step-type argument reference

Editor-derived argument shapes for every step type, keyed by canonical FSR name with the friendly YAML alias(es). Editor-only/UI-state keys are omitted. Source of truth: `docs/STEP_WIRE_SHAPES.json`.

#### Connectors — `connector`, `stop`, `end`, `utilities`, `delete_record`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `agent` | string |  | Remote agent name for distributed deployments |
| `config` | string |  | Configuration UUID or dynamically selected string |
| `connector` | string | yes | Connector name/ID (e.g., 'Slack', 'ServiceNow') |
| `for_each` | object |  | Loop configuration. Structure: {item, condition, __bulk, parallel, break_loop}. Compile-time rule: delete for_each if item empty; if agent + for_each.break_loop, delete break_loop |
| `ignore_errors` | boolean |  | Error handling flag |
| `message` | object |  | Notification message. Compile-time rule: delete if content empty |
| `name` | string | yes | Connector display label |
| `operation` | string | yes | Operation identifier (technical name) |
| `operationTitle` | string |  | Human-readable operation title |
| `params` | object | yes | Operation-specific parameters. Initialized as empty object. Values set from user input. If received as array, converted to object |
| `step_variables` | object |  | Step-level variable declarations |
| `version` | string | yes | Connector version string |
| `when` | string |  | Step condition. Deleted at compile-time if empty/undefined |

#### SetVariable — `set_variable`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `do_until` | object |  | Optional retry loop. Structure: {condition: string, delay: number\|string, retries: number\|string}. Removed at compile time if empty. Excluded from step variable generation |
| `for_each` | object |  | Optional control-flow loop. Structure: {condition: string, item: string, __bulk?: boolean, parallel?: boolean}. Removed at compile time if empty |
| `message` | object |  | Optional message/logging. Structure: {content: string, records: string, tags?: unknown[], thread?: boolean, type?: string, parentstepid?: string, tenant?: string}. Removed at compile time if empty |
| `name` | string |  |  |
| `params` | string |  |  |
| `result` | string |  |  |
| `task_id` | string |  |  |
| `when` | string |  | Optional conditional execution (Jinja expression). Removed at compile time if empty |
| `<user keys>` | any | | Arbitrary user-chosen keys at the arguments root (e.g. variable names). |

#### Decision — `decision`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `conditions` | array | yes | Array of condition objects that define routing paths. Initialized as empty array if not present. Each element is an object with optional step_iri, condition, default, option, and step_name properti… |
| `step_variables` | array |  | Optional array for step-scoped variables |

#### cybersponse.abstract_trigger — `start`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `authentication_methods` | array<string> |  | API_TRIGGER specific. Array containing single auth method: '' (token), 'Basic' (basic auth), or 'anonymous'. Editor watches authSelection and updates route accordingly |
| `fieldbasedtrigger` | object: {filters: array, logic: 'AND' | 'OR'} |  | Initialized on trigger step's arguments via prepareResourceField. Stores filter/condition logic for the trigger. Also set via 'START_ACTION' logic |
| `inputVariables` | array<{name: string, _expanded?: boolean, ...}> |  | ACTION_TRIGGER specific. Array of input parameter definitions. Each variable maps to request.data[name]. Editor sets _expanded flag for UI state. Compile transform creates params object from inputV… |
| `resource` | string |  | Legacy field, converted to resources array. Editor checks both arguments.resource and arguments.resources |
| `resources` | array<string> |  | Array of module/resource IRIs. Initialized from arguments.resource (legacy field) if present. Validated; invalid resources are filtered out. Watched to trigger field reloading. Present in all trigg… |
| `route` | string |  | API_TRIGGER specific (, UUID generated). ACTION_TRIGGER generates UUID. Format: 'deferred/...' for Basic auth or 'deferred/' prefix patterns. Modified via apiSuffix watch |
| `step_variables` | object | yes |  |
| `triggerOnReplicate` | boolean |  | Editor initializes; inverse of triggerOnSource when __triggerLimit is true. Controls whether trigger fires on replicated records |
| `triggerOnSource` | boolean |  | Editor initializes; set to true/false based on __triggerLimit and user selection. Controls whether trigger fires on source record creation |

#### FindRecords — `find_record`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `module` | string | yes | Module path with optional query parameters. Format: <path>?$limit=<N>[&$relationships=true][&$fsr_max_relation_count=<N>]. Controller reconstructs this from params |
| `query` | object | yes | Query object containing filters, logic, sort, limit, and optionally __selectFields. Structure follows Query class definition. Initialized empty, populated by UI |

#### UpdateRecord — `update_record`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `collection` | string | yes | Workflow collection IRI path; read from l.config.arguments |
| `collectionType` | string | yes | Target module type IRI; used for schema lookup; e.g. /api/3/modules/incidents |
| `fieldOperation` | object |  | Per-field operation override; defaulted; maps field names to Append/Overwrite; present in 319/334 instances; for_each removes entries for unsupported field types |
| `for_each` | object |  | Bulk/loop execution; present in 47/334 instances; structure: { __bulk: boolean, condition: string, item: string, batch_size?: number, parallel?: boolean }; deleted if item is empty string; batch_si… |
| `ignore_errors` | boolean |  | Skip step error handling; present in 4/334 instances; standard system key |
| `message` | object |  | Step message config; present in 105/334 instances; deleted if content is empty string; structure: { content: string, records: string, parentstepid?: string, tags?: array, tenant?: string, thread?:… |
| `operation` | enum |  | Field merge strategy; defaulted; present in 328/334 instances; supports Jinja expressions |
| `resource` | object | yes | Field update payload; accessed via l.config.arguments.resource; keys are field names, values are field values; supports __link for relationships |
| `step_variables` | unknown |  |  |
| `tagsOperation` | string |  | Special operation mode for recordTags field; present in 33/334 instances; similar to operation but scoped to tags |
| `when` | string |  | Jinja conditional for step execution; present in 59/334 instances; deleted if empty string; supports full Jinja expressions |

#### InsertData — `create_record`, `insert_record`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `collection` | string | yes | Primary resource identifier. Line 36822: derived from selectedModule. Conditionally prepends 'upsert/' based on __replace state. Can contain 'ingest-feeds' path. No jinja in editor |
| `collectionType` | string |  | Module type IRI for comparison logic. Line 36945: Read for change detection, NOT set by controller |
| `fieldOperation` | object |  | Maps field names to 'Overwrite'\|'Append'. Line 36841: Defaults to {}. Line 36992: Per-field defaults to 'Overwrite'. Specific to multiselectpicklist/recordTags |
| `for_each` | object |  | Bulk config: {item, condition, __bulk?, batch_size?, parallel?}. Line 25512: Checked in output generation. Line 37006: Shown in IngestBulkFeedCtrl default |
| `operation` | string |  | Relationship operation mode. Line 36841: Defaults to 'Overwrite'. Line 36904: Determines __link merge strategy |
| `resource` | object | yes | Form field values + meta keys __replace (string), __fieldsToUpdate (array, optional), __link (relationship mapping). Line 36906: __replace recalculated on save. Supports jinja in field values |

#### IngestBulkFeed — `ingest_bulk_feed`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `collection` | string | yes | Auto-calculated via $watch. Format enforced by editor, cannot be manually set by user |
| `fieldOperation` | deleted |  | REMOVED: Explicitly deleted. Unlike CreateRecord, IngestBulkFeed does not support field-level operations |
| `for_each` | object |  | Loop configuration initialized. Compile-time: deleted if for_each.item is empty |
| `operation` | deleted |  | REMOVED: Explicitly deleted. CreateRecord defaults to 'Overwrite', but IngestBulkFeed removes it entirely |
| `resource` | object | yes | Field mappings (Record<string, unknown>). Inherited from InsertDataCtrl. Contains field values and __replace key |
| `step_type` | string | yes |  |
| `step_variables` | array | yes |  |
| `uuid` | string | yes |  |
| `when` | string |  | Optional step condition. Deleted if empty at save |

#### Delay — `delay`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `delay` | object | yes | Time-based delay configuration. All time components support jinja expressions (string) or numeric values. Lines 36687-36730 show structure initialization |
| `for_each` | object |  | Optional loop configuration |
| `rule` | object |  | Optional event-based wait rule. Used for event-triggered resume instead of time-based delay. Structure visible in PauseUntilConditionCtrl (+) |
| `step_variables` | array |  |  |
| `timeout` | object |  | Optional timeout configuration for approval/manual-input steps connected after this delay. Lines 36557-36565 show structure. Deleted if isTimeout is false |
| `type` | string |  | Step delay mode. Defaults to 'TimeBased'. Determines if delay is time-based (vs event-based via rule). Only 'TimeBased' observed in DelayCtrl |

#### ManualInput — `manual_input`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `agent_id` | string|null |  | Agent for external communication. Set to null if Slack channel + agent_id conflict. Logic |
| `customEmailExternal` | boolean |  | Enable custom email body for external users. Logic, 37807-37808 |
| `customEmailInternal` | boolean |  | Enable custom email body for internal users. Logic |
| `custom_email_body_external` | string|null |  | Custom HTML body for external emails. Initialized/managed, 37807-37808 |
| `custom_email_body_internal` | string|null |  | Custom HTML body for internal emails. Initialized/managed, 37806 |
| `email_notification` | object |  | Email notification settings. Initialized |
| `external_channel_list` | array |  | List of external communication channel IRIs (e.g., Email, Slack). Initialized. Validated when unauthenticated_input=true |
| `external_email_attachments` | array|null |  | Attachments for external emails. Managed, 37807-37808 |
| `external_email_subject` | string|null |  | Subject for external user emails |
| `inline_channel_list` | array |  | List of internal communication channel IRIs. Initialized. Validated when unauthenticated_input=true |
| `input` | object | yes | Schema object containing the input form definition. Initialized |
| `inputExternalUser` | boolean |  | Allow external users to respond. Validated/cleaned |
| `inputInternalUsers` | boolean |  | Allow internal users to respond. Validated/cleaned |
| `internal_email_attachments` | array|null |  | Attachments for internal emails. Managed, 37806 |
| `internal_email_subject` | string|null |  | Subject for internal user emails |
| `isRecordLinked` | boolean |  | Track whether step is linked to a record context. Logic. When false, disables unauthenticated mode |
| `is_approval` | boolean |  | Set to true for ApprovalManualInput variant. Controls approval-style options (Approve/Reject) |
| `message` | object |  | Message/logging metadata (system key). Not usually set for ManualInput |
| `owner_detail` | object | yes | Specifies who receives the manual input request. Initialized |
| `record` | string | yes | IRI/reference to the record being worked on |
| `resources` | string |  | Module/resource type for record context |
| `response_mapping` | object | yes | Maps response options to next steps. Initialized. connecteStepsLength is DELETED before POST |
| `step_variables` | object|array | yes |  |
| `timeout` | object |  | Timeout configuration for awaiting response. Validated (max 7 days, 168 hours, 10080 minutes) |
| `type` | enum | yes | Always 'InputBased' for ManualInput steps (set in editor). ManualInput and ApprovalManualInput both use this step type with different is_approval flags |
| `unauthenticated_input` | boolean |  | Allows external/unauthenticated users to respond. Initialized. When true, triggers agent mode logic |

#### CodeSnippet — `code_snippet`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `agent` | string |  | Agent UUID for remote execution; set, 37454; deleted if not applicable |
| `config` | string |  | Configuration UUID; set conditionally, 37450; null if operation has is_config_required=false |
| `connector` | string | yes | CodeSnippet connector name; set by ConnectorStepCtrl.setActiveConnector() |
| `for_each` | string |  | Loop config: {condition, item, __bulk?, parallel?, break_loop?}; clears break_loop on agent mode toggle |
| `ignore_errors` | string |  | Suppress errors; standard connector-step key |
| `message` | string |  | Notification: {content, records, tags?, tenant?, thread?, type?, parentstepid?}; standard connector-step key |
| `name` | string |  | Display name from connector label; set |
| `operation` | string | yes | Operation name (e.g., execute_code); set by operationChanged() |
| `operationTitle` | string | yes | Human-readable title; set from operation.title |
| `params` | object | yes | Parameters object, populated from operation.parameters; for CodeSnippet includes python_function key |
| `step_variables` | unknown | yes | Step output schema |
| `version` | string | yes | Connector version; set, 37402, 37441; updated on agent change |
| `when` | string |  | Jinja conditional expression for step execution; standard connector-step key |

#### Approval — `approval`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `approvers` | array |  | LEGACY/BACKWARD-COMPAT - old format; array; parsed and deleted after converting to resource.assignedTo/resource.owners; contains {type:'User'\|'Team', '@id':..., ...} |
| `collection` | enum |  | Set by ApprovalStepCtrl; hardcoded enum value 'approvals' |
| `message` | string |  | LEGACY/BACKWARD-COMPAT - old format; moved to arguments.resource.approvaldescription, then deleted |
| `resource` | object | yes | Initialized; contains approvals entity fields. ApprovalStepCtrl populates: playbookiri, playbookuuid, playbookname, assignedTo, owners, userOwners, approvaldescription, status. Validation requires… |
| `response_mapping` | object |  | Optional; used in compile transforms. If present contains 'options' array with step_iri values transformed to full API paths |
| `step_type_name` | string |  | Editor registers widget 'Approval' of bundle |
| `step_type_uuid` | iri |  | APPROVAL_STEP_TYPE constant defined; appears in compile transforms |
| `timeout` | object |  | Optional timeout config; if present has: days, hours, minutes, step_iri |

#### ManualTask — `create_task`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `collection` | string | yes | Hardcoded by editor (ManualTaskCtrl). Always 'tasks' collection |
| `message` | object |  | Optional system key |
| `resource` | object | yes | Task record fields. Editor loads fields dynamically from Entity('tasks'). Structure determined by tasks module schema at runtime |
| `step_variables` | array |  |  |

#### SetAPIKeys — `set_api_keys`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `private_key` | string | yes | Supports Jinja expressions/tags. Controller validates via dynamicValueService.isJinjaConvertibleToTag() |
| `public_key` | string | yes | Supports Jinja expressions/tags. Controller validates via dynamicValueService.isJinjaConvertibleToTag() |

#### WorkflowReference — `workflow_reference`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `apply_async` | boolean |  | Execute referenced playbook asynchronously |
| `arguments` | object |  | Map of parameter name → value to pass to the referenced playbook. Filtered by playbook.parameters list. Supports jinja expressions |
| `do_until` | object |  |  |
| `for_each` | object |  |  |
| `ignore_errors` | boolean |  |  |
| `message` | object |  |  |
| `mock_result` | string |  |  |
| `pass_input_record` | boolean |  | Pass input record to referenced playbook. Initialized; mutually exclusive with pass_parent_env. Default injected when undefined |
| `pass_parent_env` | boolean |  | Pass parent environment to referenced playbook. Initialized; mutually exclusive with pass_input_record. Default injected when undefined |
| `step_variables` | object |  |  |
| `when` | string |  |  |
| `workflowReference` | string | yes | IRI of the referenced playbook (e.g., /api/3/workflows/{uuid}), or jinja expression string. Set by WorkflowReferenceCtrl from selected playbook @id |

#### cybersponse.post_create — `start_on_create`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `fieldbasedtrigger` | object | yes |  |
| `resource` | string | yes |  |
| `resources` | array |  |  |
| `step_variables` | object | yes |  |
| `triggerOnReplicate` | boolean |  |  |
| `triggerOnSource` | boolean |  |  |

#### cybersponse.post_update — `start_on_update`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `fieldbasedtrigger` | object |  | Filter-based trigger definition. Contains: filters (array of filter conditions), logic (string: 'AND' or 'OR'). Initialized in prepareResourceField. Line 23834-23836 |
| `resource` | string |  | Deprecated single module type. Converted to resources array on init. Line 23754 |
| `resources` | array | yes | Array of module IRI/type strings that trigger the playbook. When any record of these modules is updated, the playbook is triggered. Line 23744, 23803, 23823 |
| `step_variables` | object |  | Auto-generated by editor during compilation. Input field is deleted on init and rebuilt by compiler to: { input: { records: ["{{vars.input.records[0]}}"] } }. Lines 23725, 34569-34571 |
| `triggerOnReplicate` | boolean |  | For post_update/pre_update only: trigger when record is replicated. Maps to 'replicated' option in UI. Line 23726, 23734 |
| `triggerOnSource` | boolean |  | For post_update/pre_update only: trigger when record is created (source). Maps to 'created' option in UI. Line 23726, 23734 |

#### cybersponse.api_call — `api_endpoint`

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `authentication_methods` | array | yes | Array of authentication method values. Editor reads from authSelection and constructs this array. Line 23778-23779: editor finds matching authOption based on this value |
| `inputVariables` | array |  | Array of input variable definitions. Line 23784: initialized with default empty array. Line 23830: used for input focus handling with _expanded property on items |
| `resources` | array |  | Array of module IRIs (entity types). Line 23754: if arguments.resource exists, converted to resources array. Line 23784, 23787: initialization in ACTION_TRIGGER case (applies to all triggers). Line… |
| `route` | string | yes | API endpoint route. For APIEndpoint (this UUID), route is PRESERVED during export (not regenerated). For other step types with route, it IS regenerated. Line 33438: route regeneration conditional o… |
| `step_variables` | object | yes | COMPILE-TIME TRANSFORM: During step save for API_TRIGGER, set to {params:{api_body:'{{vars.request.data}}',api_params:'{{vars.request.params}}'}}. Line 34553-34558. Line 23725: deleted during initi… |
| `triggerOnReplicate` | boolean |  | Trigger when records are replicated. Line 23726: defaults to false if __triggerLimit true. Line 23734: set by updateTriggerLimit |
| `triggerOnSource` | boolean |  | Trigger when records are created/modified on source. Line 23726: defaults to true, modified by param.triggerLimit. Line 23734: set by updateTriggerLimit |

#### CyopsUtilites — _(no alias)_

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `agent` | string |  | Optional agent assignment for remote execution. Set by ConnectorStepCtrl |
| `config` | string |  |  |
| `connector` | string | yes |  |
| `do_until` | object |  | Retry loop config |
| `for_each` | object |  | Loop execution config |
| `ignore_errors` | boolean |  | Suppress step failure errors |
| `message` | object |  | Logging/audit message |
| `name` | string |  | Step display name. Set by ConnectorStepCtrl. Empty means not set |
| `operation` | string | yes |  |
| `operationTitle` | string | yes | Human-readable operation title. Set by ConnectorStepCtrl from operation.title |
| `params` | object | yes |  |
| `step_variables` | unknown | yes |  |
| `version` | string | yes |  |
| `when` | string |  | Conditional execution Jinja expression |

#### cybersponse.action — _(no alias)_

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `inputVariables` | array | yes | Array of input variable definitions. Each variable can have name, type, formType, label, defaultValue, required, and many other UI/validation properties. Stored in the step arguments; compiled into… |
| `resources` | array | yes | Array of module/collection IRIs that define which entities this manual start action can be triggered on. Empty array means 'no record execution' mode |
| `route` | string |  | Unique route identifier for this action trigger. Generated at init if not set. Format: UUID or API path string |
| `step_variables` | object | yes | Object containing step output variables. Compiler auto-populates step_variables.input with params (mapped from inputVariables) and records='{{vars.input.records}}' |
| `title` | string |  | Display title for this action trigger. Used in execution logs and action menus. Falls back to step name if not set |
| `triggerOnReplicate` | boolean |  | Whether to trigger when record replicated. Only applies if __triggerLimit=true |
| `triggerOnSource` | boolean |  | Whether to trigger when record created on source. Only applies if __triggerLimit=true |

#### SendEmail — _(no alias)_

| Argument | Type | Required | Meaning |
|----------|------|----------|---------|
| `attachments` | array |  | Email attachments. Not exposed in SendEmailCtrl; could be in params per inferred schema. Form handling not visible in bundle |
| `bcc` | array(string) |  | Blind carbon copy recipients. Not directly exposed in SendEmailCtrl; present in inferred params schema as optional bcc_recipients field. Possible implementation gap |
| `cc` | array(string) |  | Carbon copy recipients. Not directly exposed in SendEmailCtrl in bundle; present in inferred params schema as optional cc_recipients field. Possible implementation gap or hidden in template |
| `config` | string | yes |  |
| `connector` | string | yes |  |
| `content` | string |  | Email body content. Handled via richtext editor with Field({name: 'content', formType: 'richtext', title: 'Content'}). Set via getMarkDown callback |
| `for_each` | object |  | Loop iteration. Optional system key. If set with __bulk=true, batch_size defaults to 100. Deleted if item is empty at compile-time |
| `from_str` | string | yes | Sender email address. Defaults to SMTP settings defaultFrom or DEFAULT_FROM_EMAIL injection |
| `ignore_errors` | boolean |  | Optional system key (inferred schema). Error handling flag |
| `message` | object |  | Optional system key (inferred schema). Deleted if content is empty at compile-time |
| `mock_result` | string |  | Optional (inferred schema). Deleted if empty at compile-time |
| `name` | string |  | Display name from connector label; set. Emitted by the compiler into arguments (e.g. 'SMTP') alongside connector/config |
| `operation` | string |  | Optional system key |
| `operationTitle` | string |  | Optional |
| `params` | object |  | Optional system key |
| `step_variables` | unknown | yes |  |
| `subject` | string |  | Email subject line. Not exposed in SendEmailCtrl controller; present in inferred schema params as required iri_list+subject. Possible implementation gap or stored differently |
| `timeout` | object |  | Excluded from arguments via excludes=['timeout']. Not permitted for SendEmail steps |
| `to` | array(string) |  | Email recipient addresses. Converted from/to jinja tags format via convertVarsToTag/convertTagsToVar filters. In editor, joined with commas for display |
| `version` | string | yes |  |
| `when` | string |  | Execution condition. Optional (inferred schema) |

<!-- END GENERATED STEP REFERENCE -->
