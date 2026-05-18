# Connector-builder integration plan

**Started**: 2026-05-18. Owner: dcspille.

Pull two sibling projects under
`/Users/dylanspille/PycharmProjects/Miscellaneous/` into fsrpb so the
agent can both **find** real API examples for HTTP-shaped authoring
*and* **verify** that a custom-authored connector will actually run.

- `api_examples_catalog/catalog.sqlite` — 437 MB, 6,927 products,
  207k entries, 36k HTTP fixtures with response/parameter schemas,
  6,272 real connector implementations.
- `connector_building/validator/` — rung-1 static AST validator and
  rung-2 mock-replay validator (1.5k LOC together). Pairs with the
  catalog via `connector_op_matcher.py`.

This is the **other half** of the authoring story. Today fsrpb helps
you author playbooks against existing connectors. After this plan it
also helps you author the connectors themselves.

---

## Why this fits

| Existing fsrpb capability | Connector-builder analogue |
|---|---|
| Compiler + resolver + validator over playbook YAML | Rung-1 AST validator over connector source |
| `verify_playbook` typed-walker + live probe | Rung-2 mock-replay against real fixtures |
| `find_step_recipe` / `find_step_examples` | `find_api_example` / `find_api_fixture` |
| Reference store (`fsr_reference.db`) of FSR-native ops | Catalog (`catalog.sqlite`) of 3rd-party HTTP shapes |
| System-prompt rule: "call `verify_playbook` before showing YAML" | Mirror rule: "call `verify_connector` before declaring done" |

`VERIFY_PLAYBOOK_PLAN.md` is the architectural template. The same
"forcing-function MCP tool gates the agent loop" pattern applies.

---

## Source artifacts

### `catalog.sqlite` schema (read-only consumer)

| Table | Rows | Key columns we'll read |
|---|---:|---|
| `products` | 6,927 | `id, name, normalized, category` |
| `entries` | 207,419 | `product_id, action, http_method, http_path, code_snippet, code_lang, parameters_json` |
| `http_fixtures` | 36,015 | `product_id, method, url_template, query_params_json, request_body_json, response_body_json, **response_schema_json**, **parameters_schema_json**, operation_id` |
| `connector_lifecycle` | 6,272 | `repo_name, product, method_name, status, body, body_lines` |
| `entries_fts` | — | FTS5 over `(action, description, http_path, notes)` |
| `sources` | 9 | `name, url` — provenance |

Indexes already in place: `idx_entries_product`, `idx_entries_action_norm`,
`idx_entries_quality`, `idx_fix_product`, `idx_lc_method`,
`idx_lc_status`, `idx_lc_repo`.

### Validator surface

- `validator/runner.py` — `Issue` dataclass (`code, severity, message, file, line, context`), `ConnectorCtx` (parsed info.json + AST roots), `validate_connector(root) → list[Issue]`.
- `validator/checks.py` — 364 lines of rung-1 checks grouped:
  - **PKG** — package files
  - **INFO** — info.json semantics
  - **OP** — operation dispatch + signatures
  - **IMP** — imports
  - **HEALTH** — `check_health`
  - **ERR** — error handling
  - **PARAM** — parameter usage
- `validator/rung2.py` — 955 lines: FSR runtime stubs (`connectors`, `connectors.core`, `connectors.cyops_utilities`, `integrations`), permissive-module fallback, `requests_mock` injection, fixture-driven response synthesis, URL-shape probe, KeyError-driven param augmentation.
- `connector_op_matcher.py` — AST-extracts URL/method/name hints from `operations.py`, scores against `http_fixtures` (vendor + method + path-token + name-token overlap), returns top-N `Match` rows.

---

## Non-goals

- **Not** copying or vendoring the catalog. ATTACH read-only; the file
  stays under `Miscellaneous/`. Distribution decision deferred to
  `TODO.md` D1 (slim base vs optional sidecar).
- **Not** rewriting the validators. The plan adopts them in-place
  under `python/connector_validator/` with minimal refactors (hardcoded
  paths → config, framework-stub install isolated).
- **Not** running connectors against the live FSR instance. Rung 2 is
  mock-replay only; live verification is `run_op` (already wired).
- **Not** authoring connectors *for* the user yet. This plan ships the
  lookup + verifier; agent-driven authoring lands in a follow-up that
  reuses the same surfaces.

---

## Phasing

Each phase is independently shippable; later phases assume earlier ones
landed.

| Phase | Status | Notes |
|---|---|---|
| 0 — Catalog read-path | ⏳ not started | ATTACH + 2 MCP tools. No new code in `Miscellaneous/`. |
| 1 — Adopt rung-1 validator | ⏳ not started | `python/connector_validator/`, `fsrpb verify-connector` CLI, MCP tool. |
| 2 — Rung-2 mock-replay | ⏳ not started | Behind `--mock-replay` flag; depends on Phase 0 catalog ATTACH. |
| 3 — `verify_connector` forcing-function rule | ⏳ not started | System-prompt rule; mirrors `verify_playbook`. |
| 4 — Editor surface | ⏳ not started | Connector authoring workspace + verify badges. |
| 5 — Connector-lifecycle mining | ⏳ not started | `find_connector_implementation` MCP tool over `connector_lifecycle.body`. |

---

### Phase 0 — Catalog read-path

**Goal**: agent can search the catalog without anything else changing.

**Work**:

1. Add `python/store/catalog_attach.py` — single helper that opens an
   `sqlite3.connect(fsr_reference.db)` then `ATTACH DATABASE
   '<configurable catalog path>' AS cat`. Path comes from env
   `FSRPB_API_CATALOG` (defaults to `~/PycharmProjects/Miscellaneous/api_examples_catalog/catalog.sqlite`
   for dev; in prod, downloaded via a future `fsrpb train --with-api-catalog`).
2. New MCP tools in `python/mcp_server/tools_catalog.py`:
   - `find_api_example(product, q, limit=5)` — FTS over
     `entries_fts` joined to `entries` + `products`. Returns slim rows
     `(action, http_method, http_path, code_snippet, source_url)` by
     default; `verbose=True` returns `parameters_json` + `description`.
   - `find_api_fixture(product, method, path)` — query
     `http_fixtures` for an exact-shape example with
     `response_schema_json` and `parameters_schema_json`. Returns slim
     row plus the schemas. The forcing-function fallback when fsrpb's
     own `operations.output_schema` is stale or empty.
   - `find_api_product(name)` — fuzzy search the 6,927 products since
     users will misspell vendor names. Wraps the
     `products.normalized` index + `difflib.get_close_matches`.
3. Bridge into the existing `synthesize_http_step` stub (already an
   MCP tool name) — given a `fixture_id`, materialize an
   `http_request` step argument block from `request_body_json` +
   `query_params_json`.
4. System-prompt addition under "Latent capabilities":
   > **HTTP-shaped authoring** — when the user wants an action against
   > a vendor with no native FSR connector (or the FSR op is missing
   > params), call `find_api_fixture(product, method, path)` first.
   > It returns a real request shape grounded in OpenAPI/test corpora.
5. Tests under `python/tests/test_catalog_tools.py`:
   - Top-1 hit for canned queries: "splunk run search",
     "servicenow create incident", "crowdstrike quarantine endpoint".
   - Confirm `find_api_fixture` returns schema JSON for at least one
     known operation (`jira`, `get_issue`).
   - Graceful behavior when the catalog file is missing
     (`FSRPB_API_CATALOG=/nonexistent` returns
     `{ok: false, code: "catalog_unavailable"}` rather than throwing).

**No agent-facing changes beyond the new tools.** Existing flows are
unaffected.

**Estimated effort**: 1–2 days.

---

### Phase 1 — Adopt rung-1 validator

**Goal**: `fsrpb verify-connector <dir>` lints a connector dir and
returns structured issues. No catalog dependency.

**Work**:

1. Copy `connector_building/validator/{runner.py,checks.py,__init__.py}`
   into `python/connector_validator/`. Drop the `__main__.py` runner
   (we have `cli.py`).
2. Refactor `Issue.fmt` to also serialize as `{code, severity, message,
   file, line, context}` (it already is structurally) for JSON output.
3. New `python/cli.py` subcommand `fsrpb verify-connector <dir>
   [--json]` — calls `validate_connector(Path(dir))`, prints
   `Issue.fmt()` per line by default, or a JSON envelope with
   `--json`.
4. New MCP tool `verify_connector(connector_dir)` in
   `python/mcp_server/tools_verify_connector.py`:
   ```python
   verify_connector(connector_dir: str) -> {
       ok: bool,
       ready: bool,                # ok=true AND no errors AND ≤2 warnings
       issues: list[Issue],        # JSON-shaped
       summary: {pkg, info, op, imp, health, err, param},  # counts per group
       next_actions: list[str],
   }
   ```
5. Tests under `python/tests/test_connector_validator.py`:
   - Fixture: a known-good connector dir (copy `Miscellaneous/connector_building/jira`).
   - Fixture: a known-bad connector (missing `info.json`, malformed
     dispatch dict) — pin the issue codes.
   - JSON envelope shape stable across runs.

**Estimated effort**: 1 day.

---

### Phase 2 — Rung-2 mock-replay

**Goal**: rung-1 says "shape looks ok"; rung-2 says "the handler
actually fires the right URL and parses a real response."

**Work**:

1. Copy `connector_building/validator/rung2.py` into
   `python/connector_validator/rung2.py`. Remove the hardcoded
   `_CATALOG_DIR` path; consume `FSRPB_API_CATALOG` instead.
2. Extract the FSR runtime stub install (`_install_framework_stubs`)
   into `python/connector_validator/stubs.py` so it's reusable and
   testable in isolation.
3. Make `requests_mock` an optional dep:
   `pip install requests-mock` documented in `AUTHORING.md`; tool
   returns `{ok: false, code: "requests_mock_unavailable"}` if
   missing.
4. Extend the MCP tool:
   ```python
   verify_connector(connector_dir: str, *,
                    mock_replay: bool = False,
                    operations: list[str] | None = None) -> ...
   ```
   - `mock_replay=False` → rung-1 only (Phase 1 behavior).
   - `mock_replay=True` → rung-1 + rung-2; `operations` optionally
     filters to a subset.
   - Reuses `connector_op_matcher.match_connector` (also copied or
     adapted) to wire each operation to a catalog fixture.
5. Tests:
   - `jira` connector + `get_issue` operation → assert one successful
     replay with a captured `OpRun`.
   - URL-template-mismatch synthetic fixture → assert rung-2 emits a
     `RUNG2_URL_MISMATCH` issue.
6. CLI flag: `fsrpb verify-connector <dir> --mock-replay [--op
   <name>]`.

**Estimated effort**: 2–3 days (the mock infrastructure is the long
pole; the logic is already written).

---

### Phase 3 — `verify_connector` forcing-function rule

**Goal**: same forcing-function gate `verify_playbook` introduced for
playbooks, applied to connector authoring.

**Work**:

1. Add to `python/agent/system_prompt.md`, in a new section "Connector
   pre-submit gate":
   > Before declaring a custom connector done, call `verify_connector`
   > on its directory. If `ready` is False, apply each
   > `required_fixes` entry and re-call. Do not present the user a
   > connector dir you have not verified. Use `mock_replay=true` once
   > rung-1 is clean, to confirm the handler actually fires the
   > expected URL shape.
2. Eval scoring extension: new metrics in `python/evals/`:
   - `connector_verify_called` (bool)
   - `connector_verify_iterations_until_ready` (int)
   - `final_connector_verify_ready` (bool)
3. New eval task `build_http_connector` under `python/evals/tasks/` —
   prompt asks to author a minimal HTTP connector for a chosen product
   from the catalog. Gold = matching `connector_lifecycle.body` for
   the same product/method if available; otherwise the test asserts
   the dispatch dict + info.json shape only.

**Estimated effort**: 1 day (mostly prompt + eval plumbing).

---

### Phase 4 — Editor surface

**Goal**: human user can browse the catalog, click "scaffold a
connector," and watch verify run.

**Work**:

1. New SvelteKit route `/connector` (or sub-tab of the existing
   workspace).
2. Three panels:
   - **Browse**: search the catalog by product / method / intent
     (drives `find_api_example` / `find_api_product`).
   - **Scaffold**: pick fixtures → emit info.json + operations.py
     skeleton; reuse `synthesize_http_step`'s shape mapping.
   - **Verify**: live `verify_connector` results with per-issue
     severity badges; mirrors the existing per-step verify badges on
     the playbook canvas.
3. Backend route `/api/connector/scaffold` (POST fixture_ids → emits a
   tarball or staged dir under `store/connector_drafts/<name>/`).
4. Reuse the `FailedRunsPanel` pattern for the verify result list.

**Estimated effort**: 3–5 days.

---

### Phase 5 — Connector-lifecycle mining

**Goal**: when the agent is authoring a connector, it can ask "show me
how 5 real connectors implement `get_record` in the
threat-intel category" instead of guessing.

**Work**:

1. New MCP tool `find_connector_implementation(product=None,
   method_name=None, category=None, status='nontrivial', limit=5)` —
   query `connector_lifecycle` joined to `products` (when
   `connector_lifecycle.product` matches).
2. System-prompt addition:
   > **Authoring a connector method?** Call
   > `find_connector_implementation(method_name=...)` before writing
   > the body. The catalog has 6,272 real method bodies grouped by
   > status — copy the shape, not the code.
3. Tests:
   - Top-1 hit for `method_name="get_record",
     status="nontrivial"` returns at least one row with a non-empty
     `body`.

**Estimated effort**: 0.5 day.

---

## Risks / unknowns

1. **Catalog size at distribution.** 437 MB doesn't fit in the
   shippable base image. TODO.md D1 already anticipates an optional
   sidecar gated behind `fsrpb train --with-api-catalog`. Phases 0/2/5
   should gracefully degrade with
   `{ok: false, code: "catalog_unavailable"}` when the file isn't
   present.
2. **Licensing of `sources`.** Only 9 rows — manually verify the
   provenance before shipping the catalog to anyone else. If any
   row's source is non-redistributable, filter rows by `source_id`
   at copy time.
3. **`http_fixtures.response_schema_json` quality.** It's
   OpenAPI-derived; spot-check a handful before using it as
   authoritative shape data in `verify_playbook`'s typed walker
   fallback.
4. **Rung-2 stub install is intrusive.** It registers fake
   `connectors`, `connectors.core`, `connectors.cyops_utilities`,
   `integrations` modules into `sys.modules`. Confine to a context
   manager and revert on exit so it can't contaminate other tests.
5. **Cross-project imports.** `rung2.py` currently has
   `sys.path.insert(0, _CATALOG_DIR)` to find `connector_op_matcher`.
   Adopt the matcher into `python/connector_validator/matcher.py`
   rather than path-tricks.

---

## Cross-references

- **D3** in `../../TODO.md` (`Wire api_examples_catalog as
  first-class lookup`) is fully addressed by Phase 0 of this plan.
  Once Phase 0 lands, strike D3 from TODO.md and link here.
- **D1** in `../../TODO.md` (`Distribution`) — the catalog is the
  largest single artifact involved; this plan's Phase 0 must
  coexist with D1's sidecar story.
- **HTTP virtual-connector track** in `../../TODO.md` (`Architecture
  review findings → HTTP virtual-connector + api_examples_catalog`)
  — superseded by this plan. Items there:
  - `search_api_examples` MCP → Phase 0 (`find_api_example`).
  - `synthesize_http_step` MCP → Phase 0 (backed by fixtures).
  - `http-virtual-connector` recipe kind → out of scope (separate
    recipe-generator work).
  - `connector_catalog_map` cross-link table → unneeded; the matcher
    runs at query time.
  - Pagination + auth taxonomy mapping → still open, not addressed
    here.
- `VERIFY_PLAYBOOK_PLAN.md` is the architectural template for the
  `verify_connector` forcing-function rule (Phase 3) and the eval
  scoring shape (Phase 3 metrics).

---

## Success criteria

- Phase 0: agent calls `find_api_example` / `find_api_fixture` at
  least once per HTTP-authoring chat session in the agent-stats
  census.
- Phase 1–2: every connector under
  `Miscellaneous/connector_building/{jira,http,recorded-future-feed,…}`
  gets a `verify-connector` run with zero new false-positive errors
  vs. the standalone validator output.
- Phase 3: agentic eval `build_http_connector` reaches
  `final_connector_verify_ready=True` in ≥80% of runs after ≤2
  verify→fix iterations.
- Phase 5: agentic eval session for "author a `get_record` operation"
  shows `find_connector_implementation` called before any code is
  written.
