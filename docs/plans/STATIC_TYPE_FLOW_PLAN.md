# Static type-flow analysis plan — source→target type checking across the branch tree

**Status (updated 2026-06-06):** Phases **0, 1 (1a+1b), 2, 4 DONE & committed**; Phases 3 & 5
not started. Connector-param ingestion coercion (Phase 1b tail / Open Q #2) still deferred —
Phase 4 shipped the evidence-sound subset that does NOT need it (see Phase 4 Outcome).
**Branch:** `feat/static-type-flow` (off `feat/skill-based-playbook`).
**Green-check:** `make verify` (307 fsr_core + 159 connector) — currently green. Note the
python eval suite (`python/tests/test_evals_harness.py::test_run_matrix_gold_beats_echo`) is
gated by `verify_playbook` output, so any verify change must keep the gold fraction ≥ 0.55.

**Commits:** `7372065` (P0 branch enum) · `5513f20`+`50157b1` (P1b coercion) · `02a699e`
(P1a scoping) · `027bce3` (P2 var typing + P0 regression fix).

**RESUME HERE →** Phase 3 (playbook parameter declared types — would let
`vars.input.params.<name>` flow into the Phase 4 check) OR Phase 5 (JSON trace export). The
core ask (Phase 4 source→target check) is DONE. See each phase's **Outcome** block below for
what landed. Probes are re-runnable:
`PYTHONPATH=python:. .venv/bin/python -m probes.probe_set_variable_coercion` (and
`probe_var_scoping`); results in `store/probe_results/`.

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

**Status: 1a (scoping) + 1b (coercion matrix) DONE 2026-06-06 (live FortiCloud SOAR).
Connector-param ingestion coercion still deferred (Open Q #2, only needed for Phase 4).**

#### ✅ Phase 1a RESULT — variable scoping / lifetime (2026-06-06, live)
Probe: `python/probes/probe_var_scoping.py` → `store/probe_results/var_scoping.json`
(force-fail channel, same as 1b). Confirms the conservative model the walker already assumes:
- **Predecessor visible on the taken arm:** a var set before a decision (`a="alpha"`) reads
  back as `alpha` on the taken arm. ✓
- **Sibling-arm isolation:** a var set ONLY on the untaken Else arm reads `UNSET` on the taken
  arm — decision arms are exclusive (only one route executes per run). ✓
- **`for_each` item is loop-scoped:** `{{ vars.item }}` read in the step AFTER a `for_each`
  step is `UNSET` — the loop binding is dead outside the looping step. ✓

**Phase 2 rules locked by this:** (1) a `vars.<name>` reference resolves only if a defining
`set_variable` is a predecessor on the *same branch* (already the walker's `visible`-set
model); (2) `vars.item` is valid only inside the step that carries `for_each` — flag it as
undefined anywhere else. (Note: `vars` is a run-global mutable dict, but per-run only one
decision arm runs, so the static per-branch model is sound — no cross-arm leakage observable.)

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

---

#### ✅ Phase 1b RESULT — dated set_variable coercion matrix (2026-06-06, live FortiCloud SOAR, build 7.6.5)

Probe: `python/probes/probe_set_variable_coercion.py` → raw result in
`store/probe_results/set_variable_coercion.json`. Tested on the **FortiCloud SOAR** instance
(`mfz9...forticloud.com`, build 7.6.5).

**Mechanism gotcha (FortiCloud-DEFAULT, not engine-intrinsic — per user 2026-06-06):** on
FortiCloud, success-path step results AND run `env` are dropped server-side to save storage
(both came back `{}` on a finished run; the per-trigger `debug:true` flag did NOT override
it). Results persist only when the run **FAILS** under that default. **There is a SOAR
application-config setting that makes ALL playbooks log in debug mode** (success-path results
+ env retained) — self-managed appliances commonly have this on; FortiCloud defaults it off.
So the empty-env behavior is config-dependent, not a property of the engine. **The coercion
MATRIX below is unaffected** — type coercion is engine behavior independent of logging.
The probe uses a `start → Set Literals (set_variable) → Boom (code_snippet: raise)` force-fail
so it reads results **regardless of the log setting** (portable across instances). Same
force-fail channel the connector uses for agent-op results — auto-memory
`fsr_agent_proxied_execute_async`. (TODO if useful: locate the exact config key and offer a
debug-on success-path read as a cross-check.)

| input literal (what author writes) | runtime type | runtime value |
|---|---|---|
| `"False"` / `"True"` | **boolean** | False / True |
| `"false"` / `"true"` | **boolean** | False / True |
| `"TRUE"` (all-caps) | string | `"TRUE"` |
| `"yes"` | string | `"yes"` |
| `"123"` / `"0"` / `"-7"` | **integer** | 123 / 0 / -7 |
| `"007"` (leading zero) | string | `"007"` |
| `" 123 "` (ws-padded) | **integer** | 123 |
| `"1.5"` / `"1.0"` | **float** | 1.5 / 1.0 |
| `"1e3"` (scientific) | **float** | 1000.0 |
| `"0x1f"` (hex) | string | `"0x1f"` |
| `"1,000"` (commas) | **list** | `[1, 0]` (tuple-eval!) |
| `'["a","b"]'` | **list** | `['a','b']` |
| `'{"k":1}'` | **object** | `{'k':1}` |
| `"[1, 2"` (malformed) | string | `"[1, 2"` |
| `"null"` / `"None"` | **null** | None |
| `"~"` (YAML null token) | string | `"~"` |
| `""` (empty) | string | `""` |
| `"hello"` | string | `"hello"` |
| `"2026-06-06"` (date) | string | `"2026-06-06"` |
| `"2026-06-06T12:00:00Z"` (ISO) | string | `"2026-06-06T12:00:00Z"` |
| bare YAML `false` / `42` / `3.14` | boolean / integer / float | survive natively |
| Jinja `"{{ false }}"` | **boolean** | False (render→`False`→coerce) |
| Jinja `"{{ 1 + 2 }}"` | **integer** | 3 |
| Jinja `"{{ [1,2,3] }}"` | **list** | `[1,2,3]` |
| Jinja `"{{ '123' }}"` | **integer** | 123 (rendered `123` re-coerces!) |

**The rule is NOT pure `json.loads`** (the old auto-memory claim is corrected):
`json.loads("True")`/`("None")` would fail, yet both coerce; `json.loads("1,000")` would
fail, yet it becomes the tuple `(1,0)`→`[1,0]`. The behavior is a *smart cast* that accepts
both JSON tokens (`true`/`false`/`null`) **and** Python literals (`True`/`False`/`None`,
tuple syntax) — close to `json.loads`-then-`ast.literal_eval`, but with guards that keep
`0x1f`→str and dates→str (which `ast.literal_eval` would otherwise turn into 31 / 2014).

**Predictive classifier for the Phase 2 var-typer** (reproduces the matrix for all
author-relevant forms; degrades exotic/ambiguous forms to `any`, never false-flagging):
1. native (non-string) value after render → its JSON type;
2. string `S` (post-jinja-render):
   - `S ∈ {true, false, True, False}` (exact) → **boolean**;
   - `S ∈ {null, None}` (exact) → **null**;
   - `re.fullmatch(r"\s*-?(0|[1-9][0-9]*)\s*", S)` → **integer** (no leading zeros);
   - `re.fullmatch` decimal/scientific float (must contain `.`/`e`) → **float**;
   - `S.lstrip()[:1]=="["` and `json.loads(S)` ok → **list**;
   - `S.lstrip()[:1]=="{"` and `json.loads(S)` ok → **object**;
   - else → **string**.
   (Deliberately NOT special-casing `"1,000"`→tuple or `"0x1f"`: rare in authored
   playbooks; classifier returns `string` there, which is safe for the analyzer.)

**Still open from Phase 1b (deferred to when Phase 4 needs it):** connector-param ingestion
coercion (does a `text`-widget param receiving `"123"` see int or str?) — needs an echo op
to observe what the connector actually received; not blocking Phases 2–3. Tracked in Open Q #2.

### Phase 2 — Branch-local var typing ✅ DONE 2026-06-06
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

**Outcome:** `typed_walker` now carries a per-branch `var_env: {name → Shape}` on each
`BranchResult`, populated as the walk passes each predecessor `set_variable` and typed via
`_infer_literal_shape` (the Phase 1b classifier — `_set_variable_value_map` extracts the
{name: value} pairs from both arg_list and normalized-flat forms). This feeds Phase 4.
Per the user's **split decision** (NOT a literal move): `validator._check_undefined_vars`
**keeps** the whole-playbook "never defined anywhere" warning (compile-time, all surfaces);
the walker **adds** the branch-scoped cases it alone can see, all `severity=warning`:
`var_read_before_definition`, `var_defined_other_branch`, `loop_var_outside_for_each`
(`vars.item` outside a for_each step — justified by the Phase 1a probe). Disjoint: the walker
stays silent when a name is never defined anywhere. Tests:
`fsr_core/tests/test_walker_var_typing.py` (classifier unit + 6 scoping/typing cases). No new
diagnostics on any `examples/*.yaml`.

**Regression caught + fixed (important):** Phase 0 had pointed the *entire* `verify_playbook`
at `cres.ir`, including `_per_step_schema_checks`. The resolver rewrites an `options:`-based
`manual_input` to `type: InputBased` with `response_mapping` and no `inputVariables`, so the
"InputBased needs inputs[]" check false-fired → dropped the `gold` eval fraction 0.587→0.543
(below the 0.55 bar in `test_run_matrix_gold_beats_echo`). Fix: `cres.ir` now feeds ONLY the
typed walk (`walk_coll`); the per-step schema checks + Jinja-shape evidence run on the fresh
parse (authoring shape) exactly as before. Gold fraction restored to 0.587.

### Phase 3 — Playbook parameter declared types
- New optional YAML/IR surface for parameter types. Candidate shape (decide in build):
  `parameters: {ip: string, count: integer}` (mapping) alongside today's bare list, kept
  back-compatible (untyped list still allowed → `any`).
- Resolver/parser populate a `Playbook.parameter_types` map; walker seeds
  `vars.input.params.<name>` shapes from it.
- **Tests:** typed param flows into a connector op and a mismatch is caught; untyped param
  stays `any` (no regression on existing examples).

### Phase 4 — Source-vs-target type check (the core ask) ✅ DONE 2026-06-06
- New walker callback `param_type_fn(connector, op, param) -> target_tag` (same seam as
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

**Outcome:** `typed_walker._check_connector_param_types` runs per connector step on each
branch. It only judges a param whose value is a **pure single reference** —
`_pure_single_ref` accepts `{{ vars.steps.X.y }}` / `{{ vars.name }}` and rejects filtered
(`| int`), interpolated (`a {{ x }} b`), and call (`foo()`) forms, so the resolver's Tier 3
keeps sole ownership of filtered values and string-interpolation always coerces to str. The
source shape comes from `typed_env` (step outputs, via `_resolve_path`) or `var_env`
(set_variable, Phase 2); `_shape_to_src_tag` collapses it to int/float/bool/str/null/list/
dict (scalar `any`/unknown → skip). `tools_verify._param_type_fn` maps the param's widget +
observed_type to a target tag, mirroring the resolver's `_param_target_observed_type`.

**Evidence-honest scope (Open Q #2 still unprobed):** `_source_target_compatible` ships only
the two rules that need NO connector-param ingestion-coercion evidence:
1. **shape-into-scalar** (list/dict → any scalar target tag: int/float/bool/ipv4/url/email/
   iso8601/ipv6/epoch) → hard error; list↔json_array and dict↔json_object are the only
   accepted container pairings.
2. **numeric/bool category crossing** between two concrete scalars (bool→int, int→bool,
   int→ipv4, …) → error; int→float promotion allowed.
String/any/null sources are **always tolerated** (FSR's broad runtime string coercion + the
unprobed ingestion matrix), so no hard-error fires where the runtime might coerce. Net effect:
because most text-widget params carry `observed_type=None` (→ target tag None → skip), Phase 4
fires mainly on explicitly-typed widgets (integer/decimal/checkbox/json) and type-probed text
params (ipv4/url/…), which bounds false positives. **Audited all 24 `examples/*.yaml`: zero
new `type_mismatch` diagnostics.** `type_mismatch` added to the required-fix code list +
`_finalize` priority order. Tests: `fsr_core/tests/test_walker_param_types.py` (9 cases:
pure-ref unit, shape→tag, compat matrix, + 6 hand-built-IR integration incl. list→scalar hard
error and the no-`param_type_fn`/filtered-ref skip paths). `make verify` green (316 fsr_core +
159 connector); gold eval fraction unchanged (`test_run_matrix_gold_beats_echo` green).

**Deferred to a Phase 4b (when Open Q #2 is probed):** the full scalar→scalar tolerance matrix
(e.g. should a statically-`string` var into an `integer` widget error, given FSR runtime
`int("123")` coercion?) and list/dict → untyped-`text` param (no observed_type) — both need
the live connector-param ingestion echo probe to ship without false positives.

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
