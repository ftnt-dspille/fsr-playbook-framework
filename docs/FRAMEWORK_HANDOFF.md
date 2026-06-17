# Framework handoff — `fsrpb`

Onboarding for a new engineer receiving this repo. This is the **backend
framework** (`fsrpb`): a YAML → FortiSOAR playbook compiler, a SQLite
reference store of every connector/op/param/step-type, a typed validator
(`verify_playbook`), and MCP servers that expose all of it to an agent or IDE.

> **Scope.** This repo is the framework. The **connector**
> (`fsr-playbook-builder`, a separate repo) and the **Studio** web editor
> (`web/`) are *consumers* — the connector just vendors `fsr_playbooks/` and wraps
> it as an on-platform integration. You do not need either to use the
> framework. If someone asked for "the connector code," what they usually
> want is this — the engine the connector runs.

## What's in the box

| Path | What |
|------|------|
| `fsr_playbooks/compiler/` | parser, resolver, typed walker — the compile + static-analysis core. **Pure-offline, zero live deps.** |
| `fsr_playbooks/mcp_server/` | ~80 MCP tools (compile, validate, verify, discovery, live execution, triage). Launch: `python -m fsr_playbooks.mcp_server`. |
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
  fsr-playbook-framework/     <- this repo
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

## Setup — one command

```sh
git clone <fsrpb-repo> fsr-playbook-framework
cd fsr-playbook-framework
make bootstrap
```

`make bootstrap` walks a fresh clone to a green, testable state. It's
idempotent (re-run any time — done steps are skipped) and prompts only when it
needs input:

1. **uv** — offers to `brew install` it if missing.
2. **pyfsr sibling** — clones `../pyfsr` (prompts for the git URL, or set
   `PYFSR_REPO`).
3. **deps** — `make sync` (uv venv + editable installs).
4. **reference DB** — copy the handed-over file (prompts for the path, or set
   `FSR_DB_SRC`), build from a live box (`fsrpb probe --all`), or skip.
5. **.env** — optional; created from `.env.example` (offline work doesn't need it).
6. **green-check** — runs the framework core suite (`fsr_playbooks/tests/`) and
   reports done.

Unattended: `NONINTERACTIVE=1 PYFSR_REPO=… FSR_DB_SRC=… make bootstrap`.

> `.env` is only needed for **live** work (probing, `run-op`, executing against
> a box). Offline compile/validate/verify/type-flow need just the repo + the DB.
> `make verify` (the fuller green-check) additionally runs the *connector*
> suite, which requires the separate connector repo — `make bootstrap` uses
> `fsr_playbooks/tests/` instead so it works with just the framework.

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
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.mcp_server import verify_playbook   # structured punch-list
res = verify_playbook(yaml_text=open("playbook.yaml").read())
```

**MCP servers** (config ships in `.mcp.json`, portable via `uv run`):
- `fsr-read` — lean, read-only: reference lookups, live reads, validation. Best
  for testing/validation sessions.
- `fsrpb` — the full ~80-tool authoring brain (compile, push, run, emit, debug).
- `fsr-deploy` — connector package + deploy pipeline to SOAR:
  `connector_status` (live version/health, read-only), `connector_build`
  (vendor + tarball, no install), `connector_deploy` (bump → build → install →
  warmup → verify; **mutates the live box — requires `confirm=True`**). Finds the
  connector via `$FSR_CONNECTOR_DIR` or the standard sibling layout.

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
| build the connector | the separate `fsr-playbook-builder` repo (vendors `fsr_playbooks`) |
