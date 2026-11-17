---
title: InsertData Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- insert-data
- step-parameters
canonical: false
summary: InsertData step parameter reference.
---

# InsertData

- FSR step_type_name: `InsertData`
- Resolver short type: `create_record`
- Corpus rows with arguments: **300**

## Resolver allowlists (friendly + canonical)

| friendly | canonical |
|---|---|
| `condition` | `__bulk` |
| `mock_result` | `__recommend` |
| `module` | `_showJson` |
|  | `collection` |
|  | `collectionType` |
|  | `fieldOperation` |
|  | `operation` |
|  | `resource` |
|  | `step_variables` |
|  | `useMockOutput` |

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `collection` | 300 | 100.0% | ✓ |
| `resource` | 300 | 100.0% | ✓ |
| `step_variables` | 300 | 100.0% | ✓ |
| `operation` | 274 | 91.3% | ✓ |
| `fieldOperation` | 273 | 91.0% | ✓ |
| `__recommend` | 210 | 70.0% | ✓ |
| `_showJson` | 193 | 64.3% | ✓ |
| `for_each` | 56 | 18.7% | ✓ |
| `when` | 23 | 7.7% | ✗ unrecognized |
| `message` | 18 | 6.0% | ✗ unrecognized |
| `is_upsert` | 2 | 0.7% | ✗ unrecognized |
| `config` | 2 | 0.7% | ✗ unrecognized |
| `version` | 2 | 0.7% | ✗ unrecognized |
| `tagsOperation` | 1 | 0.3% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `when` (23 rows)
- `message` (18 rows)
- `is_upsert` (2 rows)
- `config` (2 rows)
- `version` (2 rows)
- `tagsOperation` (1 rows)
