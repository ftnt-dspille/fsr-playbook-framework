# FSR Playbook Studio — Web app plan

**Status**: Phase 5 in progress (LLM-modular + history backend done; UI routes pending)
**Owner**: Dylan
**Last updated**: 2026-05-04
**Supersedes**: UI + shipping sections of `../CHAT_APP_PLAN.md` (Streamlit). Inherits everything else from that doc — LLM context strategy, hard rules, tool dispatcher design, offline/live data buckets, risks. Read `CHAT_APP_PLAN.md` first; this doc only covers the deltas for the SvelteKit + FastAPI stack.

---

## Goal

Browser app (Mac-local for v1, hostable later) that:

1. Lets an LLM author FSR playbook YAML *live in a Monaco editor* while the user watches and chats.
2. Drives the existing `fsrpb` toolchain — compile, push, run, env, jinja, browse — through the same 19 tools the MCP server already exposes.
3. Makes the reference store (connectors / step types / Jinja idioms / recipes) browsable.
4. Single user, single machine, single FSR instance for v1. Hostability is a Phase-6 concern.

---

## Stack (settled)

| Layer | Choice | Reason |
|---|---|---|
| Frontend framework | **SvelteKit + Svelte 5 (runes)** | User pick. SSR off; this is a SPA. |
| Editor | **Monaco** via `@monaco-editor/loader` | YAML mode + diagnostics markers fit our validator output. |
| Styling | **TailwindCSS** | Fast iteration, no design system to fight. |
| Package manager | **pnpm** | User pick. |
| Backend | **FastAPI** (uvicorn, single process) | Imports `python/compiler/`, `python/mcp_server.py` handlers directly. |
| Streaming | **SSE** (chat + run-status) | User pick. Simpler than WS for one-way streams; FastAPI native via `sse-starlette`. |
| LLM v1 | **Anthropic** (`anthropic` SDK, MessagesStream) | User pick. |
| LLM later | **OpenAI** behind a `LLMProvider` interface | Pluggable from day 1; second provider lands in Phase 5. |
| Persistence | **SQLite** at `web/data/studio.db` | Chat sessions, run history, saved YAML drafts. |
| Auth | **None** (bind `127.0.0.1`) | Single-user. Phase 6 adds shared-secret header for non-localhost. |

**MCP reuse**: direct in-process import of the handler functions from `python/mcp_server.py` (decision deferred to me — picking direct import). Subprocess + MCP stdio is cleaner but doubles the moving parts and we already own both sides. If we later need true MCP isolation (multi-tenant hosting), refactor then.

**Live-editing model**: full-buffer replace per assistant turn (decision deferred to me — picking buffer-replace). The model writes the whole YAML each turn; we diff in Monaco and apply. Token-streaming into the editor cell-by-cell looks magical but fights user edits and adds significant complexity. Revisit only if buffer-replace feels too static after Phase 3.

---

## Repo layout

```
FSRPlaybookYaml/
  web/
    PLAN.md                       ← this doc
    README.md
    pyproject.toml                # backend extras (fastapi, sse-starlette, anthropic)
    backend/
      app.py                      # FastAPI entrypoint
      routes/
        chat.py                   # POST /api/chat (SSE)
        yaml.py                   # validate, compile
        playbook.py               # push, run, status (SSE)
        ref.py                    # connectors / step types / jinja / recipes
        run.py                    # env, jinja-render against past run
      llm/
        provider.py               # LLMProvider protocol + Event types
        anthropic_provider.py
        openai_provider.py        # Phase 5
        tools.py                  # JSON-schema generation from mcp_server fns
      sessions.py                 # SQLite persistence
      config.py                   # .env loading, FSR creds, API keys
    frontend/
      package.json                # pnpm
      svelte.config.js
      vite.config.ts
      src/
        routes/
          +layout.svelte          # tabs: Author | Run | Browse | History
          +page.svelte            # Author (default)
          run/+page.svelte
          browse/+page.svelte
          history/+page.svelte
        lib/
          components/
            MonacoYaml.svelte     # editor + diagnostics
            Chat.svelte           # streaming chat pane
            ToolCallCard.svelte
            RunTree.svelte        # step tree from get_run_env
            ConnectorBrowser.svelte
            StepTypeBrowser.svelte
            JinjaBrowser.svelte
          stores/
            yaml.svelte.ts        # current buffer (rune-based)
            chat.svelte.ts
            run.svelte.ts
          api.ts                  # fetch + SSE helpers
          sse.ts
    data/                         # gitignored
      studio.db
      .env                        # symlinked to ../../.env or its own
```

---

## API surface (FastAPI)

All endpoints scoped under `/api`. Errors as `{error: {code, message, details?}}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | `{fsr: ok|down, db: ok, llm: configured}` — pre-flight |
| POST | `/api/chat` | SSE: streams `text`, `tool_use_start`, `tool_use_delta`, `tool_use_final`, `tool_result`, `done` events |
| POST | `/api/yaml/validate` | → `{ok, errors: [{line, col, code, message, suggestion?}]}` |
| POST | `/api/yaml/compile` | → `{ok, data?, errors?}` |
| POST | `/api/playbook/push` | idempotent: PUT → POST → PURGE+POST. → `{collection_uuid, mode}` |
| POST | `/api/playbook/run` | trigger; returns `{task_id, pk?}` |
| GET | `/api/playbook/run/{task_id}` | SSE: status polls + final `step_detail` payload |
| GET | `/api/run/{pk}/env` | rebuilt `{vars: {...env, steps: {...}}}` |
| POST | `/api/jinja/render` | `{template, context?, from_pb_execution?}` |
| GET | `/api/ref/connectors?q=` | from `fsr_reference.db` |
| GET | `/api/ref/connector/{name}` | full schema + ops |
| GET | `/api/ref/step-types` | |
| GET | `/api/ref/jinja?q=&kind=` | filter / macro / pattern search |
| GET | `/api/sessions` / `POST` / `DELETE /{id}` | chat history CRUD |

Tool dispatcher inside `/api/chat` calls the same function set described in `CHAT_APP_PLAN.md` §"Tool dispatcher" — no new design needed.

---

## UI: Author tab (the main thing)

```
┌──────────────────────────────────────────────────────────────────┐
│ tabs: [Author] [Run] [Browse] [History]              FSR ●  LLM ● │
├──────────────────────────────────┬───────────────────────────────┤
│ Monaco YAML                       │ Chat                          │
│   diagnostics underline           │   ▸ user / assistant turns    │
│   gutter shows compile errors     │   ▸ tool-call cards inline    │
│   action bar: Validate · Compile  │   ▸ streaming text            │
│   · Push · Run                    │                               │
│                                   │   [textarea]      [Send]      │
└──────────────────────────────────┴───────────────────────────────┘
```

- **Buffer-replace flow**: assistant emits a fenced ```yaml block at end of turn; we extract it, diff against current buffer, apply via Monaco's edit operations (preserves cursor when feasible). User edits between turns are sent back to the model in the next user message as the "current YAML".
- **Diagnostics**: every keystroke debounced 400ms → `validate_yaml` → markers. Compile errors = red. Validator suggestions = info-level with quick-fix lightbulbs (Phase 3).
- **Tool-call cards**: collapsible. Args as JSON, result preview ≤ 200 chars + expand. Color-coded by family (read = blue, write/run = orange, destructive = red w/ explicit confirm before send).

---

## Phasing

| Phase | Scope | Done when |
|---|---|---|
| 0 | Scaffold. `pnpm create svelte`, FastAPI skeleton, `/api/health`, Tailwind, Monaco loads with a static YAML. Backend imports `compiler.parse` without error. | `pnpm dev` + `uvicorn` both run; opening `localhost:5173` shows editor + green health pill. |
| 1 | YAML validate + compile wired to Monaco markers. Action bar. | Editing `examples/hello_connector.yaml` underlines real errors. |
| 2 | Chat (Anthropic, SSE streaming, tool-use). In-process tool dispatcher importing from `mcp_server.py`. Buffer-replace into Monaco. System prompt + live instance context per `CHAT_APP_PLAN.md`. | "Build a hello-world playbook" produces YAML in the editor; tool calls visible. |
| 3 | Push + Run + Run viewer. SSE status stream. Jinja-render box on Run tab. | One click compiles → pushes → runs `examples/hello_connector.yaml` and shows the step tree. ✅ Push subprocess + Run SSE stream + Run page with logs and `vars` env viewer landed; structured step tree + Jinja-render box deferred to Phase 3.5. |
| 4 | Browse tab — connectors / step types / jinja / recipes. Cross-links from chat tool calls into Browse. | Search + drill-down works; tool-call cards link to `/browse/connector/<name>`. |
| 5 | History (sessions + runs). `LLMProvider` abstraction; OpenAI provider added. | Restart preserves chats; `.env` flag switches provider. **🟡 PARTIAL (2026-05-04):** `LLMProvider` abstraction landed (UsageEvent in the event union, factory + registry, `STUDIO_LLM_PROVIDER` env, `FakeProvider` for tests). History backend wired (push + chat-turn → `web/backend/history.db`, per-playbook `cost_by_playbook()`, chat↔push correlation via `~/.fsrpb/active_session`). **Still TODO:** OpenAI provider impl; `/api/history` FastAPI routes; Svelte `/history` UI (route stub already exists). |
| 6 | Hosting prep. Auth header, Dockerfile, externalize FSR creds + LLM keys, CSP. | Runs behind a reverse proxy on a non-laptop host. |

---

## Cross-cutting items inherited from `CHAT_APP_PLAN.md`

These are not re-explained here. Read the source.

- **Hard rules** (the 10 invariants) → go in `system_prompt.md` verbatim.
- **Layered context strategy** → system prompt + live instance context (refresh-on-session-start) + rolling history budget.
- **Tool dispatcher** → `inspect.signature` + docstring → JSONSchema; provider-specific wrappers around the same schemas.
- **Offline vs live data buckets** → `requires_live` annotation per tool; pre-flight at app start; "use cached schema" toggle.
- **Risks** → tool-result shape across providers, system-prompt drift, Anthropic prompt caching for the system block.

---

## Follow-ups captured during Phase 2/3

- **TS port of the Python compiler** — for tighter Monaco integration (in-browser validate/compile, hover schema from the connector store, completion). Today the editor round-trips to FastAPI for every keystroke; that's fine on localhost but limiting. Plan a port of `python/compiler/` to TypeScript so it can ship as a Web Worker the editor talks to directly, with the FSR reference DB exported as a JSON bundle. Scope: parser → resolver → validator → emitter; reuse the same error codes so server-side and client-side diagnostics interleave cleanly. Land after Phase 5 unless live-editing latency becomes a real complaint.

## Phase 5 resume notes (2026-05-04)

**Done:**
- `LLMProvider` Protocol now emits `UsageEvent` per round-trip; route is the single telemetry consumer (`_persist_usage` in `routes/chat.py`).
- Provider factory at `web/backend/llm/factory.py` (`STUDIO_LLM_PROVIDER` env). Built-in `anthropic`. Tests register `FakeProvider` (`web/backend/llm/fake_provider.py`) under the same name for plug-and-play.
- `history.db` schema: `pushes`, `push_workflows`, `chat_sessions`, `chat_turns` (with `playbook_collection`/`yaml_sha`), `chat_tool_calls`. Helpers: `record_push`, `record_chat_turn`, `list_pushes`, `get_push`, `previous_push`, `list_chat_sessions`, `get_chat_session`, `cost_by_playbook`, `yaml_diff`, `write_active_session`/`read_active_session`.
- `cli.py:cmd_push` wired (snapshots YAML, links workflows, correlates chat session via active marker).
- Per-playbook attribution: chat route extracts `collection:` + sha from `current_yaml` and stamps into UsageEvent tags → persisted on every chat turn.
- 192 tests passing (web 63, python 93, frontend 36).

**Resume here for the UI:**
1. Add `web/backend/routes/history.py` with: `GET /api/history` (timeline), `GET /api/history/push/{id}`, `GET /api/history/push/{id}/diff?against={id}` (uses `history.yaml_diff`), `GET /api/history/cost-by-playbook`, `GET /api/history/chat/{session_id}`. Mount in `app.py`.
2. Flesh out `web/frontend/src/routes/history/+page.svelte` (currently a placeholder). Timeline first, then push detail with diff button, then per-playbook cost rollup.
3. Add OpenAI provider: `web/backend/llm/openai_provider.py` mirroring `anthropic_provider.py`'s `UsageEvent` emission. Register via `factory.register("openai", OpenAIProvider)`.

## Open questions to revisit (not blocking Phase 0)

1. **Studio SQLite vs reference SQLite** — keep them separate (`web/data/studio.db` for chat/sessions, `store/fsr_reference.db` for the reference store, opened read-only). Simpler than one shared DB.
2. **Monaco YAML schema** — feed our compiler-derived JSON Schema for `playbooks.yaml` into Monaco's YAML language service for hover/completion before we even talk to the LLM. Probably Phase 3+.
3. **"Replay session" mode** for demos (from `CHAT_APP_PLAN.md` Day 3) — defer; live chat is the priority.
4. **Multi-instance FSR** — single instance for v1; later use a dropdown bound to named connections in `.env`.
5. **Cost / token meter** — surface in header pill alongside FSR / LLM status.

---

## Things I'm explicitly NOT building in v1

- Multi-user / RBAC.
- Real-time co-edit (no Yjs/CRDT). Single-tab assumption.
- Confirm-before-destructive UX for `run_op` / `push` (dev instance only — fine for now).
- A widget version inside the FortiSOAR appliance UI (that's Phase 3 of the original arc, separate effort).
