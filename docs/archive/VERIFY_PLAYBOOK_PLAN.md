# `verify_playbook` — design plan

**Status: ✅ COMPLETE** (closed 2026-05-25). All 6 phases shipped. Re-baseline run `20260525T165836Z` met the ≥90% first-show pass success criterion. Open-Q #3 resolved: `verify_runs` table in `history.db` + `record_verify_run` writer (commit pending). Remaining open follow-up is a scoring-level bug in the `live_tested` gate (`no_dry_run_target`), tracked separately.

**Goal**: close the agent loop so that a playbook isn't "done" until a
single forcing-function tool says it will actually run. Today the agent
compiles green and submits; the failures show up only when the user
runs the playbook live. We have all the validating tools — we lack the
discipline of using them in sequence.

**Working motivation**: build a `manual_input → block IP` playbook that
works end-to-end on the first push, not the third.

---

## Keep-criteria

A tool, prompt, or capability earns its place in the codebase if and
only if it serves at least one of:

- **Agent loop** — the LLM agent calls it as part of authoring or
  verifying a playbook.
- **Web app (editor / chat panel / history view)** — a human user
  interacts with it through the UI.

The CLI (`fsrpb …`) is a supported maintenance/ops surface and stays
first-class, but **CLI-only usage is not sufficient** to justify a
tool in the agent or compiler core. If the app could use a tool but
doesn't, that is a gap — either **wire it up** or **delete it**.

This rule applies to the existing surface area too, not just new work.
Phase 1 includes an explicit audit of every MCP tool, every
system-prompt directive, and every documented capability against the
rule, with a written decision (keep / wire / delete) per item.

---

## Problem statement

The success ladder gave the agent capabilities. It didn't give it a
loop. Symptoms observed:

- Compiles green, fails at runtime on Jinja paths that don't resolve.
- Picks the alphabetically-first connector instead of the one that
  matches the intent.
- Free-hands Jinja interpolations instead of grounding them in upstream
  output shapes.
- Stops at "validate_yaml ok" and never reaches dry_run / step_test.

The fix is **orchestration + a system-prompt forcing rule**, not a new
compiler.

---

## Architecture: type-checked DAG walk + live safe-op probe

The walker treats a playbook as a typed program:

1. Topo-order the steps of every reachable branch.
2. At each step, synthesize an output *shape* (not values) from static
   sources where possible, and from a **live `run_op` probe** when the
   step is a `connector_op` on the safe-read allowlist.
3. Accumulate `vars.steps.<step>.<shape>` as we walk.
4. For every downstream Jinja reference, resolve it against the typed
   env. Path doesn't exist → required_fix. Step isn't on the current
   branch → required_fix. Indexing `[0]` on a non-list → required_fix.
5. After path checks pass, do a stub-value Jinja render to catch
   filter/expression failures.
6. Aggregate per-branch results into one structured punch list.

**Key principle**: connector output_schema in the store is *evidence*,
not truth. Probe drift and vendor changes mean a stored schema can be
wrong. The walker prefers live response over stored schema for safe
ops, and marks destructive op outputs as `unknown_shape` rather than
trusting a stale row.

---

## Output shape sources (the typed env)

| Step type | Output shape source |
|---|---|
| `manual_input` | `inputVariables[].name + kind` → `{input: {<name>: <type>}}` |
| `find_record` | `module_fields(<module>)` → list of records with that field schema |
| `create_record` / `insert_record` / `update_record` | record IRI + module_fields |
| `connector_op` (safe op) | **live `run_op` response** with synthesized inputs; cached per session |
| `connector_op` (unsafe op) | `unknown_shape` — type-check inputs only; downstream refs become warnings |
| `set_variable` | `arg_list` keys verbatim |
| `code_snippet` | `unknown_shape` (Python return); downstream refs become warnings |
| `decision` | no output, branch routing only |
| `delay` | no output |
| `workflow_reference` (`apply_async=false`) | recurse into child playbook's outputs |
| `workflow_reference` (`apply_async=true`) | no output (fire-and-forget) |
| `start_on_create` / `start_on_update` / `start` (with module) | `vars.input.records[0]` ← module_fields of the trigger's `resource` |

---

## Safe-op allowlist (`op_safety` table)

Layered classifier, conservative wins. Stored in a new `op_safety`
table populated by `probe_op_safety`.

**Schema**

```sql
CREATE TABLE op_safety (
    connector_name      TEXT NOT NULL,
    op_name             TEXT NOT NULL,
    safety              TEXT NOT NULL CHECK (safety IN ('safe','unsafe','unknown')),
    reason              TEXT,             -- one-line human explanation
    evidence            TEXT,             -- JSON: {method, matched_pattern, source}
    classifier_version  INTEGER NOT NULL DEFAULT 1,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (connector_name, op_name),
    FOREIGN KEY (connector_name, op_name)
        REFERENCES operations(connector_name, op_name) ON DELETE CASCADE
);
CREATE INDEX idx_op_safety_safety ON op_safety(safety);
```

**Classifier layers** (later layers override earlier when stricter)

1. **Explicit per-op flag** if one exists on `operations` (today rare).
2. **HTTP method** when probed: `GET` / `HEAD` → safe.
3. **Op name prefix safe-pattern**: `^(get|list|search|find|fetch|lookup|describe|read|check|test|status|count|enumerate|query|show|export)_` plus trailing `_details|_info|_status` → safe.
4. **Op name prefix unsafe-pattern** (overrides 1–3): `^(block|allow|quarantine|isolate|create|update|delete|remove|insert|upsert|send|post|put|patch|disable|enable|kill|terminate|revoke|reset|restart|start|stop|run|execute|invoke|trigger|push|publish|notify|set|add|drop|attach|detach|assign|unassign|approve|reject|escalate)_` → unsafe.
5. **Connector category bias** if available: `firewall`, `EDR`, `messaging` → unsafe-leaning default; `threat-intel`, `enrichment` → safe-leaning default.
6. **Unclassified** → `unknown`. Treated as unsafe at runtime.

**Hand-curation hooks**

- Operators can override any row by direct UPDATE (the classifier
  honors `classifier_version` so future re-runs don't clobber manual
  edits without an explicit `--reclassify` flag).
- A future `op_safety_overrides.yaml` file can be loaded after the
  probe to lock in product-specific safety calls.

---

## Branch handling: all-paths verification

Walk every reachable branch. Report fixes per-branch. Rationale: the
playbooks where verify matters most are the multi-branch decision /
manual_input ones, and happy-path-only would hide the bugs verify is
supposed to catch.

Branch identification:

- `decision` step → each `branches[<label>]` is a path.
- `manual_input` step → each option's `next` is a path.
- `start_on_create` etc. → single path from trigger.
- `workflow_reference` (`apply_async=false`) recurses; cycles broken by
  visited-set.

Per-branch state: each path gets its own typed env so a step's output
on Branch A doesn't leak into Branch B if A doesn't run.

---

## The `verify_playbook` MCP tool

**Signature**

```python
verify_playbook(
    yaml_text: str,
    playbook: str | None = None,           # which pb in YAML (default: first)
    simulated_inputs: dict | None = None,  # {mi_step_name: {field: value}, trigger: {...}}
    live_probe: bool = True,               # actually run safe ops to get shapes
    verbose: bool = False,
) -> {
    ok: bool,
    ready_to_push: bool,
    required_fixes: [{code, message, path, step, branch, suggestion}],
    warnings: [...],
    checks_run: [{name, ok, summary}],
    evidence: {                            # full per-check output, redacted unless verbose
        compile: {...},
        typed_walk: {branches: [...], per_step_shapes: {...}},
        live_probes: [{connector, op, cached, shape_keys, latency_ms}],
        schema_checks: [...],
        stub_renders: [...],
    },
    next_actions: [str],                   # short ordered list of what to fix first
}
```

**Fan-out (sequential; bail on hard fail at each gate)**

1. **Compile** — `compile_yaml`. Any `severity=error` → block.
2. **Static Jinja path validation** — promote existing `validator._check_jinja_paths` misses to `required_fixes`.
3. **Typed DAG walk** — all branches.
4. **Per-step schema check** (during the walk):
   - `connector_op`: `precheck_connector_installed` + `get_op_schema` → required params present, no typos, picklist values in catalog (`precheck_picklist_value`).
   - `manual_input` w/ `type=InputBased`: at least one `inputs[]` entry.
   - `decision`: every branch label has a target step.
   - `workflow_reference`: target playbook resolvable.
   - `find_record / *_record`: module exists.
5. **Live safe-op probe** (when `live_probe=True`): for each `connector_op` classified `safe`, synthesize inputs, call `run_op`, hydrate downstream typed env.
6. **Stub-value Jinja render** — schema-driven fake values; run the real Jinja engine; catch filter/expression failures.

**Required-fix codes** (extend `ErrorCode`):

- `unreachable_step_reference` — `vars.steps.X` referenced but X isn't on this branch.
- `missing_field_on_step_output` — X exists but `.path` not in its known shape.
- `non_list_indexed` — `[0]` on a non-list shape.
- `required_op_param_missing` — connector op missing a required param.
- `op_param_unknown` — connector op has a typo'd param name.
- `picklist_value_unknown` — picklist value not in catalog.
- `branch_target_missing` — decision branch label has no target.
- `workflow_reference_unresolvable` — target playbook doesn't exist.
- `jinja_filter_failed` — stub render threw on a filter/expression.

**Warning codes**:

- `unknown_shape_downstream_reference` — downstream of a destructive
  op; output not knowable.
- `live_probe_skipped_unsafe` — safe to skip but reduces confidence.
- `picklist_value_fuzzy_matched` — case-insensitive / fuzzy match.
- `output_schema_stale` — stored schema disagrees with live probe;
  refresh recommended.

---

## System prompt rule

Add to `python/agent/system_prompt.md`:

> Before presenting any playbook YAML to the user, call
> `verify_playbook`. If `ready_to_push` is False, apply each
> `required_fixes` entry and call `verify_playbook` again. Do not show
> the user a YAML you have not verified. If a required_fix can't be
> applied (e.g. a missing connector), explain why and stop — do not
> ship a known-broken playbook.

---

## Eval scoring

New metrics in `python/evals/`:

- `verify_called_before_submit` (bool) — did the agent call
  `verify_playbook` at least once before its final answer?
- `verify_iterations_until_ready` (int) — how many verify→fix cycles.
- `final_verify_ready_to_push` (bool) — did the last verify return
  ready?

A submitted YAML where the agent never called verify, or where the
final verify still has required_fixes, fails the task regardless of
chat-review heuristics.

---

## Cost & latency model

`run_op` during verify isn't free — it hits live FSR + the third-party
vendor. Mitigations:

- **Per-session shape cache** keyed on `(connector, op, version,
  hash(synthesized_inputs))`. Verifying the same playbook twice in a
  session = one live call per safe op.
- **`live_probe: bool = True`** flag. Off ⇒ walker falls back to
  `operations.output_schema_json` with `output_schema_stale` warnings
  attached. Useful for offline / CI cycles.
- **Probe timeout**: 10 s default per safe op; on timeout, fall back to
  stored schema and emit a warning.
- **Synthesized-input determinism**: same playbook + same simulated
  inputs ⇒ identical shape-cache keys across runs.

---

## Phasing

Each phase is independently shippable; later phases assume earlier
ones landed.

**Status snapshot** (kept in sync with the codebase, not the plan's
original text):

| Phase | Status | Notes |
|---|---|---|
| 0 — Surface-area audit | ✅ done | `SURFACE_AUDIT.md` lives in the repo. Decision rules revised mid-flight: MCP tools that are unused-but-latent are **wire** (Phase 3 system-prompt), not **delete**. Deletion targets became app-side dead code (5 routes). |
| 1 — `op_safety` + audited deletions | ✅ done | `op_safety` table + `probe_op_safety` shipped. Five backend routes removed. Zero MCP-tool deletions (all unused tools turned out to have CLI/test callers). |
| 2 — Typed-walker library | ✅ done | `python/compiler/typed_walker.py`, 13 hermetic tests. Offline-pure; live-probe + module-fields + op-safety injected via callbacks. |
| 3 — `verify_playbook` MCP + CLI | ✅ done | `tools_verify.py`, `fsrpb verify`, system-prompt rule. Live-probe orchestration shipped (degrades to warning when no live FSR). Stub-value Jinja render landed via Phase 5 §"Render-Jinja preview" rather than this phase. |
| 4 — Eval scoring | ✅ done | Confidence-tier rename shipped (`draft` / `verified` / `live_tested` / `matches_example`). 3 new agent-behavior gates. New task `manual_input_block_ip`. Re-baseline run `20260525T165836Z`: agentic_anthropic 36/40 (90%) on the verify-relevant subset (manual_input_branch, manual_input_then_act, unknown_connector, manual_input_block_ip, soc_phish_block_with_approval). Every YAML-emitting task called verify once and got ready_to_push=True in 1 iteration. Open follow-up: `live_tested` gate bug (`no_dry_run_target` — `dry_run_kwargs` missing `playbook` name) — separate ticket. |
| 5 — Editor wiring | ✅ done | All 6 tickets shipped: per-step verify badges, step debugger panel, connector op picker, render-Jinja preview, "Why did this fail?" history panel + failed-runs list (combined in `FailedRunsPanel.svelte`, added as a "Failed runs" tab on the History page). |
| — System-prompt wire-ups | ✅ done | 22 latent MCP tools surfaced via a new "Latent capabilities" section in `system_prompt.md` grouping them by trigger (pre-flight / picklist / HTTP / discovery / post-mortem / self-review). |

### Phase 0 — Surface-area audit

Before any new code, produce a single audit document
(`SURFACE_AUDIT.md`) listing every MCP tool, every backend route under
`web/backend/`, every system-prompt directive, and every
`fsrpb` CLI verb, with these columns:

| Item | Used by agent? | Used by editor? | Used by CLI? | Decision |
|---|---|---|---|---|
| (e.g.) `analyze_playbook` | yes | no | yes | wire into editor OR delete (decide after reading the code) |

**Method**:

- Agent usage: grep `python/agent/system_prompt.md` and recent
  `chat_messages` for tool names.
- Editor usage: grep `web/frontend/src/` for fetches against
  `/api/...` routes; map each route back to the MCP tool it wraps.
- CLI usage: walk `python/cli.py` subparsers.

**Decision rules**:

- **keep+enhance** — actively used by agent AND/OR editor, no change.
- **wire** — would serve the editor but isn't connected; add a frontend
  surface (panel, button, badge, etc.) within Phase 5.
- **delete** — fails the keep-criterion. Schedule removal in Phase 1.

The audit is the **input** to the later phases — Phase 1's deletions
and Phase 5's wirings both pull from it.

### Phase 1 — `op_safety` data layer + audited deletions

- Add `op_safety` table to `store/schema.sql`.
- New `python/probes/probe_op_safety.py`: layered classifier; idempotent;
  records `evidence` JSON with which layer fired.
- Hook into the existing `fsrpb refresh` flow.
- Tests: classifier unit tests covering each layer + override priority;
  end-to-end probe run produces non-empty `op_safety` rows.

**No agent-facing changes in this phase.**

### Phase 2 — typed-walker library

- `python/compiler/typed_walker.py`: pure-Python, no MCP, no live calls.
  Returns `{branches: [{name, typed_env, diagnostics}]}`.
- Reuses `compiler.ir`, `compiler.validator`, `compiler.resolver`.
- Live-probe hook is a callback the caller supplies; the library itself
  is offline-pure.
- Tests: hermetic. Synthetic playbooks for each step type. Branch
  forking. Cycle detection.

### Phase 3 — `verify_playbook` MCP tool + CLI

- `python/mcp_server/tools_verify.py`.
- `fsrpb verify <yaml>` mirror in `cli.py`.
- Live-probe orchestration: synthesize inputs from upstream typed env,
  call `run_op`, cache shape per session.
- Stub-value Jinja render pass.
- Aggregated punch-list output with the codes above.
- System-prompt update.

### Phase 4 — eval scoring + agentic re-baseline (unchanged)

- New metrics in `python/evals/` for verify usage + final ready state.
- Re-baseline `agentic_anthropic` + `agentic_lmstudio` on the existing
  task set with the new system-prompt rule.
- Add a `manual_input → block IP` task to the eval set; assert the
  agent calls verify and ends with `ready_to_push=True`.

### Phase 5 — editor wiring (close the human-side gap)

Items the Phase 0 audit identifies as "would serve the editor but
isn't wired" get frontend surfaces here. Working list (to be confirmed
by the audit):

- **Per-step verify status badges** on the canvas. Calls
  `verify_playbook` on save / on demand; colors each step node by
  fix/warning/clean.
- **Step debugger panel** that drives `step_through_playbook` against
  the current draft, using simulated inputs from the inspector.
- **"Why did this fail?" panel** in the History view that calls
  `why_did_playbook_fail` for the selected past run and renders the
  punch list inline.
- **Render-Jinja preview** in the inspector for any field containing
  `{{ ... }}` — calls `render_jinja` with the typed env from the
  walker.
- **Connector op picker** that ranks results using `find_operation` +
  the user-preference store (see TODO D2).

Each Phase 5 ticket cites the audit row that justifies it. Anything
not lifted into a ticket here gets deleted in Phase 1.

---

## Open questions

1. ✅ **Stub value generation** — resolved. `web/frontend/src/lib/shapeStubs.ts`
   converts Shape → JSON stub with type-driven sentinels
   (`'_stub_text_'`, `0`, `false`, `{}` for unknown shapes, FSR
   universal keys `status` / `result` / `@id` always present). Live
   `module_fields` enrichment is automatic — the walker pulls field
   names from the store via `_module_fields_fn`.
2. ✅ **Cycle detection on `workflow_reference`** — resolved. Walker
   uses a per-branch `visited` set (`typed_walker._enumerate_branches`).
3. ✅ **Should `verify_playbook` write the punch list to `history.db`?**
   Resolved 2026-05-25 — yes. `verify_runs` table in `web/backend/history.py`;
   `tools_verify._record_history` writes every call best-effort.
   `history.session_verify_stats(session_id)` returns the loop metrics
   (called / iterations / iterations_until_ready / final_ready) that
   the eval gates and chat-review detector consume.
4. ✅ **Live-probe failure mode** — resolved (degrade-to-warning).
   `_live_probe_factory` in `tools_verify.py` swallows probe errors
   and records latency in `evidence.live_probes`; the walker then
   emits `unknown_shape_downstream_reference` warnings for refs that
   reach through the now-unknown shape.

---

## Non-goals (intentional)

- **Not** building a new compiler. All static checks already exist;
  verify is orchestration.
- **Not** running destructive ops to "see what happens." Unsafe ops
  type-check inputs only.
- **Not** caching live-probe responses across sessions. Per-session
  only; vendor responses change.
- **Not** replacing `dry_run_playbook` or `step_through_playbook`.
  Those remain useful for interactive debugging; verify is the
  one-shot pre-submit gate.

---

## Success criteria

- Every `manual_input → block IP`-class playbook the agent produces
  has `verify_playbook` called and ends with `ready_to_push=True`.
- Agentic eval: ≥90% of submitted YAMLs pass verify on the first
  shown-to-user version (≤2 verify→fix iterations).
- Production: zero "compiled green, failed at runtime on Jinja path"
  bugs reported by users for verified playbooks across a 2-week window.
