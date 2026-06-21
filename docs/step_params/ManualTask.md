---
title: ManualTask Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- manual-task
- step-parameters
canonical: false
summary: ManualTask step parameter reference.
---

# ManualTask

- FSR step_type_name: `ManualTask`
- Resolver short type: `manual_task`
- Corpus rows with arguments: **6**

## Resolver allowlists (friendly + canonical)

_(no resolver mapping or no allowlists declared)_

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `collection` | 6 | 100.0% | ✗ unrecognized |
| `resource` | 6 | 100.0% | ✗ unrecognized |
| `step_variables` | 6 | 100.0% | ✓ |
| `message` | 3 | 50.0% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `collection` (6 rows)
- `resource` (6 rows)
- `message` (3 rows)
