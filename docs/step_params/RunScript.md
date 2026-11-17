---
title: RunScript Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- run-script
- bash
- step-parameters
canonical: false
summary: RunScript step parameter reference.
---

# RunScript

- FSR step_type_name: `RunScript`
- Resolver short type: `run_script`
- Corpus rows with arguments: **4**

## Resolver allowlists (friendly + canonical)

_(no resolver mapping or no allowlists declared)_

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `arguments` | 4 | 100.0% | ✗ unrecognized |
| `script` | 4 | 100.0% | ✗ unrecognized |
| `step_variables` | 3 | 75.0% | ✓ |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `arguments` (4 rows)
- `script` (4 rows)
