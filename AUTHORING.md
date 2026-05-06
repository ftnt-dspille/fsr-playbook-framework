# Authoring playbooks in YAML

This is the working guide for writing FortiSOAR playbooks in the simplified
YAML the compiler accepts. For the bigger picture (compiler internals,
roadmap, MCP integration) see `ARCHITECTURE.md`. For source-of-truth API
details see `~/PycharmProjects/soar-reporting-dashboard-cl/docs/FORTISOAR_API.md`.

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
    is_active: false
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
| `set_variable` | `SetVariable` | `set_multiple` | `arg_list: [{name, value}, …]` or flat `{name: value}` |
| `decision` | `Decision` | `cond` | `conditions: [{option, condition}]` + `branches:` |
| `connector` | `Connectors` | `connector` | `connector, operation, params, version, config, step_variables` |
| `stop` / `end` | `Connectors` (cyops_utilities `no_op`) | `connector` | (no args — synthesized as Utils: No Operation) |
| `find_record` | `FindRecords` | `find_data` | `module, query, partial` |
| `create_record` | `InsertData` | `insert_data` | `module` (→ `collection`), `resource`, `operation` |
| `update_record` | `UpdateRecord` | `update_data` | `collection` (record IRI), `module` (→ `collectionType`), `resource`, `operation` |
| `insert_record` | `InsertData` | `insert_data` | legacy alias for `create_record` |
| `delay` | `Delay` | `delay` | `seconds` (or `minutes`/`hours`/`days`) |
| `manual_input` | `ManualInput` | `manual_input` | `title, description, options: [...], inputs: []` |
| `code_snippet` | `CodeSnippet` | `connector` | `code: |...`, optional `config: <friendly-name>` |
| `approval` | `Approval` | `approval` | `collection, resource` |
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
| `no_trigger` | no trigger step in a playbook | every playbook needs exactly one `start`, `start_on_create`, or `start_on_update` |

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
