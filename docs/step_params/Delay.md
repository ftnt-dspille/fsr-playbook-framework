# Delay

- FSR step_type_name: `Delay`
- Resolver short type: `utils_delay`
- Corpus rows with arguments: **32**

## Resolver allowlists (friendly + canonical)

| friendly | canonical |
|---|---|
| `condition` | `connector` |
| `days` | `operation` |
| `hours` | `operationTitle` |
| `minutes` | `params` |
| `mock_result` | `step_variables` |
| `seconds` | `version` |

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `delay` | 32 | 100.0% | ✗ unrecognized |
| `rule` | 29 | 90.6% | ✗ unrecognized |
| `type` | 29 | 90.6% | ✗ unrecognized |
| `step_variables` | 8 | 25.0% | ✓ |
| `timeout` | 7 | 21.9% | ✗ unrecognized |
| `for_each` | 5 | 15.6% | ✓ |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `delay` (32 rows)
- `rule` (29 rows)
- `type` (29 rows)
- `timeout` (7 rows)
