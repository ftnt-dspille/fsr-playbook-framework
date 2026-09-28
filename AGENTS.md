# AGENTS.md -- fsr-playbook-framework

Guide for coding agents (Copilot, Cursor, Windsurf, Claude, etc.) working with
this repo. For internal dev/tracker info, see CLAUDE.md.

## What this is

A YAML → FortiSOAR playbook compiler and reference store. You write playbooks
in a simple YAML IR; the compiler turns them into FortiSOAR playbook JSON.
It also ships MCP servers that expose the compiler, reference data, and
playbook-run tools to agents.

This repo does the **compiling**. The sibling [`pyfsr`](https://pypi.org/project/pyfsr/)
package does the **transport** (push to appliance, trigger playbooks, query
records). They're separate: `fsr_playbooks` never imports `pyfsr`.

## Setup

```sh
make bootstrap     # fresh clone -> .venv + deps + ready to test
# or:
make sync          # just create .venv and install deps (uv)
```

Python 3.10+. Dependencies managed with [uv](https://docs.astral.sh/uv/).

## Key commands

```sh
make verify        # offline green-check (mypy + pytest + connector suite)
make tests         # fast pytest only (excludes live + slow)
make lint          # ruff
fsrpb --help       # CLI entry point
```

## The workflow: author → compile → deploy → run

### 1. Author YAML

```yaml
collection: My Demo
visible: true
playbooks:
  - name: Hello
    steps:
      - name: Start
        type: start
        next: Set Var
      - name: Set Var
        type: set_variable
        next: Lookup
        vars:
          target: "Fortinet"
      - name: Lookup
        type: connector
        connector: fortinet-fortisiem
        operation: get_org_name_by_org_id
        config: ""
        params:
          domain_id: "{{ vars.target }}"
        next: Done
      - name: Done
        type: end
```

See [`docs/AUTHORING.md`](docs/AUTHORING.md) for the full step-type reference,
variables, branching, looping, and universal step keys (`when`, `retry`,
`for_each`, `with`, `set`, etc.).

### 2. Compile to FortiSOAR JSON

```sh
fsrpb compile in.yaml -o out.json    # emit FSR import envelope
fsrpb validate in.yaml               # check refs + "did you mean..." diagnostics
```

From Python:

```python
from pathlib import Path
from fsr_playbooks import compile_yaml

result = compile_yaml(Path("in.yaml").read_text(), Path("data/fsr_reference.db"))
if not result.ok:
    for err in result.errors:
        print(f"[{err.severity}] {err.code}: {err.message}  ({err.path})")
else:
    collection = result.fsr_json["data"][0]
```

`compile_yaml(text, db_path) -> CompileResult` returns `.ok`, `.fsr_json`,
`.errors`, `.warnings`, `.ir`. It reports problems as structured `CompileError`s,
never raises.

### 3. Deploy + run (uses pyfsr)

```sh
pip install pyfsr                    # transport layer
fsrpb push in.yaml                   # compile + push to appliance
fsrpb run-playbook "Hello" --follow  # trigger + poll to terminal
```

From Python:

```python
from pyfsr import FortiSOAR

client = FortiSOAR("https://your-fortisoar-host", auth="<api-key>")
client.workflow_collections.create(
    name=collection["name"],
    uuid=collection["uuid"],
    workflows=collection["workflows"],
)

# One-call trigger + wait + typed result
result = client.playbooks.run_and_wait("Hello", inputs={})
print(result.status)        # 'finished' / 'failed' / 'terminated'
print(result.succeeded)     # True iff status == 'finished'
```

## CLI reference (`fsrpb`)

Key commands (see [`docs/CLI.md`](docs/CLI.md) for the full list):

| Command | Purpose |
|---------|---------|
| `fsrpb compile in.yaml -o out.json` | YAML → FSR JSON |
| `fsrpb validate in.yaml` | Check refs, diagnostics (offline) |
| `fsrpb push in.yaml` | Compile + deploy to appliance |
| `fsrpb pull <name\|uuid>` | Fetch a live playbook as YAML |
| `fsrpb pull-collection <name>` | Fetch a whole collection as YAML |
| `fsrpb diff in.yaml` | Local YAML vs live appliance |
| `fsrpb search <query>` | Search connectors, operations, steps, Jinja |
| `fsrpb find-step-examples <type>` | Real-world examples for a step type |
| `fsrpb resolve in.yaml` | Show resolved variable wiring |
| `fsrpb triggers [module]` | List manual-trigger playbooks |
| `fsrpb run-playbook <name> --follow` | Trigger + poll a deployed playbook |
| `fsrpb run-op <connector> <operation>` | Fire a single connector op |
| `fsrpb explain <kind> <name>` | Explain a connector/step/filter/module |
| `fsrpb refresh` | Rebuild the reference DB from probe output |
| `fsrpb picklist list` | List picklists for a module |

## Reference store

`data/fsr_reference.db` (SQLite) is the single source of truth for connectors,
operations, parameters, step types, Jinja filters/macros, and step examples.
Query it via SQL or `fsrpb find`/`fsrpb explain`. `fsrpb refresh` rebuilds it
from a live FortiSOAR.

The published PyPI wheel ships a **slim** catalog (step types + Jinja + connector
operations). Instance-specific modules, fields, and picklists require running
`fsrpb refresh` against your own FortiSOAR.

## MCP server

The `fsrpb` MCP server exposes ~16 tools to any MCP-capable agent: compile,
validate, resolve YAML, find connectors/operations, get step schemas/examples,
run connector operations, run deployed playbooks, and build a playbook from a
recorded session. See [`data/MCP_TOOLS.md`](data/MCP_TOOLS.md) for the full
catalog.

Config (any MCP client -- Claude Desktop, Cursor, Copilot, Windsurf, etc.):

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
        "FSR_API_KEY": "<scoped FortiSOAR API key>"
      }
    }
  }
}
```

| Var | Purpose |
|---|---|
| `FSR_BASE_URL` | live FortiSOAR base URL |
| `FSR_API_KEY` | preferred auth (scoped + revocable) |
| `FSR_USERNAME` / `FSR_PASSWORD` | fallback auth (not recommended) |

## Repo layout

```
fsr_playbooks/    compiler, resolver, typed walker, MCP server (vendored into connector)
tooling/          CLI (fsrpb), probes, extra MCP servers, tests
web/              FastAPI backend + Svelte 5 Studio editor
data/             schema + reference DB + agent reference exports
examples/         YAML fixtures + expected playbook JSON
e2e/              live end-to-end harness
```

## Conventions

- **Edit `fsr_playbooks/` here**, never the connector's vendored copy. `deploy.sh`
  rsyncs from this repo and overwrites direct edits to the connector.
- Keep Python 3.10-clean (no 3.12-only syntax). The codebase uses `Optional[X]`
  / `Dict[...]` style for historical 3.9 compatibility; match the surrounding style.
- Don't add comments unless asked.
- `make verify` is the green-check for the fsr_playbooks + connector axis.
- For mass rewrites, use `sed`/`perl` in one pass, not dozens of edits.
