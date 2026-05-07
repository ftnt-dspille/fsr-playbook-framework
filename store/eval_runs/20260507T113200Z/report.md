# Eval run `20260507T113200Z`

- ts: 2026-05-07T11:32:00.310740+00:00
- live: False
- tasks: 15
- models: gold, echo

## Per-cell results

| model | task | L1 | L1.5 | L2 | L3 | L4 | gold | score | ms |
|---|---|---|---|---|---|---|---|---:|---:|
| `gold` | `hello_connector` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 32 |
| `gold` | `decision_branch` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 36 |
| `gold` | `alert_action_var_chain` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 38 |
| `gold` | `record_action_trigger` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 37 |
| `gold` | `alert_on_create` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 36 |
| `gold` | `alert_on_status_change` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 36 |
| `gold` | `code_snippet` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 52 |
| `gold` | `delay_step` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 35 |
| `gold` | `for_each_loop` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 36 |
| `gold` | `manual_input_branch` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 37 |
| `gold` | `record_create` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 34 |
| `gold` | `record_find_update` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 39 |
| `gold` | `virustotal_ip` | ✓ | ✗ | – | ✓ | – | ✓ | 3/4 | 38 |
| `gold` | `manual_input_then_act` | ✓ | ✓ | – | ✓ | – | ✓ | 4/4 | 35 |
| `gold` | `unknown_connector` | ✗ | – | – | ✗ | – | – | 0/2 | 0 |
| `echo` | `hello_connector` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `decision_branch` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `alert_action_var_chain` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `record_action_trigger` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `alert_on_create` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `alert_on_status_change` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `code_snippet` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `delay_step` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `for_each_loop` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `manual_input_branch` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `record_create` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `record_find_update` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `virustotal_ip` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `manual_input_then_act` | ✗ | – | – | ✗ | – | ✗ | 0/3 | 0 |
| `echo` | `unknown_connector` | ✗ | – | – | ✗ | – | – | 0/2 | 0 |

## Per-model totals

- **gold** — 49/58 (84%)
- **echo** — 0/44 (0%)
