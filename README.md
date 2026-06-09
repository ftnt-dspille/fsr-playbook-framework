# FSR Playbook Framework (`fsrpb`)

A YAML → FortiSOAR playbook compiler and reference store, with a Svelte visual
editor and MCP servers for authoring, validating, and running FortiSOAR
playbooks from a simple, human-readable IR instead of hand-wiring playbook JSON.

It ships three things:

- **Compiler + resolver** (`fsr_core`, `python/`) — turn the simplified YAML IR
  into FortiSOAR playbook JSON, with a typed walker that resolves variable wiring
  and type-checks source → target across the branch tree.
- **Reference store** (`store/fsr_reference.db`) — a SQLite catalog of connectors,
  operations, parameters, step types, Jinja filters/macros, and step examples that
  the compiler and agents query to ground every step.
- **Playbook Studio** (`web/`) — a FastAPI backend + Svelte 5 visual editor for
  building, debugging, and stepping through playbooks, plus **MCP servers** that
  expose the same authoring/validation/run tools to agents.

## Layout

```
fsr_core/    compiler, resolver, typed walker, MCP server (shared with the connector)
python/      CLI (fsrpb), probes that build the reference DB, extra MCP servers, tests
web/         FastAPI backend (:47821) + Svelte 5 Studio editor (:47822)
ts/          TypeScript compiler (widget-runnable; consumes fsr_reference.json)
store/       schema + reference DB + agent .md reference exports
examples/    YAML fixtures + expected playbook JSON
e2e/         live end-to-end harness (examples/*.test.yaml against a real FSR)
```

## Reference store (SQLite-first)

`store/fsr_reference.db` is the single source of truth for everything an agent or
the compiler needs — it's all queryable via SQL. `store/fsr_reference.json` is a
derived export for the TypeScript compiler / widget. `fsrpb refresh` rebuilds the
store from probe output.

> The published build ships a **slim** catalog (step types, Jinja reference, and
> the connector operation corpus). Run `fsrpb refresh` against your own FortiSOAR
> to populate instance-specific modules, fields, and picklists.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/). Python **3.11+**.

```sh
make bootstrap     # fresh clone -> green, testable state (creates .venv, installs deps)
# or just:
make sync          # create .venv and install all editable deps via uv
```

`fsr_core` is also vendored into the in-platform connector, whose runtime is
Python 3.9 — keep `fsr_core` 3.9-clean (no module-level PEP 604 unions).

## Common commands

```sh
make verify        # offline green-check: fsr_core + connector test suites
make tests         # fast pytest (excludes live + slow), incl. the offline golden-trace pin
make dev           # run backend (:47821) + frontend (:47822) together
make e2e           # run every examples/*.test.yaml against a live FSR
make lint          # ruff over fsr_core + python
fsrpb --help       # the CLI (compile, validate, resolve, refresh, query the store)
```

## MCP servers

Three MCP servers (see `.mcp.json`) expose the toolset to agents / Claude Code:

- **`fsrpb`** (`fsr_core.mcp_server`) — authoring: compile/validate/resolve YAML,
  find connectors/operations, get step schemas, debug sessions.
- **`fsr-read`** (`python/fsr_read_mcp.py`) — read-only live FortiSOAR queries
  (records, picklists, run_op, verify_playbook).
- **`fsr-deploy`** (`python/fsr_deploy_mcp.py`) — connector build/deploy helpers.

### Triage → build a playbook (Claude Desktop / Claude Code)

The `fsrpb` server lets the assistant investigate an incident, stage containment,
and compile a re-runnable playbook from what it did — with no FortiSOAR UI. There
are **two ways** to drive it; pick by front-end.

#### Recommended for Claude Desktop / Claude Code — drive it yourself (no API key)

Claude Desktop and Claude Code **are already Claude**, so they run the triage
loop themselves using the granular `fsrpb` tools. There is **no second model and
no `ANTHROPIC_API_KEY`** — the assistant just needs a way to (a) record the ops
it runs and (b) inherit the tuned triage discipline. Three primitives provide
that:

1. `triage_session_start(entity?)` — begin recording (call once, at the start).
2. drive the work: `run_op` for read-only enrichment, `emit_action_card` to
   **stage** containment (never run it silently), `get_record` / `search_module_records`
   to pivot. `run_op` records into the session automatically.
3. `build_playbook_from_trace()` — no args; compiles the recorded ops into a
   playbook. **Offer only** — call `push_playbook` explicitly to save to FSR.

`triage_guidance()` (and the MCP `triage` prompt) return the tuned instruction
sheet so the assistant follows the same discipline the packaged agent uses
(read-only investigation, correlate across alerts *and* incidents, stage—don't
run—containment). `triage_session_state()` shows what's been captured so far.

Just ask naturally — *"Triage the latest high-severity incident and build a
containment playbook from it"* — and the assistant calls these in order.

#### Packaged turn — for the FortiSOAR widget / headless runs (brings its own model)

`triage_build_turn` / `triage_build_resume` run the **entire** loop inside one
tool call, using their **own** inner LLM. This exists for front-ends that are
*not* a model (the FortiSOAR widget; cron/headless). The inner model is set by
`FSR_LLM_PROVIDER` — **default `openai`** (the gpt-oss gateway), or `anthropic`
(which calls the Anthropic API directly with `ANTHROPIC_API_KEY` — the server
**cannot** reuse Claude Desktop's subscription). For Claude Desktop / Code, prefer
the native primitives above and skip this.

#### Config (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`)

Launch with `uv run --directory <repo>` so the project resolves and the server
auto-loads this repo's `.env`. For the native path you don't need any LLM keys at
all — only live-FSR access for `run_op`.

If your `.env` is already filled, **omit the `env` block entirely**. Include it
only to set creds explicitly (e.g. a machine without this repo's `.env`, or to
override it — the `env` block wins):

```jsonc
{
  "mcpServers": {
    "fsrpb": {
      "command": "uv",
      "args": ["run", "--directory",
               "/absolute/path/to/fsr-playbook-framework",
               "python", "-m", "fsr_core.mcp_server"],
      "env": {
        "FSR_BASE_URL": "https://your-instance.fortisoar.example.com",
        "FSR_API_KEY":  "<scoped FortiSOAR API key>"
        // — OR username/password instead of FSR_API_KEY (not recommended):
        // "FSR_USERNAME": "csadmin",
        // "FSR_PASSWORD": "<password>",
        // — packaged turn only (not needed for the native path):
        // "FSR_LLM_PROVIDER": "openai",
        // "OPENAI_ENDPOINT": "https://your-gateway/v1",
        // "OPENAI_MODEL": "gpt-oss-120b",
        // "OPENAI_API_KEY": "<gateway key>"
      }
    }
  }
}
```

> JSON itself has no comments; the `//` lines above are for illustration — drop
> them (and the keys you don't use) in the real file. A minimal native-path
> `env` is just `FSR_BASE_URL` + `FSR_API_KEY`.

**Configuration surface.** All env vars; the per-server **`env` block wins over
the repo `.env`** (loaded with `setdefault`). Use `.env` as your dev default, the
`env` block for a portable config.

| Var | Purpose |
|---|---|
| `FSR_BASE_URL` | live FortiSOAR base URL (for `run_op` enrichment) |
| **`FSR_API_KEY`** | **preferred** FortiSOAR auth (scoped + revocable) |
| `FSR_USERNAME` / `FSR_PASSWORD` | fallback auth, only if no `FSR_API_KEY` |
| `FSR_LLM_PROVIDER` | *packaged turn only* — inner model: `openai` (default) or `anthropic` |
| `OPENAI_ENDPOINT` / `OPENAI_MODEL` / `OPENAI_API_KEY` | *packaged turn only* — gpt-oss gateway |
| `ANTHROPIC_API_KEY` | *packaged turn only*, and only when `FSR_LLM_PROVIDER=anthropic` |

**Prefer an API key over username/password.** Generate a least-privilege
FortiSOAR API key (read-only is enough — neither path pushes unless you call
`push_playbook`) and set `FSR_API_KEY`; the auth layer (`probes._env`) uses it
over username/password. Both `.env` and the Desktop config are plaintext, so a
revocable, scoped key contains a leak — keep `.env` gitignored and `chmod 600`
the config.

Restart Claude Desktop after editing the config — it only reads it at launch.

**Smoke-test the native path without the GUI** (no LLM key needed):

```bash
.venv/bin/python - <<'PY'
from fsr_core.mcp_server import tools_agent as ta
from fsr_core.mcp_server.tools_execution import run_op
from fsr_core.mcp_server.tools_compile import build_playbook_from_trace
ta.triage_session_start(entity={"module": "incidents"})
run_op(connector="virustotal", operation="query_ip", params={"ip": "8.8.8.8"})
print("recorded:", ta.triage_session_state()["count"])
print("built:", build_playbook_from_trace(name="Smoke PB")["ok"])
PY
```

See [`docs/ARCHITECTURE_AGENT_LOOP.md`](docs/ARCHITECTURE_AGENT_LOOP.md) for how
all three front-ends (widget, web app, MCP) share the same `fsr_core.llm` wiring.
