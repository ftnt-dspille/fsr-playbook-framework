---
title: Cybersponse API Call
category: playbook-authoring
status: reference
source: hand-written
topics:
- api-call
- integration
canonical: false
summary: Cybersponse API call step reference.
---

# cybersponse.api_call

- FSR step_type_name: `cybersponse.api_call`
- Resolver short type: `start_on_api_call`
- Corpus rows with arguments: **18**

## Resolver allowlists (friendly + canonical)

_(no resolver mapping or no allowlists declared)_

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `authentication_methods` | 18 | 100.0% | ✗ unrecognized |
| `route` | 18 | 100.0% | ✗ unrecognized |
| `step_variables` | 17 | 94.4% | ✓ |
| `triggerOnReplicate` | 9 | 50.0% | ✗ unrecognized |
| `triggerOnSource` | 9 | 50.0% | ✗ unrecognized |
| `__triggerLimit` | 8 | 44.4% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `authentication_methods` (18 rows)
- `route` (18 rows)
- `triggerOnReplicate` (9 rows)
- `triggerOnSource` (9 rows)
- `__triggerLimit` (8 rows)
