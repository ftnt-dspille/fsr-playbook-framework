# FSR Playbook Framework (`fsrpb`)

A YAML → FortiSOAR playbook compiler and reference store, with a Svelte visual
editor and MCP servers for authoring, validating, and running FortiSOAR
playbooks from a simple, human-readable IR instead of hand-wiring playbook JSON.

It ships three things:

- **Compiler + resolver** (`fsr_playbooks`, `tooling/`) -- turn the simplified YAML IR
  into FortiSOAR playbook JSON, with a typed walker that resolves variable wiring
  and type-checks source → target across the branch tree.
- **Reference store** (`data/fsr_reference.db`) -- a SQLite catalog of connectors,
  operations, parameters, step types, Jinja filters/macros, and step examples that
  the compiler and agents query to ground every step.
- **Playbook Studio** (`web/`) -- a FastAPI backend + Svelte 5 visual editor for
  building, debugging, and stepping through playbooks, plus **MCP servers** that
  expose the same authoring/validation/run tools to agents.

## Contents

- [Layout](#layout) · [Reference store](#reference-store-sqlite-first) · [Setup](#setup) · [Common commands](#common-commands)
- [MCP servers](#mcp-servers) · [MCP client config](#mcp-client-config)

## Layout

```
fsr_playbooks/    compiler, resolver, typed walker, MCP server (shared with the connector)
tooling/     CLI (fsrpb), probes that build the reference DB, extra MCP servers, tests
web/         FastAPI backend (:47821) + Svelte 5 Studio editor (:47822)
ts/          TypeScript compiler (widget-runnable; consumes fsr_reference.json)
data/        schema + reference DB + agent .md reference exports
examples/    YAML fixtures + expected playbook JSON
e2e/         live end-to-end harness (examples/*.test.yaml against a real FSR)
```

## Reference store (SQLite-first)

`data/fsr_reference.db` is the single source of truth for everything an agent or
the compiler needs -- it's all queryable via SQL. `data/fsr_reference.json` is a
derived export for the TypeScript compiler / widget. `fsrpb refresh` rebuilds the
store from probe output.

> The published build ships a **slim** catalog (step types, Jinja reference, and
> the connector operation corpus). Run `fsrpb refresh` against your own FortiSOAR
> to populate instance-specific modules, fields, and picklists.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/). This repo's
tooling needs Python **3.10+** (`requires-python = ">=3.10"`).

```sh
make bootstrap     # fresh clone -> green, testable state (creates .venv, installs deps)
# or just:
make sync          # create .venv and install all editable deps via uv
```

`fsr_playbooks` is also vendored into the in-platform connector -- keep it
Python 3.10-clean (no 3.12-only syntax).

## Common commands

```sh
make verify        # offline green-check: fsr_playbooks + connector test suites
make tests         # fast pytest (excludes live + slow), incl. the offline golden-trace pin
make dev           # run backend (:47821) + frontend (:47822) together
make e2e           # run every examples/*.test.yaml against a live FSR
make lint          # ruff over fsr_playbooks + tooling
fsrpb --help       # the CLI (compile, validate, resolve, refresh, query the store)
```

## MCP servers

Three MCP servers (see `.mcp.json`) expose the toolset to any MCP-capable
agent (Claude Desktop, Claude Code, Cursor, Copilot, Windsurf, etc.):

- **`fsrpb`** (`fsr_playbooks.mcp_server`) -- authoring: compile/validate/resolve YAML,
  find connectors/operations, get step schemas, debug sessions.
- **`fsr-read`** (`tooling/fsr_read_mcp.py`) -- read-only live FortiSOAR queries
  (records, picklists, run_op, verify_playbook).
- **`fsr-deploy`** (`tooling/fsr_deploy_mcp.py`) -- connector build/deploy helpers.

The MCP server exposes ~16 advertised tools: compile/validate/resolve YAML,
find connectors and operations, get step schemas and examples, run connector
operations, run deployed playbooks, and `build_playbook_from_trace` (compile a
playbook from a recorded session of connector ops). See
[`data/MCP_TOOLS.md`](data/MCP_TOOLS.md) for the full tool catalog and
[`docs/CLI.md`](docs/CLI.md) for the `fsrpb` CLI reference.

### MCP client config

Point any MCP-capable agent (Claude Desktop, Claude Code, Cursor, Copilot,
Windsurf, etc.) at the server. Launch with `uv run --directory <repo>` so the
project resolves and the server auto-loads this repo's `.env`.

If your `.env` is already filled, **omit the `env` block entirely**. Include it
only to set creds explicitly (e.g. a machine without this repo's `.env`, or to
override it -- the `env` block wins):

```jsonc
{
  "mcpServers": {
    "fsrpb": {
      "command": "uv",
      "args": ["run", "--directory",
               "/absolute/path/to/fsr-playbook-framework",
               "python", "-m", "fsr_playbooks.mcp_server"],
      "env": {
        "FSR_BASE_URL": "https://your-instance.fortisoar.example.com",
        "FSR_API_KEY":  "<scoped FortiSOAR API key>"
        // -- OR username/password instead of FSR_API_KEY (not recommended):
        // "FSR_USERNAME": "<your-FortiSOAR-username>",
        // "FSR_PASSWORD": "<password>"
      }
    }
  }
}
```

> JSON itself has no comments; the `//` lines above are for illustration -- drop
> them (and the keys you don't use) in the real file. A minimal config is just
> `FSR_BASE_URL` + `FSR_API_KEY`.

**Configuration surface.** All env vars; the per-server **`env` block wins over
the repo `.env`** (loaded with `setdefault`). Use `.env` as your dev default, the
`env` block for a portable config.

| Var | Purpose |
|---|---|
| `FSR_BASE_URL` | live FortiSOAR base URL (for `run_op` enrichment) |
| **`FSR_API_KEY`** | **preferred** FortiSOAR auth (scoped + revocable) |
| `FSR_USERNAME` / `FSR_PASSWORD` | fallback auth, only if no `FSR_API_KEY` |

**Prefer an API key over username/password.** Generate a least-privilege
FortiSOAR API key (read-only is enough for investigation) and set `FSR_API_KEY`;
the auth layer (`probes._env`) uses it over username/password. Both `.env` and
the client config are plaintext, so a revocable, scoped key contains a leak --
keep `.env` gitignored and `chmod 600` the config.

See [`docs/ARCHITECTURE_AGENT_LOOP.md`](docs/ARCHITECTURE_AGENT_LOOP.md) for how
the MCP server, web app, and in-platform connector share the same
`fsr_playbooks.llm` wiring.
