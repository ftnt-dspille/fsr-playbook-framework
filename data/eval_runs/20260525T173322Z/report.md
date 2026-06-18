# Eval run `20260525T173322Z`

- ts: 2026-05-25T17:33:22.445802+00:00
- live: True
- tasks: 5
- models: agentic_anthropic

## Per-cell results

| model | task | draft | verified | live | example | vCalled | vIters | vReady | score | ms |
|---|---|---|---|---|---|---|---:|---|---:|---:|
| `agentic_anthropic` | `manual_input_branch` | ✓ | ✓ | ✗ | ✗ | ✓ | 1 | ✓ | 8/9 | 210055 |
| `agentic_anthropic` | `manual_input_then_act` | ✓ | ✓ | ✗ | ✗ | ✓ | 1 | ✓ | 8/9 | 217798 |
| `agentic_anthropic` | `unknown_connector` | ✗ | ✗ | ✗ | – | ✗ | 0 | ✗ | 4/4 | 11611 |
| `agentic_anthropic` | `manual_input_block_ip` | ✓ | ✓ | ✗ | – | ✓ | 1 | ✓ | 8/9 | 249055 |
| `agentic_anthropic` | `soc_phish_block_with_approval` | ✓ | ✓ | ✗ | – | ✓ | 1 | ✓ | 8/9 | 100855 |

## Per-model totals

- **agentic_anthropic** — 36/40 (90%)
