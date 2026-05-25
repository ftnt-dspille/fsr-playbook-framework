# Eval run `20260525T175630Z`

- ts: 2026-05-25T17:56:30.208037+00:00
- live: True
- tasks: 5
- models: agentic_anthropic

## Per-cell results

| model | task | draft | verified | live | example | vCalled | vIters | vReady | score | ms |
|---|---|---|---|---|---|---|---:|---|---:|---:|
| `agentic_anthropic` | `manual_input_branch` | ✓ | ✓ | – | ✗ | ✓ | 1 | ✓ | 8/8 | 28171 |
| `agentic_anthropic` | `manual_input_then_act` | ✗ | ✗ | ✗ | ✗ | ✓ | 1 | ✓ | 6/9 | 28498 |
| `agentic_anthropic` | `unknown_connector` | ✗ | ✗ | ✗ | – | ✗ | 0 | ✗ | 4/4 | 11770 |
| `agentic_anthropic` | `manual_input_block_ip` | ✓ | ✓ | – | – | ✓ | 1 | ✓ | 8/8 | 51874 |
| `agentic_anthropic` | `soc_phish_block_with_approval` | ✓ | ✓ | – | – | ✓ | 1 | ✓ | 8/8 | 115554 |

## Per-model totals

- **agentic_anthropic** — 34/37 (92%)
