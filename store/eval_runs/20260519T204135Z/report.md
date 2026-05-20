# Eval run `20260519T204135Z`

- ts: 2026-05-19T20:41:35.636328+00:00
- live: False
- tasks: 21
- models: agentic_anthropic

## Per-cell results

| model | task | draft | verified | live | example | vCalled | vIters | vReady | score | ms |
|---|---|---|---|---|---|---|---:|---|---:|---:|
| `agentic_anthropic` | `hello_connector` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 9166 |
| `agentic_anthropic` | `decision_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 6293 |
| `agentic_anthropic` | `alert_action_var_chain` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 7480 |
| `agentic_anthropic` | `record_action_trigger` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 9328 |
| `agentic_anthropic` | `alert_on_create` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 7158 |
| `agentic_anthropic` | `alert_on_status_change` | ✗ | ✗ | – | ✗ | ✓ | 2 | ✓ | 6/9 | 10981 |
| `agentic_anthropic` | `code_snippet` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 8862 |
| `agentic_anthropic` | `delay_step` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 3583 |
| `agentic_anthropic` | `for_each_loop` | ✗ | ✗ | – | ✗ | ✓ | 1 | ✓ | 5/9 | 17148 |
| `agentic_anthropic` | `manual_input_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 6481 |
| `agentic_anthropic` | `record_create` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 5621 |
| `agentic_anthropic` | `record_find_update` | ✗ | ✗ | – | ✗ | ✓ | 3 | ✓ | 6/9 | 30897 |
| `agentic_anthropic` | `virustotal_ip` | ✓ | ✓ | – | ✗ | ✓ | 2 | ✓ | 8/9 | 17206 |
| `agentic_anthropic` | `manual_input_then_act` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 11038 |
| `agentic_anthropic` | `unknown_connector` | ✗ | ✗ | – | – | ✗ | 0 | ✗ | 3/8 | 4124 |
| `agentic_anthropic` | `manual_input_block_ip` | ✗ | ✗ | – | – | ✓ | 4 | ✗ | 5/8 | 206956 |
| `agentic_anthropic` | `soc_phish_block_with_approval` | ✗ | ✗ | – | – | ✓ | 2 | ✓ | 5/8 | 49381 |
| `agentic_anthropic` | `itops_disk_full_recheck` | ✗ | ✗ | – | – | ✓ | 3 | ✓ | 5/8 | 35163 |
| `agentic_anthropic` | `noc_sla_breach_repoll` | ✗ | ✗ | – | – | ✓ | 3 | ✗ | 4/8 | 208406 |
| `agentic_anthropic` | `soc_ueba_three_way_decision` | ✗ | ✗ | – | – | ✓ | 1 | ✗ | 4/8 | 24801 |
| `agentic_anthropic` | `soc_http_fallback_no_native_op` | ✓ | ✓ | – | – | ✓ | 2 | ✓ | 8/8 | 18717 |

## Per-model totals

- **agentic_anthropic** — 139/182 (76%)
