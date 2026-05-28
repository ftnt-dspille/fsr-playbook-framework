# Render-Path Validator — Plan & Progress

**Started**: 2026-05-08. Owner: dcspille.

Local validator + troubleshooter for FSR playbooks. Builds a full
render-path trace (every step's rendered args, simulated output, and
consumed `vars.…` references), then runs heuristic checks against it
to surface data-access issues, type mismatches, picklist drift, and
unreachable references **before** the playbook is ever pushed to FSR.

AI is an optional layer on top of the heuristics: heuristics flag,
AI proposes the fix.

---

## End goal

> A user opens a playbook, hits "Validate", and within a second sees
> red badges on the steps that will fail at runtime — with a one-line
> diagnostic + suggested fix per badge. No FSR push required.

The same trace data also powers the visual editor's per-step preview
(see `VISUAL_EDITOR_PLAN.md` Phase 5) — this plan is the analyzer
half; the editor is the UI half.

---

## Architecture

```
yaml → resolver → graph
              ↓
       trace simulator (extended step_through_playbook)
              ↓
       per-step {rendered_args, output, output_shape, consumed_paths,
                 simulated_from}
              ↓
       render-path analyzer (deterministic checks)
              ↓
       diagnostics: {step_id, kind, severity, path, expected, actual,
                     suggestion}
              ↓
       UI: red/amber dots on canvas + Diagnostics panel + "Ask Claude"
```

### FSR control-flow constructs the simulator must respect

Beyond linear `next` and Decision branches, the IR carries:

* **Step-level `condition`** — generic gate on most step types. If
  the rendered expression is falsy, FSR **skips the step entirely**.
  Simulator marks the record `conditionally_executed: true` and
  emits an empty output; analyzer downgrades C2/C5/C6 severity for
  consumers of skipped steps because the producer might not have
  run at runtime either.
* **`for_each` (already in IR)** — `{item, condition?, parallel?,
  __bulk?, batch_size?, break_loop?}`. The single owning step runs
  per element of `item`; `break_loop` is a Jinja predicate evaluated
  per iteration that exits early.
* **`do_until`** — repeat-while-not pattern; same handler, condition
  drives termination.
* **Inline `{% if %}` / `{% for %}` inside templates** — already
  handled by the consumed-paths extractor (test fixture in place);
  analyzer treats both branches' references as consumed.

### Per-step output simulation matrix

| Step kind | Output source (in order) |
|---|---|
| Trigger (post_create / post_update / api_call) | `vars.input` payload editor → `module_fields` schema scaffold → `{}` |
| Set Variable | computed from resolved `arg_list` |
| Decision | `{}` (gateway); auto-pick branch from rendered conditions, fall back to `branch_choices`, fall back to first |
| Manual Input | rendered option from `manual_choices` map → first option |
| For Each | iterate `for_each`; per-iteration bind `vars.item`; recurse loop body |
| Connector op | `mock_result` → cached `verifications` real run → safe `run_op` if available → `output_schema` scaffold → `{}` |
| Record CRUD (Create/Update/Find/Delete) | `mock_result` → `module_fields` scaffold → `{}` |
| Code Snippet | `mock_result` → optional Pyodide sandbox exec → `{}` |
| Delay | rendered duration metadata; no output |
| Workflow Ref | nested-playbook `mock_result` from this step → recurse into nested playbook → `{}` |
| Terminal / Raise Exception | rendered message; halts trace |

Each step records `simulated_from ∈ {"mock_result", "computed",
"live_run", "schema_scaffold", "user_fixture", "default_empty"}` so
diagnostics can downgrade severity when the source is weak.

### Heuristic check catalog (analyzer v1)

| # | Check | Catches | Inputs needed |
|---|---|---|---|
| C1 | Unreachable var path | `vars.steps.foo.bar` where `foo` doesn't exist or doesn't precede consumer | graph + predecessors |
| C2 | Missing key on output | path key absent from producer's output shape | output_shape + consumed_paths |
| C3 | Required-arg empty after render | jinja resolved to "" / null on a required field | schema + rendered_args |
| C4 | Picklist value drift | enum string not in live picklist | `precheck_picklist_value` |
| C5 | Type mismatch | list→string, dict→ipv4, etc. | schema param type + resolved value type |
| C6 | Index into non-list | `bar[0]` when `bar` is dict/string | inferred shape |
| C7 | Decision references unset path | branch condition reads a path never set on path-to-this-step | render-path graph |
| C8 | MI mode/output mismatch | downstream reads a key the chosen MI mode can't produce | MI catalog |
| C9 | For-each loop-var leak | `vars.item` referenced outside the loop's subgraph | graph scope |
| C10 | Dead step | step's output never consumed by any downstream | reverse index |

Severity: C1/C2/C3/C4 = error; C5/C6/C7/C8 = warning unless
provenance is strong (`live_run` / `mock_result`); C9/C10 = info.

---

## Build phases

### Phase 1 — Simulator gaps in `step_through_playbook`

Foundation. Without per-step output shapes for **every** step type,
nothing else works.

- [x] **1.1** Add `simulated_from` field to each trace record.
      (2026-05-08; values: `mock_result`, `computed`, `live_run`,
      `default_empty` — `schema_scaffold`/`user_fixture` come with
      Phase 2.)
- [x] **1.2** Honor `arguments.mock_result` as the simulated output
      for any step type that has one (record_crud, connector ops,
      code_snippet, fetch). (2026-05-08; short-circuits live exec.)
- [x] **1.3** Decision: evaluate rendered conditions against
      `vars_ctx` to auto-pick a branch when `branch_choices` doesn't
      pin it. Record the chosen branch in the trace. (2026-05-08;
      `_decision_pick_branch` honors pin → first-truthy → default →
      first-key fallback.)
- [x] **1.4** Manual Input: resolve from a new
      `manual_choices: {step_id: option_label}` arg; fall back to
      first option; emit the resolved value as the step's output.
      (2026-05-08)
- [x] **1.5** For Each: simulator iterates `for_each.item`, binds
      `vars.item` per iteration, evaluates the per-iteration
      `condition` filter and `break_loop` predicate (do-while —
      breaking iteration IS in the result list), produces a
      `list[dict]` matching live-FSR shape (each entry = body's
      set_var/mock_result keys + `task_id` stub). Trace gains
      `loop_iterations` count. Offline literal-list fallback via
      `_coerce_literal_list` so iteration works without a live
      Jinja engine. (2026-05-08)
      **Probe + fixtures (2026-05-08):**
      `python/probes/probe_render_path.py` synthesises 5 live
      scenarios (sequential / parallel / break_loop / empty /
      condition_filter). Captured fixtures under
      `python/tests/fixtures/render_path_probe/` drive the parity
      tests in `test_render_path_fixtures.py` (14 cases, all
      green). Re-run per scenario with `--scenario <name>`.
- [x] **1.6** Workflow Ref: simulator handles `type:
      workflow_reference` by resolving `arguments.target` to a
      sibling playbook in the same YAML and recursing via
      `step_through_playbook`. Child's `vars.input.params` is
      seeded from the parent's rendered `arguments.arguments`. The
      child's full env (collected via `_collect_child_env`) becomes
      the parent step's `output`, matching live-FSR shape (every
      child set_var key visible at `vars.steps.<ref>.<key>`).
      `apply_async: true` short-circuits with empty output.
      `nested_trace` is attached to the parent step record so the
      analyzer / UI can drill into the child run.
      **Probes (2026-05-08):** 4 ref scenarios captured — sync_basic,
      with_arguments, pass_parent_env_true, inside_for_each. Poll
      filter `parent_wf__isnull=True` ensures we capture the parent
      run not the child. All fixture-parity tests green.
- [x] **1.7** Output shape inference helper: produce
      `{top_keys, types, sample}` from any simulated output, used by
      C2/C5/C6 downstream. (2026-05-08; `_infer_output_shape` covers
      dict / list / scalar; attached to every trace record.)
- [x] **1.8** Tests: `python/tests/test_mcp_step_through_simulator.py`
      with 32 cases — provenance per step type, mock_result
      short-circuit on connector + record_crud, decision auto-eval
      (truthy / default / pinned), MI fallback + override, output
      shape per kind, `_truthy` edge cases. (2026-05-08; all green.)

### Phase 2 — Consumed-paths extractor

- [x] **2.1** `python/compiler/render_paths.py` — Jinja AST walker;
      handles attribute chains, constant subscripts, filter pipes,
      `{% if %}` blocks, malformed templates. Drops strict-prefix
      chains so callers see the deepest reference per template.
      (2026-05-08)
- [x] **2.2** Trace records gain `consumed_paths:
      list[{path, segments, root, source_step_id, location}]` and
      `name` for jinja-key resolution. (2026-05-08)
- [x] **2.3** 15 tests covering subscript / runtime-index skip /
      filter pipes / nested dicts + lists with location tracking /
      malformed template safety / dataclass shape / integration.
      (2026-05-08)

### Phase 3 — Analyzer v1 (4 highest-ROI checks)

- [x] **3.1** `python/compiler/render_analyzer.py` skeleton with
      `Diagnostic` dataclass, `analyze(trace, playbook?)`,
      severity tiers, dict serialization. (2026-05-08)
- [x] **3.2** C1 unreachable_var_path — flags refs to missing /
      after-the-fact producer steps, suggests rename. (2026-05-08)
- [x] **3.3** C2 missing_key — walks producer's output_shape,
      uses close-key heuristic for typo suggestions, downgrades
      severity when producer was simulated as default_empty OR
      conditionally skipped. (2026-05-08)
- [x] **3.4** C3 required_arg_empty — per-step-type required
      fields catalog (connector, record CRUD, decision, MI, set_var,
      code_snippet); flags rendered-empty values. (2026-05-08)
- [x] **3.5** C4 picklist_drift — `extract_picklist_refs` in
      `compiler/render_paths.py` statically harvests every
      ``{{ 'PL' | picklist('val') }}`` filter call and attaches
      `picklist_refs` to each trace record. Analyzer's
      `_c4_picklist_drift` calls a pluggable validator (defaults to
      `precheck_picklist_value`) per ref with a per-(pl, val) cache;
      surfaces close-match suggestions as the diagnostic's
      suggestion. Skipped silently when offline (`code: no_live_fsr`)
      so unconfigured-FSR users don't get spurious errors. CLI:
      `fsrpb analyze --execute-safe-ops` opts in. Verified end-to-end
      against live FSR catching `'In Progress'` → suggestion
      `'Investigating'`. (2026-05-08)

### 2026-05-08 follow-ups discovered while probing

- **Resolver whitelist gap for step-level `condition`** —
  RESOLVED (2026-05-08): added `condition` to all 5 `_FRIENDLY`
  blocks + connector `_CONNECTOR_RESERVED`. Subsequent live-FSR
  probe revealed FSR's runtime engine **does NOT honor a
  top-level `arguments.condition`** (the corpus's 250+ matches
  are all `for_each.condition`, never top-level). Top-level
  condition is now defensively accepted by the resolver but FSR
  silently ignores it; the simulator's defensive
  `conditionally_executed` handling stays for any future hand-
  authored YAML. Replaced the two probe scenarios with a real
  `for_each_condition_filter` that pushes cleanly.
- **Recursive output_shape** — Phase 1.7's `_infer_output_shape`
  records only TOP-level keys, so C2 misses typos in nested paths
  (`vars.steps.Fetch.data.summray` doesn't fire because the
  analyzer stops walking after `data`). Fix is to recurse one or
  two levels into dict values during shape inference. Belongs in
  Phase 5 with C5/C6.
- [x] **3.6** MCP tool `analyze_playbook(yaml_text, input?,
      branch_choices?, manual_choices?, execute_safe_ops=False)`
      returns `{ok, trace, diagnostics, error_count, warning_count,
      first_error}`. Defaults to fully offline. (2026-05-08)
- [x] **3.7** CLI: `fsrpb analyze <playbook>` runs the validator
      end-to-end. Pre-parses simplified YAML through
      `compiler.parser` so simplified-IR niceties (vars: → arg_list:,
      name → id) work; supports `--branch-choices`,
      `--manual-choices`, `--trigger-input`, `--execute-safe-ops`,
      `--json`. Human output groups diagnostics by step with
      glyph + severity + location + suggestion lines. (2026-05-08)

### Step-level skip condition (added per 2026-05-08 user note)

- [x] Simulator detects `arguments.condition` resolving to falsy and
      marks the trace record `conditionally_executed: true`,
      `status: skipped`, `output: {}`. Downstream consumers see an
      empty output and `simulated_from: computed`.
- [x] Analyzer C2 downgrades to warning when producer is
      `conditionally_executed`, since the producer might or might
      not run at runtime.
- [ ] Capture `do_until` and `for_each.break_loop` in the simulator
      when Phase 1.5 lands.

### Phase 4 — Visual editor surface

- [x] **4.1** Per-node badge in `StepNode.svelte` — error/warning
      pill in the node header keyed off the worst diagnostic per
      step (jkey-aware), with hover tooltip showing kind + sample
      message + count. (2026-05-09)
- [x] **4.2** Diagnostics drawer renders render-path diagnostics
      below YAML markers via new `RenderPathDiagnostics.svelte`.
      Per-row "Suggest fix" button calls
      `suggest_fix_for_diagnostic`; proposal renders inline with
      before/after diff + Apply / Dismiss. Click step_id to focus
      the node on the canvas via the new
      `visualStore.selectStepByName` → `pendingSelection` →
      `EditWorkspace` $effect drainer pattern. (2026-05-09)
- [x] **4.3** Toolbar gains an "Analyze" button next to Validate;
      separate render-diagnostics pill ("render N err / N warn")
      surfaces counts and opens the drawer when clicked.
      (2026-05-09)
- [ ] **4.4** Inspector "Render path" tab on the selected step:
      shows rendered args, simulated output (with provenance chip),
      consumed paths, and the producer of each path.

**Apply path:** `visualStore.applyTextSwap({stepId, location,
before, after})` walks the dotted location into `node.arguments`,
substring-replaces the leaf, and pushes to the undo stack. After
apply the drawer auto-runs `analyze()` so badges + counts refresh
against the patched YAML — same gate the agent prompt enforces
server-side.

### Phase 5 — Analyzer v2 (remaining checks)

- [x] **5.1** C5 type mismatch — **superseded** by Tier 3 of
      STATIC_TYPE_VALIDATION_PLAN (commits `c10418a` / `a3fb9ca`).
      Resolver + walker now emit `bad_value` / `bad_jinja_filter_chain`
      diagnostics for the same shape mismatches the render-path
      analyzer would have caught, with better intra-chain coverage.
- [x] **5.2** C6 index-into-non-list — shipped 2026-05-25
      (`_c6_index_non_list`). Severity warning; uses producer's
      `output_shape.types` to confirm the indexed attr isn't list-
      typed before flagging.
- [x] **5.3** C7 decision references unset path — shipped 2026-05-25 (`_c7_decision_unset_path`, static graph predecessor check; flags decision branch jinja referencing a step that's on no backward path from start to this decision).
- [x] **5.4** C8 MI mode/output mismatch — shipped 2026-05-25 (`_c8_mi_mode_mismatch` in `render_analyzer.py` + `compiler/mi_output_catalog.py` + 5 tests). Flags `input.X` reads off DecisionBased MI (no form) and `input.X` reads off InputBased MI where X is not in declared `inputVariables`. Button-only InputBased downgrades to warning. Catalog spec at `docs/research/MI_OUTPUT_CATALOG.md`.
- [x] **5.5** C9 for-each loop-var leak — shipped 2026-05-25
      (`_c9_loop_var_leak`). Flags `vars.item` consumed outside any
      for_each body; severity error since the runtime evaluates the
      reference as undefined.
- [x] **5.6** C10 dead step — shipped 2026-05-25 (`_c10_dead_step`).
      Info-level (sometimes intentional for side-effect writes); skips
      step types whose primary value isn't an output (decision /
      delay / manual_input / start / code_snippet / workflow_reference)
      and unsafe-simulated destructive ops.

### Phase 6 — AI fix layer

- [x] **6.1** `suggest_fix_for_diagnostic` MCP tool — heuristic
      patch proposer covering missing_key (close-match swap),
      picklist_drift (first valid value), required_arg_empty (TODO
      scaffold), unreachable_var_path (actionable no-fix reason).
      Returns `{step_id, location, before, after, confidence,
      explanation}`. (2026-05-09)
- [ ] **6.2** "Apply" button in the visual editor writes the patch
      via the existing `visualStore` edit path. (Phase 4 wiring.)
- [ ] **6.3** Bulk-fix: when the same typo recurs across N steps,
      one click patches all of them.

### Phase 7 — Agent integration

- [x] **7.1** System prompt enhanced (`python/agent/system_prompt.md`)
      with: mandatory analyze gate (step 6 of required workflow),
      per-diagnostic-kind fix strategies, dedicated troubleshooting
      workflow section, FSR runtime semantics block (live-verified
      for_each + workflow_reference shapes — non-obvious, must not
      be invented). (2026-05-09)
- [x] **7.2** `docs/step_params/` checked into the repo — 23
      Markdown files (one per step type) the agent can grep before
      writing args. Re-generate with `fsrpb dump-step-params`.
      (2026-05-09)
- [ ] **7.3** Hook the system prompt to fail-fast when authoring
      tools are skipped (e.g. detect "I think the args are…"
      patterns, redirect to `find_step_examples`).

---

## Cross-references

- Visual editor plan: `VISUAL_EDITOR_PLAN.md` (Phase 5 debug runner
  reuses this plan's simulator).
- Existing linter: `python/compiler/linter.py` — current static
  checks; render-path checks complement, don't replace.
- Manual-Input catalog: memory file `project_mi_decision_validation_landed.md`.
- `step_through_playbook` source: `python/mcp_server.py:3401`.
- `precheck_picklist_value`: existing MCP tool, reused by C4.
