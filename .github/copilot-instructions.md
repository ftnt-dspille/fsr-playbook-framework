# GitHub Copilot Instructions

This repo is the **fsr-playbook-framework** -- a YAML to FortiSOAR playbook
compiler and reference store with MCP servers.

## Key facts

- Python 3.10+ (no 3.12-only syntax). Deps managed with uv (`make sync`).
- The `fsr_playbooks/` package compiles YAML into FortiSOAR playbook JSON.
- The sibling `pyfsr` package handles transport (push, trigger, query records).
  `fsr_playbooks` never imports `pyfsr` -- they're separate packages.
- Edit `fsr_playbooks/` in this repo, never the connector's vendored copy.
- CLI entry point: `fsrpb` (compile, validate, find, push, pull, run-playbook).
- Green-check: `make verify`. Fast tests: `make tests`. Lint: `make lint`.
- Reference DB: `data/fsr_reference.db` (SQLite) -- connectors, operations, step
  types, Jinja. Rebuild with `fsrpb refresh`.

## Authoring workflow

1. Write YAML (see `docs/AUTHORING.md` for step types, variables, branching)
2. `fsrpb validate in.yaml` -- check refs + diagnostics (offline)
3. `fsrpb compile in.yaml -o out.json` -- emit FSR JSON
4. `fsrpb push in.yaml` -- deploy to appliance (uses pyfsr)
5. `fsrpb run-playbook "Name" --follow` -- trigger + poll

## From Python

```python
from fsr_playbooks import compile_yaml
result = compile_yaml(yaml_text, "data/fsr_reference.db")
# result.ok, result.fsr_json, result.errors, result.warnings

from pyfsr import FortiSOAR
client = FortiSOAR("https://host", auth="<api-key>")
result = client.playbooks.run_and_wait("Playbook Name", inputs={})
# result.status, result.succeeded, result.steps, result.failure
```

## Full guide

See `AGENTS.md` for the complete agent guide (setup, CLI reference, MCP server
config, playbook authoring, conventions).
