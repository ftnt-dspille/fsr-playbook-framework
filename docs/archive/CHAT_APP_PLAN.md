# Chat-app plan (Phase 2 — LLM-agnostic chat shim)

Self-contained plan for the Streamlit chat app that lets *any* LLM
(Claude, OpenAI, Ollama, etc.) drive the existing `fsrpb` compiler /
runner / picklist tools to author and fix FortiSOAR playbooks against
a live FSR instance.

This is the path that answers "do we have to use Anthropic?" with "no —
here's the same loop on GPT-4, here's the same loop on a local model".

Everything new lives under `python/chat/`. The existing compiler,
runner, picklist resolver, and CLI are untouched.

---

## Where this fits in the bigger arc

Phase 1 (today): demo in **Claude Desktop** with the existing `fsrpb mcp`
server. Zero new code. Limited to Anthropic.

Phase 2 (this plan): **Streamlit chat app**, swap LLM providers in a
dropdown, same tool surface. ~2–3 days of build.

Phase 3 (later): **FortiSOAR widget** — embed the chat into the FSR
appliance UI. Same tool surface again, just a different shell. Out of
scope here.

---

## Architecture (one page)

```
                    ┌────────────────────────────────────────┐
                    │  Streamlit chat app  (python/chat/app.py) │
                    │  - provider dropdown (claude|openai|ollama)│
                    │  - chat pane + tool-call cards           │
                    │  - sidebar: live YAML preview + run logs │
                    └──┬──────────────────────────────┬────────┘
                       │ messages, tool calls         │
              ┌────────▼──────────┐         ┌─────────▼──────────┐
              │  Provider adapter │         │  Tool dispatcher   │
              │  (chat/llm.py)    │         │  (chat/tools.py)   │
              │  - one class per  │         │  - JSON Schema gen │
              │    backend, all   │◀────────│  - calls into      │
              │    yielding the   │  schema │    python/mcp_server│
              │    same event     │         │    functions       │
              │    shape          │         │  - returns JSON    │
              └────────┬──────────┘         └─────────┬──────────┘
                       │ streamed events              │ tool result
                       ▼                              ▼
                                  Existing code (untouched):
                                  python/mcp_server.py    (tools)
                                  python/compiler/         (validate, compile)
                                  python/e2e/runner.py     (e2e)
                                  python/picklists.py
                                  python/connector_configs.py
                                  python/cli.py            (push, pull, etc.)
```

The compiler, runner, and existing MCP tool functions are
load-bearing — we **wrap** them, never touch them.

---

## Files to create

| File | Purpose | ~LOC |
|---|---|---|
| `python/chat/tools.py` | Reflects existing MCP tool functions → JSON Schema; runs them | 150 |
| `python/chat/llm.py` | Abstract `Provider` + `ClaudeProvider`, `OpenAIProvider`, `OllamaProvider` | 300 |
| `python/chat/state.py` | Normalized message / tool-call types so the UI is provider-agnostic | 80 |
| `python/chat/app.py` | Streamlit UI | 250 |
| `python/chat/system_prompt.md` | The FSR-authoring system prompt (see "LLM context" below) | 200 |
| `python/chat/__init__.py` | tiny | 5 |
| `pyproject.toml` (edit) | add `streamlit, anthropic, openai, ollama` deps | — |

---

## The LLM context problem (the most important section)

Right now in Claude Code / Claude Desktop, the LLM gets its FSR
vocabulary from a long prior conversation — months of accumulated
turns where you and the model worked out the playbook semantics.
None of that transfers to a fresh model on a fresh chat.

For Phase 2 to work *with any LLM*, we have to make that vocabulary
explicit and feed it on every turn. This is not optional. Without it
the agent will:
- Use `vars.steps.<step_id>` instead of `<Step Name with underscores>`.
- Pass picklist UUIDs instead of friendly strings (or vice versa, in the
  wrong direction).
- Forget that `like` against picklist fields never matches.
- Not know which connectors are actually configured on the box.
- Re-invent the `.test.yaml` shape every time.

### Layered context strategy

The agent's context window per turn looks like:

```
1. SYSTEM PROMPT (static, ~3–5k tokens)
   ├── Role: "You're an FSR playbook authoring assistant"
   ├── Hard rules (the 10 invariants below)
   ├── Tool-use guidance (when to call each tool)
   └── Two worked example exchanges (happy path, fix path)

2. LIVE INSTANCE CONTEXT (refreshed at session start, ~1–2k tokens)
   ├── Configured connectors on the box (live probe)
   ├── Available picklists (from store/picklist_name_map.json)
   ├── Common modules + their key fields
   └── Recent failed runs (so "my playbook is broken" works zero-shot)

3. CONVERSATION HISTORY (rolling, capped)
   ├── User messages
   ├── Assistant messages (with tool calls inline)
   └── Tool results (truncated past N=20 turns to first 500 chars)

4. CURRENT USER MESSAGE
```

The system prompt and the live instance context are the difference
between "an LLM that knows FSR" and "an LLM that hallucinates FSR".

### The hard rules (every prompt, no exceptions)

These need to be in the system prompt verbatim. They're the things we
learned the hard way over the previous chat:

1. **`vars.steps.<key>` keys off the step's display NAME, with spaces
   replaced by underscores, case preserved.** NOT the YAML `id:`. NOT
   the UUID.
2. **Picklist values in `arguments:` are friendly strings**, not IRIs.
   `severity: High` not `severity: /api/3/picklists/<uuid>`. The
   compiler resolves them.
3. **Picklist trigger filters can't use `like`** against picklist-typed
   fields (`type`, `severity`, `status`) — those store IRIs, not display
   strings. Filter on string fields (`name`, `description`) or use
   `op: changed` for post_update.
4. **Trigger params ride in `request.data`**, not `input`. FSR maps
   `request.data.<k>` → `vars.input.params.<k>`.
5. **child playbook output is at `vars.steps.<call_step_name>.<key>`** —
   it does NOT auto-merge into parent's top-level `vars`.
6. **Reserved variable names** that shadow runtime context: `input,
   steps, task_id, env, result, vars, globalVars, globals, parent_wf,
   self`. Don't use them as SetVariable arg names.
7. **Step types canonical short names**: `start, start_on_create,
   start_on_update, set_variable, decision, connector, stop, end,
   find_record, create_record, update_record, delay, manual_input,
   code_snippet, workflow_reference`. (`record_action` is gone;
   `insert_record` is a legacy alias for `create_record`.)
8. **Decision steps need every condition's `option` mapped in
   `branches:`** OR a default `next:`.
9. **Always call `validate_yaml(...)` before `compile_yaml(...)`** —
   the validator returns structured errors with "did you mean"
   suggestions.
10. **For `update_record`**: `collection:` is the *record IRI*,
    `module:` (shorthand) or `collectionType:` is the module IRI.
    Don't confuse them.

### Tool-use guidance (in the system prompt)

A tight playbook of when to use which tool — the LLM can't be expected
to figure this out from tool descriptions alone:

- "Build a playbook with X connector" → `find_connector(X)` →
  `find_operation(X, ...)` → `get_op_schema(connector, op)` →
  draft YAML → `validate_yaml` → `compile_yaml`.
- "Use a picklist value like 'High'" → friendly strings work, but if
  unsure call `resolve_picklist_value(value, module=…, field=…)` to
  confirm + get suggestions.
- "My playbook is broken" → `list_recent_failed_runs()` → pick the
  newest → `get_run_env(pk)` → diagnose → `pull` → edit → push → run.
- "What does playbook X do" → `pull` → walk steps → for unfamiliar
  Jinja, `find_jinja_pattern` → for connector calls, `get_op_schema`.
- "Connector exploration" → `find_operation(connector)` →
  `get_op_schema` → optionally `run_op` to live-test before authoring.

### Worked example exchanges (in the system prompt)

Two short scripted exchanges — one for authoring, one for fixing.
These are the closest thing to in-context fine-tuning we can do without
training. They go in `system_prompt.md` as fenced blocks, the model
sees them as part of its prompt, and gets a strong prior on the right
tool sequence.

Sample skeleton:

```
USER: Build a playbook that takes an IP and queries VirusTotal.

ASSISTANT: I'll start by confirming VirusTotal is configured.
[tool: find_connector("virustotal")]
→ {found: virustotal v3.2.1, configured: true}

Now let me find the right operation.
[tool: find_operation("virustotal", "ip")]
→ [{name: "query_ip", title: "Query IP"}, ...]

[tool: get_op_schema("virustotal", "query_ip")]
→ {params: {ip: {type: string, required: true}}, output: ...}

Here's the YAML:
```yaml
collection: VT IP Lookup
playbooks:
  - name: VT IP Lookup
    parameters: [ip]
    steps:
      - id: trigger
        type: start
        next: query
      - id: query
        type: connector
        name: Query VirusTotal
        arguments:
          connector: virustotal
          operation: query_ip
          params:
            ip: "{{ vars.input.params.ip }}"
        next: stamp
      ...
```

[tool: validate_yaml(text)]
→ {ok: true}

[tool: compile_yaml(text)]
→ {ok: true, data: ...}
```

### Live instance context (refreshed at session start)

Streamlit on app start (and on a "Refresh context" button) calls:

- `list_configured_connectors(probe=False)` → top-level connector list
  + active configs.
- Read `store/picklist_name_map.json` → known picklists for common
  modules (alerts, incidents, indicators).
- `list_recent_failed_runs(limit=5)` → seed Demo C's "what's broken"
  context.
- Read `store/STEP_FREQUENCY.md` → top step types so the agent prefers
  common patterns.

This context block is prepended to the system prompt as a fenced
"Current FSR instance" section. Refreshed once per session, not per
turn (would balloon token spend).

### Conversation history budget

Token budget per turn (Claude Sonnet 4.6 baseline):
- System prompt: 4k
- Live instance context: 2k
- History (rolling): 12k cap
- Current message: 2k
- Tool results: capped at 2k each, truncated past 5 calls back

Hard rule: tool results older than 5 turns ago are summarized
("validate_yaml returned 3 errors, all fixed in next turn") rather than
kept verbatim. Otherwise the long fixture YAML blobs eat the window.

---

## Tool dispatcher (the easy part)

`mcp_server.py` already has 19 `@mcp.tool()`-decorated functions. Don't
touch them. Instead:

```python
# python/chat/tools.py
import inspect, json
from mcp_server import (
    find_connector, find_operation, get_op_schema, run_op,
    get_step_type, find_jinja_filter, render_jinja,
    search_playbooks, validate_yaml, compile_yaml,
    get_run_env, list_configured_connectors, healthcheck_connector,
    list_recent_failed_runs, list_playbook_runs,
    list_picklists, get_picklist, picklist_for_field, resolve_picklist_value,
)

TOOLS = [find_connector, find_operation, ...]

def to_json_schema(fn) -> dict:
    """inspect.signature + docstring → {name, description, parameters} JSONSchema."""
    ...

def dispatch(name: str, arguments: dict) -> dict:
    fn = next(f for f in TOOLS if f.__name__ == name)
    return fn(**arguments)
```

Provider-specific schema wrappers:
- **Anthropic**: `{name, description, input_schema}`
- **OpenAI / Ollama**: `{type: "function", function: {name, description, parameters}}`

Both use JSON Schema for the params, so 95% is shared — just wrapped
differently.

---

## Provider adapter

```python
# python/chat/llm.py
class Provider(Protocol):
    name: str
    def stream(self, system: str, history: list[Msg], tools: list[dict],
               user_msg: str) -> Iterator[Event]: ...

# Event shape (normalized across providers):
#   TextChunk(text)
#   ToolCallStart(call_id, name, args_partial)
#   ToolCallDelta(call_id, args_partial)
#   ToolCallFinal(call_id, name, args_dict)
#   Done(stop_reason)
```

Three impls, ~80 lines each:
- **ClaudeProvider**: uses `anthropic` SDK, MessagesStream API.
- **OpenAIProvider**: uses `openai` SDK, ChatCompletion stream.
- **OllamaProvider**: uses `ollama` SDK against a local endpoint;
  restricted to models that support tool calls (qwen2.5, llama3.1+, etc.).

The trickiest bit is **conversation history serialization** — each
provider wants tool results in a different message shape. `state.py`
keeps a canonical history (a list of typed messages) and each provider
serializes on the way out.

Provider-specific gotchas to plan for:
- OpenAI's parallel tool calls in one assistant turn (Anthropic does
  too but emit shape differs).
- Ollama's tool-call support is per-model — probe/healthcheck and
  degrade gracefully.
- Token limits differ: Claude 200k, GPT-4 turbo 128k, Ollama varies.
  Sidebar shows current usage.

---

## UI (Streamlit, `app.py`)

Three-pane layout:

```
┌─────────┬───────────────────────────┬──────────────────┐
│ Sidebar │ Chat pane                 │ Right rail       │
│         │                           │                  │
│ Provider│ User: build me a VT lkup  │ ┌──── YAML ────┐ │
│  [Claude▾]│ Agent: I'll start by...│ │ collection: …│ │
│ Model   │  🔧 find_connector("vt") │ │ playbooks:   │ │
│  [opus▾]│   → {found: virustotal}  │ │ ...          │ │
│         │ Agent: now let me look…  │ └──────────────┘ │
│ FSR env │  🔧 get_op_schema(...)   │                  │
│  ✅ live│   → {params: {ip}, ...}  │ ┌── Run logs ──┐ │
│         │ Agent: here's the YAML… │ │ [320e9aa6]   │ │
│ Tokens  │ ```yaml                  │ │  triggered   │ │
│  4.2k/  │ ...                      │ │  finished 4s │ │
│  200k   │ ```                      │ └──────────────┘ │
│         │ [▶ Run e2e]              │                  │
│ Reset   │                          │                  │
└─────────┴───────────────────────────┴──────────────────┘
```

Key UX bits:
- **Tool-call cards**: collapsible. Show the args, the result preview
  (first 200 chars + expand). Color-coded by tool family (find/get =
  blue, run/push = orange).
- **Live YAML rail**: when the agent emits a yaml code block, parse it
  out and render in the right rail with syntax highlighting. Updates
  as the agent edits.
- **Run button**: when the agent has produced YAML + a `.test.yaml`,
  a "▶ Run e2e" button appears that pipes through to `runner.run_test`
  and streams logs into the right rail. **This is the dramatic
  moment.**
- **Provider switch**: changing mid-conversation shows a "history will
  be re-serialized for {provider}" toast; if there's a tool-result
  message format incompatibility, it offers "start fresh".

---

## Where the data lives (offline vs live)

This shapes the build — every tool falls into one of three buckets, and
the UI has to handle each differently (esp. error states + demo-day
fallbacks).

### Bundled with the app (offline, instant, cached)

These travel with the repo. The chat app has them the moment it starts.
SQLite is a local file; reads are sub-millisecond.

| Source | What's in it | Size |
|---|---|---|
| `store/fsr_reference.db` (SQLite) | 714 connectors, 5,517 connector ops + param/output schemas, step types, 170 Jinja filters, the whole reference store | ~12 MB |
| `store/picklist_name_map.json` | (module, field) → picklist_name auto-discovery cache | <1 KB |
| `store/connector_config_map.json` | (connector, config_name) → config UUID cache | <1 KB |
| `store/STEP_FREQUENCY.md`, `examples/demo_*.yaml` | Corpus stats + 11 working fixtures the agent can reference | ~30 KB |
| Compiler + linter (`python/compiler/`) | Pure Python; reads SQLite, no network | — |

**Tools that ONLY need this** (no live FSR call):
- `find_connector`, `find_operation`, `get_op_schema` (the bread-and-butter authoring tools)
- `get_step_type`, `find_jinja_filter`, `find_jinja_pattern`, `get_filter_examples`
- `search_playbooks` (FTS over a corpus snapshot)
- `validate_yaml`, `compile_yaml` (the linter)

**An agent can build a competent first-draft playbook 100% offline**
using just these. The authoring inner loop doesn't touch the FSR box.

### Live FSR API kicks in when…

The agent calls a tool that touches the appliance.

| Tool | Why it has to be live |
|---|---|
| `run_op` | Executes a connector op against real systems (VirusTotal, FortiGate, etc.) |
| `render_jinja` | FSR's Jinja sandbox is on the box; we send the template + ctx, FSR returns the rendered string |
| `list_recent_failed_runs` / `list_playbook_runs` / `get_run_env` | Reads the workflow runs table — by definition runtime data |
| `list_configured_connectors`, `healthcheck_connector` | Per-instance config; the SQLite snapshot doesn't know which configs the user set up |
| `list_picklists`, `get_picklist` (first call only) | Live discovery; resolved values cache to disk after that |
| `resolve_picklist_value` | Cache-first, falls back to live if (module, field) hasn't been seen before |
| Runner push/trigger/poll (the "▶ Run e2e" button) | Whole point is to deploy + run on the live box |

### Demo-time risk profile

| Demo | Authoring phase | Push/run phase | Diagnosis phase |
|---|---|---|---|
| A — vague-ask authoring | offline (safe) | live (necessary) | n/a |
| B — fix a broken draft | offline (safe) | n/a (validate-only) | n/a |
| C — "my playbook is broken" | n/a | live | **100% live (no fallback)** |
| D — reverse-engineer existing | live (`pull`) | n/a | offline reading |

**Authoring** (Demos A, B): mostly offline. Only live call in the inner
loop is `resolve_picklist_value` if a friendly value isn't cached — and
after one demo run, those *are* cached.

**Pushing + running** (Demos A end, C): unavoidably live. Mitigations:
- **Pre-flight check** at app startup: ping FSR. If it's down, banner +
  disable push/run buttons; authoring tools still work.
- **"Use cached schema" toggle**: forces every tool to skip live calls
  and use bundled snapshots. Useful for flaky networks or
  authoring-only demos.

**Diagnosis** (Demo C): 100% live by definition. If FSR is down, this
demo is dead — the captured-transcript replay mode (Day 3 polish) is
the only fallback.

### Deployment shape

When you run `streamlit run python/chat/app.py`:

```
your laptop                                FSR appliance (10.99.249.205)
─────────                                  ────────────────────────────
streamlit (localhost:8501)                
  ├── python/chat/app.py                  
  ├── python/chat/tools.py ─► python/mcp_server.py ─► 
  │                            ├── opens store/fsr_reference.db (file I/O)
  │                            └── for live calls:                          
  │                                HTTPS to ──────► /api/3/...
  │                                                  /api/wf/...
  │                                                  /api/integration/...
  │                                                  /api/triggers/...
  └── python/chat/llm.py ─► HTTPS to ──────► api.anthropic.com
                                              api.openai.com
                                              (or localhost:11434 for Ollama)
```

Nothing else. SQLite is local file I/O; FSR is HTTPS with credentials
in `.env`; the LLM is a separate HTTPS call to whichever provider.

### What gets stale

SQLite is a snapshot — taken when we last ran the FSR-ingestion
pipeline. If the user installs a new connector on the box afterwards:

- `find_connector` won't see it (snapshot doesn't know).
- `list_configured_connectors(probe=True)` *will* see it (live).
- Any op on the new connector won't have a `get_op_schema` until we
  re-ingest.

For a demo this is fine — the snapshot is current as of the last
ingestion. For ongoing use, the chat app could grow a "Refresh
reference store" button that re-runs the ingestion scripts. Out of
scope for the v1 plan but worth noting.

### Build implications

These are the things this section forces into the build that wouldn't
be obvious from the architecture diagram:

1. **Tool dispatcher needs to know per-tool which bucket** so the UI
   can render appropriate state. Add a `requires_live: bool` annotation
   to each tool's metadata. Used for:
   - Disabling live tools when FSR is down (greys out the tool-call
     card with an explanatory hover).
   - "Use cached schema" toggle behavior.
   - Pre-flight skipping of live tools in offline mode.
2. **Pre-flight is a real feature**, not an afterthought. App startup
   sequence: open SQLite → ping FSR (`/api/3/people/me` or similar) →
   read JSON caches → display status banner. ~50 LOC.
3. **Cache-warming on first run** matters for demo smoothness. After
   `git clone`, `picklist_name_map.json` is empty; the first
   `resolve_picklist_value` call goes live. For a clean demo, ship a
   "warm caches" CLI: `fsrpb warm-caches` runs the auto-discovery for
   the common (module, field) tuples (alerts.severity, alerts.status,
   incidents.severity, etc.) so the on-demo cache is non-empty.
4. **`.env` is now load-bearing for two things**: FSR credentials AND
   LLM API keys. The pre-flight should validate both. Sample `.env`:
   ```
   FSR_BASE_URL=https://10.99.249.205
   FSR_USERNAME=...
   FSR_PASSWORD=...
   FSR_ALLOW_E2E=true
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   OLLAMA_BASE_URL=http://localhost:11434
   ```
5. **The "Refresh context" button at session start** (mentioned in the
   LLM-context section) is *only* a live-FSR call away from being
   useful — it pulls configured connectors + recent failed runs. So
   the chat app needs its own pre-flight to know whether to even offer
   it. If FSR is down, hide the button or show "FSR offline — context
   from snapshot only".

---

## Shipping plan

### Day 1 — MVP (talkable, not pretty)
- `tools.py` + dispatcher + JSON Schema generation.
- `state.py` (Msg, ToolCall types).
- `system_prompt.md` (first draft from `AUTHORING.md` + the 10 hard rules).
- ClaudeProvider only.
- Single-pane Streamlit (chat + collapsible tool calls).
- "Run e2e" button.

You can demo Phase 2 with this. It answers "is this Claude-Desktop-only?"
with "no — here's a Streamlit app I'm running locally".

### Day 2 — provider parity
- OpenAIProvider, OllamaProvider.
- Provider switcher in sidebar.
- Token / cost counter.
- Right rail: live YAML + run logs.
- Live instance context block (refresh button).

### Day 3 — demo polish
- Pre-built prompt templates ("Build a playbook…", "My playbook is
  broken") as one-click buttons.
- Conversation save/load (`.jsonl` files in `store/chat_sessions/`).
- "Replay this session" mode for the demo (auto-types a saved
  transcript) — the bulletproof fallback if any live LLM provider
  hiccups on demo day.
- Branding (Fortinet colors, FSR logo).

---

## Risks I'd flag now

1. **Tool-result message shape across providers**: real engineering
   work, not boilerplate. Budget half a day per provider for "first
   chat works end-to-end with tool calls".
2. **Ollama tool-call quality varies wildly by model**. Llama 3.1 8B is
   OK at basic tool use but flaky at multi-step. Qwen 2.5 14B is the
   sweet spot for local. Acknowledge this in the UI ("local models may
   need more guidance — try a one-shot prompt").
3. **Streamlit + streaming**: Streamlit's rerun model is hostile to
   streaming. `st.write_stream` works but you can't easily mix streamed
   text with structured tool-call cards in the same message. Solution:
   render the assistant turn as it streams using `st.empty()`
   placeholders — works but adds 30 lines of fiddly code per provider.
4. **System prompt drift**: as the compiler / linter evolve, the system
   prompt has to stay accurate or the agent will hallucinate old
   behavior. Add a CI check: parse `AUTHORING.md` headings, fail if
   `system_prompt.md` doesn't reference the same set of rules.
5. **Demo-day reliability**: even with three providers, an OpenAI
   rate-limit / Anthropic outage / Ollama crash mid-demo is bad. The
   Day-3 "replay" mode is the insurance policy — it's not a real LLM,
   but the audience can't tell, and the demo can't fail.
6. **System-prompt token cost**: 4k system prompt × every turn × N
   sessions adds up fast on paid APIs. Anthropic prompt caching helps
   (cache the system block, only pay for the delta). OpenAI doesn't
   cache the same way; budget accordingly.
7. **History compatibility on provider switch**: Anthropic and OpenAI
   tool-result message shapes differ enough that mid-conversation
   switches are risky. Defensive UX: switching provider clears history
   by default, with an opt-in "try to translate".

---

## Decision points before I start

1. **Streamlit, or something else?** Streamlit is fastest to MVP.
   Alternatives: FastAPI+React (more control, ~3x time), or Textual TUI
   (terminal-native, looks like a hacker movie, less impressive to
   non-engineers).
2. **Provider mix**: Claude + OpenAI is the realistic
   answer-to-skepticism set. Adding Ollama is the on-prem story. If
   the demo audience won't ask about local models, skip Ollama for v1.
3. **System prompt source**: I draft it from `AUTHORING.md` + the
   corpus, you review? Or you write it?
4. **Day 3 polish — keep or drop?** The replay mode is what makes the
   demo bulletproof. Without it, you're trusting three live LLM
   providers on demo day.

---

## What this plan does NOT cover

- **Authentication / multi-user**: this is a single-user dev tool.
  Adding RBAC is a Phase 3 problem.
- **Streaming the run logs into Streamlit while the e2e runs**: we'll
  need a small async wrapper around `runner.run_test` to yield log
  lines as they happen. ~30 LOC, easy.
- **A FortiSOAR widget**: out of scope. Phase 3.
- **Cost tracking across providers**: token counters per turn, but no
  $/turn calc. Add later if billing matters.
- **Tool-call sandboxing**: `run_op` and `push` hit the live FSR. The
  app lets the agent call them freely. For demo on `dev` that's fine;
  for prod-adjacent we'd want a confirm-before-destructive layer.

---

## Success ladder + LLM-agnostic strategy (added 2026-05-06)

**Product principle to encode in every system prompt:**

> Producing valid YAML is the start of the job, not the end. The job is
> producing YAML that runs successfully on a real FortiSOAR instance and
> produces the outcome the user asked for. Use the success ladder to prove
> it works before declaring done.

### The success ladder

Today there is one gate (compile). Add four more, each enforced by
deterministic code, each callable as an MCP tool. The LLM walks up; failure
at any rung returns a structured `{ok, error_code, message, suggestions[]}`
and a fix hint — never prose.

| Rung | Question | Tool | Status |
|---|---|---|---|
| L1 Compile | Structurally valid YAML? | `compile_yaml` / `validate_yaml` | done |
| L2 Static-resolve | Connectors / ops / picklists / step-types / Jinja vars exist? | `resolve_yaml` (new) | partial — picklists & Jinja vars missing |
| L3 Dry-run | Step args render against expected upstream context? | `dry_run_playbook` (new; ties to I10 stepper) | missing |
| L4 Live single-step | Step N executes against real FSR with real data? | `run_op` (done) + `step_dry_execute` (new wrapper) | half |
| L5 Post-run assert | Did the playbook produce the expected outcome? | `assert_playbook_outcome` (new) | missing |

### Silent-failure surfaces to close (each becomes a ruleset module)

- **Picklist resolvability** (I1) — render every `{{ 'PL' | picklist(...) }}`
  against live FSR; FAIL with valid alternatives.
- **Connector installation** (I2) — `GET /api/integration/connectors/{name}/{version}`.
- **Step argument coverage** — every required `operation_params` row must
  appear in YAML `args` (today only structural validation runs).
- **Trigger compatibility** — alert/incident triggers reference fields that
  exist on the target module (cross-check `schema.json`).
- **Variable reachability** — every `{{ vars.steps.X.Y }}` references a
  step running *before* this one in the DAG, and `Y` exists in that step's
  declared output. Source: `operations.output_schema_observed` cached by
  `run_op`. **Highest-ROI single check we don't have.**
- **Mock-output coverage** — every Fetch step in a recipe has `mock_result`
  if the connector isn't configured.
- **Jinja arg-type discipline** — filters expecting list/dict/str receive
  matching types (signatures live in `jinja_macros` from `probe_jinja_backend`).

### LLM-agnostic surface — three contracts to enforce

1. **Structured tool I/O.** Audit every tool that returns prose errors;
   convert to `{ok, error_code, message, suggestions[]}`. Promote difflib
   hints into a dedicated `suggestions` field. Specifically: `compile_yaml`,
   `validate_yaml`, `run_op`.
2. **Externalized system prompt.** Move the implicit prompt to
   `python/agent/system_prompt.md`, version it, document the contract: tools,
   success-ladder discipline, when to ask the user, what counts as "done."
   Any LLM consuming this product loads that prompt + the MCP tool list and
   has everything needed.
3. **Token-budget discipline.** Smaller models (gpt-4o-mini, Llama-70B,
   local) can't afford 20k-token tool responses. Default `verbose=False`
   everywhere; full payloads behind explicit flag. Already trimmed
   `get_step_type` 4.9KB → 1.8KB; audit the rest.

### The proof: an LLM evaluation harness

"LLM-agnostic" is a claim until measured. Build `python/eval/harness.py`:
- Inputs: 3 representative tasks (simple connector call, decision branch,
  ingestion recipe).
- Models: Claude Sonnet, GPT-4o-mini, a local model (LMStudio).
- Score: L1 compile? L2 resolve? L3 dry-run? matches gold fixture?
- Output: a per-model rubric so the demo can show "these 4 LLMs all produce
  working playbooks via this product." ~6 hours.

### MVP demo gaps (what's still needed beyond DEMO.md)

- **L2 + L3 implemented** — without these, live demo hits silent failures.
- **`fsrpb demo run <storyboard>`** — single command that walks each
  storyboard end-to-end and asserts each leg.
- **Conversation transcript capture** — save full turn log + tool calls per
  session as a replayable artifact (token usage logging already exists;
  extend to full turns).
- **Inventory dashboard** — opens demo with "what does the assistant know?"
  (CLI stub landed 2026-05-06; web route + page pending).
- **Failure-recovery storyboard** — playbook fails → agent reads the run →
  fixes YAML → re-runs → succeeds. Needs
  `diagnose_yaml_against_pb_execution` MCP tool.
- **Demo reset script** — pre-demo: reset known modules on `dev`, delete
  test alerts/incidents, confirm required connectors configured.

### Groundwork ordering for "next-level" + MVP demo

Total to MVP-demo-ready: **~30–35 focused hours**. Load-bearing minimum is
items 1, 2, and 4 — the rest is polish.

1. **I1 + I2** (picklist + connector prechecks) — 1.5 hr; unblocks L2.
2. **`resolve_yaml` MCP tool** — wraps L2 logic. ~2 hr.
3. **`output_schema_observed` exposure** in `run_op` response — already
   cached, surface inline. ~1 hr.
4. **Variable-reachability ruleset** — DAG walk + output schema cross-check.
   ~3 hr. **Highest single-check value.**
5. **I10 stepper skeleton + `dry_run_playbook` MCP tool** — L3. ~4 hr
   scaffold; ~11 hr full per-step-type handlers.
6. **`assert_playbook_outcome` tool** — declarative expectations (record
   exists, field equals, count > N). ~3 hr. Enables L5 + eval harness.
7. **System prompt externalization + tool I/O audit** — ~2 hr.
8. **LLM evaluation harness** — 3 storyboards × 3 models. ~6 hr.
9. **`diagnose_yaml_against_pb_execution` tool** — failure-recovery loop. ~3 hr.
10. **Demo reset script + transcript capture** — ~2 hr.
11. **Inventory web dashboard** — fill in the route stubbed 2026-05-06. ~3 hr.

---

## Files referenced (for context-loading after a /clear)

When you come back to this, the relevant code lives at:
- `python/mcp_server.py` — the 19 tools we'll wrap.
- `python/compiler/resolver.py` — friendly arg expansions.
- `python/compiler/validator.py` — graph + reserved-name + Jinja-path linters.
- `python/e2e/runner.py` — 4 trigger modes; the "Run e2e" button hits this.
- `python/picklists.py`, `python/connector_configs.py` — auto-discovery + caches.
- `AUTHORING.md` — the source of truth for system prompt content.
- `DEMO.md` — the storyboards the chat app needs to support.
- `store/STEP_FREQUENCY.md` — corpus stats for picking common patterns.
- `examples/demo_*.yaml` — 11 fixtures the agent should know about.
