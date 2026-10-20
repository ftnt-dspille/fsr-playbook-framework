---
title: Agent-Loop Architecture -- Shared fsr_playbooks.llm Wiring
category: architecture
status: reference
source: hand-written
topics:
- agent-loop
- investigate
- triage
- build
- llm-wiring
canonical: false
summary: 'One agent loop in fsr_playbooks.llm: providers, turn plan, dispatch
  gates, round-level guards, delivery, grounding, and measured build behaviour.'
---

# Agent-loop architecture -- the shared `fsr_playbooks.llm` wiring

The investigate→triage→build agent loop is **one implementation in
`fsr_playbooks`**. Front-ends (the SOC Assistant connector, the web backend)
assemble a provider, a system prompt, a message list and a tool list, and call
it. Line numbers drift; grep the symbol.

## The loop is written once, in `agent_loop.run_loop`

`fsr_playbooks/llm/agent_loop.py` owns the round trip (`assistant text →
tool_use → dispatch → tool_result → repeat`), the approval boundary, the
guards, self-repair, delivery and the wrap-up rounds. Every provider used to
carry its own copy of this loop and the copies drifted, so a guard fixed in one
provider stayed broken in another and the difference read as a model
difference.

A provider now supplies only its wire format: a `WireTurn` per stream plus
`precheck`, `open_turn`, `rehydrate` (resume after approval), `contract_stop`
and `friendly_error`. Each provider's `stream()` just calls `run_loop`.
**Nothing a provider supplies decides behaviour.**

```
front-end  →  run_agent_turn(provider, system, messages, tools, …)   (llm/run_turn.py)
                  └─ provider.stream()  →  agent_loop.run_loop(provider, …)
                        ├─ provider.open_turn(...)  ← one model round per call
                        └─ guarded_dispatch → tools.dispatch(name, args)
                              └─ tier 0-2: run now;  tier 3+: SuspendedSession + ApprovalRequestEvent
```

`stop_reason == "pending_approval"` means the loop stashed a
`SuspendedSession` in the provider's approval gateway. The front-end resumes
with `resume_agent_turn(provider, suspended, decision)` (`resume_loop`).

## The pieces a front-end assembles

| # | Piece | Symbol | Notes |
|---|---|---|---|
| 1 | Provider | `fsr_playbooks.llm.factory.get_provider(name, **overrides)` | Needs a `ConfigProvider` (`set_config_provider`). Pass `approval_gateway=` as an override. |
| 2 | Turn plan | `fsr_playbooks.llm.turn_plan.plan_turn(...)` | Built from structural state (`has_open_playbook`, `has_trace`, page, read-only). Supplies the prompt layers, the round budget (`MAX_TOOL_TURNS`, 40) and the dispatch refusals. |
| 3 | System prompt | `load_intent_prompt(intent)` plus the plan's layers | `agent/system_prompt_build.md` is about 28 KB (about 4,300 words, roughly 35 absolute rules). The plan adds a context prior, a constraints block and, when one is open, an OPEN PLAYBOOK block. |
| 4 | Tool list | `tools.advertised_for_turn(...)` | The full surface minus what the turn would refuse (read-only turns, enhancement tools with nothing open). `intents.tools_for_intent` still exists but has no live caller. |
| 5 | Trace | `agent.skill_trace.set_active_trace(trace)` around the turn | `run_op` / action cards record `SkillCall`s; `build_playbook_from_trace` compiles them (P4). |
| 6 | Approvals | `llm.approvals` -- `InMemoryApprovalGateway` / `SqliteApprovalGateway` | HMAC-bound, so a tampered store fails closed. |

## History is replayed natively

Earlier turns replay as real `tool_use` / `tool_result` pairs, translated per
provider by `llm/replay.py`. An earlier design folded them into text markers
(`[called edit_playbook(...)]`); the model then learned that writing the
marker *was* calling the tool and stopped making real calls (3 of 4 runs on a
three-turn refine). Do not reintroduce collapsed history.

## How a turn decides what it is

- **Intent** comes from the front-end: an explicit `triage`/`build` wins; on
  the connector, free text defaults to build and a missing intent falls back to
  the page (authoring pages build, record pages triage).
- **Mode within build** (create, edit, explain) is decided from state, not
  wording: a playbook is open, so creating a second one is refused unless the
  analyst picked "create new" on the `playbook_scope` choice; nothing is open,
  so edit tools are refused. Read-only quick actions (explain, find issues)
  withhold and refuse every writing tool. `intents.classify_message` /
  `gate_directive` are not reached on the live connector path.
- **The conversation's own draft counts as open.** After a build turn offers
  or saves a playbook, the connector grounds later build turns in the same
  session on it, so "also add X" edits the draft instead of re-typing it. A
  request for an unrelated second playbook in that session therefore starts
  as an edit turn until the model raises the scope choice.

## Dispatch: what happens to each call

`guarded_dispatch` (agent_loop) runs, in order: argument parsing
(`bad_tool_arguments`), not-advertised refusal, `repeated_call_guard` (the
identical call already errored this turn), `duplicate_offer`,
`duplicate_card`, and the triage discipline rules (most are inert on build).
`tools.dispatch` then runs: read-only refusal, the turn-plan gate, stray
`emit_card` key folding, the run-not-author redirect, scalar coercion, the
argument gate, the `verify_playbook` live-probe default (on, so verify runs
the playbook's `op_safety == safe` steps against the box), tier authorization,
and pre-card refusals.

The model only learns a tool is refused for this turn by calling it. On a
build turn record and triage tools are withheld from the list, but the
turn-plan refusals (offer while open, edit while nothing is open) cost a
round each time.

## Round-level guards (after the model stops calling tools)

Each nudge that continues the turn consumes a round.

| Guard | Fires when | Effect |
|---|---|---|
| Fence self-repair (`MAX_SELF_REPAIR_TURNS` 2) | The reply carries a YAML fence that fails to compile | Asks the model to fix it |
| Fence neutralising | A failing fence survives repair | Replaces it with a note, so it cannot be saved |
| Loop-run verify | A clean draft was never verified | The loop runs `verify_playbook` itself |
| `PromisedActionGuard` | The text describes a call that was never made | Nudge |
| `BuildProgressGuard` | Research tools only, no draft, and no answered investigation | Directive to author (does not fire after a triage lookup is answered) |
| Unverified draft / failed edit directives | A draft or edit is left failing | Directive to fix |
| `EnhanceDeliveryGuard` / `CreateDeliveryGuard` | A passing edit or verify was never offered | The loop emits the offer itself, no model round |
| `VerdictDeliveryGuard` | A triage turn authored no verdict | Up to two forced attempts |
| `ProgressMeter` | 3 repeat-only rounds or 6 all-error rounds | Ends the turn as stalled |
| Budget | `MAX_TOOL_TURNS` reached (8 on the connector's resume path) | A no-tools wrap-up or a budget choice card |

A delivered offer card ends the turn. The connector adds its own backstops
after the loop returns: `_salvage_build_offer` / `_salvage_enhancement_offer`
synthesise an offer from the last fence or last verified YAML. They do not
check read-only, so an explain turn that prints a changed, verifying fence can
still produce an Apply card.

## How a playbook is represented while authoring

- **New playbook:** the model writes whole YAML into `verify_playbook`; the
  offer carries a `verified_id`, and only the verified bytes can be offered.
- **Open playbook:** the model sends `edit_playbook` operations (`add_step`,
  `update_step`, `rename_step`, `remove_step`, `set_route`, `remove_route`,
  `add_parameter`, `remove_parameter`, `add_playbook`). The tool applies them
  to FortiSOAR's copy, verifies, and returns a `verified_id`; unnamed steps
  carry over untouched.
- **From an investigation:** `build_playbook_from_trace`; the model writes no
  YAML.
- Validation is split across `validate_yaml` (structural, not the gate),
  `verify_playbook` (the gate, live probe on), `analyze_playbook` (offline
  simulation, safe ops off by default) and the verify inside `edit_playbook`.
  The model chooses among them each turn.
- Errors come back as data: a code, a path, a severity and `required_fixes`.

## Grounding the model can reach

| Source | Reached through | Caveat |
|---|---|---|
| Connectors and operations on the box | `find`, `get_op_schema`, `list_configured_connectors` | Filled by the connector's warmup; empty on a cold catalog |
| Operation output shape | `get_op_schema` `output_paths` | Only for ops with a recorded run (grounded shapes); otherwise the generic envelope rule |
| Module fields and picklists | `find(kind=field)`, `picklist` | From the warmed catalog |
| Step types | `get_step_type` | Packaged with the wheel |
| Reference playbooks | `find(kind=playbook)` | Box's own playbooks first, then the corpus |
| Vendor API catalog | `find(kind=api|example)`, `synthesize_http_step` | Needs the optional `probes` package; without it the tools return `catalog_unavailable` with a hint |

## Measured build behaviour

From 1,871 build-intent turns in a local connector store (eval and simulation
traffic on several open-weight models, not live analysts):

- Median 6 model rounds per turn (mean 8.0, p90 16). New builds average 9.1,
  edits 6.6, explain turns 2 to 3.
- `find` and `get_step_type` are 41% of all tool calls. `get_step_type` runs
  in 68% of turns, often four or more times, and 87 calls guessed a type name
  that does not exist.
- Successful and failed builds share the same discovery prefix; they differ at
  the close. Good turns end `verify_playbook → emit_card`; failed turns end in
  prose (9% of builds), a guard-refused card (10% of turns), or a forced stop
  (7%).
- The most common `verify_playbook` required fixes are
  `missing_field_on_step_output` (a read of an output field the op does not
  produce) and `connector_config_missing`.
- Generic `emit_card` delivers offers about 15 times as often as the retired
  dedicated offer tools.

These are the numbers to beat when changing the loop.

## Where the loop is accumulated patchwork

Recorded so a redesign removes them deliberately rather than by accident:

- Offers are backstopped in three places: loop delivery guards, the offer tool
  itself, and the connector's salvage.
- Two fence repair paths (self-repair, neutralising) plus connector fence
  handling.
- Triage guards (hunt floor, verdict, containment follow-through, enrichment
  cap) share the build path, inert there.
- Two `BUILD_ONLY_TOOLS` lists (framework `intents.py`, connector
  `ops_prompts.py`) that already differ.
- `advertised_for_turn` makes the tool list vary with open-playbook and
  read-only state, which changes the cached prompt prefix at those boundaries.
- Prompt rules that code already enforces (no offer while a playbook is open)
  or could enforce (no changed fence on a question turn).

### Providers

| `llm_provider` | provider class | wire format | key custody | streaming |
|---|---|---|---|---|
| `anthropic` (connector default) | `AnthropicProvider` | Anthropic Messages API | `anthropic_api_key` (external) | yes (SSE) |
| `openai` | `OpenAIProvider` | OpenAI Chat Completions | `openai_api_key` (external, or `base_url`→any OAI-compatible endpoint) | yes (SSE) |
| `lmstudio` (web/MCP only) | `LMStudioProvider` | OpenAI Chat Completions (local) | env-backed (local server ignores it) | yes (SSE) |
| `fortiai-proxy` | `FortiAIProxyProvider` | on-appliance `agent_chat_completions` via `/api/integration/execute/` | **none** (on-platform crudhub loopback) | **no** (one call per round-trip) |

All four share the same `LLMProvider` protocol (`stream` / `resume` → `Event`
stream) and the same HITL machinery (tier resolution, approval suspension,
self-repair, forced assessment). Adding a backend is a *provider* addition,
not a loop change -- the contract is the loop boundary.

#### On-box mode (`fortiai-proxy`)

`fortiai-proxy` drives the agent loop against the `fortinet-fortiai-proxy`
connector's `agent_chat_completions` operation. The connector runs on-box and
holds its own credential, so there is **no customer-supplied API key**; the
provider reaches `/api/integration/execute/` via the crudhub loopback with no
explicit auth.

**This is not automatically egress-free.** The stock connector configuration
points at FortiAI on FortiCloud (`fortiai.forticloud.com`), so inference leaves
the appliance. It suits an air-gapped or egress-restricted box only when
FortiAI itself is deployed on-prem and the configuration's `server_address`
says so. (An earlier revision of this document claimed "no egress -- suitable
for air-gapped boxes" unconditionally. That was wrong.)

**Reasoning depth is selectable.** The `feature` (`AI_MODEL_MEDIUM` /
`AI_MODEL_LARGE`) and `reasoning_effort` knobs ride per call in
`params.config`; the appliance ships the same choice as two connector
configurations, "Low Reasoning" (default) and "High Reasoning". One
compatibility rule, enforced in `_resolve_llm_config`: **effort implies
`AI_MODEL_LARGE`** -- an effort against a non-LARGE feature is a hard 400.

**Non-streaming:** the proxy has no SSE support, so the provider makes one HTTP
call per LLM round-trip and the user sees no text until the full response
arrives (sub-second for short answers; longer dead air for narratives is the
trade-off). This limit is real and remains.

**Tool calls may arrive in batches** -- the response's `tools` array carries
every elected call, while `tool_name`/`tool_args` hold only the first for
back-compat. They round-trip via flattened-text messages; the proxy rejects
structured `tool`-role blocks.

See `docs/plans/FORTIAI_PROXY_PROVIDER_PLAN.md` for the original wire contract
and `docs/plans/FORTIAI_PROXY_CAPABILITY_CORRECTION.md` for the corrections
above.


## Front-ends

| Concern | Connector (`connector-fsr-soc-assistant`) | Web (`web/backend/routes/chat.py`) |
|---|---|---|
| Entry | `chat_turn` / `chat_resume` (sync op, `asyncio.run`, detached with `chat_poll`) | `POST /api/chat` / approvals route (SSE) |
| Config provider | platform-decrypted `config` dict | `backend.settings` adapter |
| History | widget-sent `messages[]`, last turns replayed natively | request body |
| Approval gateway | SQLite-persisted gateway (survives a cold worker) | in-memory default gateway |
| Streaming | frames in `turn_progress`, read by `chat_poll` | SSE frames via `on_event` |
| Output | widget contract envelope | SSE event frames |

## Gotchas

- `get_provider` raises if no `ConfigProvider` is installed.
- A guard's docstring can lag its code: `CreateDeliveryGuard` describes a
  tool-choice-pinned round, but the loop now dispatches the offer directly;
  `VerdictDeliveryGuard` says triage-only but checks whether a verdict was
  authored. Trust the loop body.
- Push safety: playbook writes happen only on the analyst's Apply, never from
  a tool the model can call on a chat turn.
