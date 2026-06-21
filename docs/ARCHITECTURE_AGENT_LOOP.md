---
title: Agent-Loop Architecture — Shared fsr_playbooks.llm Wiring
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
summary: 'Shared investigate→triage→build agent loop implementation across repos:
  one fsr_playbooks.llm wiring.'
---

# Agent-loop architecture — the shared `fsr_playbooks.llm` wiring

The investigate→triage→build agent loop is **one implementation in
`fsr_playbooks`** with **three front-ends** that each assemble the same five
pieces. If you're adding a fourth surface (or debugging an existing one),
this is the contract. Everything here is verified against the code as of
2026-06-08; line numbers drift, so grep the symbol.

## The loop itself lives in the provider, not the front-end

The agentic round-trip (`assistant text → tool_use → dispatch → tool_result
→ repeat`) runs **inside `provider.stream()`** (`anthropic_provider.py`,
`openai_provider.py`, `lmstudio_provider.py`). `run_agent_turn`
(`fsr_playbooks/llm/run_turn.py`) is the *consumer* of that event stream — it
coalesces text, writes history rows, sniffs YAML, and returns a
`TurnResult`. No front-end writes a loop.

```
front-end  →  run_agent_turn(provider, system, messages, tools, …)
                  └─ provider.stream()  ← the actual tool loop
                        └─ fsr_playbooks.llm.tools.dispatch(name, args)  ← runs the MCP tool fn
                              └─ tier 0–2: run now;  tier 3+: stash SuspendedSession + emit ApprovalRequestEvent
```

`stop_reason == "pending_approval"` ⇒ the provider stashed a
`SuspendedSession` in the **approval gateway it was constructed with** and
emitted an `ApprovalRequestEvent`. The front-end resumes by popping that
session and calling `resume_agent_turn(provider, suspended, decision)`.

## The five pieces (all in `fsr_playbooks`)

| # | Piece | Symbol | Notes |
|---|---|---|---|
| 1 | Provider | `fsr_playbooks.llm.factory.get_provider(name, **overrides)` | Needs a `ConfigProvider` installed via `set_config_provider`. Pass `approval_gateway=` as an override — the factory forwards it (filtered by the provider ctor signature). |
| 2 | System prompt | `fsr_playbooks.llm.intents.load_intent_prompt(intent)` | `"triage"` / `"build"`, loaded from `fsr_playbooks/agent/system_prompt_{triage,build}.md`, inline fallback if the file is missing. |
| 3 | Tool slice | `fsr_playbooks.llm.intents.tools_for_intent(intent)` | `build` → `[]` (provider self-fills the full `SAFE_TOOLS` registry); `triage` → registry minus `BUILD_ONLY_TOOLS`. |
| 4 | Trace | `fsr_playbooks.agent.skill_trace.set_active_trace(trace)` around the turn | Makes `run_op` / `emit_action_card` record `SkillCall`s into a per-session `SkillTrace`, which `build_playbook_from_trace` later compiles. Process-local active trace; `clear_active_trace()` in a `finally`. |
| 5 | Approvals | `fsr_playbooks.llm.approvals` — `InMemoryApprovalGateway` / `SqliteApprovalGateway` | Implements `stash`/`peek`/`pop`/`clear`. HMAC-bound (`bind`/`verify`) so a tampered store fails closed. |

## How each front-end wires them

| Concern | Connector (`operations.py`) | Web (`web/backend/routes/chat.py`) | MCP shim (`fsr_playbooks/mcp_server/tools_agent.py`) |
|---|---|---|---|
| Entry | `chat_turn` / `chat_resume` (sync op, `asyncio.run`) | `POST /api/chat` / `POST /approvals/{id}` (SSE) | `triage_build_turn` / `triage_build_resume` (`@mcp.tool`, `asyncio.run`) |
| Config provider | platform-decrypted `config` dict | `backend.settings` adapter (`app.py`) | env-backed `_EnvConfigProvider` (`FSR_LLM_PROVIDER` + shared `OPENAI_*`/`ANTHROPIC_*`; `STUDIO_LLM_PROVIDER` honored as legacy fallback; default `openai` → gpt-oss gateway) |
| Session/history | sqlite (`storage.py`) + widget messages, `_wire_messages` collapse | request body, `_build_messages` | in-process `_SESSIONS` dict, collapsed-assistant-turn replay (`_collapse_assistant_turn`) |
| Approval gateway | `PersistedApprovalGateway` (sqlite, survives restart) | module default `InMemoryApprovalGateway` (`set_default_gateway`) | per-session `InMemoryApprovalGateway` (drop = re-run) |
| Streaming | event feed + `chat_poll` cursor | SSE frames via `on_event` | none — `on_event=None`, one final transcript |
| Output | widget contract envelope (`_event_to_wire`, `CONTRACT_VERSION`) | SSE event frames | compact `{text, cards[], staged_actions[], approval?, playbook_offer?}` (`_flatten`) |

### Why the assistant turn is collapsed, not replayed verbatim
Both the connector (`_text_of`) and the MCP shim (`_collapse_assistant_turn`)
fold a finished turn's `tool_use`/`tool_result` blocks into compact text
markers (`[called run_op({…})]`) before storing it as the next turn's
history. Replaying raw blocks would require exact, paired `tool_use` ids;
the collapsed markers let the model recall what it did without that
fragility. Keep this behavior identical across front-ends.

## Trace recording over MCP (resolved spike)
`set_active_trace(trace)` around the turn is sufficient — the MCP `run_op`
entrypoint records into the active trace with no connector-specific wiring
(MCP_TRIAGE_AGENT_PLAN Open-Q #1). The plain MCP toolbox does **not**
auto-record; the shim's trace scope is what enables `build_playbook_from_trace`.

## Gotchas
- `get_provider` raises if no `ConfigProvider` is installed. The MCP shim
  installs one lazily **only if** `factory._CONFIG_PROVIDER is None`, so an
  embedding host's config still wins.
- MCP tools are sync `def`; `asyncio.run` is safe because FastMCP runs them
  in a worker thread with no running loop (same as the connector's sync op).
- Push safety: the desktop default is *offer only* — the `triage` slice
  drops `push_playbook`; an explicit build-intent turn is needed to write to
  live FSR (MCP_TRIAGE_AGENT_PLAN Open-Q #2).
