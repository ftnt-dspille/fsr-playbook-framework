# FSRPlaybookYaml — TODO / resume state

**Last touched**: 2026-05-06. Live FSR target: `https://10.99.249.205` (label `dev`).

## Success ladder + LLM-agnostic groundwork (added 2026-05-06)

**Principle**: producing valid YAML is the start of the job, not the end.
A playbook is useless if it doesn't run on a real FSR and produce the
asked-for outcome. Every check below is deterministic code, callable as
an MCP tool, returning structured `{ok, error_code, message, suggestions[]}`.

Full strategy in `CHAT_APP_PLAN.md` "Success ladder + LLM-agnostic strategy
(2026-05-06)". Ordered punch list (load-bearing minimum: 1, 2, 4):

1. ~~**I1 + I2 — picklist + connector prechecks**~~ ✅ DONE 2026-05-06.
   New module `python/recipes/prechecks.py` with `check_connector_installed`
   + `check_picklist_value` + `run_recipe_prechecks` orchestrator.
   Wired into `fsrpb generate-recipe` (with `--skip-prechecks` for offline).
   Surfaced as MCP tools `precheck_connector_installed` +
   `precheck_picklist_value`. L2 of the success ladder is now partially
   live; `resolve_yaml` (item 2 below) bundles these for whole-YAML checking.
2. ~~**`resolve_yaml` MCP tool**~~ ✅ DONE 2026-05-06.
   New MCP tool wraps `validate_yaml` + the live prechecks; extracts every
   connector and `{{ 'PL' | picklist('value') }}` literal from the YAML,
   verifies each on the live FSR, returns one consolidated report. CLI
   parity: `fsrpb resolve <file>` (`--json` for machine-readable).
   Verified end-to-end against `dev` FSR: catches `'In Progress'` →
   `'Investigating'` for AlertStatus, resolves `Severity/Critical` to its
   real IRI. Jinja-var reachability still pending (see item 4 below).
3. **Surface `output_schema_observed` inline in `run_op`** — already cached
   at `mcp_server.py:81-96`; agent should not need a follow-up
   `get_op_schema` call. ~1 hr.
4. **Variable-reachability ruleset** — DAG walk: every `{{ vars.steps.X.Y }}`
   references a prior step whose declared output contains `Y`. Source:
   `operations.output_schema_observed`. ~3 hr. **Highest-ROI single check
   we don't have today.** New module under `python/compiler/rulesets/`.
5. **I10 stepper skeleton + `dry_run_playbook` MCP tool** — L3 of the
   ladder. ~4 hr scaffold; ~11 hr full per-step-type handlers.
6. **`assert_playbook_outcome` MCP tool** — declarative expectations
   (record exists, field equals, count > N). Enables L5 + eval harness.
   ~3 hr.
7. **Externalize system prompt + structured tool I/O audit** — move
   implicit web prompt to `python/agent/system_prompt.md`; convert prose
   errors in `compile_yaml`/`validate_yaml`/`run_op` to
   `{ok, error_code, message, suggestions[]}`. Promote difflib hints to
   `suggestions`. ~2 hr. *Required for any LLM to drive the product.*
8. **LLM evaluation harness** — `python/eval/harness.py`: 3 tasks × 3
   models (Claude / GPT-4o-mini / LMStudio local), scores L1→L4 +
   gold-fixture match. Proves "LLM-agnostic" is a measurement, not a
   claim. ~6 hr.
9. **`diagnose_yaml_against_pb_execution` MCP tool** — pull failed run env,
   render each step's args, surface shape mismatches. Closes the
   failure-recovery loop. ~3 hr.
10. **Demo reset script + full-transcript capture** — `fsrpb demo prep`
    resets `dev` FSR known state; web backend persists full turn log per
    session (token usage logging already exists). ~2 hr.
11. **Inventory web dashboard** — fill in the route alongside the CLI
    stubbed 2026-05-06 (`python/inventory.py` + `fsrpb inventory`). ~3 hr.

**Token-budget audit**: smaller / local models can't afford 20K-token tool
responses. `get_step_type` was trimmed 4.9KB → 1.8KB on 2026-05-04; audit
remaining tools and default `verbose=False` everywhere with full payload
behind an explicit flag.

**Estimated total to MVP-demo-ready: ~30–35 focused hours.**

## Architecture review findings (2026-05-06)

Full review captured the project is sound and on-direction for an AI FortiSOAR
assistant (compiler + SQLite reference store + MCP server with deterministic
lookups; LLM only authors YAML and sequences tools). Action items distilled
below; cross-reference the existing I1–I10 list in the next section.

**Priority queue (start here)**
1. **I1 — live picklist precheck at recipe generation** (~1 hr). Generator
   should call `render_jinja` on every `{{ 'PL' | picklist('value') }}` and
   FAIL with suggested alternatives if it doesn't resolve. Today picklists
   silently emit broken IRIs. Edit point: `python/recipes/generator.py` +
   `python/compiler/resolver.py`.
2. **I2 — connector-installed precheck** (~30 min). `GET
   /api/integration/connectors/{name}/{version}` before emitting; fail with
   "solution pack X needed" if missing.
3. **I3 — recipe persistence + `generate_recipe` MCP tool** (~1.5 hr). Add
   `recipes` table; expose tool so agents can emit/retrieve recipes inline
   (today it's CLI-only via `fsrpb generate-recipe`).
4. **Linter v1 core 3** (~2 hr; subset of TODO #9). Bare `yes/no` in decision
   branches, step-name charset (`[A-Za-z0-9 _]` only), missing `mock_result`
   on Fetch in templates.
5. **I10 stepper skeleton** (~2 hr research, 11 hr full). Unblocks
   `dry_run_playbook` MCP tool and agent self-correction loop.

**MCP server fixes (deferred but tracked)**
- `run_op` should return both the live result AND the inferred shape it
  cached, so the agent doesn't need a follow-up `get_op_schema` round-trip.
  Edit: `python/mcp_server.py` lines 81–96.
- Tool-result truncation in web backend is too aggressive (4000 char cap,
  `web/backend/routes/chat.py:64–67`). Stream large results or raise the cap
  per tool category (`get_op_schema`: 20K; `search_playbooks`: 10K/result).
- Add `diagnose_yaml_against_pb_execution` tool: pull failed run env, render
  each step's args, surface shape mismatches. Closes the manual debug loop.
- Expose `generate_recipe` as a tool (see I3 above).

**SQLite efficiency wins (low priority, real ROI)**
- Wire FTS5 on `connectors`/`operations` (today `find_connector` uses LIKE
  fallbacks at `mcp_server.py:131–150`).
- Denormalize picklist options into a `param_options(connector, op, param,
  label, value, iri)` table so SQL — not Python JSON-decode — filters them.
- Move `connector_config_map.json` into a `connector_configs` SQLite table
  populated by `probe_connectors` tier 1; lets `resolve_picklist_value`
  query without a side JSON file.
- Widen `playbooks_seen` FTS to index Jinja exprs, step args, connector
  calls so agents can search by intent ("fetches from VirusTotal") not just
  workflow name.

**Freshness / sync gaps**
- Probes are on-demand, not continuous. For 24/7 agent use, add a
  background sync (hourly or change-notification driven) so newly-installed
  connectors land in `find_connector` without a manual probe re-run.
- Recipe cache not persisted (covered by I3 above).
- Connector-version collapse: `INSERT OR REPLACE` on connector name only
  keeps latest version; recipes pinned to v1 vs v2 will drift. Low priority.

**LLM-vs-deterministic audit**
- Lookups (`find_connector`, `validate_yaml`, `compile_yaml`) are correctly
  deterministic — no LLM in the resolution loop. Preserve that.
- Gaps where LLM is currently filling in for missing determinism: picklist
  resolution (I1), connector availability (I2), sample-data shapes (I8/I9).
  Each closes a hallucination surface.
- Decision-branch authoring relies on the agent to quote `yes/no` —
  promote to a hard linter rule (see linter core 3 above).

**Multi-provider cost tracking**
- `web/backend/llm/provider.py:74–78` sums tokens per chat regardless of
  model. Stamp `model` into each `UsageEvent` so per-turn pricing works
  when the user switches providers mid-chat.

**HTTP virtual-connector + api_examples_catalog integration (added 2026-05-06)**
The `Miscellaneous/api_examples_catalog/catalog.sqlite` (5.9 GB; 207,419
entries across 6,927 products with FTS5) is ATTACHed read-only at
`python/probes/common.py:62-66` but **zero queries reference it today**.
Combined with FortiSOAR's HTTP connector (10 ops including `http_request`,
`http_paginate`, `fetch_records`), this corpus lets the assistant author
playbooks for vendors we don't have a dedicated connector for.

- **HTTP v2.0.0 not in reference DB** — `Miscellaneous/connector_building/http`
  has v2 (adds `http_paginate`, `fetch_records`); our DB has v1.0.0 only.
  Re-run `probe_connectors` against that path. (~15 min.)
- **MCP `search_api_examples(product, query, limit)`** — FTS over
  `catalog.entries_fts` joined to `entries`+`products`; returns method,
  path, auth, params, snippet, source_url. ~40 lines. (~30 min.)
- **MCP `synthesize_http_step(entry_id)`** — deterministic transformer:
  catalog entry → `http_request` step args dict (no LLM). One auth-mapping
  table covers Basic/Bearer/API Key/OAuth2. (~1 hr.)
- **New recipe kind: `http-virtual-connector`** — when no native connector
  exists, generator emits HTTP-connector playbook seeded from a catalog
  entry's request shape + `Return Sample Data` from `sample_response`.
  Reuses recipe scaffolding. (~3 hr; depends on the two MCP tools above.)
- **Cross-link table `connector_catalog_map(connector_name,
  catalog_product_id, confidence)`** — populated once at probe time via
  fuzzy match on display names. Lets the agent answer "native connector,
  or HTTP fallback?" in one query. (~1 hr.)
- **Pagination + auth taxonomy mapping** — small lookup tables that
  translate catalog free-text auth/pagination into HTTP connector enums
  (`auth_type`, `http_paginate` strategy). Deterministic. (~1 hr.)

**Inventory / audit surface (added 2026-05-06)**
No single way today to ask "what does the assistant know?" Add:
- `python/inventory.py` — one function per category returning row counts,
  trust ratios, last-probe timestamps. Read-only over `_probe_runs`,
  `verifications`, `v_verification_state`, attached `catalog`.
- `fsrpb inventory [summary|connectors|api-examples|stale|search <q>]`
  CLI command — thin wrapper around `inventory.py`. (~1.5 hr.)
- `/api/ref/inventory` web route + a one-page dashboard. (~2 hr.)
- Both surfaces should colour-code by trust (`is_trusted=1` vs `seen`).

**Architecture invariants to preserve** (do not regress)
- SQLite is the single source of truth — never hardcode connector/op data.
- Compiler is a library: no `print()`, all errors are structured objects
  with codes (`unknown_connector`, `unknown_param`, …) + difflib hints.
- Trust tracking: `is_trusted=1` only when source ∈ {live_api_get,
  backend_introspect} AND a `verifications` row says `tested_pass`.
- LLM authors YAML and sequences tool calls; everything else is code.

## Ingestion recipe + validator follow-ups (added 2026-05-05)

The threat-feed and data-ingest recipe generators ship today (see
`python/recipes/generator.py`, CLI `fsrpb generate-recipe`). Validator
ruleset layering is live (`python/compiler/rulesets/{__init__,_shared,
data_ingest,feed_ingest}.py`, CLI `fsrpb validate-ingestion`). Open work
beneath that surface:

I1. **Live picklist resolvability check at recipe-generation time.**
    Generator emits `{{ 'TrafficLightProtocol' | picklist('White') }}` and
    leaves resolution to runtime — that's fine, we do NOT need to hardcode
    UUIDs into the playbook. What we DO need: at generation (or validation)
    time, smoke-render each picklist Jinja expression against the live FSR
    and confirm it returns a valid IRI (not an error / not None). E.g.
    verify `TrafficLightProtocol` exists as a picklist on the target
    module's allowed picklists, and that `picklist('White')` resolves to
    a real value. Use the existing `render_jinja` MCP path / `fsrpb jinja`
    CLI which already talks to live FSR. On any failure FAIL with the
    missing/invalid picklist + value. Implementation: walk the generator
    output's resource block for `picklist(...)` calls, render each, assert
    output matches `/api/3/picklists/<uuid>`. ~1 hr.

I2. **Connector precheck against live FSR.**
    Per `project_recipe_connector_requirement`, `generate-recipe` should
    refuse to emit if the target connector isn't installed on the configured
    FSR. Today the generator runs purely from local info.json. Add a
    pre-flight `GET /api/integration/connectors/{name}/{version}` call,
    surface "connector not installed; install via SolutionPack X first".
    ~30 min after I1.

I3. **Persist generated recipes to the `recipes` table.**
    Schema already exists (`store/schema.sql`, table `recipes` with cols
    `name, kind, when_to_use, yaml_template, source_playbook`). Generator
    should optionally write to it (`--persist`) so `fsrpb show recipe
    <connector>` retrieves a previously-generated recipe. Also lets the
    MCP `find_recipe` tool surface ingestion templates. ~45 min.

I4. **MCP tool: `generate_recipe(kind, connector, …)`.**
    Wrapper around the existing generator. Authoring agents currently
    have no way to request "build me an ingestion playbook for connector
    X" inline. Add to `python/mcp_server.py`. Should self-validate and
    return YAML (decompile output) so the user can edit before pushing.
    ~30 min.

I5. **`compile --lax` flag for round-trip use case.**
    Compiler currently FAILs on `unknown_param` / `unknown_connector`
    even though the YAML round-trip would otherwise produce
    byte-equivalent output (Path B in the round-robin test). Add
    `--lax` that demotes those two error codes to WARN. Round-trip
    tests can then exercise the full text-form pipeline. ~20 min.

I6. **Extract + index all saved RPMs and import their playbooks.**
    `store/rpm_cache/` holds downloaded RPMs from
    `repo.fortisoar.fortinet.com` (probe_connectors tier 3). Each RPM
    contains a `playbooks/playbooks.json`. We currently ingest connector
    metadata but not the bundled sample playbooks. Goal: extract all RPMs,
    parse every `playbooks.json` they contain, store the workflows into
    `playbooks_seen` (and step args into the existing tables) so the
    corpus expands beyond the live-FSR pull. The threat-feed +
    data-ingest validators will then have far more calibration data, and
    the recipe generator can mine real ship-state ingestion playbooks
    instead of relying on the four reference points (TAXII2, AWS, FAZ,
    FSM). New probe: `python/probes/probe_rpm_playbooks.py`. ~3 hr.

I9. **Live-probe sample data via `run_op` during recipe generation.**
    Stronger version of I8. Plumbing exists today (`fsrpb run-op`, MCP
    `run_op`, `list_configured_connectors`). Flow:
    (a) Generator detects candidate fetch op(s) via existing heuristic.
    (b) If ambiguous (0 or >1), interactive prompt: "Which op fetches
    alerts/indicators?" — fail loudly with the list in non-interactive
    runs (`--fetch-op <name>` already exists for override).
    (c) Resolve a configured connector instance (`list_configured_
    connectors`). If not configured, FAIL with "configure on FSR first"
    (matches `project_recipe_connector_requirement`).
    (d) Call `run_op(connector, op, {limit: 1, ...})` with safe sample
    params. `run_op` already caches the observed output shape into the
    reference store, so this also improves future generations.
    (e) Use the captured response three ways:
       - Embed as the literal `Return Sample Data` step body — real
         shape, real data the wizard's mapping pane will show.
       - Walk the response to discover all fields actually present
         (output_schema is often incomplete); auto-suggest mappings
         to FSR resource fields (severity → severity, eventId →
         sourceId, etc.) using fuzzy field-name match.
       - Render-check picklist Jinja calls against the captured values
         (closes the loop with I1).
    (f) On run_op failure (auth error, timeout, empty result) FAIL the
    recipe with the live error — better than emitting a recipe that
    won't work in production.
    Generator gets new flags: `--probe` (live-probe required, no
    fallback), `--probe-params <json>` (override the default
    `{limit: 1}`), `--no-probe` (current generic-placeholder behavior).
    ~3 hr.

I8. **Use connector-provided sample data in the env_setup branch.**
    Generator's `Return Sample Data` step currently emits a hardcoded
    2-record placeholder regardless of connector. The Data Ingestion
    Wizard's right-hand "Sample Data" panel shows whatever this branch
    returns — so generic placeholders mean useless mapping previews.
    Three sources to draw from, in order of preference:
    (a) explicit `sample_response` / `ingestion_sample_data` /
    `mock_result` field on the fetch op or the connector — none of our
    4 reference connectors carry it today, but some real connectors do
    ("some do that" per user 2026-05-05); accept whatever field name
    the FSR docs canonicalize on.
    (b) Synthesize from the op's `output_schema` by walking the schema
    tree, treating empty strings/zeros/None as field placeholders, and
    emitting 2–3 records with the real shape. RF's
    `output_schema.indicators[0]` already has every field a record needs.
    (c) Fall back to current generic placeholder.
    Also: data-ingest variant should populate the sample with the
    `dedup_field` / severity / status fields the generator was told
    about (so wizard mapping shows them as clickable fields). ~1.5 hr.

I10. **Interactive playbook stepper with live feedback.**
    Forward step-through authoring loop. As an author (human or LLM
    agent) writes each YAML step, the stepper executes it against the
    live FSR and returns the real `vars` context for the next step to
    consume. Per-step-type handlers (connector → run_op, set_variable
    → local Jinja, decision → render condition, create/find/update/
    delete record → /api/3/<collection>, manual_input/wait → mock,
    workflow_reference → recursive). Approval gate before any
    state-mutating step. Three modes: interactive REPL, LLM-agent
    approval loop, troubleshoot-resume from a past pb_execution_id.
    Full design at memory `project_playbook_stepper_design.md` —
    survives `/clear`. ~11 hr core; workflow_reference recursion +
    code_snippet sandbox are follow-on. Reuses existing `run_op`,
    `fsrpb env`, `render_jinja`, compiler IR, and run_op's
    destructive-op confirm guard.

I7. **Recipe gold-standard test fixtures.**
    Today calibration relies on live `/tmp/*_generated.json` runs.
    Bake known-good generator outputs as fixtures
    (`tests/fixtures/recipes/threat_feed_taxii.json`, …) and a pytest
    that asserts byte-equality. Catches accidental changes to the
    generator's output shape. ~1 hr.

## Backlog (open)

Each item is grounded in something a recent session exposed; estimates
assume the patterns established in 2026-05-03/04 are followed.

1. **Apply the strict-whitelist pattern to the other resolver normalizers.**
   `manual_input` hard-errors on unknown keys and on bad `type:` values
   (silent-drop trap fixed). The same trap still exists for `delay`,
   `code_snippet`, `start_on_create` / `start_on_update`, and the record
   CRUD trio (`create_record`, `update_record`, `find_record`). Add a
   per-handler accepted-keys check + fail-on-unknown the way
   `_normalize_manual_input_args` does. Template: `compiler/resolver.py`,
   the `_FRIENDLY` / `_CANONICAL` whitelists pattern. ~30 min.

2. **Slim the other big tools the way `get_step_type` was slimmed.**
   Token analyzer + history db are built (`fsrpb chat-stats`,
   `web/backend/usage.jsonl`, `history.cost_by_playbook()`). Run a real
   chat session and trim whatever sits at the top of the tool-cost
   ranking. Likely candidates: `search_playbooks` (full snippet JSON × N),
   `validate_yaml` (returns the entire compiled collection), `decompile`.
   Pattern: add a `verbose: bool = False` parameter + default cap,
   mirroring `get_step_type`. ~1 hr after seeing real data.

3. **Investigate the `--mode upsert` HTTP 400.** Every push to
   `/api/3/bulkupsert/workflow_collections` 500s with a generic
   `TypeError` from FSR. Replace mode works as a workaround. Either fix
   the payload shape or remove the `upsert` option from `cli.py:cmd_push`
   and document why. Reproduce with `fsrpb push --mode upsert <yaml>`.
   ~1 hr.

4. **Roundtrip test against the friendly-form examples.** Decompile →
   recompile may regress YAMLs from friendly form to canonical wire form
   after the friendly-form work. Run `fsrpb roundtrip` on the 11 demo
   examples and confirm nothing diverges semantically. ~15 min smoke.

5. **Smoke test for the 9 examples without `.test.yaml` sidecars**
   (`decision_branch`, `find_and_update`, `hello_connector`,
   `ip_reputation_check`, `ip_reputation_check_abuseipdb`,
   `manual_input_then_act`, `parent_calls_child`, `test_complex_e2e`,
   `test_manual_input_e2e`). A "compile + push + check link 200" smoke
   per example would catch regressions like the URL-pattern bug fixed
   2026-05-04 (`cli.py:cmd_push`'s post-push GET on
   `/api/3/workflows/<uuid>`).

6. **History tab UI** — backend done (see 2026-05-04 changes); UI still
   parked. Need: `GET /api/history?type=push|chat`, `GET /api/history/push/<id>`,
   `GET /api/history/push/<id>/diff?against=<id>` (use `history.yaml_diff`),
   `GET /api/history/cost-by-playbook`. Frontend `/history` route already
   exists as a stub in `web/frontend/src/routes/history/+page.svelte`.
   Reader fns in `web/backend/history.py` already shaped for the UI:
   `timeline()`, `list_pushes()`, `get_push()`, `previous_push()`,
   `list_chat_sessions()`, `get_chat_session()`, `cost_by_playbook()`.

7. **Promote drafts to backend (optional)**. Editor drafts live in
   localStorage today (`web/frontend/src/lib/yamlStore.svelte.ts`). Once
   #6 lands, drafts can be persisted into `history.db` for cross-browser
   sync + cross-reference with pushes. Not blocking.

8. **Push overwrite safeguard for imported playbooks.** `pull` /
   decompile already lets users import playbooks from a live FSR. The
   risk is the inverse direction: `fsrpb push --mode replace` does PUT →
   POST → PURGE+POST, which will silently clobber any out-of-band edits
   made on the FSR side after the pull. Add a drift-detection step
   (compare local IR vs. live collection's current state) and require an
   explicit `--confirm-overwrite` (or interactive y/N) when drift is
   detected. Goal: a user who pulled a playbook, then pushed back days
   later, can never lose someone else's UI edits without acknowledging
   them. Pure import (collection doesn't exist yet) needs no confirm.

9. **Refine the YAML grammar + linter for agent/human ergonomics.**
   Current authoring is close to the wire shape, which is unambiguous
   but verbose and full of foot-guns we keep discovering one at a time
   (e.g. `step_variables: [{name, value}]` silently emitting one
   variable named `step_variables`; `step_variables` meaning a *dict*
   on Start/Connector but flat keys on `set_variable`; `for_each`
   living inside `arguments` on the wire but as a sibling in the IR).
   Goal: a more compact, self-explanatory YAML where the same concept
   reads identically across step types, and a strong linter that
   rejects shape mismatches with a clear "did you mean" message
   instead of letting them through to the runtime. Concrete:
   - Audit every step type's accepted-keys whitelist; reject unknown
     keys at compile time (only `set_variable` already has flat-key
     freedom; everything else should be strict-whitelist).
   - Promote `for_each`, `when`, `mock_result`, `step_variables`, and
     other cross-cutting concepts to first-class step-level fields
     (siblings of `arguments`) so authors never confuse them with
     step-config args.
   - Friendlier shapes for common idioms: short-hand for
     decision conditions, sugar for record-shape `resource:` blocks,
     a single `set:` for inline-vars on connector/create steps so the
     `step_variables` dict isn't named twice across step types.
   - Linter passes that catch: anti-patterns from the AUTHORING.md
     "Setting variables" section, recipe-tag drift (canonical tag set
     enforcement), missing `mock_result` on Fetch steps in recipe
     templates, and Jinja paths that point at fields the upstream
     step doesn't actually output.
   - **Norway problem on Decision steps** — `option: yes` /
     `branches: { yes: ... }` get parsed as YAML 1.1 booleans (`True`),
     making FSR's Decision route lookup fail with `CS-WF-10: Either
     the Step IRI or the Condition is not set`. Lint should reject any
     unquoted `option:` or `branches:` key matching the magic words
     `yes|no|on|off|true|false|y|n` (case-insensitive) and tell the
     author to quote it. Hit while validating recipe_threat_feed.yaml.
   - **Step name charset is `[A-Za-z0-9 _]` only** — FSR's designer
     enforces this (validation message: "Only alphanumeric character,
     space and _ is allowed"). Em-dashes, hyphens, question marks,
     colons, parentheses, etc. all get rejected. Lint should reject
     any step `name:` containing characters outside the whitelist and
     suggest a sanitized form (replace runs of disallowed chars with
     a single underscore). Pushed playbooks with bad names compile and
     push fine but can't be edited in the designer without first
     cleaning up the name.
   - **Mocked runs hide failure-branch traversal** —
     `cyops_utilities.raise_exception` honors `useMockOutput=true` and
     returns null instead of raising, so a recipe whose Decision routes
     to a `Raise Exception` failure branch reports `finished` under
     `--mock` even though the failure path was taken. Lint should warn
     authors that `--mock` is for plumbing validation only and won't
     exercise the failure semantics; `fsrpb e2e run` (real mode) is
     the only way to verify failure branches actually fail.
   - **`IngestBulkFeed` is NOT in `EXCLUDED_FROM_MOCK_OUTPUT`** —
     it runs LIVE even when triggered with `useMockOutput=true`. So a
     recipe template's `IngestBulkFeed` step needs its own
     `mock_result` placeholder for users who want to validate the
     plumbing before plugging in real picklist UUIDs. Recipe-template
     lint should require `mock_result` on every `IngestBulkFeed` and
     every `create_record`/`update_record`/connector step that lives
     downstream of a mockable Fetch — otherwise `--mock` runs surface
     resolveRange/picklist errors against TODO placeholders.
   - Output: an updated AUTHORING.md and a `fsrpb lint <file>`
     subcommand.


## Recent changes (most-recent first)

- **2026-05-04 — LLM modular by Protocol; chat history wired.**
  - `web/backend/llm/provider.py` — new `UsageEvent` + `ToolCallUsage` events
    in the union; `LLMProvider.stream()` now takes a `tags` param. Telemetry
    is no longer Anthropic-specific — any provider just yields a UsageEvent
    per round-trip and the route handler is the single consumer.
  - `web/backend/llm/factory.py` — `register(name, factory)` + `get_provider(name=None)`
    (env: `STUDIO_LLM_PROVIDER`). Built-in registration of `anthropic`. Adding
    OpenAI/Bedrock/Ollama is one line: `register("openai", OpenAIProvider)`.
  - `web/backend/llm/fake_provider.py` — scripted `FakeProvider(turns)` for
    tests, captures `last_messages`/`last_tools`/`last_tags`. Used to plug in
    a deterministic provider in `web/tests/test_chat.py`.
  - `web/backend/llm/anthropic_provider.py` — refactored to emit `UsageEvent`
    (no more inline `print` / `log_turn`). Side effects moved to the route.
  - `web/backend/routes/chat.py` — uses `get_provider()`; `_persist_usage()`
    writes JSONL + `history.db` on every UsageEvent; `_yaml_tags()` extracts
    `playbook_collection` (from `collection:` line) + `yaml_sha` from
    `current_yaml` so per-turn cost can be attributed to a playbook;
    stamps `~/.fsrpb/active_session` for the duration of the stream so a
    follow-up `fsrpb push` correlates.
  - `web/backend/history.py` (now wired): `pushes`, `push_workflows`,
    `chat_sessions`, `chat_turns` (with new `playbook_collection` +
    `yaml_sha` columns + index), `chat_tool_calls`. `cost_by_playbook()`
    rolls up tokens + USD by `collection:` tag using `_resolve_pricing()`
    (exact → strip `-YYYYMMDD` suffix → longest prefix). `yaml_diff()`
    helper for unified diffs.
  - `cli.py:cmd_push` — calls `record_push()` on success AND failure;
    snapshots source YAML; correlates to chat session via active marker;
    post-push `GET /api/3/workflows/<uuid>` check + ✓/✗ marker (the SPA
    serves index.html for every path, so the API check is what tells you
    the deep-link works); OSC 8 hyperlink output on TTY stderr.

- **2026-05-04 — Editor save/load/undo (frontend, client-side).**
  - `web/frontend/src/lib/yamlStore.svelte.ts` — text + drafts + last
    snapshot all persisted to localStorage. `setText(text, reason)`
    auto-snapshots before any wholesale replacement; `saveDraft(name)`,
    `loadDraft(name)`, `deleteDraft(name)`, `restoreSnapshot()` (itself
    undoable), `suggestedName()` (parses `collection:` line).
  - `web/frontend/src/lib/components/DraftsMenu.svelte` — new dropdown
    with relative-age timestamps and per-row delete; mirrors ExamplesMenu.
  - `+page.svelte` — Save button (defaults name to suggested), Drafts
    menu, amber Undo button shown only when `lastSnapshot` exists.

- **2026-05-04 — `manual_input` strict whitelist + input field expansion.**
  - `_normalize_manual_input_args` rejects unknown top-level keys
    (`label`, `message`, `timeout`, `textarea`, etc.) as **errors** (was
    silently dropped → screenshot bug). `type:` value must be `InputBased`
    or absent. `input` not-a-dict pre-empts the FSR `'str' has no attribute
    .get` runtime crash.
  - `_expand_input_variables` — friendly `inputs: [{name, kind, label?,
    tooltip?, required?, default?, options?}]` expands to FSR's canonical
    25-key inputVariable shape. Kinds: text, textarea, richtext, html,
    email, url, password, integer, number, checkbox, boolean, select,
    datetime, json. `kind: select` requires `options:`. Pre-expanded
    fields (with `formType` + `templateUrl`) pass through unchanged.

- **2026-05-04 — `arg_validator.py` skip gated by `step.handler`** (was
  `step.type`). Stops false-positive `unknown_param` warnings on the
  resolver-injected wire-format keys (`name`, `operationTitle`,
  `operation`, `collectionType`, `type`, `rule`) for `stop`/`end`/
  `update_record`/`create_record`/`delay`/`code_snippet`/`set_variable`.

- **2026-05-04 — `mcp_server.get_step_type` slim by default**, with
  short→canonical mapping for all 17 short types and a `friendly_form`
  block per type. Default response 1.8 KB for `manual_input` (was 4.9 KB),
  0.7 KB for `code_snippet` (was 18 KB — corpus example contained an
  18 KB Python blob). `verbose=True` returns full corpus dump.

- **2026-05-04 — Chat token analyzer.** `web/backend/llm/usage_log.py`
  writes `usage.jsonl`. `fsrpb chat-stats [path]` rolls up per-session,
  worst turns, and tool-cost ranking. Used to find what blew up context.

- **2026-05-04 — Test coverage.** 192 tests passing (web 63, python 93,
  frontend 36). New: `test_manual_input_resolver.py`, `test_input_fields.py`,
  `test_arg_validator_skip.py`, `test_mcp_get_step_type.py` (uses
  `pytest.importorskip("mcp.server.fastmcp")` — skips cleanly on envs
  without the `mcp` pkg), `test_llm_factory.py`, `test_history.py`,
  rewritten `test_chat.py` (uses factory.register for plug-and-play),
  `yamlStore.test.ts`.

- **2026-05-03 — Jinja corpus mining**: new `probe_jinja_corpus` walks 1,669 live workflows, extracts every `{{…}}`/`{%…%}` block (19,305 total → 7,789 unique idioms), populates `jinja_expressions` (kind=expr/set/for/if/macro/…) and `jinja_filter_usage`. Most-used real example auto-promoted onto `jinja_macros.example`. New table column `jinja_macros.curated_doc` + 13 hand-written long-form filter docs (json_query JMESPath syntax breakdown, picklist, fromIRI, resolveRange, map, selectattr, regex_search, regex_replace, ternary, default, dict2items, flatten, from_json/to* family). New MCP tool `find_jinja_pattern(q, kind)` and enriched `find_jinja_filter` / `get_filter_examples`.
- **2026-05-03 — `store/JINJA_IDIOMS.md`** (new) — 10 corpus-mined patterns with occurrence counts.
- **2026-05-03 — Live e2e loop closed**: `fsrpb push` is idempotent (PUT → POST → PURGE+POST including child-workflow purge), `run-playbook --follow` auto-dumps step diagnostics on failure (fetches `?step_detail=true`), `fsrpb env <pb_execution>` rebuilds the live `{vars: {…env, steps: {Step_Name: result}}}` Jinja context, `fsrpb jinja '<tpl>' --from-pb-execution <id>` renders against it. MCP equivalents: `get_run_env`, `render_jinja(from_pb_execution=…)`.
- **2026-05-03 — Connector params 14 % → 90 %**: new RPM-based tier in `probe_connectors`. Downloads each connector's RPM from `repo.fortisoar.fortinet.com`, extracts `info.json`, ingests params. Fingerprint diff (`connectors.rpm_fingerprint`) so re-runs short-circuit. Cache at `store/rpm_cache/`.
- **2026-05-03 — Connector healthcheck**: `fsrpb health [name] [--probe] [--config <uuid>]`. Lists configured + active via `POST /api/integration/connector_details/?configured=true&active=true`; per-config probe via `GET /api/integration/connectors/healthcheck/{name}/{version}/?config=…`. MCP: `list_configured_connectors`, `healthcheck_connector`.
- **2026-05-03 — Compiler**: start step now emits `arguments.step_variables.input.params=[]` (was `{}`, caused runtime `pop expected at most 1 argument`).
- **2026-05-03 — `vars.steps.<step_id>` rule confirmed**: keyed off `step.name.replace(" ", "_")` (case **preserved**, not lowercased). Verified against the Jinja editor widget's `view.controller.js`. AUTHORING.md updated.



## Where we are

Compiler v1, reference store, live e2e (push/run/poll/env), MCP server (16 tools), and corpus-mined Jinja docs are all live. Open work: demo MVP, Phase 8 frontend research, `CONNECTORS.md` generation.

| Probe | What it captures | Status |
|---|---|---|
| `probe_api_endpoints` | Hydra root + dashboard endpoint inventory | live |
| `probe_connectors` | 3 tiers: live (installed) → solutionpacks (catalog) → **fortinet_repo_rpm** (RPM `info.json` from `repo.fortisoar.fortinet.com`, fingerprint diff so re-runs short-circuit) | 714 connectors, 6,762 ops, **6,097 with params (90%)** |
| `probe_modules` | `/api/3/staging_model_metadatas?$relationships=true` + `/api/3/picklist_names` | 62 modules, 1,233 fields |
| `probe_playbooks` | step types, playbook corpus, trigger recipes | 43 step types, 1,669 playbooks |
| `probe_jinja` | Widget constants + PDF + live `type_debug` rendering | 144 filters, 99 w/ observed types |
| `probe_jinja_backend` | Backend introspection via `inspect.signature()` | 170 filters, 15 globals, 39 tests |
| `probe_jinja_corpus` (NEW) | Mines every `{{…}}`/`{%…%}` block from live workflow args | 19,305 blocks → 7,789 unique idioms |
| `probe_step_handlers` | FUNCTION_MAP signatures | 100% coverage |
| `probe_playbook_constraints` | rule constraints | live |
| `probe_cleanup` | pattern-matched delete of test artifacts (gated on `FSR_ALLOW_E2E`) | live |

DB at `store/fsr_reference.db`, schema at `store/schema.sql`. All probes are
idempotent and re-runnable. `python/probes/_env.py` loads `.env` (already
populated; API key auth, SSL verify off).

## Trust model recap

- Local sources (rpm_info_json, schema_json, schema_ts, widget_constants,
  playbook_guide_pdf) are **always `seen` only** — never trusted.
- Live methods (live_api_get, live_api_render, live_op_exec, playbook_e2e)
  with `tested_pass` promote to `is_trusted=1` in `v_verification_state`.
- **`backend_introspect`** is the new highest-trust method (added today) —
  reads the actual Python objects on the FSR box.

## Open TODOs (priority order)

### 1. ~~Surface FSR-custom filter set explicitly~~ ✅ DONE 2026-05-02
Generated `store/FSR_CUSTOM_JINJA.md` (385 lines, 32 entries: 5 globals + 27
filters from `workflow.*` and `sealab.*`). Pointer added to
`FORTISOAR_RESOURCES_INDEX.md` so future agents grep it first.
Builder: `python/store/export_jinja_cheatsheet.py`. Re-run after any
`probe_jinja_backend` run.

### 2. ~~Backend introspection for workflow step types~~ ✅ DONE 2026-05-02
Found the canonical dispatcher: `workflow.eval.FUNCTION_MAP` (44 entries).
Each step type's `args_schema_json.script` ends in `/wf/workflow/tasks/<key>`
where `<key>` is a FUNCTION_MAP entry. Captured all 44 signatures via
`scripts/dump_function_map.py`; ingested by `probe_step_handlers` into
new `step_handlers` table. Bundled into `fsr_reference.json`.

Discovery path: celery tasks (`scripts/dump_step_types.py`) turned out
to be cleanup jobs, not step handlers — `workflow/builtins/*.so` houses
the actual handlers but they're dispatched by name through FUNCTION_MAP.
Three step types reference handlers not in FUNCTION_MAP:
`workflow_reference`, `map`, `fetch_email_and_explode` — flagged in
`GAPS.md`.

### 3. Live-instance probes (Phase 5) — ✅ DONE 2026-05-03
End-to-end via CLI: compile → push (idempotent w/ child-workflow purge)
→ trigger via `/api/triggers/1/notrigger/<wf>` → poll
`/api/wf/api/workflows/?task_id=` → on terminal, fetch `?step_detail=true`
and dump per-step status + top-level error inline. `fsrpb env <pk>` and
`fsrpb jinja '<tpl>' --from-pb-execution <pk>` close the loop for
authoring the next step against the previous run's real data.

### 4. Compiler v1 — vertical slice landed; widen coverage next
✅ Pipeline complete: parser → resolver → validator → emitter, plus
   decompiler and round-trip checker.
✅ Round-trip on `pb_examples/all_fsr_evoke_playbooks.json`:
   **1596/1596 (100%) semantic match** across every step type FSR uses
   in production. 1 skip is an empty-steps record.

✅ CLI: `fsrpb compile / validate / decompile / roundtrip / explain` (`python/cli.py`).
✅ Argument-shape validation (`python/compiler/arg_validator.py`):
   uses `step_handlers` signatures to enforce required params and
   reject unknown args on handlers without `**kwargs`. Framework-injected
   params (step, step_id, wf_id, env, …) are excluded from the
   "required" check.

Remaining for v1 → v1.1:
Reference store is rich enough to start. Phase 3 from
`Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md`. See `ARCHITECTURE.md` for how
this fits the bigger picture (it's the engine all three authoring
surfaces — CLI, MCP, visual editor — sit on top of). Targets:
- `python/compiler/parser.py` — YAML → IR
- `python/compiler/resolver.py` — connector/op/param/step/jinja-filter
  references resolve against the SQLite store
- `python/compiler/validator.py` — strict mode rejects unknown refs with
  Levenshtein "did you mean..." suggestions; **errors are structured
  objects with code/location/suggestion**, never bare strings (MCP needs
  machine-readable diagnostics)
- `python/compiler/emitter.py` — IR → FSR `WorkflowCollection` JSON
- Library-first; CLI is a thin wrapper around the same functions MCP
  and the widget will call.
- Acceptance: bambenek-feed YAML → JSON byte-equivalent (modulo UUIDs/ts)
  to the vendor original.

### 5a. `fsrpb push` — idempotent ✅ DONE 2026-05-03

The actually-shipped path: `cmd_push --mode replace` does PUT → POST →
PURGE+POST. The crucial fix that unblocked re-push was that **the
collection-level hard-purge does not cascade to its workflows** — orphaned
workflows from a prior failed import keep their UUIDs, which causes the
second POST to 409 on the workflow (not the collection). Solution: the
purge step now also deletes every child workflow UUID via
`DELETE /api/3/delete/workflows?$hardDelete=true {ids: [...]}`. Verified
by re-pushing `examples/hello_connector.yaml` twice — both succeed as
`PURGE+POST` with the same `uuid=3a892679`.

`bulkupsert` is documented but not wired — the PURGE+POST path works,
and bulkupsert had separate PHP-side bugs in `UpsertController.php` we
didn't want to depend on.

---

### 5a-archive. Original re-push parking notes (kept for context):

✅ **First-create** push works end-to-end.
`POST /api/3/workflow_collections` with the **unwrapped collection
entity body** (not the export envelope) is the right path. Cascade-persist
on the entity automatically writes nested `workflows[]` and their
steps/routes. Verified by `examples/hello_connector.yaml` deployed live
as `Compiler Demo` (collection visible in FSR UI; `pull` round-trips back
to the original YAML).

⏸️ **Re-push** is parked pending appliance backup. Root cause: FSR
soft-deletes (sets `deletedat=NOW()` rather than purging). After a DELETE,
the UUID is still owned by the soft-deleted record, so a subsequent POST
hits 409 `UniqueConstraintViolationException` — error message even names
the recycle bin.

Attempts and results:

| Approach | Result |
|---|---|
| POST first time | ✅ creates |
| POST after DELETE | ❌ 409 (UUID still owned by soft-deleted) |
| PUT `?$showDeleted=true` body `deletedAt:null` | ❌ 409 |
| `DELETE /api/3/delete-with-query/workflow_collections?$showDeleted=true` (with body, hard-purge — same path `PlaybookConfig.php` uses for replace-mode imports internally) | not yet attempted (deferred until backup exists) |

Earlier rabbit hole — `import_jobs` is the **multi-type configuration
bundle import** (Solution Pack format: collections + modules + connectors
+ fixtures + roles + …), not single-collection import. Verified from
`Service/ConfigExportImport/ImportService.php` (iterates `configTypes`)
and `Entity/Core/ImportJob.php` (no `data` column; `file` IRI field for
Solution Pack zip uploads). Documented in
`soar-reporting-dashboard-cl/docs/FORTISOAR_API.md` "Workflow collection
import" section.

Mode flags wired in `cli.py cmd_push`:
- `--mode replace` (default): try PUT first, fall back to POST on 404.
  Currently fails on existing soft-deleted records.
- `--mode create`: POST only; clean for first-create.
- `--mode update`: PUT in-place; no-op so far (entity expects path under
  `?$showDeleted=true`).

To unblock re-push when ready (after backup):
1. Ensure backup of `Compiler Demo` and any other test collections.
2. Try `DELETE /api/3/delete-with-query/workflow_collections?$showDeleted=true`
   with body `{logic:"AND", filters:[{field:"uuid", operator:"in", value:[<uuid>], type:"primitive"}]}` via pyfsr's authenticated session.
3. If that hard-purges, wire it as the prelude inside `cmd_push --mode replace`.
4. Alternative: tail nginx while clicking "Save" on an existing playbook
   in the FSR UI to see what the official client sends.

Workaround for now: use `--mode create` for first imports; for updates
go through the FSR UI, or compile to JSON and use `app:import:from:file`
on the appliance.

### 5. MCP server v1 — ✅ LIVE (16 tools)
`python/mcp_server.py` over stdio; `.claude/settings.json` registers it
as `fsrpb`. Tools (verified 2026-05-03): `find_connector`,
`find_operation`, `get_op_schema`, `get_connector_source`, `run_op`
(w/ confirm guardrails + risk classification), `get_step_type`,
`find_jinja_filter` (returns `corpus_uses` + `curated_doc`),
`find_jinja_pattern` (search corpus by block kind), `get_filter_examples`,
`render_jinja` (w/ `from_pb_execution`), `search_playbooks`,
`validate_yaml`, `compile_yaml`, `get_run_env`,
`list_configured_connectors`, `healthcheck_connector`.

**Open follow-ups:**
- `dry_run_playbook` — sandbox-execute compiled JSON without persisting.
- Bug: `render_jinja` doesn't unwrap non-string scalar results (returns
  `{"output": '{"result": 5}'}` instead of `{"output": "5"}`).

### Read-only probes landed 2026-05-03

- ✅ **CONNECTORS.md** generated (13,595 lines, 714 connectors / 6,749 ops / 4,753 params, grouped by 85 categories). Builder: `python/store/export_connectors.py`.
- ✅ **RECIPES.md** generated (355 lines: 5 hand-curated patterns + trigger frequency table + top-25 connector orchestrations). Builder: `python/store/export_recipes.py`.
- ✅ **YAQL filter probe** — confirmed `yaql` is a live Jinja filter via `/api/wf/api/jinja-editor/`. 6/6 probes pass; output type `list`; shape `{{ v | yaql("$.where($ > 1)") }}`. Recorded into `verifications` and `jinja_macros.output_type_observed`. Script: `scripts/probe_yaql_smoke.py`.
- ✅ **Custom-macro corpus grep** — FSR "macros" are scalar globals accessed via `{{ globalVars.NAME }}` (NOT Jinja `{% macro %}`). 12 defined in pb_examples; 122 ref occurrences. Recorded into `jinja_context_vars` (`scope='globalVars'`).
- ✅ **GlobalVars / macros endpoint** — `GET /api/wf/api/dynamic-variable/` confirmed live 2026-05-03. Schema `{id, name, value, default_value}`. Full CRUD via `/{pk}/`. UI capture #14 closed without needing capture.
- ✅ **historical-workflows record shape** — confirmed via live fetch. Per-run record: `@id, name, result.{data,status,message}, template_iri, created, modified, env.{wf_id, step_id, task_id, lastPullTime,...}, status, tags, metadata.{routes, groups}`. Use top-level `status` for completion polling, `result.status` for pass/fail.
- ✅/⚠️ **Bulkupsert characterized** — `POST /api/3/bulkupsert/workflow_collections` body = single workflow_collection object. **Works only for fresh creates with no existing match** (live or soft-deleted). Two FSR-side PHP 8 bugs confirmed via `prod.log`:
  - `UpsertController.php:89` — `array_key_exists()` on `stdClass` (the json-decoded body). Crashes when an existing soft-deleted record matches by uuid/name, blocking the resurrect path.
  - `UpsertController.php:258` (`upsertWorkflowCollections`) — `['workflows']` array-index access on stdClass when called via the bulk list path. Crashes during update.
  - `BulkRequestService.php:70` — `count()` on stdClass.

  Bottom line: bulkupsert can't update existing records. Kept as `--mode upsert` opt-in for never-seen UUIDs only.

- ✅ **Canonical UI delete endpoints** (from user UI capture 2026-05-03):
  - Soft-delete: `DELETE /api/3/delete/workflow_collections` body `{ids:[<uuid>]}`
  - Hard-delete: `DELETE /api/3/delete/workflow_collections?$hardDelete=true` body `{ids:[<uuid>]}`
  - These work on records visible to the caller. They do NOT reach into the recycle bin — for that, the `delete-with-query` path with `?$showDeleted=true` is the right tool.

- ✅ **`fsrpb push --mode replace`** wired up for the success path (PUT → POST → on 409 PURGE+POST). Soft-delete recovery path requires the recycle-bin scope, but a once-soft-deleted UUID with sub-entity wedge can still 409 — manual cleanup of that record needed for fully clean re-push idempotency.
- ✅ **`?name=` filter** — works as exact match after URL-encoding (`&`→`%26`). Django suffix variants (`name__exact`, `name__contains`) do NOT work on `/api/3/`. `POST /api/query/workflow_collections` body filter also works. Earlier failure was a URL-encoding bug.
- ✅ **`attribute_metadatas`** — 1233 entries; richer per-field metadata than `module_fields`. Worth a follow-up probe but not blocking compiler v1.
- ✅ **Picklist hydration** — confirmed: `model_metadatas` embeds `dataSource: {model:'picklists', query: …}` rather than inlining values. Current ingest path correct.

### Live-instance gaps still pending (need backend recon)

`scripts/fsr_recon.sh` is a single-shot read-only recon script for `csadmin@10.99.249.205`. Outputs to `/home/csadmin/fsrpb_recon/<ts>/` + a tarball next to it. Covers:
- Symfony route table + filtered views (workflow / trigger / purge / import).
- Workflow Django app `urls.py` + `/api/wf/runs/` view code (the 403 endpoint).
- Live `workflow.eval.FUNCTION_MAP` dump (resolves missing `map`, `fetch_email_and_explode` handlers).
- `PlaybookConfig.php` delete logic for soft-delete purge unblocking.
- `cyops-integrations` log tail for connector op execution shape.
- `nginx` confs (so we know which `/api/*` prefix maps to which service).
- Copies of `api_platform/`, `routes/`, `Entity/Workflow/`, `Controller/`.

Once the tarball is back: extract under `store/incoming/recon_<ts>/` and write `probe_recon.py` to ingest the diffs.

### 5b. Pull / diff / status — local-only, working
- ✅ `fsrpb pull <name|uuid> [-o out.yaml]` — fetch live collection,
  decompile to YAML. Verified end-to-end except: API Platform `?name=`
  filter on `/api/3/workflow_collections` returns 0 hits; need a
  different filter syntax (see "Open" below).
- ✅ `fsrpb diff <yaml> [-c name]` — semantic diff between local YAML
  (compiled) and live collection (pulled).
- ✅ `fsrpb status [-n N]` — list recent `import_jobs` with state.
  Confirmed working.

Open (cheap fixes):
- `fsrpb pull "<name>"` doesn't find any collections because `?name=`
  exact-match filter isn't honored. Workaround: pull by UUID. Real fix:
  use `?name__exact=<value>` or `$filter=name=<value>` per the
  power-user query options doc, or fetch all and filter client-side.

### 5c. Backlog (parked, scope sketches preserved here)
The following are unblocked locally and can be picked up without user
intervention. Listed in rough priority order:

1. **MCP server v1** — wraps compiler + store + (eventual) push as
   agent tools. See ARCHITECTURE.md §3 for tool table. Read-only first
   (`find_connector`, `get_op_schema`, `find_step_type`, `find_handler`,
   `find_jinja_filter`, `search_playbooks`), then validate/compile/
   decompile, then `render_jinja` (live). `dry_run_playbook` blocks on
   §3 e2e probes.
2. **More example YAMLs** — decision branches, `manual_input`,
   `find_record`+`update_record`, parallel paths. Each example doubles
   as agent grounding (LLMs benefit from more curated examples) and a
   round-trip regression fixture.
3. **TS compiler port skeleton** — `ts/src/compiler/` with the same IR
   shape so the future widget surface isn't an afterthought. Same tests
   can be ported via vitest.
4. **`fsrpb explain` extensions** — `explain jinja_filter <name>`,
   `explain module <name>`, `explain recipe <trigger_type>`. Currently
   only `connector`/`step`/`handler` are wired.
5. **AUTHORING.md** — single doc explaining the YAML shape with
   copy-pastable snippets pulled from `step_examples`. Should describe
   the connector/decision/set_variable/find_record/update_record/
   workflow_reference patterns, plus jinja idioms.
6. **YAQL probe** — Playbooks Guide pp.218-220, currently 0% covered.
   Likely has its own render endpoint similar to jinja-editor.
7. **Per-filter input-type contract probe** — sweep each of 144 jinja
   filters with str/list/dict/int inputs to populate `input_type_hint`
   data-driven (currently NULL).
8. **Cleanup probe** — find/delete `*__fsrpb_probe__*` and
   `Compiler Demo*` collections so e2e probes don't leave residue.
9. **`probe_workflow_runtime`** — exercise `wf/workflow/tasks/<func>/`
   for a few simple FUNCTION_MAP entries (`no_op`, `add`,
   `set_multiple`) to confirm direct dispatch surface and capture
   response shape — needed for the future `dry_run_playbook` MCP tool.

### 6. Smaller wishes
- Rerun `probe_jinja` after `probe_jinja_backend` so the type_debug
  observed types overlay onto the backend-canonical signatures (they're
  in different columns; just want to make sure both are present per
  filter).
- Multi-version connector support — switch primary key from `name` to
  `(name, version)` if multi-version coverage starts mattering. Currently
  `INSERT OR REPLACE` collapses versions; 760 catalog entries → 95 unique
  names.
- YAQL filter language probe (separate from Jinja; Playbooks Guide
  pp.218-220).
- Per-filter input-type contract — multi-shape probe (str / list / dict /
  int) so `input_type_hint` becomes data-driven instead of NULL.
- Param shape inference for the 26 jinja filters whose `tested_fail`
  message wasn't a "missing N required" pattern. The backend introspect
  dump fixes most of these but worth diffing.
- TS compiler port (`ts/src/`) once Python compiler v1 stabilizes.
- ~~`build_reference_json()` end-to-end~~ ✅ DONE 2026-05-02 —
  `store/fsr_reference.json` (5.9 MB) now contains all probe data
  including api_endpoints + jinja.globals + jinja.tests.
- ~~`store/STEP_TYPES.md` cheatsheet~~ ✅ DONE 2026-05-02 —
  92 KB, 43 step types frequency-ordered with 3 examples each.

## Cross-project doc updates pending

Already updated `soar-reporting-dashboard-cl/docs/FORTISOAR_API.md` with:
- "Endpoints used by `fsrpb`" section
- Power-user `/api/3/*` query options (dot notation, `$fields=`, `$exists=`,
  `$relationships=true`)
- `/api/query/*` pagination quirk (use `?$limit&$page`, body params ignored)
- Jinja render endpoint + filter catalog + type discipline + generator-list

Should still update:
- Add `POST /api/integration/connectors/{name}/{version}/?format=json` as a
  confirmed-live entry (it's working but not yet in the API doc).
- Note that `/api/3/connectors` is a Hydra ghost (advertises but 404s).

## Key files / paths

- Live plan: `Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md`
- Open gaps: `FSRPlaybookYaml/GAPS.md`
- API truth: `soar-reporting-dashboard-cl/docs/FORTISOAR_API.md`
- Schema: `store/schema.sql`
- Probes: `python/probes/probe_*.py`
- Backend dump scripts: `scripts/dump_jinja_filters.py`
  (next: `scripts/dump_step_types.py`)
- Incoming backend dumps: `store/incoming/filters.json` (170 filters
  introspected from `/opt/cyops-workflow/sealab/.../sealab.jinja`)
