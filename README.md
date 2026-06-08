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
