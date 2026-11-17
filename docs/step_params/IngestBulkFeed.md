---
title: IngestBulkFeed Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- ingest-bulk-feed
- threat-feed
- step-parameters
canonical: false
summary: IngestBulkFeed step parameter reference.
---

# IngestBulkFeed

- FSR step_type_name: `IngestBulkFeed`
- Resolver short type: `ingest_bulk_feed`
- Corpus rows with arguments: **18**

## Resolver allowlists (friendly + canonical)

_(no resolver mapping or no allowlists declared)_

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `collection` | 18 | 100.0% | ✗ unrecognized |
| `resource` | 18 | 100.0% | ✗ unrecognized |
| `step_variables` | 18 | 100.0% | ✓ |
| `for_each` | 16 | 88.9% | ✓ |
| `__recommend` | 14 | 77.8% | ✗ unrecognized |
| `_showJson` | 8 | 44.4% | ✗ unrecognized |
| `when` | 5 | 27.8% | ✗ unrecognized |
| `mock_result` | 2 | 11.1% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `collection` (18 rows)
- `resource` (18 rows)
- `__recommend` (14 rows)
- `_showJson` (8 rows)
- `when` (5 rows)
- `mock_result` (2 rows)
