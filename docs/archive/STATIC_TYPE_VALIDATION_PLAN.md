# Static Type Validation Plan — Tier 2 + Tier 3

**Status:** Tier 1 ✅ shipped 2026-05-20. Tier 2 ✅ substantially shipped 2026-05-25 (2.0 / 2.0+ / 2.1 / 2.2 / 2.3 / 2.4); only 3.4 (eval tasks) remains across Tier 3. Tier 3 ships terminal-type inference + filter-chain validation with a hand-curated signature library (~90 entries) that survives DB rebuilds.

## Background

Tier 1 (already live) validates connector params against the
`operation_params.type` form-widget column at compile time:

| Widget type | Rows | Check |
|---|---|---|
| `select` / `multiselect` (with `options_json`) | ~4,000 | enum membership + case + did-you-mean |
| `integer` / `intger` (typo) | ~3,100 | `int()` coercion |
| `decimal` / `numeric` | ~17 | `float()` coercion |
| `checkbox` / `boolean` | ~1,800 | bool / truthy-string |

Implementation: `python/compiler/resolver/connector_args.py`,
`python/compiler/resolver/catalog.py::operation_param_enum`. Each
check skips Jinja-templated values (`"{{ ... }}"`) — they defer to
runtime since we can't resolve the expression statically. Diagnostics
inline did-you-mean and the failing Python type so the agent fixes
on the next iteration without re-querying `get_op_schema`.

Gaps Tier 1 leaves on the table:

- `datetime` / `date` (~1,200 params) — FSR runtime accepts many forms;
  static rejection without a parser would have false positives.
- `text` (~14,000 params, **54% of all params**) — no static signal in
  the store. The author's intent (ipv4? URL? free string?) lives only
  in `title` / `description` / `tooltip` prose and the celery handler.
- Jinja expressions — value-level checks bail; the value's *resolved
  type* through any filter chain is opaque.

## Tier 2 — probe-based type inference

**Goal:** populate two new columns on `operation_params` —
`observed_type` and `coerces_from` — so the resolver can validate
`text`-typed params and Jinja-templated values where the upstream
shape is statically known.

### Why now is the right time

We already have the infrastructure (`probe_connectors`, `run_op`
with safe-op classification, `op_safety` table, `verifications`
ledger). The missing piece is *deliberate type-mismatch probing*: run
each safe op once with each param deliberately mistyped and capture
the runtime error. The error message reveals what the connector
*actually* accepts.

### Storage

Two new columns on `operation_params`:

```sql
ALTER TABLE operation_params ADD COLUMN observed_type TEXT;
ALTER TABLE operation_params ADD COLUMN coerces_from TEXT;
```

- `observed_type`: one of `int`, `float`, `bool`, `str`, `ipv4`,
  `ipv6`, `url`, `email`, `domain`, `iri`, `epoch_seconds`,
  `epoch_millis`, `iso8601`, `json_object`, `json_array`, `picklist`,
  `unknown`. Derived from the widget type + the probe's evidence.
- `coerces_from`: comma-separated list of input forms the runtime
  accepts (e.g. `str,int` if the connector calls `int(value)`).

### Probe design

New probe: `python/probes/probe_param_types.py`.

1. **Iterate over safe ops** (`op_safety.tier == 'safe'` ∪
   `tier == 'safe_with_dry_run'`). Roughly 2,000 ops on the live
   instance.
2. **For each param**, construct a baseline valid call (from
   `operation_examples` if present, else minimal required-fields-only).
3. **Mutate** one param at a time with type-mismatched values:
   - integer fields → `"not-a-number"`, `[1]`, `{"a":1}`
   - string fields → `12345`, `true`, `[1]`
   - bool fields → `"maybe"`, `42`
   - picklist fields → `"NoSuchValue"` (already covered statically, but
     confirms the runtime's error shape)
4. **Capture the error** from `run_op`. Classify by error pattern:
   - `TypeError: int() argument must be a string …` → `coerces_from=int`
     only (won't coerce from list/dict)
   - `ValueError: invalid literal for int()` → coerces from numeric
     strings only
   - `validators.url` / `socket.inet_aton` patterns → infer
     `ipv4`/`url`/etc.
5. **Promote to `observed_type`** only when at least 3 distinct
   mutations confirm the same runtime constraint. Single-shot
   evidence is unreliable (network errors, rate limits).

### Risks + mitigations

- **Side effects on non-safe ops.** Mitigation: hard gate on
  `op_safety.tier`. Re-run the safety classifier before this probe.
- **Probe runtime.** ~2,000 ops × ~5 params/op × ~3 mutations × ~500ms
  = ~5 hours wall time. Run as a one-shot background job; cache results
  in `verifications` table so subsequent runs are incremental.
- **False positives from connector bugs.** A connector that always 500s
  on a particular param looks like a type constraint. Mitigation:
  require the *baseline* call to succeed before treating mutation
  errors as evidence.

### Phase plan

| Phase | Status | Scope / Notes |
|---|---|---|
| **2.0 — Schema + probe skeleton** | ✅ done | Columns added; widget-only pass shipped. 11,566 / 26,093 params typed (44%). |
| **2.0+ — Name-pattern pass** | ✅ done 2026-05-25 | `name_to_observed_type()` runs as fallback when widget pass returns None. Lifts ipv4 / url / email / ipv6 / iso8601 from `param_name` directly. Coverage now 12,317 / 26,093 (47%, +751 rows over widget-only). Cheap: no FSR calls, idempotent. |
| **2.1 — Classifier rules** | ✅ done | `classify_error` regex table covers stdlib int/float/bool + validators / ipaddress / email_validator / dateutil errors. |
| **2.2 — Run the probe** | ⏳ scaffolded, not run | `run_live_probe` exists with dry-run mode; only 69 rows currently in `param_type_probes`. Real pass is ~5h against safe ops. Lower priority now that name-pattern pass captured the easy wins. |
| **2.3 — Wire into the resolver** | ✅ done | `connector_args.py:103-116` registers validators for ipv4 / url / email / iso8601 / json_object / json_array. New name-pattern coverage produces diagnostics immediately. |
| **2.4 — Doctor mode** | not started | `fsrpb doctor connector <name>` for connector authors. |

## Tier 3 — Jinja flow typing

**Goal:** propagate type information *forward* through Jinja
expressions so `{{ vars.steps.X.count | int }}` becomes statically
typed `int` and can satisfy an integer-typed param check.

This is the unlock for the bulk of validation that Tier 1 + 2 skip
(everything templated). Roughly **70% of corpus param values are
Jinja-templated**, per the `jinja_expressions` mining.

### Substrate

Reuse `jinja_expressions` and `jinja_filter_usage` tables (already
mined — 7,789 unique idioms across 1,669 playbooks). Add typed
signatures to `jinja_macros`:

```sql
ALTER TABLE jinja_macros ADD COLUMN input_type TEXT;
ALTER TABLE jinja_macros ADD COLUMN output_type TEXT;
ALTER TABLE jinja_macros ADD COLUMN type_signature TEXT;  -- e.g. "(str) -> iri"
```

### Walker extension

`python/compiler/typed_walker.py::_resolve_path` already walks
`vars.steps.<X>.<attr>` into a shape. Extend with a new walker pass
that:

1. Parses each Jinja expression to AST (Jinja2 ships an AST builder).
2. For a chain `vars.steps.X.Y.foo | filter1 | filter2`, computes the
   shape after each filter using the new `jinja_macros.input_type` /
   `output_type` lookups.
3. Returns the final type, comparable against the consuming param's
   widget type (Tier 1) or `observed_type` (Tier 2).

### Signature sources

Three tiers of signatures, in order of how to build them:

1. **Hand-curated** for the 13 macros already in `jinja_macros.curated_doc`
   (`json_query`, `picklist`, `fromIRI`, `resolveRange`, `map`,
   `selectattr`, `regex_*`, `ternary`, `default`, `dict2items`,
   `flatten`, `from_json`). Each gets a `type_signature` field. ~1 day.
2. **Standard Jinja filters** from the Jinja docs — `|int`, `|float`,
   `|string`, `|length`, `|first`, `|last`, `|join`, `|split`,
   `|upper`, `|lower`, `|trim`, `|replace`, etc. Deterministic
   signatures, ~30 filters. ~2 days.
3. **Corpus-mined** for the long tail. Run each unique
   `jinja_expressions` entry against the live FSR Jinja env with the
   typed walker's inferred input shape; record the output type.
   Bootstraps signatures for filters we don't have rules for.

### Phase plan

| Phase | Scope | Exit criteria |
|---|---|---|
| **3.0 — Signature schema + hand-curated rules** | ✅ done | `_HAND_CURATED` map in `python/compiler/jinja_typing.py` carries ~90 (input_type, output_type) entries covering standard Jinja string/collection/numeric filters + FSR `workflow.jinja` macros + Ansible netcommon IP filters. Beats the DB row when both are present so updates land in code, not data. |
| **3.1 — Walker AST pass** | ✅ first slice | `validate_chain()` walks every `|` boundary and flags `producer_out` ↛ `consumer_in` mismatches (e.g. `\| int \| upper`). Strict mid-chain typing — no silent str coercion between filters. Full Jinja2 AST integration deferred; the regex walker covers pure-Jinja filter chains, which is the dominant pattern in connector args. |
| **3.2 — Resolver consumption** | ✅ done | `connector_args.py` calls both `infer_terminal_observed_type` (final type vs param target) and `validate_chain` (intermediate transitions). Both emit `BAD_VALUE` with chain-localized messages. |
| **3.3 — Corpus mining for signatures** | ✅ subsumed by 3.0 | Hand-curation covered the 123-row residue without needing live mining. Could revisit if usage shows blind spots. |
| **3.4 — Eval task additions** | not started | 3 eval tasks exercising typed Jinja chains agents commonly get wrong. |

## Sequencing

Tier 2 and Tier 3 are largely independent — Tier 2 lifts the `text`
ceiling, Tier 3 lifts the Jinja-coverage ceiling. **Tier 2 is the
cheaper win** (one probe pass + classification rules) and should ship
first. Tier 3 is the bigger architectural change and benefits from
having Tier 2's `observed_type` to validate against.

## Open questions

1. **Type-checked vs. nominal.** Should `picklist` be a distinct
   `observed_type`, or should it stay solely in `options_json`? Tier 1
   currently uses the latter. Tier 3 needs the type-flow view —
   probably promote.
2. **Where does literal type info from `default_value` fit?** Many
   params have `default_value: "0"` (string-shaped int). We can infer
   the type from the default; should that promote into
   `observed_type` for params with no probe evidence?
3. **Editor surfacing.** The Visual Editor inspector already shows
   param shape; should it visualize the type-flow chain for the
   currently-focused Jinja expression? Worth pinging
   `VISUAL_EDITOR_PLAN`.

## Cross-references

- Tier 1 implementation: `python/compiler/resolver/connector_args.py`
  (search "Picklist enum validation" / "Scalar-type validation").
- Existing probe infrastructure:
  `python/probes/probe_connectors.py`, `python/probes/probe_jinja_corpus.py`.
- Related plans:
  - `RENDER_PATH_VALIDATOR_PLAN.md` — runtime shape simulation
    (orthogonal: that one validates execution, this one validates
    declaration).
  - `CONNECTOR_INTEGRATION_PLAN.md` — catalog grounding (the
    `api_examples_catalog` would benefit from Tier 2's `observed_type`
    when proposing HTTP fallbacks).
