# cybersponse.post_update

- FSR step_type_name: `cybersponse.post_update`
- Resolver short type: `start_on_update`
- Corpus rows with arguments: **59**

## Resolver allowlists (friendly + canonical)

| friendly | canonical |
|---|---|
| `condition` | `__triggerLimit` |
| `mock_result` | `fieldbasedtrigger` |
| `module` | `resource` |
| `modules` | `resources` |
| `when` | `step_variables` |
|  | `triggerOnReplicate` |
|  | `triggerOnSource` |
|  | `useMockOutput` |

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `fieldbasedtrigger` | 59 | 100.0% | ✓ |
| `resource` | 59 | 100.0% | ✓ |
| `step_variables` | 59 | 100.0% | ✓ |
| `resources` | 54 | 91.5% | ✓ |
| `__triggerLimit` | 21 | 35.6% | ✓ |
| `triggerOnReplicate` | 21 | 35.6% | ✓ |
| `triggerOnSource` | 21 | 35.6% | ✓ |
| `version` | 1 | 1.7% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `version` (1 rows)
