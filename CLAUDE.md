# CLAUDE.md -- fsr-playbook-framework

@AGENTS.md

Everything in `AGENTS.md` (repo layout, CLI, authoring, conventions) applies. This
file adds what Claude Code needs on top of it: which gate to run, release rules, and
the product context.

## Verify before you trust

- Trackers, notes and memory drift from git. Check `git log`, the tag, and the
  connector's `requirements.txt` pin before acting on a "release owed" or "broken" line.
- Box and env state come from `make doctor` (a stale editable install, an old
  `pyfsr`, or an empty reference DB each once looked like a product bug).
- Use `/usr/bin/grep` when a search on a known file returns nothing. Some shell
  greps are wrappers that skip large files.

## Which gate to run

Pick the gate for the axis you touched. There is no single "all green" command.

| You changed | Run |
|---|---|
| `fsr_playbooks/`, `tooling/` | `make verify` (doctor, mypy, `fsr_playbooks/tests`, connector suite). Offline. |
| Fast loop while iterating | `make tests` (`tooling/tests` only, excludes live and slow) |
| Compiler emit or round-trip | `make corpus-gate` |
| Tool descriptions, system prompt, tool set | `make tool-gate` (~2-4 min; diffs against a pinned baseline) |
| Agent behaviour across the corpus | `make matrix LANE=screen` (free, offline) |
| Studio frontend (`web/frontend`) | `npm run check && npm run test` in `web/frontend` |
| Connector contract surface | Run it in the connector repo (`conn_main`), not here |

Notes:
- `make matrix` takes `REPEAT=n`. It has no `RUNS` variable, and `RUNS` is silently
  ignored, so invoke it twice for two runs. `LANE=confirm` and `LANE=attribute`
  are paid or live and need `LIVE_OK=1`.
- `make tool-gate` reports NOT COMPARABLE when the baseline is from another world. It
  withholds the table on purpose. Re-baseline (`make tool-gate BASELINE=<run_id>`), don't dig for cells.
- Don't run the full corpus to check a tool-description edit. Use `make tool-gate`.

## Releases

- The user cuts releases and pushes `main`. Agents don't. A release is `make release VERSION=X.Y.Z`
  and it is permanent and public.
- Framework changes reach the connector only through a release. The connector pins the wheel in its
  `requirements.txt`, so a change here is not visible to its CI until released.
  Before a release, run both `make tests` (`tooling/tests`) and `make verify` (which covers
  `fsr_playbooks/tests` and the connector suite). Neither alone is the release gate.
- Tests must not name `data/fsr_reference.db`. It is a gitignored dev cache, and CI does not have it.
  Fifteen existing test files still do. That is known debt, so don't add more.

## Product context

The framework is the **P4 "bottle it"** engine of the FortiSOAR SOC Assistant
("AI finds the pattern. A playbook runs it forever."): it compiles an investigation
into a deterministic playbook. The other promises (cited investigation, tier-gated
approvals, reach to on-prem targets) live mostly in the connector and widget. Work
that serves none of the four is drag.

Roadmap and cards live in the private tracker repo (`ROADMAP.md`, edited there; the
user pushes). Cards are managed with `scripts/tracker.sh` (`show|comment|close|create|status|list`),
not raw `gh issue`. Claim a card before working it, because several agents run in
parallel, and update or close it in the same session.

## Rules for changing agent behaviour

- **One approval decision.** `fsr_playbooks/llm/authorization.py` `authorize()` decides.
  Guards live in `fsr_playbooks/llm/agent_loop.py` and `fsr_playbooks/llm/_loop_helpers.py`.
  Before you add or remove a guard, read `docs/GUARDS.md`. Prefer a tool-contract
  change that makes the mistake impossible, and delete the guard that change replaces.
- **Playbook side uses playbook tools only.** On build or fix-playbook turns the dispatch refuses other tools
  (`TurnPlan.gate_refusal` in `fsr_playbooks/llm/turn_plan.py`). Don't rely on prompt wording.
- **No regex or phrase-list intent detection.** Gate on structure: cards emitted, draft
  contents, grounded state. Never on what the user or the model wrote.
- **Library first.** Before you write a playbook validator, extend the existing ones:
  `FieldValueValidator`, `PicklistMixin`, the typed walker, and `module_schema.field_names`
  (the one field lookup).
- **Public-repo hygiene.** This repo ships. No lab IPs, appliance hostnames, ports tied to a box,
  credentials, usernames, or capture dates in tracked files. Use placeholders. Test-net
  addresses (RFC 5737) are not internal: use `is_internal_ip`, not `ipaddress.is_private`.
- **Typing.** Use typed fields or pydantic models, not bare dicts or loose params.
- **Pyfsr.** Scripts that talk to FortiSOAR use pyfsr's typed methods, not raw `c.get`/`c.post` calls.
- **Scripts.** Use `#!/usr/bin/env bash`, not `/bin/bash`. macOS ships bash 3.2.
  In zsh, `$FLAGS` with a multi-word value is one argument. Use arrays.
- **Commits.** Author as the user. No AI attribution.

## Dev servers and ports

`make backend` serves FastAPI on :47821, and `make frontend` serves Vite on :47822.
Don't kill the user's servers on those ports. Test backends use 47831 or higher. `make preflight`
checks the ports, and `make kill-ports` frees them.
