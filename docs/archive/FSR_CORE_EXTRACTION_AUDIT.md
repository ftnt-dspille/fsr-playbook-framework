# fsr-core Extraction — Import & Coupling Audit

Pre-Phase-1 audit for `FSR_CONNECTOR_PLAN.md`. Scope: `python/compiler/`, `python/mcp_server/`, `web/backend/llm/`. Question for each file: what must change before it can live in a FastAPI-free package?

Date: 2026-05-28. Tooling: ripgrep over the three trees.

## Headline

**Zero** `fastapi` / `starlette` / `sse_starlette` / `uvicorn` / `Request` / `HTTPException` / `Depends` / `app.state` imports in any of the three trees. The agent loop, MCP tool layer, and compiler are already framework-agnostic at the syntactic level. The remaining work is:

1. One hard import of `backend.settings` from `web/backend/llm/factory.py`.
2. Two hard-coded reference-DB paths anchored to repo layout.
3. Several env-var reads that should accept constructor arguments (env can stay as the fallback).

The approval gateway and history sink that the plan worries about — they already don't exist inside these trees. History is written by `web/backend/` route code, not by the LLM module. Approvals are an in-memory dict (`approvals.py`) with no SSE/queue/HTTP coupling; the suspended-session record is the entire contract.

## Per-tree findings

### `python/compiler/`

- **No web-framework imports.** Pure stdlib + pydantic + jinja2 + sqlite3.
- **Hard-coded reference DB path** — `validator.py:17` computes `Path(__file__).resolve().parent.parent.parent / "store" / "fsr_reference.db"`, and `rulesets/_shared.py:290-307` does the same with an `FSRPB_DB` env override and an in-tree fallback. **Refactor:** introduce a `ReferenceDB` provider (resolved via `importlib.resources.files('fsr_playbooks.reference') / 'fsr_reference.db'`) and pass the path/connection in. Keep `FSRPB_DB` as the last-resort fallback.
- `rulesets/feed_ingest.py:56` reads `FSRPB_INFO_JSON`. Same fix — accept a path argument; env is the fallback.
- Everything else (resolver, typed_walker, render_analyzer, jinja_typing, emitter, parser, etc.) takes a `sqlite3.Connection` already and is portable as-is.

### `python/mcp_server/`

- **No coupling whatsoever** — no env reads, no web imports, no file-path globals. The only repo-relative reference is a docstring at `tools_catalog.py:144` mentioning a `$HOME/...` corpus path inside an error message; cosmetic, not code.
- Moves as-is.

### `web/backend/llm/`

- **`factory.py:34` — `from backend import settings`.** This is the *only* import that ties the LLM layer to the FastAPI app. The settings module owns provider selection, API keys (via keyring), URLs, models. **Refactor:** replace with a `ConfigProvider` protocol that returns the equivalent `ProviderConfig`. FastAPI side supplies one backed by `backend.settings`; connector side supplies one backed by `config["anthropic_api_key"]` etc.
- **`approvals.py`** — in-memory dict + threading lock, 10-minute TTL, no FastAPI coupling. The route layer pops from it on `/api/approvals/{id}`, but the module itself doesn't care who calls. Moves as-is; connector wraps it with persistence (per plan — `PersistedApprovalGateway`).
- **`anthropic_provider.py:41`** — `STUDIO_ANTHROPIC_MODEL` env var as default model. Fine to keep; the constructor already accepts `model` and `api_key` kwargs and the SDK falls back to `ANTHROPIC_API_KEY` env if neither is passed. No work needed.
- **`tools.py:259`** — `EVAL_APPROVAL_POLICY` env. Used only by the eval harness; keep.
- **`usage_log.py:43`** — `STUDIO_USAGE_LOG` env. The log path is the only stateful thing; trivial to parameterize but env-fallback is fine.
- **`lmstudio_provider.py`** — three env vars for local LM Studio. Self-contained; keep.

## Implied protocol surface for `fsr_playbooks`

Distilled from the above; matches the plan's intent in §1.3:

```python
class ConfigProvider(Protocol):
    def provider_config(self, name: str) -> ProviderConfig: ...
    # FastAPI impl: backend.settings.load_provider(name)
    # Connector impl: returns ProviderConfig from config["anthropic_api_key"], etc.

class ReferenceDB(Protocol):
    def connect(self) -> sqlite3.Connection: ...
    # FastAPI impl: open store/fsr_reference.db (or FSRPB_DB)
    # Connector impl: open importlib.resources.files('fsr_playbooks.reference') / 'fsr_reference.db'

class ApprovalGateway(Protocol):
    def stash(self, session: SuspendedSession) -> None: ...
    def pop(self, approval_id: str) -> SuspendedSession | None: ...
    def peek(self, approval_id: str) -> SuspendedSession | None: ...
    # FastAPI impl: in-memory (current approvals.py)
    # Connector impl: sqlite-backed (paused-turn rows keyed by turn_id)
```

The plan's `HistorySink` does **not** need to live in `fsr-core` — history-writing currently happens in `web/backend/` route handlers, not in the LLM module. The connector implements its own; nothing to extract.

## Migration steps (refined)

1. Create `fsr_playbooks/` in-place (under the current repo) before splitting to its own repo. Move trees, fix the three coupling points, run existing tests.
2. Add `fsr_playbooks/protocols.py` with the three Protocols above.
3. `web/backend/llm/factory.py` → `fsr_playbooks/llm/factory.py`: drop `from backend import settings`; accept a `ConfigProvider`. Add a `_FastAPIBackendConfigProvider` in `web/backend/` that wraps `backend.settings` and inject it at app startup.
4. `validator.py` + `rulesets/_shared.py`: accept a `ReferenceDB` (or just a `sqlite3.Connection`); keep the env+path fallback as a default impl for CLI/tests.
5. Approvals: rename the in-memory store to `InMemoryApprovalGateway` implementing the protocol; FastAPI keeps using it, connector subs in a persisted one in Phase 3.
6. Verify with `python -c "import fsr_playbooks, sys; assert not any('fastapi' in m for m in sys.modules)"` and the existing pytest suite.

## Open items uncovered during audit

- None blocking. Reference DB ships as a build artifact per plan §1.5 — confirm the build script (`scripts/build_reference.py`) exists or needs writing; current DB at `store/fsr_reference.db` is git-tracked, so for Phase 1 we can just copy it in.
