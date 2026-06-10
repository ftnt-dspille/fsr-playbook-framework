# Working on the AI chat — cross-repo runbook

The agentic chat ("triage → enrich → build a playbook") spans **two repos**.
This is the one doc that ties them together: where the code lives, the inner
dev loop (offline → live → deployed), and the exact commands. Start here before
touching prompts, tools, intents, or the chat operations.

## The two repos

| Repo | Path | What it owns for chat |
|------|------|-----------------------|
| **Framework** (this repo) | `…/PycharmProjects/fsr-playbook-framework` | `fsr_core/` — the shared brain: prompt assembly, intent routing, tool registry, tier/safety, the agent loop. Plus the offline test harness + scoring. |
| **Connector** | `…/PycharmProjects/ConnectorsV2/fsr-playbook-builder` | The in-platform surface: `chat_turn`/`chat_poll`/`chat_resume` operations, live crudhub bridge, deploy + live-drive tooling. Consumes `fsr_core` (vendored at build, symlinked in dev). |

**Golden rule (from CLAUDE.md):** edit `fsr_core` **only** in the framework repo.
The connector's `fsr_core` is a symlink in dev and is `rsync`-replaced at build —
direct edits there are destroyed. Source edit → commit → deploy.

## Where the chat behavior lives (fsr_core)

- **Prompts** — `fsr_core/…` triage/system prompt assembly (pinned by
  `test_triage_prompt*.py`, `test_build_prompt_skeleton.py`).
- **Intent routing** — slicing a user turn → intent + params
  (`test_intent_slice_and_params.py`).
- **Tool registry / SAFE_TOOLS** — what the agent can call + tier/HITL
  (`fsr_core.llm.tools`). A tool the agent must use has to be in `SAFE_TOOLS`
  or it's never advertised/dispatchable.
- **Gates → levers** — low-signal / enrichment-offer / playbook-offer gates
  (`test_low_signal_gate.py`, `test_playbook_offer.py`, `test_lever_coverage.py`).
- **Build fidelity** — trace → YAML grounding (`test_build_fidelity*.py` +
  the pinned golden).

## The inner loop — fastest signal first

### 1. Offline structure/contract guards — default while tuning (~2s, no API, no box)
Run this on **every** prompt/tool/intent edit. It pins prompt assembly, intent
routing, the tool registry, the gate→lever map, and the golden-trace contract —
reddening before any live spend.

```sh
cd …/fsr-playbook-framework
make chat-fast
```

### 2. Live single-scenario drive — proves one flow end-to-end (costs API credits)
Needs `.env` (FSR creds + `ANTHROPIC_API_KEY`) **and a reachable deployed
connector**. Drives one scenario, scores it, validates render, prints a verdict.

```sh
make chat-drive SCENARIO=<fixture-name>     # a named investigation fixture
make chat-drive MSG="triage incident 65f9… and pivot on the IPs"
```

### 3. Live capability gate — the whole fixture set (costs more credits)
```sh
make chat-calibrate                 # every investigation fixture
make chat-calibrate SCENARIO=<name> # just one
```

### 4. Full offline green-check before declaring done
```sh
make verify     # fsr_core/tests + the connector's offline suite on this repo's .venv
```

## Shipping a change to the live box (connector)

`fsr_core` edits don't reach the platform until the connector is rebuilt +
installed. Use the **unified deploy** (bump → vendor `fsr_core` → build slim
tarball → install via `$replace` → post-install warmup → all-workers rollout
gate). Do **not** run the steps by hand.

```sh
cd …/ConnectorsV2/fsr-playbook-builder
scripts/deploy.sh                 # bump patch, build, install ($replace)
scripts/deploy.sh --bump none     # rebuild+install CURRENT version (no bump)
scripts/deploy.sh --with-config   # also create/refresh the Anthropic config
scripts/deploy.sh --no-install    # bump + build only (CI / dry run)
```
Creds + `ANTHROPIC_API_KEY` come from `$FSR_ENV` (default the framework `.env`),
sourced automatically. See `[[fsr_connector_deploy_publish_recycle]]` for the
publish-recycle nuance (a `$replace` alone doesn't recycle uwsgi workers).

## Live drive exactly like the widget (connector)

`prompt_loop.py` drives `chat_turn` (detached) + `chat_poll` with the
`since_turn` fence to completion, captures a widget-shaped export
(manifest + paired tool_use/tool_result), then runs a failure/anti-pattern
analysis. This is the closest offline-to-widget fidelity.

```sh
cd …/ConnectorsV2/fsr-playbook-builder
set -a; source ../../fsr-playbook-framework/.env; set +a   # creds FIRST
PY=../../fsr-playbook-framework/.venv/bin/python           # has requests

# one prompt against the current deployment
$PY scripts/prompt_loop.py --prompt "look up ip 1.1.1.1"
# push a fresh build first, then a named scenario
$PY scripts/prompt_loop.py --push --scenario ip_triage
# multi-turn (each --prompt is its own threaded turn)
$PY scripts/prompt_loop.py --prompt "look up ip 1.1.1.1" --prompt "now build a playbook"
# ground the turn in a record (entity context, like the drawer)
$PY scripts/prompt_loop.py --scenario ip_triage --entity /api/3/incidents/<uuid>
# replay a saved multi-turn chain
$PY scripts/prompt_loop.py --file _b4_chain.json
```

## Gotchas (the ones that bite)

- **Never `uv run --extra test` the connector suite** — it builds an env without
  `fsr_core`, so every test errors `ModuleNotFound: yaml`. Use `make verify`
  (this repo's `.venv` + `PYTHONPATH=.`).
- **Source `.env` BEFORE** any live drive (`prompt_loop.py`, `chat-drive`).
- **Edit `fsr_core` in the framework only.** Re-vendor via `deploy.sh`.
- **A new tool won't dispatch** unless it's registered in `SAFE_TOOLS`
  (the `build_playbook_from_trace` regression — see auto-memory).
- Don't kill the user's dev servers on :47821/:47822; use 47831+ for test backends.
- **`run_op` summarizes by default — it can silently drop fields + cap lists.**
  `_summarize_op_output`→`_truncate_generic` keeps only the first 40 dict keys
  and first 5 list items. A tool whose digest needs a late-ordered field (e.g.
  FMG device `name`/`sn`/`ip`, which sit past key 40) gets it stripped, and long
  lists silently shrink to 5. If the caller does its own bounded digest, pass
  `run_op(..., summarize=False)` — and project at the source (e.g. FMG
  `json_rpc_get` honours `data:{fields:[…]}`) so the payload stays small.
- **`run_op` may route through the force-fail-playbook agent-wrap, which reads a
  PERSISTED, FSR-truncated step result.** It only SHOULD do this for connectors
  reachable ONLY via a remote agent. `_agent_config_ids` now subtracts
  `_local_config_ids` so a master-local config (even one a tenant agent also
  echoes) uses direct execute. If a live read comes back capped to ~5 rows but a
  raw `/api/integration/execute/` curl returns the full list, suspect the wrap.
- **A connector's `json_rpc_get`-style output shape may differ from the named-op
  shape.** The `fortinet-fortimanager-json-rpc` connector nests rows under
  `get_response`, not `result[].data`. Keep sim fixtures faithful to the REAL
  shape — a lying fixture makes offline green while live returns 0 rows.

## Pointers
- Chat behavior plan / current phase: `docs/plans/CHAT_INTELLIGENCE_PLAN.md`.
- Streaming: `docs/plans/CHAT_STREAMING_PLAN.md`, `docs/STREAMING_300S.md`.
- Connector architecture/deploy nuance: auto-memory `[[connector_state]]`,
  `[[fsr_connector_deploy_publish_recycle]]`.
</content>
</invoke>
