# WorkflowReference

- FSR step_type_name: `WorkflowReference`
- Resolver short type: `workflow_reference`
- Corpus rows with arguments: **624**

## Resolver allowlists (friendly + canonical)

| friendly | canonical |
|---|---|
| `target` | `apply_async` |
|  | `arguments` |
|  | `ignore_errors` |
|  | `pass_input_record` |
|  | `pass_parent_env` |
|  | `step_variables` |
|  | `workflowReference` |

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `arguments` | 624 | 100.0% | ✓ |
| `step_variables` | 624 | 100.0% | ✓ |
| `workflowReference` | 624 | 100.0% | ✓ |
| `apply_async` | 618 | 99.0% | ✓ |
| `pass_input_record` | 570 | 91.3% | ✓ |
| `pass_parent_env` | 532 | 85.3% | ✓ |
| `for_each` | 164 | 26.3% | ✓ |
| `when` | 52 | 8.3% | ✗ unrecognized |
| `ignore_errors` | 28 | 4.5% | ✓ |
| `message` | 9 | 1.4% | ✗ unrecognized |
| `do_until` | 8 | 1.3% | ✗ unrecognized |
| `mock_result` | 2 | 0.3% | ✗ unrecognized |
| `params` | 1 | 0.2% | ✗ unrecognized |

## ⚠ Unrecognized keys (resolver gaps)

These keys appear in real corpus playbooks but the resolver doesn't whitelist them. Either widen the allowlist or confirm FSR ignores them at runtime (probe before adding).

- `when` (52 rows)
- `message` (9 rows)
- `do_until` (8 rows)
- `mock_result` (2 rows)
- `params` (1 rows)
