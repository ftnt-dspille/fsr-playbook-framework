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
      - ...
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
| `start` | `cybersponse.abstract_trigger` | (trigger) | (none — just routes downstream) |
| `set_variable` | `SetVariable` | `set_multiple` | `arg_list: [{name, value}, …]` |
| `decision` | `Decision` | `cond` | `conditions: [{option, condition}]` + `branches:` |
| `connector` | `Connectors` | `connector` | `connector, operation, params, version, config` |
| `find_record` | `FindRecords` | `find_data` | `module, query, partial` |
| `update_record` | `UpdateRecord` | `update_data` | `collection, resource` |
| `insert_record` | `InsertData` | `insert_data` | `collection, resource` |
| `delay` | `Delay` | `delay` | `delay` (seconds) |
| `manual_input` | `ManualInput` | `manual_input` | `record, type, input, timeout` |
| `code_snippet` | `CodeSnippet` | `connector` | (uses connector dispatch internally) |
| `approval` | `Approval` | `approval` | `collection, resource` |
| `workflow_reference` | `WorkflowReference` | (per-type validator) | `target` (local name) or `workflowReference` (IRI) + `arguments` |

Other FSR step types (`cybersponse.action`, `RestApi`, `RunScript`,
`ParallelExecution`, `MapPlaybook`, `FetchEmail`) round-trip
correctly through the compiler — they just don't have a friendly short
alias yet. Use the canonical name in `type:` when you need them.

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

## Variables and Jinja

Inside a playbook you read state via Jinja templates:

| Expression | What it gives you |
|---|---|
| `{{ vars.input.records[0] }}` | the trigger record (alert/incident/etc.) |
| `{{ vars.input.params.<name> }}` | input param declared in `parameters:` |
| `{{ vars.steps.<step_id>.<field> }}` | output of a previous step |
| `{{ vars.<name> }}` | a variable set via `set_variable` |
| `{{ vars.env.<key> }}` | env-level variables (organization, user, …) |

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
| `bad_value` | wrong shape for a field (e.g. `branches:` not a mapping) | check the column types in the table above |
| `no_trigger` | no `start` step in a playbook | every playbook needs exactly one `type: start` |

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

## What the compiler does NOT validate (yet)

- **Jinja template correctness** — we accept any string in jinja contexts;
  type-mismatches surface only at runtime. The reference store has type
  data per filter (run `fsrpb explain filter <name>` to see) but the
  compiler doesn't yet flow-type pipelines.
- **`for_each` / `do_until` semantics** — accepted as opaque mappings.
- **Permission checks** — the compiler trusts you have RBAC on the
  modules / connectors you reference.
- **Schedule definitions** — `schedules:` on a playbook isn't yet
  modeled in the IR.

These are tracked in `TODO.md` §6 (Smaller wishes).
