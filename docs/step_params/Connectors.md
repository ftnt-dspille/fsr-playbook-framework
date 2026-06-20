# Connectors

- FSR step_type_name: `Connectors`
- Resolver short type: `connector`
- Corpus rows with arguments: **1,332**

## Resolver allowlists (friendly + canonical)

| friendly | canonical |
|---|---|
|  | `condition` |
|  | `config` |
|  | `connector` |
|  | `mock_result` |
|  | `name` |
|  | `operation` |
|  | `operationTitle` |
|  | `params` |
|  | `pickFromTenant` |
|  | `step_variables` |
|  | `useMockOutput` |
|  | `version` |

> **Note:** connector accepts any registered op parameter at the arguments root; the resolver auto-lifts op-specific keys into `params:`. Unrecognized-key detection is suppressed because the universe is per-op, not static.

## Corpus observations (top-level arguments keys)

| key | count | % of rows | accepted? |
|---|---:|---:|---|
| `connector` | 1332 | 100.0% | ✓ |
| `operation` | 1332 | 100.0% | ✓ |
| `version` | 1332 | 100.0% | ✓ |
| `params` | 1331 | 99.9% | ✓ |
| `name` | 1330 | 99.8% | ✓ |
| `operationTitle` | 1328 | 99.7% | ✓ |
| `config` | 1273 | 95.6% | ✓ |
| `step_variables` | 1073 | 80.6% | ✓ |
| `pickFromTenant` | 498 | 37.4% | ✓ |
| `mock_result` | 115 | 8.6% | ✓ |
| `operationOutput` | 53 | 4.0% | ✗ unrecognized |
| `ignore_errors` | 46 | 3.5% | ✗ unrecognized |
| `when` | 38 | 2.9% | ✗ unrecognized |
| `for_each` | 30 | 2.3% | ✓ |
| `message` | 18 | 1.4% | ✗ unrecognized |
| `do_until` | 12 | 0.9% | ✗ unrecognized |
| `annotation` | 5 | 0.4% | ✗ unrecognized |
| `agent` | 3 | 0.2% | ✗ unrecognized |
| `displayConditions` | 1 | 0.1% | ✗ unrecognized |
| `executeButtonText` | 1 | 0.1% | ✗ unrecognized |
| `inputVariables` | 1 | 0.1% | ✗ unrecognized |
| `noRecordExecution` | 1 | 0.1% | ✗ unrecognized |
| `resources` | 1 | 0.1% | ✗ unrecognized |
| `route` | 1 | 0.1% | ✗ unrecognized |
| `singleRecordExecution` | 1 | 0.1% | ✗ unrecognized |
| `title` | 1 | 0.1% | ✗ unrecognized |
| `apply_async` | 1 | 0.1% | ✗ unrecognized |
| `from_str` | 1 | 0.1% | ✗ unrecognized |
| `ip` | 1 | 0.1% | ✗ unrecognized |
| `ip_block_policy` | 1 | 0.1% | ✗ unrecognized |
| `ip_group_name` | 1 | 0.1% | ✗ unrecognized |
| `ip_type` | 1 | 0.1% | ✗ unrecognized |
| `method` | 1 | 0.1% | ✗ unrecognized |
| `ngfw_mode` | 1 | 0.1% | ✗ unrecognized |
| `time_to_live` | 1 | 0.1% | ✗ unrecognized |
