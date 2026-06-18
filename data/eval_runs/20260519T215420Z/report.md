# Eval run `20260519T215420Z`

- ts: 2026-05-19T21:54:20.286634+00:00
- live: False
- tasks: 21
- models: agentic_anthropic

## Per-cell results

| model | task | draft | verified | live | example | vCalled | vIters | vReady | score | ms |
|---|---|---|---|---|---|---|---:|---|---:|---:|
| `agentic_anthropic` | `hello_connector` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 9135 |
| `agentic_anthropic` | `decision_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 6799 |
| `agentic_anthropic` | `alert_action_var_chain` | ✓ | ✓ | – | ✗ | ✓ | 2 | ✓ | 8/8 | 13332 |
| `agentic_anthropic` | `record_action_trigger` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 11016 |
| `agentic_anthropic` | `alert_on_create` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 4497 |
| `agentic_anthropic` | `alert_on_status_change` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 7699 |
| `agentic_anthropic` | `code_snippet` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 7057 |
| `agentic_anthropic` | `delay_step` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 3495 |
| `agentic_anthropic` | `for_each_loop` | ✗ | ✗ | – | ✗ | ✓ | 2 | ✓ | 6/8 | 23411 |
| `agentic_anthropic` | `manual_input_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 8826 |
| `agentic_anthropic` | `record_create` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 4869 |
| `agentic_anthropic` | `record_find_update` | ✓ | ✓ | – | ✗ | ✓ | 2 | ✓ | 8/8 | 10140 |
| `agentic_anthropic` | `virustotal_ip` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 20096 |
| `agentic_anthropic` | `manual_input_then_act` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 7649 |
| `agentic_anthropic` | `unknown_connector` | ✗ | ✗ | – | – | ✗ | 0 | ✗ | 4/4 | 3805 |
| `agentic_anthropic` | `manual_input_block_ip` | ✓ | ✓ | – | – | ✓ | 2 | ✓ | 8/8 | 18507 |
| `agentic_anthropic` | `soc_phish_block_with_approval` | ✓ | ✓ | – | – | ✓ | 2 | ✓ | 8/8 | 211533 |
| `agentic_anthropic` | `itops_disk_full_recheck` | ✓ | ✓ | – | – | ✓ | 4 | ✓ | 8/8 | 52186 |
| `agentic_anthropic` | `noc_sla_breach_repoll` | ✓ | ✓ | – | – | ✓ | 1 | ✓ | 8/8 | 32689 |
| `agentic_anthropic` | `soc_ueba_three_way_decision` | ✗ | ✗ | – | – | ✓ | 3 | ✗ | 4/8 | 38742 |
| `agentic_anthropic` | `soc_http_fallback_no_native_op` | ✓ | ✓ | – | – | ✓ | 1 | ✓ | 8/8 | 22837 |

## Per-model totals

- **agentic_anthropic** — 158/164 (96%)
