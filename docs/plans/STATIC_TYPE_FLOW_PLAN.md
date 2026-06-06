# Static type-flow analysis plan — source→target type checking across the branch tree

**Status:** PLAN ONLY (2026-06-06). No code written yet — awaiting design approval.
**Branch when building:** new branch off `feat/skill-based-playbook` (multi-file walker change).
**Green-check:** `make verify` after every phase.

---

## Why this exists

`verify_playbook` today validates a connector param's **type** only in two places, and
those two places **never share data**:

1. **Resolver (`resolver/connector_args.py`)** — runs per-step, knows the *consuming
   param's declared type*. It checks:
   - literal values → param type (Tier 1/2: `int`/`float`/`bool`/picklist; Tier 2.3:
     `ipv4`/`url`/`email`/`iso8601`/`json_*` for type-probed text params),
   - **pure Jinja with a terminal filter** → param type (Tier 3, `jinja_typing.py`):
     `{{ x | int }}` into a text param, `{{ list | length }}` is int, etc.,
   - filter-chain internal compatibility (Tier 3.1): `{{ x | int | upper }}`.
2. **Typed walker (`typed_walker.py`)** — runs across steps, knows *source shapes*
   (`vars.steps.<x>` → object/list/scalar with a scalar `type`). It checks structure
   only: missing field, indexing a non-list, unknown/unreachable step. It **records each
   shape's scalar `type` but never compares it to anything.**

### The gap

The half that knows **target types** (resolver, per-step) and the half that knows
**source types** (walker, cross-step) are separate passes that don't meet. Not caught
today:

- **(G1) Bare cross-step reference into a typed param** — `{{ vars.steps.fetch.count }}`
  (no filter) passed to a `text` param, or a string field passed where `integer` is
  required. The walker *knows* `count` is integer and the resolver *knows* the target;
  the comparison only runs when a terminal filter is present.
- **(G2) Shape-into-scalar** — an object/list reference passed into a scalar param
  (e.g. a `hydra:member` list into `ip`). Walker knows `kind=list`; never cross-checked.
- **(G3) `vars.<name>` (set_variable) and `vars.input.params.<name>` are untyped** — the
  walker records them as scalar `"any"`; playbook parameters carry no declared type. The
  *source* type is unknown, so there's nothing to check.

### A second, latent defect found while scoping this

The walker is **already written to be branch-aware** — it enumerates every trigger→leaf
path, each branch has its own `typed_env`, and a reference is valid only if its producer
is in the branch's `visible` set ("only what's above you in the tree"); cross-branch refs
already emit `unreachable_step_reference`. **But it never forks.** `verify_playbook` walks
a *fresh re-parse* of the YAML, and `step.branches` is only populated during *resolve* —
so the walked IR has `branches={}` and enumeration stops at the first `decision`. Verified:
`verify_playbook(decision_branch.yaml)` returns a single branch
`start → read_severity → branch_on_severity` and never walks the escalate/log arms.
`compile_yaml` already returns the resolved IR as `cres.ir`; the walker just isn't using it.

This must be fixed first — the user's "parallel branches, each with their own variables,
references only see what's above them" requirement depends on branch enumeration actually
working.

---

## Governing principle: evidence-driven

**No type rule ships without observed evidence backing it.** Every coercion claim, scoping
rule, and source/target compatibility decision in this plan must trace to a live FSR probe
or a runtime observation captured in a test fixture — not to assumption about how the engine
"should" behave. Concretely:
- The Phase 1 probes produce a **dated coercion matrix** from real runtime reads; that matrix
  is the source of truth.
- Phase 2 (var typing) and Phase 4 (source→target compatibility + coercion tolerance) derive
  their rules *from that matrix*. If the matrix doesn't cover a case, the analyzer degrades to
  `unknown`/skip rather than guessing.
- Each rule lands with a test that pins the observed behavior, so an FSR upgrade that changes
  coercion is caught by a failing test (re-run the probes, update the matrix).

## Design decisions (locked with user)

- **Coverage:** full — step outputs, set_variable vars, AND playbook params.
- **Severity:** type mismatch is an **error** (blocks `ready_to_push`).
  - Sub-rule to keep false-positives down: shape-vs-scalar (list/object → scalar param) is
    an unambiguous **error**; scalar-vs-scalar where FSR does runtime string coercion reuses
    the existing `_types_compatible` tolerance before erroring.
- **Branch model:** evaluate step-by-step, per branch; parallel branches keep isolated
  var/type envs; a reference resolves only against producers above it on its branch.
- **Reference scoping must be probed live** (FSR var semantics: shared mutable dict vs
  branch-isolated) before set_variable typing is finalized.
- **Troubleshooting export:** BOTH a per-run trace JSON file (e.g.
  `store/verify_traces/<sha>.json`) AND the trace folded into `verify_playbook`'s verbose
  evidence.

---

## Phases

Each phase is independently shippable and green under `make verify`.

### Phase 0 — Activate branch enumeration (prerequisite + standalone fix) ✅ DONE 2026-06-06
- Walk `cres.ir` (resolved IR, branches populated) instead of re-parsing in
  `tools_verify.py`. Confirm the resolver mutates Step objects in place so `cres.ir` carries
  `branches`.
- Guard: if `cres.ir` is None (compile failed earlier), keep current behavior.
- **Tests:** decision and manual_input playbooks enumerate >1 branch; each branch's
  `typed_env` keys differ; a cross-branch `vars.steps.X` ref emits
  `unreachable_step_reference`; a same-branch ref stays clean. Lock the
  `decision_branch.yaml` branch count as a regression.
- **Risk:** previously-dormant branch diagnostics may now fire on existing examples —
  audit all `examples/*.yaml` for newly-surfaced diagnostics and fix any real bugs vs
  false-positives before landing.

**Outcome:** `tools_verify.verify_playbook` now walks `cres.ir` (falls back to a fresh
`parse_yaml` only if `cres.ir is None`). Verified empirically: `decision_branch.yaml` went
1→2 branches; each arm's `typed_env` carries only its own terminal step. Audited all 24
`examples/*.yaml` — branch counts rose where expected, **zero new error diagnostics**
(the two pre-existing errors in `demo_record_find_update`/`find_and_update` are unchanged).
Tests: `fsr_core/tests/test_walker_branch_enumeration.py` (5 cases, incl. the re-parse-vs-IR
regression anchor and cross-/same-branch `find_record` reference checks). `make verify`
green (300 fsr_core + 159 connector).

**Gotcha discovered:** set_variable outputs are rewritten by the resolver to `vars.<name>`,
NOT `vars.steps.<step>` — so a cross-branch *set_variable* leak is invisible to the current
`vars.steps.*` machinery. That confirms Phase 2 (branch-local `vars.<name>` typing) is where
cross-branch set_variable scoping actually gets enforced. Cross-branch tests here use
`find_record` (output survives as `vars.steps.<step>`).

### Phase 1 — Probe FSR engine behavior: variable creation, scoping, and type coercion (live)

This phase is the empirical foundation. **How the playbook engine actually creates
variables and auto-coerces their types dictates what the static analyzer can soundly
claim.** We do not guess the runtime model — we drive real playbook flows on the live box,
read back the resulting `vars`, and encode the observed behavior into the type lattice the
walker uses. A static checker built on the wrong coercion model will both miss real bugs
and false-flag valid playbooks.

**1a. Variable scoping / lifetime**
- Does a `vars.<name>` set in one decision arm leak into a sibling arm? Is `vars` a single
  shared mutable dict for the whole workflow run, or per-path?
- Are set_variable definitions later in source but earlier in execution visible? What about
  loop (`for_each`) iteration scope — is `vars.item` only live inside the loop body?
- Outcome → correctness rule for Phase 2: conservative model is "a var is readable only if a
  defining set_variable is a guaranteed predecessor on the branch."

**1b. Type creation + auto-coercion matrix (the `"False"`→bool case)**
- Build a small battery of probe playbooks that `set_variable` a spread of literal forms and
  read the runtime type back (via a code_snippet `type()` dump or a downstream type-sensitive
  op). Cover at minimum:
  - `"False"` / `"True"` / `"false"` → bool? case-sensitive?
  - `"123"` / `"1.5"` / `"0x1f"` → int / float / str?
  - `'["a","b"]'` / `'{"k":1}'` → list / dict (JSON parse) vs str?
  - `"null"` / `""` / `"None"` → None / empty / str?
  - `"2026-06-06"` / ISO timestamps → str or datetime?
  - quoted-in-Jinja vs bare (`{{ false }}` vs `"false"` vs `false`).
- **Known starting point** (from auto-memory `fsr_set_variable_coercion`): set_variable runs
  `json.loads` on its input, so the **output type follows the input shape**, not `str` —
  `"False"`→bool, `"123"`→int, `'["a"]'`→list, and a value that fails `json.loads` stays a
  string. Phase 1b *verifies and extends* this into a complete, dated matrix (including the
  edge cases above and the Jinja-quoting interactions), because the static var-typer in
  Phase 2 must reproduce exactly this rule to infer set_variable types correctly.
- Also probe **connector-param ingestion coercion**: when a `text`-widget param receives
  `"123"`, does FSR coerce to int before the connector sees it, or pass the string? This is
  the runtime-coercion tolerance that decides which scalar→scalar mismatches in Phase 4 are
  hard errors vs tolerated (e.g. int source into text param).

**Deliverables**
- A dated **coercion matrix** committed into this doc (and `store/` reference if useful) —
  the single source of truth the walker's type lattice + `_types_compatible` tolerance must
  match.
- Probe playbooks kept under `python/probes/` (or `examples/`) so the matrix is
  re-verifiable when FSR upgrades.
- Findings recorded in auto-memory; update `fsr_set_variable_coercion` with anything new.

### Phase 2 — Branch-local var typing
- Extend `typed_env` to carry `vars.<name>` shapes per branch, populated as the walk
  passes each predecessor set_variable; infer scalar/list/object type from the value
  **using the Phase 1b coercion matrix** (e.g. `"False"`→bool, `"123"`→int, `'["a"]'`→list,
  json.loads-failure→str) — not an ad-hoc rule. Pure-Jinja value → reuse `jinja_typing`
  terminal inference. Cases outside the matrix → `any` (skip, don't guess).
- Move undefined-`vars` detection out of `validator.py` (`_check_undefined_vars`, added
  2026-06-06, whole-playbook) INTO the walker so it is branch-scoped. Keep the malformed-
  Jinja check in `validator.py` (it is branch-agnostic).
- **Tests:** var defined on branch A not visible on branch B; var read before its
  set_variable flagged; typed var feeds Phase 4 checks.

### Phase 3 — Playbook parameter declared types
- New optional YAML/IR surface for parameter types. Candidate shape (decide in build):
  `parameters: {ip: string, count: integer}` (mapping) alongside today's bare list, kept
  back-compatible (untyped list still allowed → `any`).
- Resolver/parser populate a `Playbook.parameter_types` map; walker seeds
  `vars.input.params.<name>` shapes from it.
- **Tests:** typed param flows into a connector op and a mismatch is caught; untyped param
  stays `any` (no regression on existing examples).

### Phase 4 — Source-vs-target type check (the core ask)
- New walker callback `param_type_fn(connector, op, param) -> observed_type` (same seam as
  `op_safety_fn`/`module_fields_fn`), wired from `tools_verify` to the resolver's
  `operation_param_observed_type` + `_param_target_observed_type`.
- At each connector-step reference site, compare the reference's inferred source type (from
  `typed_env`) against the consuming param's target type. Emit a new `type_mismatch`
  diagnostic (error). The scalar→scalar pairs treated as compatible (tolerated coercion) vs
  incompatible (error) are **taken directly from the Phase 1b connector-param ingestion
  matrix**, not assumed; `_types_compatible` is updated to match it. Shape-vs-scalar
  (list/object → scalar param) → hard error.
- Also cover set_variable→param and param→param flows now that those are typed.
- **Tests:** integer field → text param (per coercion rule), list shape → `ip` scalar
  (hard error), correctly-typed flow clean, Jinja-with-filter path unchanged.
- Add `type_mismatch` to the required-fix code list in `tools_verify.py`.

### Phase 5 — JSON trace export / troubleshooting
- Build a per-branch, per-step trace: typed_env evolution + every reference's
  (source_type → target_type → verdict) decision.
- Write to `store/verify_traces/<yaml_sha>.json` AND include in `verify_playbook` verbose
  evidence (`evidence["type_trace"]`).
- **Tests:** trace file written; verbose payload carries the trace; lean payload when
  `verbose=False`.

---

## Open questions
1. Phase 3 parameter-type YAML shape — mapping vs list-of-dicts; default when omitted.
2. Coercion tolerance for scalar-vs-scalar in Phase 4 — exactly which pairs FSR coerces at
   runtime (informs which mismatches are error vs warning). Phase 1 probe partly answers.
3. Whether `code_snippet` / `workflow_reference` (unknown output shapes) should ever produce
   type errors or always degrade to "unknown, skip."
4. Trace file retention/cleanup policy for `store/verify_traces/`.

## Files in scope
- `fsr_core/compiler/typed_walker.py` — branch walk, typed_env, type comparison (P0,P2,P4,P5).
- `fsr_core/mcp_server/tools_verify.py` — walk resolved IR, callbacks, evidence, trace (P0,P4,P5).
- `fsr_core/compiler/validator.py` — relocate undefined-var check (P2).
- `fsr_core/compiler/resolver/catalog.py` / `connector_args.py` — expose param target type (P4).
- `fsr_core/compiler/ir.py` + `parser.py` + resolver — parameter types (P3).
- `fsr_core/compiler/jinja_typing.py` — reuse terminal inference for var values (P2).
- `fsr_core/tests/` — new test modules per phase.
- Connector copy: re-vendor `fsr_core` after landing (per CLAUDE.md) to ship to the box.
