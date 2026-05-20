# Eval run `20260519T213626Z`

- ts: 2026-05-19T21:36:26.555965+00:00
- live: False
- tasks: 21
- models: agentic_anthropic

## Per-cell results

| model | task | draft | verified | live | example | vCalled | vIters | vReady | score | ms |
|---|---|---|---|---|---|---|---:|---|---:|---:|
| `agentic_anthropic` | `hello_connector` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 8625 |
| `agentic_anthropic` | `decision_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 7340 |
| `agentic_anthropic` | `alert_action_var_chain` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 7172 |
| `agentic_anthropic` | `record_action_trigger` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 17363 |
| `agentic_anthropic` | `alert_on_create` | ✗ | ✗ | – | ✗ | ✓ | 2 | ✓ | 6/9 | 14252 |
| `agentic_anthropic` | `alert_on_status_change` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 9246 |
| `agentic_anthropic` | `code_snippet` | ✓ | ✓ | – | ✗ | ✓ | 3 | ✓ | 8/9 | 8139 |
| `agentic_anthropic` | `delay_step` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 4167 |
| `agentic_anthropic` | `for_each_loop` | ✓ | ✓ | – | ✗ | ✓ | 2 | ✓ | 8/9 | 203272 |
| `agentic_anthropic` | `manual_input_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 8532 |
| `agentic_anthropic` | `record_create` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 8475 |
| `agentic_anthropic` | `record_find_update` | ✗ | ✗ | – | ✗ | ✓ | 1 | ✓ | 6/9 | 14707 |
| `agentic_anthropic` | `virustotal_ip` | ✓ | ✓ | – | ✗ | ✓ | 2 | ✓ | 8/9 | 17303 |
| `agentic_anthropic` | `manual_input_then_act` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/9 | 8557 |
| `agentic_anthropic` | `unknown_connector` | ✗ | ✗ | – | – | ✗ | 0 | ✗ | 3/8 | 3900 |
| `agentic_anthropic` | `manual_input_block_ip` | ✓ | ✓ | – | – | ✓ | 3 | ✓ | 8/8 | 21701 |
| `agentic_anthropic` | `soc_phish_block_with_approval` | ✗ | ✗ | – | – | ✓ | 1 | ✓ | 5/8 | 211305 |
| `agentic_anthropic` | `itops_disk_full_recheck` | ✗ | ✗ | – | – | ✓ | 3 | ✗ | 5/8 | 200323 |
| `agentic_anthropic` | `noc_sla_breach_repoll` | ✗ | ✗ | – | – | ✗ | 0 | ✗ | 3/8 | 194046 |
| `agentic_anthropic` | `soc_ueba_three_way_decision` | ✗ | ✗ | – | – | ✓ | 2 | ✗ | 4/8 | 203150 |
| `agentic_anthropic` | `soc_http_fallback_no_native_op` | ✓ | ✓ | – | – | ✓ | 1 | ✓ | 8/8 | 21398 |

## Per-model totals

- **agentic_anthropic** — 144/182 (79%)
