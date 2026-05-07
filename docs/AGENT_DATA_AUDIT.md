# Agent data audit (Phase 2)

Audit of the top-5 tools from `docs/AGENT_TOOL_USAGE.md`. Each section
covers SQL completeness (2A), tool-contract crispness (2B), and
source-of-truth alignment (2C). Quick-win fixes (<30 min) are inlined.

Reference store last refreshed:

| probe | latest |
|---|---|
| `probe_playbook_steps` | 2026-05-06 |
| `probe_jinja_corpus` | 2026-05-03 |
| `probe_filter_usage` | 2026-05-03 |
| `probe_connectors` | 2026-05-03 |
| `probe_modules` | 2026-05-02 |
| `probe_api_endpoints` | 2026-05-02 |

---

## 1. `validate_yaml` — 25 calls (top by volume)

**SQL coverage.** No DB read. Runs the in-process compiler pipeline
(parse → resolve → validate) over `store/fsr_reference.db` via
`compiler.compile_yaml`. Rows touched are whatever the compiler hits
(connectors / operations / operation_params / step_types / picklists).

**Contract.**
- Median result 408 chars, p95 3,561 — well-budgeted.
- Error envelope: ✓ uses `_err(...)` with `code`, `message`, `errors`,
  `next_fix`. The `next_fix` field is the right pattern — every other
  search-class tool should mimic it.
- Schema reflection: ✓ single required `yaml_text` arg. Nothing to fix.

**Source-of-truth.** Compiler is exact; no staleness risk.

**Verdict.** No changes. Use this tool's contract as the template for
the others.

---

## 2. `find_operation` — 15 calls

**SQL coverage.** Reads `operations` (6,773 rows). All filters (`title`,
`description`, `op_name`) are populated:

| column | total | null/empty | % |
|---|---:|---:|---:|
| description | 6,773 | 5 | 0.07% |
| title | 6,773 | 0 | 0% |
| `output_schema_json` | 6,773 | 174 | 2.6% |

5 ops with no description and 174 with no `output_schema_json` (all
in connectors that ship sparse `info.json`, e.g. anomali-enterprise,
threatstream). Not a search-side problem — `find_operation` only
reads name/title/description.

**Contract.**
- Median 968 chars, p95 8,096 — p95 is fat. The verbose=False path
  already drops description, so the bloat is from listing many ops on
  one connector at the default `limit=20`. Action: lower default to
  `limit=10` (the agent's actual top use is "find op X on connector Y",
  not "list everything"); the corpus has zero calls that needed >10
  results.
- Error envelope: returns `{matches, suggestion?, near?}` even on miss.
  Good — tells the agent "did you mean Z" without forcing it to
  re-search. Keep.
- Schema reflection: ✓ all args have type hints.

**Source-of-truth.** `operations` last refreshed 2026-05-03; FSR
operation catalog is stable enough that 4-day staleness is fine.

**Quick fix (≤5 min).** Lower default `limit` from 20 to 10 in
`mcp_server.find_operation`.

---

## 3. `get_step_type` — 12 calls

**SQL coverage.** Reads `step_types` (43 rows, 0 NULL `args_schema_json`)
and `step_examples` (66 rows, 3 per major type).

**Contract.**
- Median 1,844 chars, p95 4,938 — appropriate after the slim/verbose
  split landed.
- ✓ Has `friendly_form` block for major types — the right level of
  detail for authoring.
- Error envelope: ✗ returns `{"error": "step type 'X' not found"}`.
  Should mirror `validate_yaml`: `{ok: false, code: "not_found",
  message, suggestion, near}`. The agent has no structured way to
  branch on "step type missing" today. **Quick fix below.**
- Schema reflection: ✓.

**Source-of-truth.** Step types come from disk-only sources (no live
FSR probe needed for the canonical 21 types).

**Quick fix (≤15 min).** Replace the bare `{"error": ...}` with the
shared `_err()` envelope, and run `difflib.get_close_matches` against
known step-type names + `_SHORT_TO_CANONICAL` keys for a `near=` hint.

```python
# in mcp_server.get_step_type, replace:
#     if not rows:
#         return {"error": f"step type '{name}' not found"}
# with:
if not rows:
    known = list(_SHORT_TO_CANONICAL.keys()) + [
        r["name"] for r in _rows(conn, "SELECT name FROM step_types", ())
    ]
    near = difflib.get_close_matches(name, known, n=3, cutoff=0.4)
    return _err(
        "not_found",
        f"step type {name!r} not found",
        suggestion=f"did you mean one of {near}?" if near else
                   "use the canonical FSR name (ManualInput, Decision, ...)",
        near=near,
    )
```

---

## 4. `find_connector` — 9 calls

**SQL coverage.** Reads `connectors` (714 rows).

| column | total | null/empty |
|---|---:|---:|
| label | 714 | 1 |
| category | 714 | 6 |
| description | 714 | 1 |

The 1 connector with a NULL description (`aiassistant-utils`) is also
absent from the recent probe — likely a stub. Acceptable.

**Contract.**
- Median 311, p95 4,498 — fine. p95 is from a substring match returning
  many rows; default `limit=15` is reasonable.
- Error envelope: ✓ returns `{matches, suggestion, near}` with a
  difflib fallback. Already follows the find_operation pattern.
- Schema reflection: ✓.

**Source-of-truth.** Last refreshed 2026-05-03.

**Verdict.** No changes.

---

## 5. `get_op_schema` — 8 calls (the heaviest payload)

**SQL coverage.** Reads `operations` + `operation_params` (26,093 rows).

| operation_params column | total | null/empty | % |
|---|---:|---:|---:|
| type | 26,093 | 0 | 0% |
| required | 26,093 | 0 | 0% |
| description | 26,093 | 1,834 | 7.0% |
| options_json (has) | 26,093 | 4,141 | 15.9% |

**Contract — biggest issues.**
- Median **5,406 chars**, p95 **8,859** — by far the fattest tool the
  agent calls. Returns the entire `operations` row PLUS every param
  PLUS three big JSON blobs (`output_schema_json`,
  `conditional_output_schema_json`, `output_schema_observed`).
- No `verbose` switch. Slim mode would cut this to ~1.5 KB by default.
- `output_schema_observed` is **NULL on all 6,773 ops** — the column
  is plumbed through but no `run_op` has ever populated it. The
  `output_schema_hint` text is shown for any op without
  `output_schema_json` (174 ops) but the agent has no way to actually
  trigger the run_op call (it's not in `SAFE_TOOLS`).
- Error envelope: ✗ returns `{"error": "..."}`. Same fix as
  `get_step_type`. Worse, when the connector itself is unknown the
  message just says "operation 'X' not found on connector 'Y'" —
  doesn't surface "did you spell the connector right?" Ties directly
  to the **22% Phase-1C violation** of the
  "find_connector before get_op_schema" rule: the tool is silent about
  the real cause.
- Schema reflection: ✓.

**Source-of-truth.** As above; static catalog is fine. The
`output_schema_observed` gap is dynamic and only fillable by running
ops live.

**Quick fixes (~25 min total).**

1. Add a `verbose: bool = False` arg. Slim default returns:
   `{op_name, title, description, params: [name,type,required,options],
   output_schema_summary, output_schema_hint?}`. Verbose returns the
   full blobs.
2. When the connector is unknown, return:
   ```python
   _err("connector_not_found",
        f"connector {connector!r} has no operations in store",
        suggestion="call find_connector first to confirm the name",
        near=difflib.get_close_matches(connector, all_connector_names, n=3))
   ```
   Same pattern when only the op is unknown but the connector is real
   (use `find_operation`'s near-match logic).
3. Open ticket: schedule a one-shot `run_op` sweep (sandboxed) over
   the most-referenced ops to populate `output_schema_observed`. Out
   of scope for this audit, but the lever is now visible.

---

## Cross-cutting findings

**A. Error-envelope inconsistency.** Two patterns exist:

| Pattern | Used by |
|---|---|
| `_err(code, message, ...)` with `ok: false` | `validate_yaml` |
| Bare `{"error": "..."}` | `get_op_schema`, `get_step_type` |
| Soft return `{matches, suggestion, near}` | `find_connector`, `find_operation` |

Recommendation: **all not-found cases use `_err()`** so the agent can
branch on `code`. The match-returning tools can keep their soft
envelope (they're queries, not lookups by primary key) but should add
`code: "no_results"` inside the `suggestion` block for consistency.

**B. The "find_connector before get_op_schema" prompt rule is
mechanically enforceable.** Phase 1C found 22% of sessions skip it.
If `get_op_schema` returns `code: "connector_not_found"` with a
`near=` hint, the LLM has structured feedback to correct itself
without re-reading the prompt. This is the single highest-ROI Phase 2
fix.

**C. Result-payload caps.** Add a soft 8 KB cap to `get_op_schema`
verbose mode and a 4 KB cap to slim mode. Anything bigger gets
truncated with a `truncated: true` flag and a hint to narrow the
query — same pattern `get_step_type` already uses for examples.

---

## Status (2026-05-07)

Quick-wins #1, #2, #3, #4 below all landed in `python/mcp_server.py`:

- `get_step_type` now uses `_err()` with `near=` close-matches.
- `get_op_schema` now uses `_err()` and distinguishes
  `connector_not_found` from op-level `not_found`, with `near=` hints.
- `get_op_schema` gained `verbose: bool = False`. Slim mode collapses
  `output_schema_json` / `conditional_output_schema_json` /
  `output_schema_observed` to `*_keys` summaries and trims params to
  `name/type/required/options/description`. Smoke test on
  `virustotal/analysis_file`: 1,250 chars slim vs 3,280 verbose
  (previous median was 5,406).
- `find_operation` default `limit` lowered 20 → 10.

All 216 unit tests still pass.

## Suggested order of attack

1. **(15 min)** `get_step_type` error envelope → mirrors validate_yaml,
   no behavior change for happy path.
2. **(20 min)** `get_op_schema` error envelope + connector-not-found
   branch → directly addresses the 22% Phase-1C violation.
3. **(15 min)** `get_op_schema` `verbose=False` slim mode → halves
   the median payload of the most expensive tool.
4. **(5 min)** `find_operation` default limit 20 → 10.
5. *(deferred)* `output_schema_observed` backfill — needs a run_op
   sweep, scope it separately.

After 1–4 land, re-run `fsrpb agent-stats` and confirm:
- `get_op_schema` median p95 < 5 KB.
- "find_connector before get_op_schema" pass rate > 90%.
- Total tool-call output tokens per session drop measurably.
