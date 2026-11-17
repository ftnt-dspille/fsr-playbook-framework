---
title: SendMail Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- send-mail
- email
- step-parameters
canonical: false
summary: SendMail step parameter reference.
---

# SendMail

- FSR step_type_name: `SendMail`
- Resolver short type: `send_email`
- Corpus rows with arguments: **23**

## Resolver allowlists (friendly + canonical)

_(no resolver mapping or no allowlists declared)_

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `config` | 23 | 100.0% | ✗ unrecognized |
| `connector` | 23 | 100.0% | ✗ unrecognized |
| `version` | 23 | 100.0% | ✗ unrecognized |
| `from_str` | 22 | 95.7% | ✗ unrecognized |
| `operation` | 22 | 95.7% | ✗ unrecognized |
| `params` | 22 | 95.7% | ✗ unrecognized |
| `step_variables` | 22 | 95.7% | ✓ |
| `operationTitle` | 21 | 91.3% | ✗ unrecognized |
| `when` | 6 | 26.1% | ✗ unrecognized |
| `for_each` | 1 | 4.3% | ✓ |
| `ignore_errors` | 1 | 4.3% | ✗ unrecognized |
| `message` | 1 | 4.3% | ✗ unrecognized |
| `mock_result` | 1 | 4.3% | ✗ unrecognized |
| `agent` | 1 | 4.3% | ✗ unrecognized |
| `name` | 1 | 4.3% | ✗ unrecognized |
| `pickFromTenant` | 1 | 4.3% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `config` (23 rows)
- `connector` (23 rows)
- `version` (23 rows)
- `from_str` (22 rows)
- `operation` (22 rows)
- `params` (22 rows)
- `operationTitle` (21 rows)
- `when` (6 rows)
- `ignore_errors` (1 rows)
- `message` (1 rows)
- `mock_result` (1 rows)
- `agent` (1 rows)
- `name` (1 rows)
- `pickFromTenant` (1 rows)
