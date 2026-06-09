# FindRecords

- FSR step_type_name: `FindRecords`
- Resolver short type: `find_records`
- Corpus rows with arguments: **305**

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
| `module` | 305 | 100.0% | ✓ |
| `query` | 305 | 100.0% | ✗ unrecognized |
| `step_variables` | 305 | 100.0% | ✓ |
| `checkboxFields` | 245 | 80.3% | ✗ unrecognized |
| `when` | 7 | 2.3% | ✗ unrecognized |
| `message` | 6 | 2.0% | ✗ unrecognized |
| `do_until` | 3 | 1.0% | ✗ unrecognized |
| `for_each` | 3 | 1.0% | ✓ |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `query` (305 rows)
- `checkboxFields` (245 rows)
- `when` (7 rows)
- `message` (6 rows)
- `do_until` (3 rows)
