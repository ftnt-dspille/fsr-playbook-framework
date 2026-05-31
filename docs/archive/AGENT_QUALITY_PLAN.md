# Agent loop quality plan

**Why this exists.** Before we tune the prompt or rewrite tools, we need
ground truth: *what is the agent actually looking up, does the data
store back those lookups completely, and are the prompt instructions
producing the right behaviors?* This plan is the roadmap. It is
ordered: do **Phase 1** first (otherwise we're optimizing blind),
**Phase 2** second (so we know what data is missing before tweaking
prompts), **Phase 3** last (so prompt changes get an A/B baseline).

Every phase ends in a concrete artifact you can read and act on.

---

## Phase 1 — Discover what the agent looks up

> Build the evidence base. No code changes to tools yet — only readers.

**Status (2026-05-07):** Phase 1A/1B/1C landed as `fsrpb agent-stats`
(`python/agent_stats.py`). Re-run any time to regenerate the three
artifacts under `docs/`. First run on 9 sessions / 74 tool calls
surfaced two real adherence violations:

- 22% of sessions called `get_op_schema` without a prior
  `find_connector` (rule 1).
- 44% referenced `vars.steps.X.Y` without a prior `find_step_examples`
  / `get_op_schema` lookup (rule 2).

Caveat: only 8/74 tool calls have full `tool_use` content rows in
`chat_messages`, so the args-shape histogram and the validate-spiral
detector are sparse until more sessions accumulate (or until the
backend starts persisting full args/results for every call).

### 1A. Tool-call census from `history.db`

Add `fsrpb chat-stats --tool-detail` (or extend the existing
`chat-stats`) to emit, across **every** session in `web/backend/history.db`:

- Per-tool **call count** (descending).
- Per-tool **call args histogram** — for top tools, group on the most
  common argument shape (e.g. `find_connector(name="virustotal")`
  vs `find_connector(name="<jinja>")`).
- Per-tool **median + p95 result-payload size** (chars and est tokens).
- Per-tool **immediate-follow-up rate** — when tool X is called,
  what tool fires within the next 2 LLM rounds? Reveals "agent
  always calls Y after X" coupling, which often means tool X is
  missing data Y has.
- Per-tool **error rate** — share of `tool_result` payloads that look
  like error envelopes (`{ok: false}`, `error:`, `code: ...`).
- Per-tool **session-success correlation** — split tool usage by
  sessions that ended with a thumbs-up vs thumbs-down vs no rating.
  Tools that show up disproportionately in thumbs-down sessions are
  the suspects.

**Source data:** `chat_messages` (kind `tool_use`, `tool_result`),
`chat_turns` (token totals), `chat_feedback` (rating + summary).

**Artifact:** `docs/AGENT_TOOL_USAGE.md` — auto-generated table sorted
by call count, with the metrics above per tool. Re-run any time.

### 1B. "Missing data" signal extraction

Inside the same scan, surface lookup patterns that strongly imply the
data store has gaps:

- **Repeated identical calls** in one session — e.g. the agent calls
  `find_connector("foo")` three times because the first two returned
  empty. Indicates either a broken query or missing data.
- **Search → "did you mean" → search again** sequences — the agent
  ran a fuzzy match, got a suggestion, and re-queried. The
  suggestion path is where authoritative data should live but
  doesn't yet for whatever it asked.
- **Tool result is empty / minimal** — `result_chars` < 50 on a
  search-class tool means probably "nothing found." Aggregate by
  the search needle so you can see *what topics the agent looks
  for and gets nothing*.
- **LLM follow-up that quotes the tool result back at the user as a
  question** — a heuristic regex on assistant text after a tool
  result: presence of "I couldn't find" / "no results for" /
  "doesn't appear to be" indicates data gap.

**Artifact:** `docs/AGENT_DATA_GAPS.md` — ranked list of (search needle,
tool name, miss count, first-seen-session). This is the input list
for Phase 2's data audit.

### 1C. Prompt-instruction adherence sniff

The system prompt at `python/agent/system_prompt.md` lays out rules
("call `find_connector` first," "use `get_op_schema` before referencing
fields," "never paste full payloads back at the user," etc.). For each
rule that has a structural signature, write a one-shot detector that
scores adherence across history:

| Rule | Detector |
|---|---|
| Call `find_connector` before `get_op_schema` | sequence check on tool order |
| Don't reference `vars.steps.X.Y` without prior `find_step_examples` or `get_op_schema` | regex on assistant YAML cross-checked against the same session's tool calls |
| Wrap YAML in ` ```yaml ` fenced block, not generic ` ``` ` | already exists in `chat_review` — generalize |
| When validate fails, fix only the highest-priority error first | compare error-count delta across consecutive validate calls in same session |
| Don't issue more than 8 tool calls without text to user | count tool-use streaks |

**Artifact:** `docs/AGENT_PROMPT_ADHERENCE.md` — per-rule pass-rate +
sample violating session ids. The violations point at where the
prompt isn't sticking.

---

## Phase 2 — Audit data coverage for the top lookups

**Status (2026-05-07):** audit at `docs/AGENT_DATA_AUDIT.md`. Top-5
tools assessed; quick-wins #1–#4 landed in `python/mcp_server.py`
(error envelopes for `get_step_type` + `get_op_schema`,
slim `verbose=False` mode for `get_op_schema`, lower default limit
on `find_operation`). Deferred: `output_schema_observed` backfill via
a sandboxed `run_op` sweep.


> Phase 1 told us what the agent reaches for. Now make sure those
> reaches actually find a good answer.

For each of the **top 10 tools by call count from Phase 1A**, plus
every entry on the gap list from Phase 1B, do this audit:

### 2A. SQL completeness check
- What table(s) does the tool query? (Trace from
  `web/backend/llm/tools.py` → MCP server handlers in `mcp_server.py`
  → `inventory.py` / direct sqlite.)
- For each backing table:
  - Row count today.
  - Last refreshed ts (per `_probe_runs` table).
  - Schema diff vs the contract the tool advertises (every field the
    tool returns must be NOT NULL or backfilled — flag NULL-heavy
    columns the LLM is reading).
- For each gap-list needle from 1B:
  - Run the same query the tool runs. Document why it returned
    empty: missing row, wrong index, alias issue, FTS not indexed,
    case sensitivity.

### 2B. Tool contract crispness
- **Return-payload audit**: does the tool ship more than the LLM
  needs? (Phase 1A's median result size feeds this — anything > 5k
  chars is a candidate for `verbose: false` defaults, mirroring
  `get_step_type`.)
- **Error envelope audit**: does the tool emit `{ok: false, code,
  message, suggestion}` when it can't answer, or just empty? The
  former lets the prompt say "if `code: not_found`, ask me which
  connector"; the latter forces the LLM to guess at the situation.
- **Schema reflection**: is the tool's argument schema (Anthropic
  `input_schema` / OpenAI `parameters`) complete enough that the
  LLM doesn't have to guess argument names? Compare every required
  arg to "did the agent ever pass an unknown arg" in Phase 1A.

### 2C. Source-of-truth alignment
For tools that return live FSR state (connectors installed, picklists,
etc.), verify the cached store reflects what the live FSR currently
exposes. The probes already do this; report the staleness window per
tool.

**Artifact:** `docs/AGENT_DATA_AUDIT.md` — one section per audited tool
with: table coverage table, top empty-result needles + diagnosis, list
of contract issues with suggested fixes. Where a fix is < 30 min,
include the diff inline so it can be applied immediately.

---

## Phase 3 — Eval harness for measurable improvements

**Status (2026-05-07): Phase 3A + 3B (partial) + 3C landed.**
- 3A: corpus expanded from 3 → 15 tasks under `python/evals/tasks/`
  (gold pointers map to existing `examples/*.yaml`; one negative
  task `unknown_connector` has no gold for graceful-failure testing).
- 3B: added L1.5 strict-whitelist gate in `python/evals/scoring.py`
  (fails if compiler emits any UNKNOWN_PARAM / corpus-drift
  warnings). Tool-budget + no-error-spiral assertions deferred —
  they need an agentic eval loop the providers don't yet have.
- 3C: `python/evals/harness.py` gained `save_run`, `load_run`,
  `list_runs`, `delta_vs`, `render_delta`. `fsrpb evals` CLI now
  takes `--save`, `--baseline <run_id>`, `--list-runs`. Archives
  matrix.json + report.md under `store/eval_runs/<run_id>/`.

First baseline run on the gold provider scored **49/58 (84%)** —
L1.5 surfaced 7/15 fixtures with compiler warnings, useful follow-up.


> Now that we know what to fix, build the rig that tells us our
> fixes actually helped.

The codebase already has `python/evals/`: `tasks/` (3 starter tasks),
`scoring.py` (L1/L2/L3/L4/gold gates), `harness.py` (matrix runner),
`providers.py` (deterministic + LLM providers). Build on top of it.

### 3A. Expand the task corpus to 15–20 fixed tasks
Cover the failure modes Phase 1 surfaced. Suggested coverage:
- Pure authoring (3): hello world / decision branch / record action
- Connector lookup (3): well-known (virustotal), niche (recorded
  future), nonexistent (typo'd name → expect graceful failure)
- Picklist lookup (2): valid (Severity → Critical), invalid (made-up)
- Step-shape lookup (2): manual_input formType permutations,
  decision conditions
- Recipe generation (2): threat-feed ingestion, alert ingestion
- Diagnostics (2): broken YAML → expected next_fix, var-reachability
  failure
- End-to-end push+run (1, live-mode only): canary

Each task is a JSON file under `python/evals/tasks/` with `prompt`,
`gold_yaml_path`, optional `notes`. Same shape that exists today.

### 3B. Add ladder + tool-call assertions to scoring
`scoring.py` already has L1/L2/L3/L4/gold. Add:
- **L1.5 — strict-whitelist**: compile produced no UNKNOWN_PARAM warnings.
- **Tool-budget**: total tool calls ≤ a threshold per task (catches
  "agent spirals 12 validates"). The Phase-1 census tells us
  reasonable thresholds.
- **No-error-spiral**: validate count never increases in two
  consecutive turns without an error count drop (≥1).
- **Adherence**: the Phase 1C detectors run against this session.

### 3C. CLI runner + comparable reports
`fsrpb evals run --model <m> --baseline <prior_run_id>` → runs every
task against `<m>` (or all configured models), saves a structured
report under `store/eval_runs/<run_id>/`, and prints a delta table vs
the baseline (rows red where regression, green where improvement).

Output should be both human-readable and machine-readable so changes
can be wired into CI later.

**Artifact:** `docs/AGENT_EVAL_REPORT_<run_id>.md` per run, plus a
rolling `docs/AGENT_EVAL_TIMELINE.md` showing the trend.

---

## Order of work for a fresh session

If you're picking this up on `/clear`, work it in this order:

1. **Phase 1A** (tool-call census) — pure read; biggest ROI; produces
   the data Phase 2 needs.
2. **Phase 1B** (data-gap signals) — same pass; almost free.
3. **Phase 1C** (prompt adherence) — same pass; reuses
   `chat_review` detectors.
4. **Read** the three Phase-1 artifacts. Decide if there are obvious
   data fixes worth doing before any prompt work — usually yes.
5. **Phase 2A/B/C** for the top 10 tools.
6. **Phase 3A** corpus expansion.
7. **Phase 3B/C** scoring extensions + CLI runner.
8. Re-run Phase 1A as a sanity check — call counts should have
   shifted toward the tools you cleaned up.

## Reference: existing pieces to reuse

| Need | Existing |
|---|---|
| Iterate sessions in history.db | `chat_review.load_session(id)` |
| Token + tool-cost stats | `fsrpb chat-stats` |
| Pattern detectors over a session | `python/chat_review.py` |
| Ladder evaluation per turn | `web/backend/llm/ladder.py` |
| Gold-fixture scoring | `python/evals/scoring.py` + `harness.py` |
| Live LLM + deterministic providers | `python/evals/providers.py` |
| MCP tool catalog | `python/mcp_server.py`, `web/backend/llm/tools.py` |
| System prompt | `python/agent/system_prompt.md` |
| Auto-doc CLI reference | `scripts/dump_cli_docs.py` → `docs/CLI.md` |

## What this plan does NOT do (deliberately)

- **No prompt rewrites yet.** Phase 1C might reveal that the prompt
  rules are fine and the data is the problem, or vice versa. Wait
  for the data.
- **No new tools yet.** Phase 2 might show existing tools just need
  better data, not replacement.
- **No model swaps.** The harness in Phase 3 makes that decision
  empirical instead of a hunch.
