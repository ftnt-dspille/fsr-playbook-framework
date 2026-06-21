---
title: CodeSnippet Step Parameters
category: playbook-authoring
status: reference
source: hand-written
topics:
- code-snippet
- python
- jinja
canonical: false
summary: CodeSnippet step parameter reference.
---

# CodeSnippet

- FSR step_type_name: `CodeSnippet`
- Resolver short type: `code_snippet`
- Corpus rows with arguments: **28**

## Resolver allowlists (friendly + canonical)

| friendly | canonical |
|---|---|
| `code` | `connector` |
| `condition` | `operation` |
| `config` | `operationTitle` |
| `mock_result` | `params` |
| `python` | `pickFromTenant` |
|  | `step_variables` |
|  | `version` |

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `config` | 28 | 100.0% | ✓ |
| `connector` | 28 | 100.0% | ✓ |
| `operation` | 28 | 100.0% | ✓ |
| `operationTitle` | 28 | 100.0% | ✓ |
| `params` | 28 | 100.0% | ✓ |
| `step_variables` | 28 | 100.0% | ✓ |
| `version` | 28 | 100.0% | ✓ |
| `when` | 2 | 7.1% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `when` (2 rows)
