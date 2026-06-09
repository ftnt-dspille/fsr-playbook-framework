# MCP triage-agent plan — run the packaged triage→build loop from Claude Code / Desktop

**Goal.** Expose the connector's *packaged* investigate→triage→build agent (tuned
system prompt + grounding + tier-based HITL + auto trace→playbook) as **two MCP
tools**, so Claude Desktop / Claude Code can run a full triage-and-build turn
turnkey — an alternate front-end to the FortiSOAR widget, with no FSR UI.

> **Status:** NOT STARTED (planned 2026-06-08). Alternate path to the in-platform
> connector + the Studio web app; see [[connector_state]], Path C = `make dev`.

---

## Why this is small now

The agent loop is **already extracted into `fsr_core.llm.run_turn`** — the hard
part is done:

- `run_agent_turn(*, provider, system, messages, tools, …) -> TurnResult` —
  drives one user turn, returns the full transcript (text + tool calls + emitted
  cards). HITL suspends mid-turn and surfaces a `pending_approval`.
- `resume_agent_turn(*, provider, suspended, decision, …) -> TurnResult` —
  re-enters after the user approves/denies.

The connector's `chat.py` and the web backend (`web/backend/routes/chat.py`)
already call these. We are NOT writing an agent loop — we're writing a **session
shim + two `@mcp.tool` wrappers** that replicate `chat.py`'s wiring with an
in-process session store instead of the connector's sqlite/widget.

**Revised effort: ~½ day** (was "½–1 day"). The only genuinely fiddly part is
HITL resume across MCP request boundaries — and `resume_agent_turn` already
exists, so it's a session-store problem, not a control-flow one.

---

## The five wiring pieces (all already exist; we just assemble them)

| Piece | Source to reuse | Notes |
|---|---|---|
| Provider | `fsr_core.llm.factory` | anthropic / openai from env. **Default to the local `gpt-oss-120b` OpenAI endpoint** (`OPENAI_ENDPOINT`) — see Token efficiency. |
| System prompt | the triage `system_prompt_build.md` the connector loads | load verbatim; do not re-author. |
| Tool slice | `SAFE_TOOLS` → `openai_tools()` / `anthropic_tools()` in `fsr_core.llm.tools` | same slice the connector advertises. |
| Trace recorder | `skill_trace.set_session_trace` / `_session_trace_scope` | per-session `SkillTrace`; this is what makes `build_playbook_from_trace` work. The plain MCP toolbox does NOT auto-record — this shim is what fixes that. |
| Approval gateway | `fsr_core.llm.approvals` (`ApprovalGateway` + `SuspendedSession`) | an **in-memory** gateway keyed by session_id is enough (no sqlite/HMAC durability needed for a desktop tool). |

---

## Design

### Session store (in-process)
```
SESSIONS: dict[str, Session]
Session = { messages: list[Message], trace: SkillTrace,
            gateway: InMemoryApprovalGateway, suspended: SuspendedSession|None }
```
TTL-evict to keep memory bounded. No persistence across MCP-server restarts —
acceptable for an interactive desktop tool (a dropped approval just re-runs).

### Tool 1 — `triage_build_turn`
```
triage_build_turn(message: str, session_id?: str, entity?: str) -> {
    session_id, stop_reason, text, cards[], staged_actions[], playbook_offer? }
```
- new session_id if omitted; install trace via `_session_trace_scope`; build the
  provider + system + SAFE_TOOLS slice; append the user message (+ optional
  `entity` record injected like the connector does).
- `await run_agent_turn(...)`; `on_event=None` (no streaming — MCP returns the
  final transcript). Flatten `TurnResult.transcript` → text + a compact `cards[]`
  (action_card / choice / capability_gap / playbook_offer).
- if `stop_reason == "pending_approval"`: stash `suspended` on the session and
  return the action card so the client can decide.

### Tool 2 — `triage_build_resume`
```
triage_build_resume(session_id: str, decision: "approve"|"deny", card_id?: str)
    -> same shape as triage_build_turn
```
- pop `suspended` from the session's gateway; `await resume_agent_turn(...)`;
  flatten + return. Re-suspends if the next tier-3 call needs another approval.

### Accept → build
The build is just the agent calling `build_playbook_from_trace` + `push_playbook`
inside the loop (already in SAFE_TOOLS, already trace-driven). `triage_build_turn`
with *"build a re-runnable playbook from what you just did"* triggers it — same as
the live B4 chain. No extra tool needed; the offer/accept can ride the normal
turn or a thin `triage_build_accept(session_id)` convenience that calls the
compiler directly (mirror connector `operations.chat_resume` accept branch).

---

## Token efficiency (explicit, since it's a goal)

1. **Run triage on the local `gpt-oss-120b` gateway by default.** The OpenAI
   provider already points at `OPENAI_ENDPOINT` — triage loops are token-heavy and
   this makes them ~free. Anthropic stays available via env for quality A/Bs.
2. **Reuse the existing hunt-token-optimizations** ([[hunt_token_optimization]]):
   `get_record` projection (96% cut, `full=` escape) + SIEM/FAZ event-list digest
   in `run_op`. They're in the toolbox already; nothing to add.
3. **No streaming over MCP** — `on_event=None`, `coalesce_text=True`: one final
   transcript, not per-token frames.
4. **Cap the loop** — keep `MAX_TOOL_TURNS` (already enforced) so a runaway
   investigation can't burn budget.
5. **Return compact cards, not raw tool dumps** — the flatten step keeps the MCP
   response small (text + structured cards), so the *client* model (Claude
   Desktop) spends few tokens reading results.

---

## Tasks

| # | Task | Size |
|---|---|---|
| 1 | `InMemoryApprovalGateway` (implements `ApprovalGateway`: push/pop `SuspendedSession` by session_id) | XS |
| 2 | Session store + TTL evict | XS |
| 3 | `_assemble(session)` helper: provider (env) + system prompt loader + SAFE_TOOLS slice + trace scope — factor out of connector `chat.py` so both share it | S |
| 4 | `transcript → {text, cards[], staged_actions[], playbook_offer}` flattener | S |
| 5 | `@mcp.tool triage_build_turn` | S |
| 6 | `@mcp.tool triage_build_resume` (+ optional `triage_build_accept`) | S |
| 7 | Register in `fsr_core.mcp_server`; add to the read-only vs mutating tool gating | XS |
| 8 | Offline test: stub provider that emits a tool_use→pending_approval→resume, assert the two tools round-trip a HITL approval and produce a playbook offer | M |
| 9 | Claude Desktop config snippet + a short README section | XS |

**Definition of done:** from Claude Desktop, "triage incident X and build a
containment playbook" runs the packaged loop, surfaces an approval card, resumes
on approval, and returns a validated playbook offer — driven by the local
gpt-oss model, no FortiSOAR UI.

## Open questions
1. ✅ **RESOLVED (2026-06-08 spike).** Trace recording works identically over MCP.
   Verified outside any connector, sim mode: `set_active_trace(trace)` → the exact
   MCP `run_op` entrypoint (`tools_execution.run_op`) recorded both calls into the
   active trace → `build_playbook_from_trace("")` read it and built a valid
   playbook (`ok=True`, `static_errors=[]`, cross-step `ip_addresses` wire
   resolved). **The shim only needs `set_active_trace(session.trace)` around the
   turn — no connector-specific recorder wiring.** Estimate locked at ~½ day.
2. **Push target** — `push_playbook` writes to live FSR. For a desktop tool,
   default to *offer only* (compile + validate, return YAML) and gate the actual
   push behind an explicit `triage_build_accept` so a desktop user can't
   accidentally write to production.
3. Multi-client concurrency — the in-process store is per-MCP-server; fine for one
   desktop. Note it, don't solve it.

## Out of scope
Streaming/SSE, sqlite/HMAC approval durability, the widget contract envelope —
all connector concerns that a desktop MCP front-end doesn't need.
