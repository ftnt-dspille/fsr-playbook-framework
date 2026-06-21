---
title: FortiSOAR Playbook Recipes
category: playbook-authoring
status: reference
source: hand-written
topics:
- recipes
- patterns
- threat-feed
- data-ingest
- examples
canonical: true
summary: Curated multi-step composition patterns (threat-feed ingestion, data-ingest,
  HITL); complete, importable YAML.
---

# FortiSOAR playbook recipes

Generated from `examples/*.yaml` + `store/fsr_reference.db` by `python/store/export_recipes.py`. Recipes are *multi-step* compositions — for per-step shape see `STEP_TYPES.md`, for connector ops see `CONNECTORS.md`.

---

## Curated patterns

Each pattern below is a complete, importable YAML. Compile with `fsrpb compile <file>`; push with `fsrpb push <file>`. They round-trip lossless against the live instance.

### Hello world — start → set_variables → connector

**Use when**: Smoke-testing the compiler end-to-end, or as the skeleton of a one-off automation. Three steps and you're done.

_File_: `examples/hello_connector.yaml`

```yaml
collection: Compiler Demo
description: Smallest possible end-to-end — start, set a variable, call a connector.
visible: true

playbooks:
  - name: Hello Connector
    description: Demonstrates start -> set_variable -> connector flow.
    is_active: false
    steps:
      - id: start
        type: start
        name: Start
        next: prep

      - id: prep
        type: set_variable
        name: Prepare inputs
        arguments:
          arg_list:
            - name: target_org
              value: "Fortinet"
        next: lookup

      - id: lookup
        type: connector
        name: Get organization
        arguments:
          connector: fortinet-fortisiem
          operation: get_org_name_by_org_id
          config: ""
          params:
            domain_id: "{{ vars.target_org }}"
```

---

### Decision branch — route by condition

**Use when**: Any time the next step depends on data: severity tiers, indicator types, IOC categories, approval/deny.

_File_: `examples/decision_branch.yaml`

```yaml
# Branching: a Decision step routes to different next-steps based on a condition.
# Each entry under `branches:` is `<option_label>: <step_id>`. The `option`
# label is what FSR shows on the canvas edge; `condition` is jinja that
# evaluates to truthy/falsy for that branch.
#
# `set_variable` accepts a list of {name, value} pairs in `arg_list`.

collection: Compiler Examples
description: Decision branching with high/low severity routing.
visible: true

playbooks:
  - name: Route By Severity
    description: Demonstrate decision branches.
    steps:
      - id: start
        type: start
        next: read_severity

      - id: read_severity
        type: set_variable
        name: Read severity
        arguments:
          arg_list:
            - name: severity
              value: "{{ vars.input.records[0].severity }}"
        next: severity_decision

      - id: severity_decision
        type: decision
        name: Branch on severity
        arguments:
          conditions:
            - option: high
              condition: "{{ vars.severity in ['critical', 'high'] }}"
              # FSR populates step_iri at runtime from the route binding,
              # but for the compiler we resolve it via `branches:` below.
        branches:
          high: escalate
          low: log_low      # `low` is the implicit "else" — last branch with no condition

      - id: escalate
        type: set_variable
        name: Escalate to Tier 2
        arguments:
          arg_list:
            - name: tier
              value: "tier2"

      - id: log_low
        type: set_variable
        name: Log low-severity
        arguments:
          arg_list:
            - name: tier
              value: "tier1"
```

---

### Find and update — the canonical mutation pattern

**Use when**: Look up a record by query, then mutate it. Most ingestion playbooks reduce to this. Pair with a Decision branch on the find_record result count to handle no-match.

_File_: `examples/find_and_update.yaml`

```yaml
# find_record + update_record — the canonical "look something up, mutate it"
# pattern. Most ingestion playbooks look like this.
#
# `find_record` (handler `find_data`):
#   module: target module name (alerts, incidents, indicators, etc.)
#   query: filter spec; supports `eq`, `contains`, `in`, etc.
#   partial: when true, returns first page only
#
# `update_record` (handler `update_data`):
#   collection: module name (yes, "collection" — the param name is misleading;
#               it's the records collection, not a workflow_collection)
#   resource: dict of {field: new_value}; the record IRI to update is
#             passed via the special `__bulk` mechanism FSR adds at runtime.

collection: Compiler Examples
description: find + update pattern.
visible: true

playbooks:
  - name: Tag Existing Indicator
    description: Look up an indicator by value and tag it.
    parameters:
      - indicator_value
      - tag
    steps:
      - id: start
        type: start
        next: find

      - id: find
        type: find_record
        name: Find indicator by value
        arguments:
          module: indicators
          query:
            logic: AND
            filters:
              - field: value
                operator: eq
                value: "{{ vars.input.params.indicator_value }}"
          partial: true
        next: tag

      - id: tag
        type: update_record
        name: Apply tag
        arguments:
          collection: indicators
          resource:
            tags: "{{ vars.steps.find.records[0].tags + [vars.input.params.tag] }}"
```

---

### Manual input — pause for human approval

**Use when**: Approval flows. Bot proposes an action, user confirms via the FSR UI before the next step runs.

_File_: `examples/manual_input_then_act.yaml`

```yaml
# manual_input — pause execution and ask a human a question.
# Common in approval flows: bot proposes an action, user confirms.
#
# manual_input arguments:
#   record:        IRI of the record to attach the prompt to (alert/incident)
#   type:          input form type (single-select / free-text / etc.)
#   input:         the form definition; rendered in FSR UI
#   timeout:       seconds before the playbook is auto-cancelled
#
# After resume, the user's choice is in `vars.steps.<step_id>.input.<field>`.

collection: Compiler Examples
description: Approval loop — ask a human, then act based on their response.
visible: true

playbooks:
  - name: Confirm Before Block
    description: Ask SOC analyst to approve a block, then act.
    steps:
      - id: start
        type: start
        next: ask

      - id: ask
        type: manual_input
        name: Ask analyst
        arguments:
          record: "{{ vars.input.records[0]['@id'] }}"
          type: single-select
          input:
            title: Block this IP?
            options:
              - block
              - skip
          timeout: 3600    # 1 hour
        next: branch

      - id: branch
        type: decision
        name: Block or skip
        arguments:
          conditions:
            - option: block
              condition: "{{ vars.steps.ask.input.choice == 'block' }}"
        branches:
          block: do_block
          skip: noop

      - id: do_block
        type: set_variable
        name: Pretend we blocked
        arguments:
          arg_list:
            - name: result
              value: blocked

      - id: noop
        type: set_variable
        name: Skip
        arguments:
          arg_list:
            - name: result
              value: skipped
```

---

### Parent calls child — playbook composition

**Use when**: Reusable subroutines. Anything called from more than one place should live in a child playbook + workflow_reference.

_File_: `examples/parent_calls_child.yaml`

```yaml
collection: Multi-Playbook Demo
description: Two playbooks; the parent invokes the child with input parameters.

playbooks:
  - name: Resolve Hostname
    description: Child playbook — looks up an IP for a hostname.
    parameters:
      - hostname
      - dns_server
    steps:
      - id: start
        type: start
        next: lookup
      - id: lookup
        type: set_variable
        name: Stub lookup
        arguments:
          arg_list:
            - name: ip
              value: "10.0.0.1  # would be {{vars.input.params.hostname}} resolved via {{vars.input.params.dns_server}}"

  - name: Add Host And Resolve
    description: Parent — calls Resolve Hostname with input args.
    steps:
      - id: start
        type: start
        next: call_child
      - id: call_child
        type: workflow_reference
        name: Resolve via child playbook
        arguments:
          target: Resolve Hostname        # local-name reference; emitter rewrites to IRI
          arguments:
            hostname: "fsr-1"
            dns_server: "8.8.8.8"
          apply_async: false
          pass_parent_env: false
          pass_input_record: false
          step_variables: []
```

---

## Trigger-type frequency (from live instance)

Which trigger to pick when authoring? Frequencies below are observed across **1664** playbooks on the connected instance. Match your authoring intent to the pattern that already dominates real-world use.

| Trigger step type | Playbooks | When to use |
|---|---:|---|
| `cybersponse.action` | 823 | User clicks a Module Action button on a record. Most common. |
| `cybersponse.abstract_trigger` | 726 | Generic programmatic trigger (called by other playbooks or the API). |
| `cybersponse.post_update` | 59 | Fire when a record is updated in a module. |
| `cybersponse.post_create` | 36 | Fire when a record is created in a module. |
| `cybersponse.api_call` | 18 | External system POSTs to a webhook URL exposed by FSR. |
| `cybersponse.post_delete` | 1 | Fire when a record is deleted in a module. |

---

## Common connector orchestrations

Top connectors invoked by real playbooks on the connected instance. Use this to ground recipe choice — if a connector dominates the table, examples for it likely exist in `pb_examples/all_fsr_evoke_playbooks.json` and can be pulled with `fsrpb pull` for read-only inspection.

| Connector(s) used | Playbook count |
|---|---:|
| `cyops_utilities` | 183 |
| `fortinet-fortimanager-json-rpc` | 83 |
| `fortinet-fortimanager` | 67 |
| `github` | 65 |
| `openai` | 46 |
| `fortigate-firewall` | 46 |
| `fortinet-fortisiem` | 45 |
| `fortinet-fortianalyzer` | 45 |
| `fortinet-fortirecon-easm` | 43 |
| `servicenow` | 37 |
| `fortinet-fortirecon-aci` | 36 |
| `fortinet-fortiedr` | 31 |
| `infoblox-ddi` | 29 |
| `tenable-io` | 26 |
| `fortinet-fortimail` | 26 |
| `fortinet-fortindr-cloud` | 22 |
| `code-snippet` | 21 |
| `abnormal-security` | 20 |
| `exchange` | 19 |
| `fortinet-fortiflex` | 17 |
| `slack` | 16 |
| `alienvault-otx` | 16 |
| `virustotal` | 15 |
| `jira` | 15 |
| `activedirectory` | 15 |

---

**Adding a new recipe**: drop a hand-curated YAML in `examples/`, add a row to `EXAMPLE_HEADERS` in `python/store/export_recipes.py`, regenerate. Recipe YAMLs double as round-trip regression fixtures.
