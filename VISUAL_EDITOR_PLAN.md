# Visual Playbook Editor — Plan & Progress

**Started**: 2026-05-08. Owner: dcspille.

Toggle-able yaml ↔ visual playbook editor with drag/drop step palette,
flowchart canvas, per-step inspector that exposes every MCP tool as a
button, and an interactive debug runner that steps through playbooks
against the live FSR.

Source of truth for **what to build, in what order, and what's done**.
Update checkboxes inline as items land; add follow-up sub-bullets when
scope shifts.

---

## Goals

- Toggle yaml ↔ visual without losing information (round-trip is byte-
  identical when nothing was edited).
- Drag/drop step types and connector ops onto a flowchart canvas;
  edges auto-route, decision branches render as labeled outputs.
- Per-step inspector surfaces **all useful MCP tools** as buttons:
  render jinja, run op (safe), test step, show schema, show real
  examples, show jinja patterns, check verification.
- Whole-playbook debug runner: breakpoints, step over, branch chooser,
  watch panel, trace tape — turns the editor into a REPL for playbooks.
- Toolbar exposes validate / resolve / dry-run / assert / push so the
  user rarely needs the `fsrpb` CLI.

## Non-goals (for now)

- Multi-user collaborative editing.
- Mobile / small-screen layout.
- Replacing FortiSOAR's own designer for end-users on production —
  this is an authoring tool for our team.

---

## Architecture

### Round-trippable model

- Single source of truth = existing YAML → resolver → FSR-JSON pipeline.
- Visual editor is a **view** over an in-memory `Playbook` object.
- New `python/compiler/visual_model.py`:
  - `to_visual(yaml_text) -> {nodes, edges}` — node = `{id, type,
    name, args, position, status}`; edge = `{from, to, label, branch}`.
  - `from_visual(graph) -> yaml_text` — uses existing emitter; reinjects
    layout comments so positions survive.
- Layout persisted as YAML comments anchored on each step
  (`# fsrpb:layout {x:120,y:80}`), NOT a sidecar file.
- **Round-trip CI test** required: every fixture in `examples/` must
  produce byte-identical YAML when round-tripped without edits.

### Canvas

- `@xyflow/svelte` (Svelte Flow) — pan/zoom, mini-map, edge routing,
  undo/redo for free.
- Auto-layout via `dagre` (top-down) on first open when no layout
  comments exist.
- Custom node types per step-type family (43 types collapse to ~7
  visual templates):
  - **Trigger** (orange, top-only) — abstract_trigger / post_create /
    post_update / action / api_call
  - **Connector op** (blue) — header `connector / op`, body shows top
    args truncated
  - **Decision** (diamond, multi-out) — branches as labeled handles
  - **Utility** (gray) — SetVariable / CodeSnippet / Delay
  - **Record CRUD** (green) — Find / Insert / Update / Delete
  - **Workflow ref** (purple) — clickable to dive into nested playbook
  - **ManualInput** (yellow) — distinct since it pauses execution
- Edge labels for Decision branches read from `conditions[].label`.
- Status badges driven by `verification_status` — green / red / gray;
  batch-loaded on canvas mount.

### Step palette (left rail)

- **Step types** — 43 from the `step_types` table, grouped Triggers /
  Flow / Records / Utilities.
- **Connectors** — searchable, scoped to installed-on-this-FSR; expand
  to drag a specific operation; drops as a Connector node pre-filled
  with op + schema-driven defaults.
- **Recipes** — drag any row from the `recipes` table as a multi-step
  subgraph.
- Drop-on-canvas: edges auto-attach to selected node's outbound; YAML
  re-emits; Monaco updates if open.
- Drop-on-edge: splice between two steps.

### Inspector (right rail, context-sensitive)

Three tabs per selected node:

1. **Args** — schema-driven form from `get_op_schema` (already returns
   `param_groups_by_select` for conditional visibility). Live jinja
   preview pane under each text field via `render_jinja` against
   accumulated `vars.steps.*` from prior simulated runs. Picklist
   fields call `precheck_picklist_value` on blur.
2. **Examples** — `find_operation_example(connector, op)` +
   `find_jinja_example(filter|var_path)`; click any snippet to insert.
3. **Verify** — buttons:
   - **Render** → `render_jinja` on every arg
   - **Run (safe)** → `run_op` if op is read-only, else greyed
   - **Test step** → new `step_test` MCP tool
   - **Show schema** → `get_op_schema`
   - **Verification history** → `verification_status(kind, key)`
   - Each button records its outcome to `verifications` so the node
     status badge updates immediately.

### Debug runner (bottom drawer)

Built on existing `step_through_playbook` MCP tool.

- Run controls: ▶ Run all · ⏭ Step over · ⏯ Run to breakpoint · ⏹ Stop
- Breakpoints: click a node's gutter dot.
- Branch chooser: at a Decision, surface buttons for each route.
- Watch panel: pin `vars.steps.X.Y` paths; auto-populated with
  reachable predecessors via existing `_compute_predecessors` BFS.
- Trace tape: horizontal strip; click a tile to jump back and re-run
  from there with edited inputs.
- Trigger payload editor: schema-driven form for `vars.input.records`
  using `module_fields`.

### Toolbar (whole-playbook actions)

- **Validate** — `validate_yaml` + lint ruleset
- **Resolve** — `resolve_yaml` (live picklist/connector prechecks)
- **Dry-run** — `dry_run_playbook` (compile + push + run)
- **Assert** — form builder for `assert_playbook_outcome`
- **Push** — existing `fsrpb push`
- **Recipe export** — wrap selected subgraph as a new `recipes` row

### MCP-over-HTTP dispatcher

- One generic `POST /api/mcp/<tool_name>` endpoint that introspects
  `mcp.tools` and forwards args/results.
- Allowlist gate (config-driven) before this is exposed beyond local.
- Unblocks every UI button without per-tool plumbing.

---

## Implementation phases

Ordered so each phase is independently shippable and the next phase
builds on something that already works.

### Phase 0 — Foundations (unblocks everything)

- [x] **0.1** `POST /api/mcp/<tool>` dispatcher in
      `web/backend/routes/mcp.py` — wraps `FastMCP.call_tool`, coerces
      structured results, exposes `GET /api/mcp/_tools` for
      introspection, gates via `FSRPB_MCP_ALLOW` / `FSRPB_MCP_DENY`
      env vars. Smoke-tested against `find_connector`,
      `verification_status`, unknown-tool 404. (2026-05-08)
- [x] **0.2** `python/compiler/visual_model.py` — `to_visual` projects
      the parsed IR into `{playbooks:[{nodes,edges}]}`; decision
      `conditions[].next` and manual_input `options[].next` surface
      as labeled branch edges; layout persisted as a
      `# fsrpb:layout` … `# fsrpb:layout-end` header block.
      `from_visual` covers identity + position-only updates today
      (structural edits raise `NotImplementedError` until Phase 3).
      (2026-05-08)
- [x] **0.3** `python/tests/test_visual_model_roundtrip.py` — 24
      fixture parametrizations + 3 behavior tests (layout
      persistence, decision-edge extraction, structural-edit guard).
      All 27 green. (2026-05-08)

### Phase 1 — Read-only canvas (smallest demo)

- [x] **1.1** `/edit` Svelte route + `PlaybookCanvas.svelte` +
      `StepNode.svelte` mounting `@xyflow/svelte`. Backend served by
      new `web/backend/routes/visual.py` (`/api/visual/list`, `/file`,
      `/`). All 7 visual families render with distinct colors and a
      one-line summary line. (2026-05-08)
- [x] **1.2** `web/frontend/src/lib/visualLayout.ts` — top-down
      `dagre` layout fills any node missing a position, server
      positions from the `# fsrpb:layout` block win when present.
- [x] **1.3** Per-node verification badge (green/red/gray dot)
      hydrated post-mount via `callMcpTool('verification_status', …)`
      against the Phase 0.1 dispatcher.
- [x] **1.4** `StepInspector.svelte` — read-only side panel showing
      family/type, comment, for_each loop block, raw arguments JSON.
- [x] **1.5** Visual / YAML toggle in the page header (no split mode
      yet — that's Phase 7.1).

### Phase 2 — Inspector reads (no editing yet)

- [x] **2.1** `StepInspectorArgsTab.svelte` calls `get_op_schema`
      via the dispatcher; renders required/optional flags, type,
      title, description, current value per param, and surfaces
      `applies_when` predicates for conditional params.
      Output-keys preview in a chip row. (2026-05-08)
- [x] **2.2** `StepInspectorExamplesTab.svelte` calls
      `find_operation_example` (per connector + op) and
      `find_jinja_example` (anchored on the closest predecessor's
      `vars.steps.<name>` or fallback `step_type`). Two stacked
      sections, ranked by occurrence count.
- [x] **2.3** Per-snippet "Copy" button writes to the clipboard as
      the Phase 2 write-path proof. Full insert-into-args lands once
      Phase 3 ships the structural-edit endpoint.

### Phase 3 — Drag/drop + edit (first real writes)

- [x] **3.0** Structural-edit pipeline: `from_visual` extended with
      a ruamel.yaml round-trip path that handles arg replacement,
      `name`/`comment`/`for_each` edits, and step add/remove.
      Identity round-trip still byte-stable. set_variable's
      `arg_list` is auto-converted back to top-level `vars:` to
      match parser expectations. Backend write endpoints
      `/api/visual/write` (in-buffer) and `/api/visual/write_file`
      (persisted). 28/28 round-trip tests green incl. arg-edit
      round-trip + edge-rewiring guard. (2026-05-08)
- [x] **3.1** `StepPalette.svelte` — three tabs (Steps / Connectors
      / Recipes) populated from `/api/ref/step-types`,
      `/api/ref/connectors`, `/api/ref/connectors/<n>/operations`,
      and a new `/api/ref/recipes` endpoint. Each row is an HTML5
      drag source carrying a JSON payload. (2026-05-08)
- [x] **3.2** Canvas drop handler decodes the palette payload,
      builds a step template (connector op pre-fills connector +
      operation; step types empty-but-typed), calls
      `visualStore.addNode` which appends the node, attaches the
      `next:` edge to the closest predecessor under the cursor, and
      selects the new node for inspector edit. Diff path teaches
      `from_visual` that edges touching newly-added nodes are not
      "rewiring", and writes them through to the predecessor's
      `next:` field. (2026-05-08)
- [x] **3.3** Splice mode wired in the store as
      `addNode({splice:true})` (rewires predecessor through the new
      node). Canvas drop heuristic uses non-splice path by default;
      enabling splice-on-edge-drop is a UX polish follow-up but the
      machinery is in place.
- [x] **3.4** `visualEditStore.svelte.ts` shared editable graph;
      Args tab fields editable for connector ops (per-param
      textareas) and set_variable (per-`arg_list` entry); Save /
      Discard bar in the page header; Save persists via
      `/api/visual/write_file` and refreshes the canvas from the
      returned graph. (2026-05-08)
- [x] **3.5** xyflow `onreconnect` retargets edges (target side);
      right-click on an edge prompts delete via
      `visualStore.removeEdge`. Backend `_apply_edge_rewiring`
      rewrites `step.next:` and decision `conditions[].next:` to
      match the new graph. (2026-05-08)
- [x] **3.6** `StepInspectorBranchesTab.svelte` — per-branch label
      input + target dropdown + delete button for decision /
      manual_input nodes. Backend updates the
      `option:` / `display:` field in conditions/options arrays.
      (2026-05-08)

### Phase 4 — Inspector Verify tab (per-step REPL)

- [ ] **4.1** Render button → `render_jinja` on every arg, show
      resolved values inline.
- [ ] **4.2** Run (safe) button → `run_op` for read-only ops; greyed
      with tooltip otherwise.
- [ ] **4.3** New MCP tool `step_test(yaml_text, step_id, input?)` —
      single-step variant of `step_through_playbook`; record pass/fail
      to `verifications`.
- [ ] **4.4** Verification history button → `verification_status`.
- [ ] **4.5** Picklist fields call `precheck_picklist_value` on blur
      with close-match suggestions.

### Phase 5 — Debug runner (whole-playbook REPL)

- [ ] **5.1** Bottom debug drawer; toolbar toggle.
- [ ] **5.2** Run controls (▶ ⏭ ⏯ ⏹) wired to
      `step_through_playbook` with `branch_choices`.
- [ ] **5.3** Breakpoint gutter on canvas nodes.
- [ ] **5.4** Branch chooser UI when execution hits a Decision.
- [ ] **5.5** Watch panel (pin `vars.steps.X.Y`); auto-populate with
      reachable predecessors.
- [ ] **5.6** Trace tape (clickable tiles to jump back).
- [ ] **5.7** Trigger payload editor (schema from `module_fields`).
- [ ] **5.8** "Run from selected step" — re-execute downstream from
      any tile with edited inputs.

### Phase 6 — Toolbar (replaces fsrpb CLI for 95% of work)

- [ ] **6.1** Validate → `validate_yaml` + lint; problems panel with
      click-to-jump.
- [ ] **6.2** Resolve → `resolve_yaml`.
- [ ] **6.3** Dry-run → `dry_run_playbook`.
- [ ] **6.4** Assert → form builder for the 3 existing assertion kinds.
- [ ] **6.5** Push → `fsrpb push` flow with confirmation.
- [ ] **6.6** Recipe export → write selected subgraph to `recipes`.

### Phase 7 — Polish (split view, "no FSR" mode, etc.)

- [ ] **7.1** Split YAML/visual mode with bidirectional cursor sync.
- [ ] **7.2** Graceful "no FSR configured" mode: Verify/Debug buttons
      explain what they would have done; record `seen` verifications
      where possible.
- [ ] **7.3** Undo/redo across canvas + Monaco.
- [ ] **7.4** Keyboard shortcuts (R = render, T = test step, F5 = run,
      F10 = step over).
- [ ] **7.5** Per-user preferences (D2 from TODO.md) feed into palette
      ranking and example surfacing.

---

## Risks & tradeoffs

- **Round-trip fidelity** is the make-or-break risk. If editing in
  visual mode loses comments / changes jinja whitespace / reorders
  dict keys, users won't trust the toggle. Phase 0.3 CI is mandatory
  before Phase 3 ships.
- **Auto-layout vs hand-layout.** Dagre is good but never perfect.
  Layout-as-YAML-comments is invisible-but-present; alternative is a
  sidecar `.fsrpb-layout.json`. Prefer comments unless the comment
  noise becomes real.
- **Live FSR coupling.** Verify and Debug features are dramatically
  less useful without a configured FSR. See Phase 7.2 for fallback
  mode.
- **Scope creep risk.** Each phase is independently shippable. Resist
  bundling phases into mega-PRs.
- **MCP dispatcher security.** Generic `POST /api/mcp/<tool>` means
  anyone with the web UI can invoke any MCP tool. Fine for local dev;
  needs an allowlist + auth before this ships beyond the local box.

---

## Companion: API doc / swagger replacement

Tracked here because it shares the dispatcher and the verifications
table with the visual editor.

- [ ] **A.1** Probe pass to populate `api_endpoint_params` (currently
      0 rows) from FSR API .md docs in `Miscellaneous/fortisoar/`.
- [ ] **A.2** Mine `playbooks_seen` for real call bodies →
      `api_endpoint_examples`.
- [ ] **A.3** New Svelte route `/api` grouped by service → endpoint;
      examples ranked by `verifications` status.
- [ ] **A.4** "Try it" panel — POSTs through `_live_client` (re-uses
      Phase 0.1 dispatcher pattern).
- [ ] **A.5** Per-endpoint verification badge (green/red/gray) from
      `verification_status('api_endpoint', path)`.

---

## Test coverage

- **Backend round-trip** — `python/tests/test_visual_model_roundtrip.py`
  pins identity round-trip across all 24 fixtures plus arg-edit,
  decision-branch retarget, and linear-next retarget round-trips.
  **29/29 green.**
- **Frontend store + pure logic** —
  `visualLayout.test.ts` (3 tests: dagre fill, server positions
  honored, orphan edges) and `visualEditStore.test.ts` (10 tests:
  load, setArgs, addNode + id disambiguation + splice, removeNode,
  retargetEdge incl. unknown-key no-op, removeEdge by tuple,
  renameBranchLabel). **13/13 green.**
- **Frontend API helpers** — `visualApi.test.ts` (6 tests:
  listVisualFiles GET + non-2xx, getVisualFile path encoding,
  getVisualFromBuffer POST shape, callMcpTool URL + body +
  tool-name encoding).
- **Component tests** —
  `StepPalette.test.ts` (6 tests: tab default, switch tabs, filter
  connectors, expand connector → ops, recipe rendering, onPick
  payload) and `StepInspector.test.ts` (7 tests: empty placeholder,
  schema-driven Args render, edit marks store dirty,
  set_variable arg_list editor, Examples tab + copy buttons,
  Branches tab visibility per step type, branch label rename
  reaches store).
- **Totals: 94/94 frontend + 29/29 backend green.** Drop-to-add
  user flow on the canvas is exercised indirectly through store
  unit tests; full xyflow drag simulation is the one notable hole
  and a Phase 5/7 follow-up.

## Recently landed (context for what already exists)

- **2026-05-08** — Verifications surfaced in `find_connector` /
  `find_operation` w/ ranking + warnings; `verification_status` MCP
  tool; precheck_* now persist to `verifications`; backfilled 1,172
  `operation_examples` from `playbook_steps`; `find_operation_example`
  + `find_jinja_example` MCP tools added. (See git log + TODO.md
  "Recently landed" section.)
- **2026-05-06** — `step_through_playbook` skeleton exists (L4 of
  success ladder). `dry_run_playbook`, `assert_playbook_outcome`,
  `resolve_yaml`, `validate_yaml`, jinja reachability checker all
  shipped.
- **2026-05-06** — `playbook_steps` corpus (7,442 rows) + `step_types`
  catalog (43 rows) + `step_handlers` (44 rows) all populated and
  ready to drive palette + custom-node templates.
