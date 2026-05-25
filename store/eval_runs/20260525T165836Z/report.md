# Eval run `20260525T165836Z`

- ts: 2026-05-25T16:58:36.297216+00:00
- live: True
- tasks: 5
- models: agentic_anthropic

## Per-cell results

| model | task | draft | verified | live | example | vCalled | vIters | vReady | score | ms |
|---|---|---|---|---|---|---|---:|---|---:|---:|
| `agentic_anthropic` | `manual_input_branch` | ✓ | ✓ | ✗ | ✗ | ✓ | 1 | ✓ | 8/9 | 23799 |
| `agentic_anthropic` | `manual_input_then_act` | ✓ | ✓ | ✗ | ✗ | ✓ | 1 | ✓ | 8/9 | 33807 |
| `agentic_anthropic` | `unknown_connector` | ✗ | ✗ | ✗ | – | ✗ | 0 | ✗ | 4/4 | 11419 |
| `agentic_anthropic` | `manual_input_block_ip` | ✓ | ✓ | ✗ | – | ✓ | 1 | ✓ | 8/9 | 46781 |
| `agentic_anthropic` | `soc_phish_block_with_approval` | ✓ | ✓ | ✗ | – | ✓ | 1 | ✓ | 8/9 | 80706 |

## Per-model totals

- **agentic_anthropic** — 36/40 (90%)
