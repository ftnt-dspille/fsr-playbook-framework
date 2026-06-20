# `for_each` — looping over a list

## The one rule that breaks agents

`for_each` is a **step modifier**, not a step type. It lives at the
top level of an existing step, alongside `arguments:`. There is no
`type: for_each`. The compiler rejects it with a did-you-mean.

```yaml
# WRONG — `type: for_each` is not a thing.
- type: for_each
  arguments:
    list: "{{ vars.alerts }}"
    steps: [...]            # there is no "body" key

# RIGHT — modify a real step.
- type: create_record
  name: Create Alert Per Item
  for_each:
    item: "{{ vars.steps.Build_Alerts.alerts_to_create }}"
    parallel: false
  arguments:
    module: alerts
    operation: Replace
    resource:
      name: "{{ vars.item.name }}"
      severity: "{{ vars.item.severity }}"
```

The iterating element is bound as `vars.item` inside the step.

## Where it's valid (host allowlist)

Compiler-enforced. Derived from 369 corpus uses across 1,669 playbooks.

| Host step type | Typical use |
|---|---|
| `workflow_reference` | Fan out per-record to a child playbook (most common) |
| `update_record` | Bulk field updates, often with `__bulk: true` |
| `create_record` | Create N records from a list |
| `find_record` | Run a parameterized query per element |
| `connector` | Call an op once per element |
| `set_variable` | Build per-element values into env |
| `delay` | Stagger per-element waits |
| `code_snippet` | Per-element transform |
| `send_mail` | Per-element notification |
| `ingest_bulk_feed` | Bulk threat-feed ingest (`__bulk: true` ~89%) |

Rejected by the parser (`bad_value` at `<step>.for_each`):
`start`, `start_on_create`, `start_on_update`, `decision`, `end`,
`manual_input`. These steps gate control flow and cannot be iterated.

## Fields

```yaml
for_each:
  item: "{{ vars.list }}"   # required — Jinja list expression
  parallel: false           # default; true fans out concurrently
  condition: ""             # optional Jinja gate; falsy → skip iteration
  __bulk: false             # batched mode (update/create/ingest)
  batch_size: 100           # required when __bulk: true
  break_loop: ""            # do-while; truthy iteration is INCLUDED
```

Unknown keys are rejected. `item` is required.

## Modes

| Mode | When | Caveats |
|---|---|---|
| **Sequential** (`parallel: false`) | Default. Order matters, downstream reads need the *last* iteration's env. | `vars.steps.<loop>.<key>` falls through to last iteration's value. |
| **Parallel** (`parallel: true`) | Independent work — API calls, child playbooks per record. | `vars.steps.<loop>.<key>` returns `None` (race). Read the per-iteration list instead. With `workflow_reference`, set `pass_parent_env: false` to avoid races on parent env. |
| **Bulk** (`__bulk: true`, `batch_size: N`) | `update_record` / `create_record` / `ingest_bulk_feed` against large lists. | Server-side batching — much faster than per-row. Use only on the step types listed. |

## Runtime shape (`vars.steps.<loop>` after completion)

`vars.steps.<loop_step>` is a **list of per-iteration dicts**, not the
last value. Each dict carries the body's `set_var` / `mock_result`
keys plus a `task_id`. Sequential mode aliases `.<key>` to the last
iteration's value via env; parallel mode does not (race).

`break_loop` is do-while semantics: the iteration where the
expression becomes truthy IS in the result list, not excluded.

## Common pitfalls

1. **Treating `for_each` as a step type.** Compiler rejects with the
   "modifier, not a type" hint. Fix: move it onto a real step.
2. **`vars.item` outside the loop body.** It's only bound during
   iteration. After the loop, reference `vars.steps.<loop>[i].<key>`.
3. **Parallel + `vars.steps.<loop>.<key>`.** Race. Iterate the result
   list instead, or run sequentially if order matters.
4. **`__bulk: true` on the wrong host.** Only `update_record`,
   `create_record`, `ingest_bulk_feed` support it. Compiler does not
   yet enforce — verify against the host allowlist above.
5. **Missing `batch_size` with `__bulk`.** Server picks a default but
   it varies; set explicitly (corpus default is `100`).
6. **`workflow_reference` + `parallel: true` + `pass_parent_env: true`.**
   Children read parent env concurrently — undefined ordering. Set
   `pass_parent_env: false` (or use sequential).

## Canonical example

`examples/demo_for_each.yaml` — sequential `create_record` over a
static list with `vars.item.<field>` substitution. Use this as the
template when in doubt.
