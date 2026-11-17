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

Write YAML IR (`docs/AUTHORING.md` is the step-type reference), check it with
`fsrpb validate in.yaml`, **look at it** with `fsrpb graph in.yaml` (ASCII flow;
flags steps nothing routes to), compile with `fsrpb compile in.yaml -o out.json` or
`compile_yaml(text, db_path)` (returns structured errors, never raises), then
push and run through pyfsr (`fsrpb push`, `fsrpb run-playbook --follow`).
Worked example with Python snippets: [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

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

The `fsrpb` MCP server exposes ~16 tools (compile, validate, resolve, find
connectors/operations, step schemas/examples, run ops and playbooks, build a
playbook from a recorded session). Catalog: [`data/MCP_TOOLS.md`](data/MCP_TOOLS.md).
Client config and env vars: README, "MCP client config".

## Repo layout

```
fsr_playbooks/    compiler, resolver, typed walker, MCP server (published wheel the connector pins)
tooling/          CLI (fsrpb), probes, extra MCP servers, tests
web/              FastAPI backend + Svelte 5 Studio editor
data/             schema + reference DB + agent reference exports
examples/         YAML fixtures + expected playbook JSON
e2e/              live end-to-end harness
```

## Conventions

- **Edit `fsr_playbooks/` here.** The connector consumes it only as the released
  `fsr-playbooks` wheel pinned in its `requirements.txt`; it has no copy to edit.
- Keep Python 3.10-clean (no 3.12-only syntax). The codebase uses `Optional[X]`
  / `Dict[...]` style for historical 3.9 compatibility; match the surrounding style.
- Don't add comments unless asked.
- `make verify` is the green-check for the fsr_playbooks + connector axis.
- For mass rewrites, use `sed`/`perl` in one pass, not dozens of edits.
