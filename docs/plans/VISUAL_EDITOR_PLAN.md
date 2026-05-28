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

- [x] **4.1** Render button → `render_jinja` on every arg, show
      resolved values inline. New `StepInspectorVerifyTab.svelte` walks
      every string arg (incl. nested dicts/lists) and dispatches
      `render_jinja` per template; literals are echoed, errors surfaced
      inline. Wired as a new "Verify" tab in `StepInspector`. Test
      `StepInspector.test.ts` covers the resolved + literal paths.
      (2026-05-08)
- [x] **4.2** Run (safe) button → `run_op` for read-only ops; greyed
      with tooltip otherwise. Verify tab now has a Run section that
      shows for connector_op nodes; disabled when op-name doesn't
      match `_SAFE_NAME_PREFIXES` (mirrored on the frontend so the
      gate is instant). Server `requires_confirmation` response
      surfaces as an amber banner; ok-path renders `data` inline.
      Two new tests cover the safe + locked cases. (2026-05-08)
- [x] **4.3** New MCP tool `step_test(yaml_text, step_id, input?)` —
      single-step variant of `step_through_playbook`; pinpoints by
      `id` or by `name`-with-spaces→underscores; renders args via the
      live FSR Jinja engine, executes only safe-prefix connector ops
      via `run_op`, and writes `step_test_pass` / `step_test_fail`
      rows into `verifications`. Wired to a "Test step" button in the
      Verify tab. Backend covered by `test_mcp_step_test.py` (5
      tests — render-only, executed pass, unsafe-skip, by-name lookup,
      step-not-found); frontend covered by a new StepInspector test.
      (2026-05-08)
- [x] **4.4** Verification history button → `verification_status`.
      Verify tab History section auto-derives `(kind, key)` per node:
      `operation` + `<connector>:<op>` for connector_op nodes, else
      `step_type` + node.type. Surfaces strongest status, method, ts,
      excerpt + total row count; "no verifications recorded" when
      empty. (2026-05-08)
- [x] **4.5** Picklist fields call `precheck_picklist_value` on blur
      with close-match suggestions. Args tab now scans every param
      value for `{{ 'VAL' | picklist('NAME') }}` literals on blur,
      runs each unique pair through `precheck_picklist_value`, and
      surfaces `✓` / `⚠ value + suggestions` rows directly under
      the textarea. Stale results clear when the literal is removed.
      (2026-05-08)

### Phase 4.5 — Authoring gap-fill (post-Phase 4 audit, 2026-05-08)

Closed gaps the original Phase 3 / 4 plan claimed shipped but didn't:

- [x] **G1** Node drag enabled (`nodesDraggable=true`); positions
      persist via `setPosition` store method → `# fsrpb:layout` round-trip.
- [x] **G2** Edges connectable; `addEdge` with branch-kind inference
      (decision sources → `branch`, others → `next`); source-side
      reconnect via `retargetEdgeSource`.
- [x] **G3** set_variable add/remove variable buttons in Args tab.
- [x] **G4** Decision Branches tab grew an "Add branch" form
      (label + target dropdown).
- [x] **G5** Connector/op swap: collapsible `<details>` block in
      Args tab; switching `operation` clears `params` (op-specific).
- [x] **G6** Inspector header gained editable step name + Delete
      button (with parent `onDelete` callback). Comment editor in
      Raw tab.
- [x] **G7** Freeform connector params: rename / remove / + Add for
      params not declared in the schema.
- [x] **G10** Tab visibility per family — Decision lands on Branches,
      terminal lands on Raw, Args/Examples gated.
- [x] **G12** Backend round-trip pins source-side edge moves
      (`test_edge_source_move_round_trips`).
- [x] **G16** Drop position bug fix — node lands at cursor (manual
      viewport-transform inversion to derive flow coords).
- [x] **G31** LR layout uses left/right Handle positions; `direction`
      lifted to `+page.svelte` and threaded into canvas + StepNode.
- [x] **G32** Arrowheads on every edge via `markerEnd: ArrowClosed`
      with explicit hex color (slate / amber for branch).
- [x] **G33** Visible reconnect anchors via custom `FlowEdge.svelte`
      wrapping `BaseEdge` + `EdgeReconnectAnchor` at source + target.
- [x] **G34** Selected node highlight — 3px ring + glow driven by
      xyflow's `selected` flag.
- [x] **G35** Edge anchors only render when the edge is selected
      (xyflow portals the anchor outside `.svelte-flow__edge`, so
      conditional `{#if isSelected}` is the gate, not CSS descendant).
- [x] **G36** Mid-edge × delete button at the bezier midpoint when
      the edge is selected — calls `visualStore.removeEdge`.
- [x] **G37** Tone down xyflow's default Handle dots — hidden at rest,
      surface only when an edge is hovered/selected (via `:has()`)
      or while a connection is mid-drag. Arrowhead size shrunk to
      xyflow defaults so the tip sits flush against the target node.
- [x] **G38** Stale-node-ref bug — `+page.svelte` cached
      `selectedNode` by reference; store mutators replace
      `pb.nodes[idx]` so the inspector kept reading the old object
      (manifested as set_variable add/remove not updating the DOM).
      Fixed by switching to `selectedNodeId` + `$derived` lookup
      against the live graph.
- [x] **G39** CSS-rule pin for handle visibility — new
      `StepNodeStyles.test.ts` asserts the hide-by-default + edge-
      hover/selected reveal + `connecting*` + selection-ring rules
      live in `StepNode.svelte` so refactors can't silently regress.
- [x] **G40** Comprehensive UI capabilities test pass — new
      `__test_harness/InspectorHarness.svelte` mimics
      `+page.svelte`'s `selectedNodeId → derived node` flow;
      `InspectorIntegration.test.ts` (7 tests) drives add-variable,
      add-two-in-a-row, remove-variable, add+remove cycle, header
      rename, decision-add-branch, comment-write through real DOM
      events. These would have failed pre-G38.

Remaining post-audit work, tracked here so it doesn't fall off:

- [x] **G9**  Audit older phase mentions across plans / TODOs — done as
      part of the Studio unification rewrite. (2026-05-08)
- [ ] **G11** Pane-click create-step popover with corpus-driven next-
      step suggestions (mining `playbook_steps` for what usually
      follows the selected anchor) + "Suggest with AI" fallback that
      hits the chat agent.
- [ ] **G13** Palette defaults to **configured** connectors (live FSR
      `/api/integration/configurations/`); toggle to show all installed
      / available.
- [ ] **G14** Install connector from the palette (FSR install API
      wrapped as an MCP tool); refresh palette + verifications log on
      success.
- [ ] **G15** Configure connector from the editor — POST/PUT
      `/api/integration/configurations/`; cache config schema per
      connector.
- [x] **G41** Connection handles on all four sides of every node so
      connect/reconnect works regardless of TB/LR layout. StepNode now
      renders secondary source+target handles on the two sides
      perpendicular to the active layout (left/right when TB, top/bottom
      when LR). CSS handle-visibility gates already cover them.
- [x] **G42** Drop a moving edge anywhere on the node body to count
      as connect. Solved by raising xyflow's `connectionRadius` to 140
      in PlaybookCanvas — drops within node-body distance snap to the
      nearest handle, including the new G41 side handles.
- [x] **G52** Make new-edge dragging discoverable. Handles were
      hidden at rest and only surfaced when an existing edge was
      hovered/selected — that worked for reconnect but left
      first-time edge creation undiscoverable. Now handles also show
      whenever the user hovers any node, are larger (12 px) with a
      white outline + brand-colored fill, and scale up + show a
      crosshair cursor on hover so it's obvious they're grab targets.
- [x] **G51** Auto-name + dynamic param controls + real conditional
      visibility. (a) When the user picks an operation, the step's
      name auto-updates to the operation's title — but only if the
      current name is a generic system default (`Connector Action`,
      `connector_action`, empty, or the previous op's title/op_name).
      Manual edits are preserved. (b) Args tab now picks the right
      control per `param.type`: `<select>` when `options_json` is
      populated, number input for integer/number, checkbox for boolean,
      textarea for free-text. Defaults / placeholders / tooltips from
      the schema are surfaced. (c) `parent_param_name` +
      `condition_value` (and the OR list under `applies_when`) now
      actually hide gated params instead of just labelling them. A
      collapsible "Hidden — gated by other field values" footer lets
      the user inspect what's lurking and what would unlock it.
- [x] **G50** Three corrections in one pass:
      (a) `list_connector_configurations` now reads `connectors.info_json`
      first — the probe ingest already captured the full configuration
      array per connector. SQLite hit ~5 ms vs ~2 s live; live remains
      as the fallback when info_json is missing or `refresh=True`.
      (b) ConnectorPicker + new OperationPicker no longer write to the
      store on every keystroke. They commit on Enter, list-select, or
      blur. That kills the "operation 'b' not found" flash that was
      appearing while the user typed, and it lets the suggestions list
      narrow correctly because the input text and parent prop are no
      longer racing through the reactivity cycle.
      (c) StepInspector header collapsed: name input + Delete button
      on one row, family · type · id on a tiny dimmed line below.
      Examples tab cards rebuilt — header bar with op name + outline
      Copy button, syntax-highlighted JSON body (keys/strings/nums
      colored via a tiny inline highlighter), notes footer.
- [x] **G49** Connector configuration picker. New
      `list_connector_configurations(connector, refresh)` MCP tool wraps
      the existing `connector_configs.list_configurations` live-fetch
      and adds an in-process cache (configs change rarely; user can
      pass `refresh=True`). Inspector args tab now renders a `<select>`
      of `[{config_id, name, default}]` once a connector is picked,
      both in the empty-state form and as a compact "Config" row in
      the populated header. Empty list shows a "No configurations on
      the live FSR" hint instead of a broken control. Backend tests
      cover pass-through caching, refresh-bypass, and live-fetch error.
- [x] **G48** Connector combobox + big inspector icon. Replaced the
      `<datalist>` typeahead with `ConnectorPicker.svelte` — a custom
      combobox that renders each suggestion as `[icon] name / label`,
      supporting ↑/↓/Enter/Esc keyboard nav (native datalist hides
      images, so a custom popover was the only way to surface icons
      inline). Inspector args header now also shows a 64px icon next
      to the connector name in the empty-state form so the visual
      anchor is present even before an operation is picked.
- [x] **G47** Connector icons (info.json PNGs) — three-tier cache plus
      UI rendering. New `get_connector_icon` MCP tool fetches via
      `/api/integration/connectors/<name>/<version>/?format=json` (POST
      because FSR rejects GET on this route), and write-throughs to a
      `connector_icons(name PK, version, icon_small, icon_large,
      fetched_at)` SQLite table so process restarts hit disk (~1 ms)
      instead of refetching live (~300–1600 ms). Reused `_live_client`
      now memoises the FortiSOAR client across calls so we don't pay
      a fresh TLS handshake every time. New `ConnectorIcon.svelte`
      component with module-level inflight Promise dedupe; rendered as
      small icon in StepPalette rows + StepNode connector_op headers,
      and large icon in the StepInspector connector_op header. Backend
      tests cover memory→disk→live cache hierarchy + missing-connector
      and missing-FSR error paths.
- [x] **G46** `get_op_schema` arg-name fix — frontend was sending
      `op_name` but the pydantic-validated MCP tool requires `op`,
      surfacing as a "Field required" ToolError the moment the user
      typed a connector. Switched StepInspectorArgsTab to `op` and
      added an integration test that captures the actual fetch body
      and asserts the `{connector, op, verbose}` contract so a future
      rename can't reintroduce the regression.
- [x] **G45** Quick-menu z-index hoist + connector/operation typeahead.
      `:global(.svelte-flow__node:has(.fsrpb-add-next-menu))` lifts the
      host node above its siblings while the popover is open so the
      menu isn't covered by the next node's body. Connector + operation
      inputs in StepInspectorArgsTab now hydrate `<datalist>`s via
      `find_connector` / `find_operation` MCP tools so the user picks
      from real options instead of typing blind.
- [x] **G44** Best-path edge routing. Each node now carries source AND
      target handles on all four sides (`{top,right,bottom,left}-{s,t}`).
      `pickHandles(srcId, tgtId)` in PlaybookCanvas compares laid-out
      node-center deltas and selects the dominant-axis handle pair so
      lines exit and enter on whichever side is closest, instead of
      always leaving the bottom and wrapping around the node body.
- [x] **G43** Per-node "+ add next step" affordance. StepNode renders
      a circular `+` button at the source side (visible on hover or
      selection); clicking opens a quick-pick menu of the most common
      step types (set_variable, connector, decision, manual_input,
      record CRUD, delay, code_snippet, raise_exception). Selection
      calls `visualStore.addNode` with `predecessorId` so the new node
      arrives connected and offset 320px (LR) or 160px (TB) downstream.

### Phase 5 — Debug runner (whole-playbook REPL)

- [x] **5.1** Bottom debug drawer; toolbar toggle.
- [x] **5.2** Run controls — **shipped 2026-05-25**, **UX
      consolidated 2026-05-26** to 3 buttons (▶ Run / ⏭ Step / ⏹
      Stop). ▶ Run creates a session AND continues end-to-end in one
      click; ⏭ Step also creates if needed + advances one and
      auto-skips the trivial trigger entry; ⏹ Stop drops session,
      trace stays visible; Run/Restart label flips after done/stop
      so the rerun path is obvious. Server-side stateful sessions
      via 5 MCP tools (`start_debug_session` / `step_debug_session`
      / `continue_debug_session` / `stop_debug_session` /
      `get_debug_session`) in `tools_analysis.py` +
      `mcp_server/debug_session.py`. Frontend at `DebugPanel.svelte`
      + `api.ts`. Also fixed 2026-05-26: friendly-YAML decision
      branching + manual_input option routing (via
      `_normalize_friendly_steps`); `as_status()` now includes the
      full trace. 9 frontend tests + 12 session tests + 11 e2e
      against real `examples/*.yaml`.
- [x] **5.3** Breakpoints (tile click toggles, ⏯ continues until
      BP hit). Canvas-gutter UI still pending.
- [ ] **5.4** Branch chooser UI when execution hits a Decision.
      Server side ready (`branch_choice_override` on
      `step_debug_session`); UI affordance not yet wired.
- [ ] **5.5** Watch panel (pin `vars.steps.X.Y`); auto-populate with
      reachable predecessors. Server exposes `vars_keys` via
      `get_debug_session` — pin UI pending.
- [x] **5.6** Trace tape (clickable tiles to jump back).
- [ ] **5.7** Trigger payload editor (schema from `module_fields`).
      Server side ready (`input` arg on `start_debug_session`);
      UI form not yet built.
- [ ] **5.8** "Run from selected step" — re-execute downstream from
      any tile with edited inputs.

### Phase 6 — Toolbar (replaces fsrpb CLI for 95% of work)

- [x] **6.1** Validate → `validate_yaml` + lint; debounced auto-validate
      drives a click-to-jump diagnostics drawer. (2026-05-08, BuildBar)
- [ ] **6.2** Resolve → `resolve_yaml`.
- [ ] **6.3** Dry-run → `dry_run_playbook`.
- [ ] **6.4** Assert → form builder for the 3 existing assertion kinds.
- [x] **6.5** Push → `fsrpb push` flow surfaced via the Run split-button
      (Push only / Push & Run / Mock / Live). Logs stream into the
      Diagnostics drawer's Deploy tab. (2026-05-08, RunButton)
- [ ] **6.6** Recipe export → write selected subgraph to `recipes`.

#### Utility toolbar (G19, 2026-05-08 ask)

A single toolbar row above the canvas hosting day-to-day actions so
the user rarely touches the CLI / external tabs:

- [x] **G19/T1** Auto-layout TB / LR toggle button (G22) — re-runs
      dagre via `forceLayout()`, persists into all node positions
      via `setPosition` so undo can roll it back. (2026-05-08)
- [x] **G19/T2** Undo / Redo buttons (G20) — graph snapshot stack
      capped at 50 entries with JSON-equality dedupe so rapid
      keystrokes don't pile up. `canUndo`/`canRedo` getters drive
      the disabled state. (2026-05-08)
- [ ] **G19/T3** Jinja Test button (G21) — modal w/ template + context
      editor wired to `render_jinja`; accepts a `from_pb_execution`
      task_id so the user can render against a real run env. **Stub
      button shipped** in the toolbar; modal port pending — base
      logic in `WebstormProjects/widget-jinja-editor/widget/` (Angular
      controller + Monaco service to translate to Svelte/TS).
- [ ] **G19/T4** Play (Mock) — variant in the Run split-button surfaces
      a "not yet implemented" status. Backend wiring pending: should
      invoke `step_through_playbook` and stream into the Diagnostics
      Deploy tab. (2026-05-08 — split-button shipped, mock branch is
      the gap.)
- [x] **G19/T5** Play (Live) — Run split-button's "Live run" / "Push & Run"
      variants do `pushPlaybook` then `postSse('/api/playbook/run')`;
      logs / task_id / exit_code stream into runStore and the Diagnostics
      Deploy tab. (2026-05-08, RunButton + playbookActions.pushAndRun.)
- [x] **G19/T6** Save / Discard live in the unified PlaybookHeader at
      the top of the page (Save / Save as… / Revisions / + New / Delete).
      Visible in BOTH Design and CLI. (2026-05-08, PlaybookHeader.)

#### Command palette + shortcuts

- [ ] **G17** Cmd-K command palette — fuzzy-search registry of every
      toolbar action, plus playbook switch, search step by name, jump
      to errors, clear selection. Single source of truth for actions.
- [ ] **G18** Keyboard shortcuts bound to the palette commands:
      `⌘S` save, `⌘Z` / `⌘⇧Z` undo/redo, `Del` delete node, `R` render,
      `T` test step, `F5` Play (Live), `F6` Play (Mock), `⌘L` auto-
      layout, `Esc` clear selection, `⌘K` open palette.

### Phase 6.5 — Live run sync + playbook env (2026-05-08 ask)

Originated from the user's screenshot showing FSR designer's
Input/Output / Functions / Global Variables picker. The goal is to
turn each prior step's output (declared schema, last-run JSON env, or
on-demand `run_op` probe) into clickable jinja insertions.

- [ ] **G25** Live play mode — push draft, kick off run via
      `/api/wf/api/triggers/`, poll `/api/wf/instances/{id}/` (or SSE
      if available) for per-step status until terminal.
- [ ] **G26** Playbook env store — capture each step's rendered input
      + output (live or mock) into a per-playbook env keyed by
      `(playbook_name, run_id)`. Persist last N runs locally so users
      can author against real outputs after the run ends. Backed by
      existing `from_pb_execution` plumbing in `render_jinja`.
- [ ] **G27** Variable picker side panel — three tabs:
      - **Input/Output** — searchable token tree mined from the
        selected step's output schema + last-run env + reachable-
        predecessor outputs (BFS via `_compute_predecessors`).
      - **Functions** (G29) — FSR jinja filter catalog from
        `find_jinja_example`; click to insert an example snippet.
      - **Global Variables** (G30) — live FSR `globalVars`; click to
        insert `{{ globalVars.<name> }}`.
- [ ] **G28** Jinja insertion at cursor — picker click inserts at the
      caret of the most-recently-focused arg field. Handles textarea
      and input. Selection tracked across blur for one-click flows.

### Phase 7 — Polish

- [x] **7.1** ~~Split YAML/visual mode with bidirectional cursor sync.~~
      **Superseded** by the page-level Design/CLI mode toggle: each
      mode is a full workspace, the same playbook follows the user via
      `playbookStore`, and the in-Design Visual/YAML sub-toggle was
      retired. (2026-05-08)
- [ ] **7.2** Graceful "no FSR configured" mode: Verify/Debug buttons
      explain what they would have done; record `seen` verifications
      where possible.
- [ ] **7.3** Undo/redo across canvas + Monaco.
- [ ] **7.4** Keyboard shortcuts (R = render, T = test step, F5 = run,
      F10 = step over).
- [ ] **7.5** Per-user preferences (D2 from TODO.md) feed into palette
      ranking and example surfacing.

---

## Studio playbook unification (landed 2026-05-08)

Major chrome rewrite that consolidated Design (visual) + CLI (chat/YAML)
into a single Studio page with shared lifecycle. Recording here so the
plan reflects the actual state of the world.

### Architecture — four stores, one active doc

- `playbookStore.svelte.ts` — **source of truth for the active YAML.**
  `{kind, name, savedYaml, yaml}` + `dirty` derived. Backed by
  `/api/playbooks` (server-side drafts table with revisions).
- `visualStore.svelte.ts` — parsed graph + edit ops only. No longer
  owns YAML; `loadFromYaml` consumes from playbookStore, `renderToYaml`
  flushes back via the emitter.
- `yamlStore.svelte.ts` — legacy mirror kept alive so Chat /
  DiagnosticsList / DeployPanel keep working without a wholesale
  rewire. The page-level `$effect` syncs `playbookStore.state.active.yaml`
  → `yamlStore.text` on every doc change.
- `playbookActions.svelte.ts` — validate / compile / push / pushAndRun
  pipeline. Both modes call into it; reads YAML from `playbookStore`
  (no caller-passed buffer to go stale).

The `getActiveYaml` flush hook on `PlaybookHeader.save()` calls into
the page so Design renders its dirty graph through the emitter and
CLI returns the Monaco buffer — without it, save-while-on-Design lags
behind unsaved canvas edits.

### Backend — Phase A

- `web/backend/routes/playbooks.py`: 7 endpoints under `/api/playbooks`
  (list combined, get example, get draft, PUT draft, DELETE draft,
  list revisions, get revision, POST clone-from-example).
- `store/drafts.db` — separate SQLite from `fsr_reference.db` so user
  data lives apart from the curated reference store. Schema:
  `drafts(name PK, yaml, created/updated_ts)` +
  `draft_revisions(id, draft_name FK CASCADE, yaml, reason, is_auto, created_ts)`.
- Save semantics: every PUT writes a revision; `auto=true` distinguishes
  system snapshots (mode switch / picker change / deploy) from named
  user saves so the Revisions UI can bucket them.
- `/api/visual/write_file` hardened: refuses to mutate `examples/`
  fixtures (`code: "examples_readonly"`) so visual edits can't corrupt
  test reference YAML.

### Frontend — Phase B + consolidation

- `PlaybookHeader.svelte` — single picker with **two visual buckets**
  (My drafts / Examples), Save / Save as… / Revisions drawer / + New /
  Delete / Clone & Edit (for examples). Mode toggle is a right-aligned
  segmented control inside the header (saved a full row of chrome).
- `EditorToolbar.svelte` — Design's only chrome row, absorbed BuildBar:
  `↶ ↷ · ↧↦ · ƒ Jinja · | · Validate · Compile · ▶ Run▾ · status · [N err / N warn]`.
- `BuildBar.svelte` — kept as a thin row for **CLI mode** (no editor
  toolbar to merge into).
- `RunButton.svelte` — split-button (Push only / Push & Run / Mock /
  Live). Last-used variant persists in localStorage.
- `DiagnosticsDrawer.svelte` — diagnostics / fixes / compile / deploy
  tabs visible in BOTH modes. Closed by default. Fixes tab gracefully
  self-disables in Design (no Monaco refs to apply edits through).
- `EditWorkspace.svelte` — visual canvas + popover palette (left edge
  toggle) + popover inspector (right edge tab, only surfaces when a
  node is selected and the panel was manually closed).
- `StatusBar.svelte` — VS Code-style ~22px footer with backend / FSR /
  LLM / secrets pills. Replaced the right-side header health pills.

### Retired / superseded

- `/run` route — log surface lives in DiagnosticsDrawer's Deploy tab.
  Route survives only as a redirect to `/`.
- `/edit` route — folded into `/`.
- `ExamplesMenu.svelte`, `DraftsMenu.svelte`, `ExamplesMenu.test.ts` —
  PlaybookHeader supersedes them; deleted.
- Top-nav: Capabilities + Docs moved under Settings (sub-page links);
  ThemeSwitcher moved into Settings; HealthPill replaced by StatusBar.
  Final nav: Studio · Browse · Inventory · History · Settings.
- Inline draft-naming row, "Save · <draft>" button, Reset, Undo
  Loaded-Draft banner — all dead code, removed.
- Visual/YAML sub-toggle inside Design — Design is canvas-only; YAML
  authoring is the CLI mode.

### Autoload behavior

- First-visit: opens `examples[0]` so the canvas isn't blank; seeds
  Chat with a single greeting turn explaining what the agent does.
- Subsequent visits: `playbookStore.open()` writes
  `localStorage['fsrpb.last_opened']` on every load, and the page
  restores from it on mount (validates against the live picker
  buckets first to handle deleted-elsewhere drafts).
- One-time migration: `playbookStore.migrateLocalDrafts(yamlStore.drafts)`
  runs on first visit, copying browser-local drafts into the server
  drafts table with `reason: "migrated from localStorage"`. Gated by
  the `fsrpb.drafts.migrated_v1` flag.

### Test coverage added

- Backend: `web/tests/test_playbooks_routes.py` (8 tests) — list
  combine, draft head + linear revisions, auto vs named flags, 404s,
  cascade delete, name validation, clone-from-example + non-overwrite,
  example serve.
- Frontend: `playbookStore.test.ts` (12), `playbookActions.test.ts`
  (7), `EditorToolbar.test.ts` (Jinja-only), `EditorWiring.test.ts`
  (parent-state → MonacoYaml).
- Totals: **171 frontend + 308 python = 479** at the end of session.

### Known gaps (carried into next session)

- `Mock run` variant in RunButton surfaces a placeholder status —
  needs `step_through_playbook` SSE wiring.
- `visualStore.dirty` and `playbookStore.dirty` track independently;
  Design canvas stays internally "dirty" even after PlaybookHeader
  saves. Cosmetic; doesn't affect persistence.
- `EditWorkspace` `onJinjaTest` is still an `alert()` — the modal port
  from `WebstormProjects/widget-jinja-editor` is still pending.

---

## AI step drafter (landed 2026-05-08)

Inspector header on every supported step type (17 types) now shows a
**✨ Describe** button. Click → modal with a single textarea; the
user types intent in plain English, the backend composes a
deterministic system prompt per step type (intro + live module
schema + top 3 corpus skeletons from E1's summariser), and the
configured LLM provider returns a JSON `arguments:` body. The modal
renders a side-by-side diff (current vs proposed); one click applies
through `setArgs`. ⌘/Ctrl-Enter submits, Esc closes.

Backend lives at `web/backend/step_drafter.py` (13 unit tests) +
`POST /api/visual/draft-step`. Every call tags the UsageEvent with
`{feature: 'step_drafter', step_type: <type>}` so cost attribution
is wired for the dashboard read-side later.

Open follow-ups: tool-using variant (model can call
`list_picklists` / `find_step_examples` mid-turn instead of relying
on the pre-loaded prompt), inline validator pass before the diff is
shown.

## Upcoming — step-type authoring completion

Inspector surfaces vary in fidelity per step type. Next pass: bring
every step type to first-class authoring parity so users don't have
to drop into the Raw tab for the long tail.

Status by family (as of 2026-05-08):

- [x] `connector_op` — Args (schema-driven), Examples, Verify, Branches
      n/a. Complete.
- [x] `set_variable` — `arg_list[]` editor in Args tab. Complete.
- [x] `decision` — Branches tab now exposes per-row condition predicate
      + default (else) flag in addition to label + target. Renames /
      retargets / add / delete keep `arguments.conditions[]` in lockstep
      with the edges so emitted YAML is coherent. Complete.
- [x] `manual_input` — Args tab is now a visual form builder:
      title + description + per-field rows (name, label, formType,
      required, defaultValue, tooltip) reading either friendly
      `arguments.inputs[]` or canonical `arguments.input.schema.
      inputVariables[]`. Writes friendly form and clears the canonical
      block so there's one source of truth (resolver expands at compile
      time). A "Buttons" preview at the bottom of the Args tab shows
      the outgoing branch labels + targets so the analyst-facing form
      shape is visible at a glance. Branches tab still covers full
      label / target / formType editing per option.
- [x] `delay` — friendly days/hours/minutes/seconds grid in Args tab;
      writes friendly form, lets resolver expand to canonical TimeBased
      rule at compile time. Complete.
- [x] `raise_exception` / `terminate` / `assert` — dedicated mini
      editor (message + predicate for assert). Complete.
- [~] `workflow_reference` — Args tab now wires:
        - target IRI input (free text or Jinja — live picker still
          queued),
        - apply_async / pass_input_record / pass_parent_env toggles,
        - input mapping editor (key/value list under
          `arguments.arguments`).
      Still open: live cross-collection playbook picker (today user
      types/pastes the IRI) and "open nested playbook" jump action.
- [x] Trigger steps (`start_on_create` / `start_on_update` /
      `manual_action` / `api_call` / `start`) — Args tab now exposes
      resource (module) input, triggerOnSource / triggerOnReplicate /
      __triggerLimit toggles, and a recursive AND/OR `FilterTreeEditor`
      backing `arguments.fieldbasedtrigger.{logic, filters[]}`. Filter
      tree supports nested groups + the 13 leaf operators from
      `store/QUERY_API.md` §2.1 (eq/neq/lt/lte/gt/gte/in/nin/like/
      contains/exists/isnull) and the three value types
      (primitive / object / datetime). Sort + limit pass through
      untouched on every edit. Resource input is backed by a live
      module dropdown (sourced from the trained `modules` table via
      `GET /api/ref/modules`); FilterTreeEditor pulls per-field
      operator catalogs from `GET /api/ref/modules/<m>/fields` so
      operators are scoped to the field's FSR type (no more `like`
      on a boolean, no `gt` on a picklist).
- [~] Record CRUD (`find_record` / `create_record` / `update_record` /
      `delete_record` / `ingest_bulk_feed`) — Args tab now wired:
        - Module input (writes `module: '<name>?$limit=30'` for find,
          `collection: '/api/3/<name>'` for write, `/api/ingest-feeds/`
          for bulk).
        - find_record reuses `FilterTreeEditor` against
          `arguments.query.{logic, filters[]}` (full nested AND/OR).
        - Write steps render `resource` as a key/value field list with
          per-field `fieldOperation` (Overwrite / Append / Replace) and
          a top-level `operation` selector for update_record. `__bulk`
          checkbox surfaced with a tooltip clarifying it does NOT skip
          on-create triggers (per `feedback_bulk_vs_ingest_bulk_feed`).
        - delete_record: usage hint pointing at the upstream record IRI
          pattern.
      Write fields are now schema-driven: each entry under
      `arguments.resource` reads its FSR type from the
      `/api/ref/modules/<m>/fields` catalog and renders the matching
      editor — picklist dropdown (sourced from
      `module_fields.picklist_options`), boolean checkbox, number
      input, datetime input, or relation IRI input with a hint. The
      "+ Add field" affordance is now a dropdown over every
      not-yet-set field on the module. Free-text fallback survives
      when the catalog is empty.
      Verify tab wires a "Test query" action on `find_record`: posts
      the current `arguments.query` body via the new
      `test_find_record` MCP tool to `POST /api/query/<module>` and
      renders total + first 5 records (or a structured error) inline.
      Relation fields render a live `RelationPicker` dropdown
      (`search_module_records` MCP → `GET /api/3/<rel>?$search=…`)
      with a 200ms debounce + out-of-order request guard; users can
      pick a record by name without ever typing an IRI, but the
      input still accepts free-text Jinja for templated relations.
      Still open: dedicated Ingest Bulk Feed authoring.
- [x] `code_snippet` — Monaco-embedded editor (Python language mode,
      tab-indents 4 spaces, line numbers, word-wrap) bound to
      `params.python_function`. The wrapper (`MonacoCode.svelte`) is
      language-agnostic and reusable for future fields that need
      proper code editing. Open follow-up: register a tokenized
      Jinja-Python dialect so templated expressions visually
      distinguish from Python identifiers.
- [ ] `delay` — minimal but dedicated: number + unit picker.
- [ ] `raise_exception` / `terminate` / `assert` (terminal family) —
      one-line editors per type.
- [x] Ingest Bulk Feed step type — distinct "Feed source" block
      (item iterable + batch size + parallel + when-predicate; always
      asserts `for_each.__bulk: true`) above the schema-driven field
      editor. Field editor surfaces a `vars.item.<key>` hint so users
      see the binding pattern. Bypasses on-create triggers per
      `feedback_bulk_vs_ingest_bulk_feed`. Open follow-up: source
      schema preview (read the iterable's first element to suggest
      field bindings) — small AI-builder extension.

Each step-type build-out should ship with: schema-driven Args, at
least one fixture playbook, an Inspector tab test, and a corpus
sanity check (params present in 100% of `playbook_steps` samples
must appear in the editor).

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

## Companion: API explorer + Studio HTTP-step bridge (future)

Deferred but in scope. Not blocking Studio — surfaces later as a
**Studio integration point**: pick any of the 207K cataloged API
examples, hit "Insert into playbook" and an HTTP connector step
lands on the canvas pre-filled with method, path, parameters, sample
body, and expected output shape. Same path for the standalone `http`
connector and any custom connector wrapping a REST endpoint.

### The corpus we're sitting on

`Miscellaneous/api_examples_catalog/catalog.sqlite` — **339 MB,
207,419 entries spanning 6,927 products from 9 sources**. Per entry:

```sql
entries(
  id, product_id, source_id, action, action_normalized, description,
  example_type, source_url, implementation_url, example_quality,
  has_working_example, auth_method, notes,
  raw_inputs_json, parameters_json,
  http_method, http_path,
  code_snippet, code_lang
)
-- plus entries_fts (full-text index), products, sources,
-- connector_lifecycle
```

This is the most valuable authoring asset in the project — orders of
magnitude beyond what a hand-written Swagger UI could surface. Top
products by entry count: 33,783 (#2286), 13,818 (#2567), 5,081
(#3629). Mostly working examples (`has_working_example=1` is common,
`example_quality` ranks them).

### Why integrate with Studio

- "Find a working example for product X / action Y" → "Insert into
  playbook" closes the loop between discovery and authoring without
  curl + copy-paste round-trips.
- `auth_method` field tells us which connector configs the example
  needs; we can offer to create the matching config when one isn't
  present.
- `parameters_json` + `raw_inputs_json` give us schema-level fidelity,
  not just curl strings — that's what makes a useful HTTP step.
- The FSR reference store's `verifications` table augments the
  catalog: when an endpoint we've seen used in a real `playbook_steps`
  row matches a catalog entry, that entry gets a "battle-tested" badge.

### Phases (do not start until step-type completion lands)

- [ ] **A.1** Read-only mount of `catalog.sqlite` from the FastAPI
      backend (separate connection from `fsr_reference.db`; treat as
      external corpus, not user data).
- [ ] **A.2** `/api/api-catalog` endpoints — search by product +
      action + http_method, paginated; full-text via `entries_fts`.
- [ ] **A.3** Svelte `/api` route — product picker on the left,
      action list grouped by `http_method`, detail pane shows
      parameters + sample request + code snippet. Ranking: working
      examples > example_quality > source recency.
- [ ] **A.4** "Try it" panel — POSTs through `_live_client` (reuses
      Phase 0.1 MCP dispatcher pattern). Saves outcomes back to
      `verifications` so Studio benefits from the exploration.
- [ ] **A.5** Cross-link to FSR reference store: when a catalog entry
      matches `(connector, op)` in the FSR `playbooks_seen` corpus,
      surface a "verified in production" badge with link-back to the
      step example.
- [ ] **A.6 — Studio bridge** — "Insert into playbook" action that
      pre-fills an HTTP connector step from the catalog entry: method,
      URL (with the configured base URL substituted), headers, body
      template (params expanded with `{{ vars.input.… }}`-style
      placeholders the user can wire), expected output schema. Uses
      an existing connector config when one matches `auth_method`;
      offers to create one otherwise.
- [ ] **A.7** Reverse link — from a Studio HTTP step, jump straight
      to the catalog entry for the matching endpoint so authors can
      debug a request in the explorer without losing canvas context.

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
- **Phase 4 backend** — `python/tests/test_mcp_step_test.py` covers
  the new `step_test` MCP tool: render-only path, executed-pass path
  with stubbed `run_op` + `_record_verification` (asserts
  `step_test_pass` is recorded), unsafe-op skip path, by-name lookup,
  and step-not-found. **5/5 green.**
- **Phase 4.5 backend** — `test_visual_model_roundtrip.py` grew a
  new test (`test_edge_source_move_round_trips`) pinning that moving
  the SOURCE of an edge (UI: drag the edge handle off step A onto B)
  round-trips through `from_visual` cleanly and is stable on a
  second pass. **30/30 round-trip green.**
- **Phase 4.5 frontend** — `visualEditStore.test.ts` grew 7 tests
  for `setPosition` (write + unknown-id no-op), `addEdge` (default
  next, decision branch inference, explicit override, dedupe),
  `retargetEdgeSource`, and `addNode` with explicit drop position.
  `StepInspector.test.ts` grew 9 tests covering the new add-branch
  form, set_variable +/- buttons, connector-op swap clearing
  params, freeform param add, header rename, Delete-node callback,
  comment-textarea edit, and Decision/Connector tab visibility.
- **Phase 6/4.5 follow-on tests** —
  - `EditorToolbar.test.ts` (5 tests): undo disabled at rest, undo
    fires store, TB layout sets top-down positions, LR layout sets
    left-to-right + parent callback, Jinja/Mock/Live button dispatch.
  - `visualEditStore.test.ts` grew undo/redo coverage (5 tests):
    undo restores previous, redo replays, fresh mutation clears
    redo, undo no-op on empty stack, `load()` clears both stacks.
  - `visualLayout.test.ts` grew LR + `forceLayout` coverage.
  - `InspectorIntegration.test.ts` (7 tests, NEW): drives the real
    UI flow through `InspectorHarness.svelte` (mimics `+page.svelte`'s
    `selectedNodeId → derived node` pattern). Catches G38-class bugs
    where store mutations don't propagate to the rendered DOM —
    add variable, add 2 in a row, remove variable, add+remove cycle,
    rename header, add decision branch, write comment.
  - `StepNodeStyles.test.ts` (4 tests, NEW): pins the handle-
    visibility CSS gates (hidden by default; revealed via
    `:has(.svelte-flow__edge:hover/.selected)` and `connecting*`)
    and the selection-ring rule so refactors can't silently regress.
- **Totals: 145/145 frontend + 305/305 backend + 30/30 visual round-
  trip (one pre-existing emitter timestamp-flake deselected;
  unrelated to Phase 4 / 4.5 / 6).** Full xyflow drag-handle
  simulation remains the one notable testing hole — store-level
  coverage is thorough; an end-to-end Playwright pass is tracked
  under Phase 7.

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
