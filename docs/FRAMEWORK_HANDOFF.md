# Framework handoff — `fsrpb`

Onboarding for a new engineer receiving this repo. This is the **backend
framework** (`fsrpb`): a YAML → FortiSOAR playbook compiler, a SQLite
reference store of every connector/op/param/step-type, a typed validator
(`verify_playbook`), and MCP servers that expose all of it to an agent or IDE.

> **Scope.** This repo is the framework. The **connector**
> (`fsr-playbook-builder`, a separate repo) and the **Studio** web editor
> (`web/`) are *consumers* — the connector just vendors `fsr_core/` and wraps
> it as an on-platform integration. You do not need either to use the
> framework. If someone asked for "the connector code," what they usually
> want is this — the engine the connector runs.

## What's in the box

| Path | What |
|------|------|
| `fsr_core/compiler/` | parser, resolver, typed walker — the compile + static-analysis core. **Pure-offline, zero live deps.** |
| `fsr_core/mcp_server/` | ~80 MCP tools (compile, validate, verify, discovery, live execution, triage). Launch: `python -m fsr_core.mcp_server`. |
| `python/cli.py` | the `fsrpb` CLI (`fsrpb compile`, `validate`, `verify`, `probe`, `run-op`, …). |
| `python/probes/` | reference-store builders — hit a live FSR box and populate `store/fsr_reference.db`. |
| `python/fsr_read_mcp.py` | a lean **read-only** MCP server (subset of the above) for testing/validation. |
| `store/fsr_reference.db` | the 63 MB reference data backbone (gitignored — see below). |

## Prerequisites & cross-repo dependencies

1. **`uv`** — the package manager (`brew install uv`).
2. **`pyfsr` as a sibling clone.** `make sync` runs `uv pip install -e ../pyfsr`.
   It is the live HTTP client; the **offline core never imports it**, but the
   install step needs the repo present at `../pyfsr`. Clone it next to this repo.
3. **(optional) `../Miscellaneous/api_examples_catalog/catalog.sqlite`** — the
   reference DB *auto-attaches* this read-only if present, for cross-vendor API
   examples. It's **guarded** (`if exists()`): without it, everything still
   works; a few `api_example` lookups just return empty. Not required.

Directory layout the tooling expects:

```
<workspace>/
  FSRPlaybookYaml/     <- this repo
  pyfsr/               <- required sibling
  Miscellaneous/       <- optional (api examples catalog)
```

## The reference DB (the one thing git won't carry)

`store/fsr_reference.db` is **gitignored** (63 MB) — a clone won't include it,
and it's the data backbone for every reference/discovery tool. Two ways to get
it:

- **Hand it over directly (recommended).** Copy the file into `store/`. It
  needs no live box and works immediately. Rebuilding requires FSR access, so
  for someone without a box this is the only practical path.
- **Rebuild from a live box** (if they have FSR creds): set up `.env` (below),
  then `fsrpb probe --all` (or `fsrpb refresh`). Idempotent.

## Setup (fresh clone → green)

```sh
git clone <fsrpb-repo> FSRPlaybookYaml
git clone <pyfsr-repo> pyfsr            # required sibling
cd FSRPlaybookYaml
make sync                                # uv venv + editable installs
cp /path/to/fsr_reference.db store/      # the handed-over DB
make verify                              # green-check: fsr_core + connector suites
```

`.env` is only needed for **live** work (probing, `run-op`, executing against a
box). Offline compile/validate/verify/type-flow need just the repo + the DB.

```sh
cp .env.example .env     # then fill FSR_BASE_URL + one auth block
```

> Never commit `.env`. It's gitignored; keep it that way. Live upload/execute
> probes also refuse to run unless `FSR_ALLOW_E2E=true` — never set that on prod.

## Using it

**CLI** (the everyday surface):
```sh
fsrpb compile playbook.yaml          # YAML -> FSR JSON
fsrpb verify  playbook.yaml          # full static gate (type-flow, refs, schema)
fsrpb find connector virustotal      # search the reference store
fsrpb run-op virustotal query_ip --params '{"ip":"8.8.8.8"}'   # live (needs .env)
```

**Python API** (offline core — no live box):
```python
from fsr_core.compiler import compile_yaml
from fsr_core.mcp_server import verify_playbook   # structured punch-list
res = verify_playbook(yaml_text=open("playbook.yaml").read())
```

**MCP servers** (config ships in `.mcp.json`, portable via `uv run`):
- `fsr-read` — lean, read-only: reference lookups, live reads, validation. Best
  for testing/validation sessions.
- `fsrpb` — the full ~80-tool authoring brain (compile, push, run, emit, debug).

A Claude Code / MCP client that opens this repo picks up `.mcp.json`
automatically. (The gitignored `.claude/settings.json` is for personal,
machine-specific overrides only — don't rely on it for sharing.)

## What does NOT travel in a clone (by design)

- `store/*.db` (gitignored) — hand the DB over out-of-band.
- `.env` (gitignored) — secrets; recipient makes their own from `.env.example`.
- Untracked scratch (`_b3_*.py`, `_poll_*.py`, scratch eval logs) — local only.

## Boundary cheat-sheet

| Want to… | Need |
|----------|------|
| compile / validate / verify / type-flow | repo + DB (no pyfsr, no box) |
| reference lookups (connectors/ops/params) | repo + DB |
| probe / run-op / execute live | repo + DB + `pyfsr` + `.env` + reachable FSR |
| build the connector | the separate `fsr-playbook-builder` repo (vendors `fsr_core`) |
