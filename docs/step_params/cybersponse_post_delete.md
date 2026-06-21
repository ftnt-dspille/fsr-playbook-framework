---
title: Cybersponse Post Delete Trigger
category: playbook-authoring
status: reference
source: hand-written
topics:
- trigger
- post-delete
canonical: false
summary: Cybersponse post-delete trigger reference.
---

# cybersponse.post_delete

- FSR step_type_name: `cybersponse.post_delete`
- Resolver short type: `start_on_delete`
- Corpus rows with arguments: **1**

## Resolver allowlists (friendly + canonical)

_(no resolver mapping or no allowlists declared)_

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `__triggerLimit` | 1 | 100.0% | ✗ unrecognized |
| `fieldbasedtrigger` | 1 | 100.0% | ✗ unrecognized |
| `resource` | 1 | 100.0% | ✗ unrecognized |
| `resources` | 1 | 100.0% | ✗ unrecognized |
| `step_variables` | 1 | 100.0% | ✓ |
| `triggerOnReplicate` | 1 | 100.0% | ✗ unrecognized |
| `triggerOnSource` | 1 | 100.0% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `__triggerLimit` (1 rows)
- `fieldbasedtrigger` (1 rows)
- `resource` (1 rows)
- `resources` (1 rows)
- `triggerOnReplicate` (1 rows)
- `triggerOnSource` (1 rows)
