# FSR Playbook Studio — project guide

YAML → FortiSOAR playbook compiler + reference store, with a Svelte visual editor,
an MCP server, and an in-platform connector (lives in a sibling repo, see below).

## Commands (use these, don't re-derive)
- `make verify` — **the green-check for the fsr_core + connector axis** (offline): `fsr_core/tests/` + the connector's full suite, both on this repo's `.venv` (editable `fsr_core` + its `yaml`/`anthropic` deps). Run before declaring work done.
  - GOTCHA: do **not** run the connector suite via `uv run --extra test` — that builds an isolated env without `fsr_core`, so every test errors on `ModuleNotFound: yaml`. Use this repo's `.venv` python with `PYTHONPATH=.` (what `make verify` does).
  - Studio frontend (`web/frontend`, Svelte) and the live/golden contract harness are NOT in `make verify` — run them separately when working on those.
- `make tests` — fast pytest only (`-m "not live and not slow"`).
- `make e2e` — run every `examples/*.test.yaml` against live FSR (10/11 expected).
- `make dev` — backend (:47821) + frontend (:47822) together. `make preflight` checks ports, `make kill-ports` frees them.
- Single test: `uv run python -m pytest python/tests/<file>.py -q`.
- Python deps via **uv** (`make sync`); venv at `.venv/`. Runtime target is **Python 3.9** (SOAR baseline) — keep `fsr_core` 3.9-clean (no module-level PEP 604 unions).

## Repo layout
- `python/` — compiler, resolver, typed walker, MCP server (`python/mcp_server.py`), tests.
- `fsr_core/` — vendored core shared with the connector. **ALWAYS edit here (FSRPlaybookYaml/fsr_core/), NEVER edit the connector's copy directly** (`ConnectorsV2/fsr-playbook-builder/fsr-playbook-builder/fsr_core/`). `deploy.sh` runs `rsync` which blows away any direct edits to the connector's copy. Edit source → commit → deploy.
- `web/backend` (FastAPI :47821), `web/frontend` — the **Playbook Studio** editor, **Svelte 5**/Vite (:47822). This is the only frontend in this repo.
- Connector (in-platform MCP + chat): **`/Users/dylanspille/PycharmProjects/ConnectorsV2/fsr-playbook-builder`** — has `scripts/install_to_fsr.py`, `scripts/probe_fsr.py`, `tests/fsr_contract.py`. The contract harness runs **there**, after a live `probe_fsr.py` re-capture — not in this repo's `make verify`.
- **Angular widget** (the surface that renders inside FortiSOAR) is a separate WebStorm project with its own toolchain — not in this repo or the connector repo.

## Connector install/verify cycle
1. Bump connector version + use `$replace` → no service restart needed.
2. `python scripts/install_to_fsr.py` to push.
3. Drive live via `/api/integration/execute/`; offline replay via mock mode (contract harness).
4. Services: `ssh fsr-root`. Host/build details + verified API endpoints are in auto-memory.

## Conventions
- Don't kill the user's dev servers on :47821/:47822 — use ports 47831+ for any test backend.
- Branch before multi-file refactors; don't work directly on `main`.
- For mass rewrites use `sed`/`perl` in one pass, not dozens of Edit calls.
- Git commits: author as the user, no AI attribution.

## Pointers
- Live plan / current phase: `/Users/dylanspille/PycharmProjects/Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md` (check before starting work).
- FortiSOAR schema + API docs index: `/Users/dylanspille/PycharmProjects/Miscellaneous/FORTISOAR_RESOURCES_INDEX.md`.
- `TODO.md` — "Next steps" is the session resume point.
- Auto-memory holds host map, verified endpoints, and per-session resume notes.
