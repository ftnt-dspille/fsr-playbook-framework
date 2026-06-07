# FSR Playbook Builder — FortiSOAR Connector Plan

Goal: turn the chat-driven playbook authoring side of `fsr-playbook-framework` into a FortiSOAR connector (`.so`) that backs a chat widget. Structure the code so updates to the source app flow into the connector through a git submodule.

Scope here: **connector + portable core only.** Widget work is tracked separately in `fortisoar-widget-harness/FSR_PLAYBOOK_BUILDER_WIDGET_PLAN.md`.

---

## Architecture

```
fsr-core/                       <-- NEW standalone repo (the submodule)
  fsr_core/
    compiler/                   <-- from python/compiler/
    mcp_server/                 <-- from python/mcp_server/
    llm/                        <-- from web/backend/llm/
    agent/system_prompt.md      <-- from python/agent/
    reference/fsr_reference.db  <-- build artifact, copied at release time
  pyproject.toml
  tests/

fsr-playbook-framework/                <-- existing repo, refactored
  fsr-core/                     <-- git submodule -> fsr-core repo
  web/backend/                  <-- now imports from fsr_core.*
  web/frontend/                 <-- unchanged
  python/                       <-- shrinks: CLI, probes, evals stay; core moves out

fsr-playbook-connector/         <-- NEW repo (the connector package)
  fsr-core/                     <-- git submodule -> same fsr-core repo
  connector/
    info.json
    operations.py               <-- thin handlers calling fsr_core
    storage.py                  <-- history.db + secrets adapter
    requirements.txt
  Makefile                      <-- build .so, package, install
  tests/
```

Both consumers pin `fsr-core` by commit. Updating the connector = `git submodule update --remote fsr-core && make package`.

---

## Phase 1 — Extract `fsr-core` from `fsr-playbook-framework`

Goal: a portable Python package with **no FastAPI, no uvicorn, no SSE, no web-specific globals**. Async is fine.

1. **Create `fsr-core` repo** with `pyproject.toml` declaring `anthropic`, `pydantic`, `sqlalchemy` (if used), `pyyaml`, `jinja2`. No `fastapi`, no `sse-starlette`, no `uvicorn`.
2. **Move code:**
   - `python/compiler/` → `fsr_core/compiler/`
   - `python/mcp_server/` → `fsr_core/mcp_server/`
   - `web/backend/llm/` → `fsr_core/llm/` (all files: `anthropic_provider.py`, `tools.py`, `approvals.py`, `factory.py`, `ladder.py`, `provider.py`, `_loop_helpers.py`, `usage_log.py`, optionally `lmstudio_provider.py`, `fake_provider.py`)
   - `python/agent/system_prompt.md` → `fsr_core/agent/system_prompt.md`
3. **Audit imports.** Grep moved files for `fastapi`, `starlette`, `sse_starlette`, `request.app.state`, anything web-shaped. Refactor each into a constructor argument or a thin protocol:
   - History writer → `HistorySink` protocol (FastAPI app provides SQLite-backed impl, connector provides its own).
   - Secrets/config reader → `ConfigProvider` protocol (FastAPI uses dotenv+keyring, connector uses FortiSOAR secrets store).
   - Approval callback → `ApprovalGateway` protocol (FastAPI uses in-memory queue + SSE, connector uses persisted state keyed by `turn_id`).
4. **Public API surface** — `fsr_core/__init__.py` exports:
   ```python
   from fsr_core.llm.factory import build_provider
   from fsr_core.llm.tools import build_tool_registry, ToolRegistry
   from fsr_core.llm.approvals import ApprovalGateway
   from fsr_core.compiler import compile_yaml, validate_yaml, resolve_yaml
   from fsr_core.mcp_server import ALL_TOOLS
   ```
5. **Reference DB**: ship `fsr_core/reference/fsr_reference.db` as a build artifact via a `scripts/build_reference.py` that runs the probes. Connector and FastAPI both read from `importlib.resources.files('fsr_core.reference') / 'fsr_reference.db'`.
6. **Tests**: move/duplicate the relevant unit tests for compiler + tools into `fsr-core/tests/`. CI runs them on every PR to the submodule.

**Done when**: `python -c "import fsr_core; assert not any('fastapi' in m for m in sys.modules)"` passes, and `fsr-core`'s test suite is green.

---

## Phase 2 — Refactor `fsr-playbook-framework` to consume `fsr-core` as submodule

1. `git submodule add <fsr-core-url> fsr-core` at repo root.
2. Add `fsr-core/` to `pyproject.toml` as a path dependency (`fsr_core = { path = "./fsr-core", develop = true }`).
3. Delete the moved directories from `python/` and `web/backend/llm/`.
4. Update imports throughout `web/backend/` — `from llm.anthropic_provider` → `from fsr_core.llm.anthropic_provider`, etc.
5. Wire FastAPI's own implementations of `HistorySink`, `ConfigProvider`, `ApprovalGateway` (these may already exist inline — just lift them).
6. Run the existing e2e suite. Must pass unchanged.

**Done when**: the Svelte chat works end-to-end with the agent loop now living in the submodule.

---

## Phase 3 — Stand up `fsr-playbook-connector`

1. New repo. Add `fsr-core` as submodule at root.
2. **`connector/info.json`** — declare operations:
   - `chat_turn(messages: list, intent: str, session_id: str)` → returns `{turn_id, transcript: [...events], stop_reason}`. Runs the full async agent loop server-side. Events are tool_use / tool_result / text blocks in order.
   - `chat_resume(turn_id: str, decision: "approve"|"reject", note?: str)` → resumes a turn paused for approval; returns same shape as `chat_turn`.
   - `chat_history(session_id: str, limit?: int)` → returns prior turns from history.db.
   - `compile_yaml(yaml: str)` / `validate_yaml(yaml: str)` / `resolve_yaml(yaml: str)` — thin pass-through.
   - `push_playbook(workflow_json: dict, collection_id?: str)` — POSTs to `/api/3/workflows/` via `from integrations.crudhub import make_request` (service-to-service token against `https://localhost`; no re-auth, no loopback through public HTTPS).
   - `dry_run_playbook(workflow_json: dict, inputs?: dict)` / `run_op(...)` / `render_jinja(...)` — pass-through.
   - `health_check` — verifies Anthropic key reachability, reference DB present.
3. **`connector/operations.py`** — each operation is a ~10-line wrapper:
   ```python
   async def chat_turn(config, params):
       provider = build_provider(config["model"], api_key=secret("anthropic_api_key"))
       registry = build_tool_registry(ALL_TOOLS, context=connector_context(config))
       gateway = PersistedApprovalGateway(storage)
       result = await run_agent_turn(provider, registry, gateway,
                                     messages=params["messages"],
                                     intent=params["intent"],
                                     session_id=params["session_id"])
       return result.to_dict()
   ```
4. **`connector/storage.py`** — SQLite at the connector's data dir for `history.db` and paused-turn state. Same schema as `web/backend/history.db` (copy/move it into `fsr-core` if it makes sense; otherwise reimplement — it's small).
5. **Secrets** — Anthropic API key declared in `info.json` as a `"type": "password"` field in `configuration.fields` (with `"value": ""` — never embed a default). FortiSOAR encrypts it at rest and decrypts before calling `execute()`; the operation reads it as plaintext via `config["anthropic_api_key"]`. The platform auto-renders a "Use Vault" toggle on password fields — no extra wiring.
6. **Outbound network** — Anthropic API only. Document the egress requirement in the connector README.
7. **Build/package** — connectors ship as `.tgz` of pure Python; build via FortiSOAR RDK (`fsr build`), not a hand-rolled Makefile. A small wrapper script is fine for ergonomics:
   - `scripts/sync.sh` → `git submodule update --remote fsr-core`
   - `fsr build` → produces `fsr-playbook-connector.tgz` (RDK handles layout + manifest)
   - `pytest` → runs connector tests + `fsr-core` tests
   - Install: import the `.tgz` via the FortiSOAR Connector Store UI (or CLI).
   - Cython `.so` compilation is optional and only worth it for hot paths; default is pure Python. Runtime Python is 3.9+.
8. **Tests** — mock the Anthropic provider (`fake_provider.py` already exists in `fsr-core`); assert each operation's contract.

**Done when**: connector installs into a dev FortiSOAR instance, `health_check` passes, `compile_yaml` round-trips a known sample, and a hand-crafted `chat_turn` call with `fake_provider` returns the expected transcript shape.

---

## Phase 4 — Sync workflow

The day-to-day "I improved my original app, sync to the connector" loop:

```bash
# In fsr-playbook-framework — make changes inside fsr-core/ submodule
cd fsr-core
git checkout -b feat/new-tool
# ... edit ...
git commit -am "add new MCP tool" && git push
cd ..
# original app picks up the new commit
git add fsr-core && git commit -m "bump fsr-core"

# In fsr-playbook-connector
make sync           # pulls latest fsr-core commit
make test           # confirms still green
make package        # rebuild .so
```

**Discipline rules:**
- Never add `fastapi` / `starlette` / `uvicorn` imports inside `fsr-core`. CI in `fsr-core` greps for them and fails the build if found.
- Any new agent capability that needs platform-specific I/O is exposed as a protocol in `fsr-core`, implemented in both consumers.
- Widget UI changes do NOT trigger connector rebuilds — only `fsr-core` bumps do.

---

## Status (2026-05-28)

- **Phase 1 (in-place extraction)** ✅ complete on `main`. `fsr_core/` lives at the repo root; web backend consumes it directly. Audit + protocols in `docs/plans/FSR_CORE_EXTRACTION_AUDIT.md`.
- **Phase 3 (connector standup)** — initial cut shipped on `~/PycharmProjects/ConnectorsV2/fsr-playbook-builder`:
  - All 10 operations declared in `info.json` with password-typed `anthropic_api_key`
  - **Real:** `health_check`, `compile_yaml`, `validate_yaml`, `resolve_yaml`, `push_playbook` (via `integrations.crudhub.make_request`), `chat_turn`, `chat_resume`, `chat_history`
  - **Stubbed:** `dry_run_playbook`, `render_jinja` (need their own fsr_core entry points)
  - sqlite-backed `Storage` + `PersistedApprovalGateway` so paused HITL turns survive worker restart
  - 29 tests passing; `fsr_core` consumed via editable install for now (submodule deferred per Phase 2)
- **Agent-loop lift** ✅ done on `agent-loop-lift` branch (5 commits). `fsr_core.llm.run_agent_turn` is the shared consumer used by both `web/backend/routes/chat.py` and the connector. Plan + risk list in `docs/plans/AGENT_LOOP_LIFT_PLAN.md`.

## Resolved decisions (2026-05-28)

1. **Packaging.** Pure-Python `.tgz` built with the FortiSOAR RDK (`fsr build`); runtime Python 3.9+. No restriction on `anthropic`, `pydantic`, `sqlalchemy`, `pyyaml`, `jinja2`. Cython `.so` compilation optional, deferred. Evidence: `Miscellaneous/fortisoar/fsr_connector_toolkit/tests/CONNECTOR_BUILDING_GUIDE.md` L56-61, L2712, L2751, L2970.
2. **In-platform HTTP.** Use `from integrations.crudhub import make_request` for `/api/3/...` calls — service-to-service token, no re-auth, no public-HTTPS loopback. Reference usage: `ConnectorsV2/fortinet-fortiguard-threat-intelligence/connector.py:7,39`. Also available as `connectors.core.connector.make_request`.
3. **Secrets.** `info.json` password fields are encrypted at rest and decrypted into `config[...]` before `execute()` runs (guide L221-235, L1801-1810). Vault toggle is automatic. Implementation: declare `anthropic_api_key` with `"type":"password"`, `"value":""`.
4. **history.db scoping.** No automatic user identity in `kwargs`; widget must pass `session_id` explicitly as an operation parameter. Default schema keys on `session_id` alone; add `user_id` column only if/when multi-user history is needed. Reference: `ConnectorsV2/cyops_utilities/connector.py:51-54`.

---

## Out of scope (handled elsewhere)

- Widget UI, controller, service — see `fortisoar-widget-harness/FSR_PLAYBOOK_BUILDER_WIDGET_PLAN.md`.
- MCP Streamable HTTP transport — deferred; tool registry already supports it through the same `ToolRegistry` abstraction when ready.
- Token streaming — deferred; widget polls/renders per-turn.
