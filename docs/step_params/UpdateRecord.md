---
title: UpdateRecord Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- update-record
- step-parameters
canonical: false
summary: UpdateRecord step parameter reference.
---

# UpdateRecord

- FSR step_type_name: `UpdateRecord`
- Resolver short type: `update_record`
- Corpus rows with arguments: **385**

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
| `collection` | 385 | 100.0% | ✓ |
| `resource` | 385 | 100.0% | ✓ |
| `collectionType` | 383 | 99.5% | ✓ |
| `step_variables` | 383 | 99.5% | ✓ |
| `operation` | 377 | 97.9% | ✓ |
| `fieldOperation` | 367 | 95.3% | ✓ |
| `__recommend` | 280 | 72.7% | ✓ |
| `_showJson` | 244 | 63.4% | ✓ |
| `message` | 137 | 35.6% | ✗ unrecognized |
| `when` | 59 | 15.3% | ✗ unrecognized |
| `for_each` | 52 | 13.5% | ✓ |
| `tagsOperation` | 35 | 9.1% | ✗ unrecognized |
| `ignore_errors` | 5 | 1.3% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `message` (137 rows)
- `when` (59 rows)
- `tagsOperation` (35 rows)
- `ignore_errors` (5 rows)
