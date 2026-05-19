# Agent loop refinement plan

**Started**: 2026-05-18. Owner: dcspille.

Three orthogonal refinements to the existing agent loop. The loop's
architecture (YAML IR, compiler-owns-resolution, verify_playbook
forcing-function) is correct and stays. What changes is **where**
information lives and **how** the LLM is constrained.

The driver: `fsrpb agent-stats` shows real adherence violations
(22% skip `find_connector` before `get_op_schema`; 44% reference
`vars.steps.X.Y` without any prior lookup). The model isn't ignoring
the prompt — lookups are expensive enough that it gambles. Each
refinement below removes one class of gamble.

---

## Refinement A — Static reference data into the prompt cache

**Why this exists.** Today the LLM round-trips through MCP for facts
that never change: the 14 canonical step types, decision-step shape,
manual_input mode rules, Norway problem, `vars.steps.<slug>.*`
addressing rule, the canonical Jinja filter list, the friendly-form
catalog for the high-volume step types. Per `AGENT_TOOL_USAGE.md`,
`get_step_type` is the 3rd most-called tool (12 calls / median 1.8 KB
result / 1234 p95 tokens). Those tokens recur every session.

Prompt caching makes static content effectively free after the first
miss. The agent stops paying for the lookup, and the response is
deterministic — no MCP-server flakiness, no truncation, no version
skew.

**Keep-criteria for what moves to the prompt vs stays in MCP**:

| Stays in MCP | Moves to prompt cache |
|---|---|
| Connector inventory (tenant-specific, refreshes) | The 14 step types + their canonical YAML shape |
| Picklist values (tenant-specific) | Decision step grammar + Norway/charset rules |
| Module fields (tenant-specific) | `manual_input` formType taxonomy + co-presence rules |
| Live FSR run results | Friendly-form catalog (`get_step_type(name)/friendly_form` for the 7 high-volume types) |
| Recent failed runs | The full FSR Jinja filter list (170 filters) |
| Search across user's playbook corpus | The "must-call verify before submit" gate rules |
| `verify_playbook` itself | Hard rules already in `system_prompt.md` |

The rule of thumb: **if a fact's value would be byte-identical across
every tenant on every appliance, it goes in the prompt.** Tenant-shape
or live-state stays in MCP.

### Phasing

| Phase | Status | Notes |
|---|---|---|
| A1 — Generator script | ✅ done | `scripts/build_static_prompt.py` reads `_FRIENDLY_FORMS` + `fsr_reference.db`; emits `python/agent/static_grammar_block.md` (14.9 KB). Idempotent. |
| A2 — Wire into providers | ✅ done | `python/agent/__init__.py:load_system_prompt()` prepends the static block. The Anthropic provider already wraps the whole system string in a single cached block, so the static prefix is cached automatically. LM Studio gets the same string (unchached) for parity. |
| A3 — Trim MCP outputs | 🟡 partial | `system_prompt.md` now references the static block as authoritative for shapes and tells the agent NOT to call `get_step_type` / `find_jinja_filter` to re-derive that content. Slimming `get_step_type`'s default response is deferred until A4 confirms call-count drop in real sessions. |
| A4 — Re-run agent-stats | ⏳ not started | Confirm `get_step_type` call count drops, total prompt+tool tokens drops. Needs ≥5 fresh chat sessions to measure. |

### A1 — Generator

`scripts/build_static_prompt.py` reads `store/fsr_reference.db` and
emits a `python/agent/static_grammar_block.md`. Content:

- **Step-type catalogue** — for each of the 14 canonical types, the
  friendly-form YAML skeleton + 2 lines of guidance. Already encoded
  in `web/backend/step_args_help.py` and `step_examples.py`.
- **The full FSR Jinja filter list** — name + one-line description.
  Sourced from `store/fsr_reference.db` (`jinja_filters` table) and
  capped at one line per filter. ~170 entries × ~80 chars =
  ~14 KB, comfortably fits a single cache block.
- **The `vars.steps.<slug>.*` and `vars.input.params.<k>` rules**
  with worked examples for each step type.
- **The Norway problem + step-name charset rule** with rejected vs
  accepted examples.
- **Decision + manual_input mode tables** copied from
  `MI_DECISION_VALIDATION_AUDIT.md` §0.

The block is generated, not hand-written — it lives in `docs/`
alongside the other auto-generated artifacts. Re-run any time the
underlying corpus refreshes.

**Size budget**: 30–40 KB. Single cache block at the top of the
system prompt. Anthropic's cache TTL is 5 min by default; for a chat
session that completes within that window, it's free after turn 1.

### A2 — Provider wire-up

The Anthropic and LM Studio providers already build the system prompt
from `python/agent/system_prompt.md`. Extend:

```python
system_blocks = [
    {"type": "text", "text": _static_grammar_block(),
     "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": _live_prompt()},
]
```

LM Studio's OpenAI-compat doesn't honor `cache_control`; for it, the
block is still sent but unchached. Acceptable cost for parity.

### A3 — Trim MCP outputs

Once the friendly-form block is in the prompt, `get_step_type(name)`
becomes lookup-of-last-resort for verbose schema. Change its default
to "not in prompt? then return the full schema" — and the system
prompt note says "the canonical shapes are above; only call
get_step_type when you need the full corpus dump or annotation."

### A4 — Re-run agent-stats

Compare per-tool call counts pre vs post. Expected effects:

- `get_step_type` calls drop ≥60%.
- `find_jinja_filter` / `find_jinja_pattern` calls drop near-zero
  (filter list now visible).
- Total prompt+tool tokens per session drops 15–30% even after the
  added prompt block, because the recurring MCP round-trips fall off.

If the numbers don't move, the block isn't sticking — revisit
positioning or content.

**Estimated effort**: 2 days (mostly the generator script; provider
wiring is small).

---

## Refinement B — Constrained generation for hot shapes

**Why this exists.** Today the LLM emits YAML, the validator parses
it, and a fix loop catches shape errors. The cheapest class of shape
error — wrong key name, missing required key, malformed decision
branch — happens turn after turn. The validate→fix loop spends ~30%
of its calls on errors that constrained generation would make
literally impossible.

The lever: Anthropic tool-use schemas (`input_schema`) are enforced
on the wire — the model **cannot** emit a tool call with a missing
required field or a wrong-type value. We can recast the high-volume
authoring step types as tool calls with strict schemas, then convert
the tool-call payload into YAML inside the dispatcher.

**Scope** — the "hot shapes," ranked by `AGENT_TOOL_USAGE.md`
follow-up coupling (`validate_yaml → validate_yaml × 23` is the
validate-spiral signature):

1. **`decision` step body** — every entry has `display, when, next`;
   exactly one entry has `default: true` (no `when`). Encoded as a
   tool with `conditions: Conditional[]` + `default_branch: Branch`.
2. **`manual_input` step options** — first option primary unless
   another marked; each option has `display, next`. Strict array
   schema rejects the malformed cases.
3. **`connector` step `arguments.params`** — per-op shape. Schema is
   already in the store (`operations.parameters_json`). For each
   op, generate a JSON schema at tool-prep time. The LLM literally
   cannot pass an unknown param key.
4. **`set_variable` step `vars:` block** — flat string-to-string
   mapping; the LLM keeps nesting it.
5. **`find_record` / `update_record` filter trees** — already have
   a typed schema (`python/compiler/resolver/filters.py`); expose it
   as a tool's input_schema.

### Architecture

Two paths coexist:

- **Free-author path** (today): LLM writes a YAML block, validator
  parses, fix loop catches errors. Stays for edge cases — niche step
  types, multi-step refactors, novel patterns not in the hot-shape
  catalog.
- **Constrained-author path** (new): for each hot shape, a tool
  named `emit_<step_type>_step(...)` that takes strict structured
  args and returns the rendered YAML fragment. The agent calls the
  tool, gets back valid YAML, splices it into the editor buffer.

The system prompt sells the constrained path as the **preferred**
mode: "prefer `emit_decision_step` over hand-writing decision YAML —
it cannot produce invalid shapes." Free-author is the fallback.

### Phasing

| Phase | Status | Notes |
|---|---|---|
| B1 — `emit_decision_step` | ✅ done | `python/mcp_server/tools_emit.py`. Strict input schema (nested `additionalProperties:false`, `minItems:1`, name regex) wired via new `TOOL_SCHEMA_OVERRIDES` map in `web/backend/llm/tools.py` — Anthropic enforces on the wire. Hand-rolled YAML render matches canonical shape; runtime check covers non-LLM callers. System prompt §3 nudges the model to prefer the tool over hand-writing. Tier 0 / auto-confirm. |
| B2 — `emit_manual_input_step` | ⏳ not started | Mode-aware: schema depends on `mode` discriminator (Context/Behavior/InputType). |
| B3 — `emit_connector_step` | ⏳ not started | Per-op schemas generated from `operations.parameters_json`; cached. |
| B4 — `emit_set_variable_step` | ⏳ not started | Trivial schema; catches a recurring nesting bug. |
| B5 — `emit_find_record_step` | ⏳ not started | Reuses the filter-tree schema already in resolver. |
| B6 — Adherence measurement | ⏳ not started | Re-run agent-stats; expect validate-loop spirals to drop. |

### B1 — `emit_decision_step` (pattern for the rest)

Tool definition (Anthropic shape):

```python
{
  "name": "emit_decision_step",
  "description": "Emit a `decision` step. The shape is enforced — invalid combinations are rejected before the LLM sees the result.",
  "input_schema": {
    "type": "object",
    "required": ["name", "conditions", "default_branch"],
    "properties": {
      "name": {"type": "string",
               "pattern": "^[A-Za-z0-9 _]+$",
               "description": "Step name. Title Case, no special chars."},
      "conditions": {
        "type": "array",
        "minItems": 1,
        "items": {
          "type": "object",
          "required": ["display", "when", "next"],
          "additionalProperties": false,
          "properties": {
            "display": {"type": "string"},
            "when": {"type": "string", "description": "Jinja expression returning truthy/falsy"},
            "next": {"type": "string", "description": "Target step name"},
          }
        }
      },
      "default_branch": {
        "type": "object",
        "required": ["display", "next"],
        "additionalProperties": false,
        "properties": {
          "display": {"type": "string", "default": "Else"},
          "next": {"type": "string"},
        }
      }
    }
  }
}
```

Dispatcher writes:

```yaml
- type: decision
  name: <name>
  conditions:
    - display: <c.display>
      when: "<c.when>"
      next: <c.next>
    # ...
    - display: <default.display>
      default: true
      next: <default.next>
```

…and returns it to the LLM as the tool result. The LLM splices it
into its YAML output. The validator still runs (catches reachability
issues a per-step schema can't see), but it never catches a *shape*
error in a decision step again.

### B3 — `emit_connector_step` per-op schemas

For each `(connector, op)` row in `operations`, generate a strict
input_schema from `parameters_json` at MCP-server startup (cached).
The schema enforces `required` params, picklist enums (from
`picklist_options`), and rejects unknown keys.

This is the biggest payoff because connector_op shape errors are the
single most common compile failure in the corpus.

Trade-off: tool count grows. With 6,000+ operations, we can't emit
6,000 tools. Solution: a single tool
`emit_connector_step(connector, op_name, params)` whose input_schema
includes `connector` and `op_name` as required strings; the dispatcher
validates `params` against the per-op schema **server-side** and
returns a structured error envelope if it fails. This isn't quite
"impossible to emit invalid" — it's "rejected at the dispatcher
boundary with a structured envelope the LLM can act on." Still way
better than the validate→fix loop.

### B6 — Adherence measurement

Re-run `agent-stats`. Expected effects:

- The `validate_yaml → validate_yaml × N` chains shrink (because shape
  errors are eliminated at emit time).
- Total turn count per task drops; total tool calls per turn rises
  modestly (one `emit_*` per step is cheap).
- Net tokens/session expected down 20–40%.

**Estimated effort**: 1 day per hot shape (B1–B5), 0.5 day for B6.

---

## Refinement C — Separate the "enhance" path from the "build" path

**Why this exists.** Today the prompt + tools are tuned for the
build path: "no playbook yet → produce one." The enhance path is
different work: "playbook exists → make a small, surgical edit that
preserves the rest."

Failure modes the enhance path exhibits that the build path doesn't:

- Rewriting steps the user didn't ask to touch (loses UI cosmetics —
  step positions, custom labels — that compile-time normalization
  doesn't capture).
- Adding a new step that duplicates an existing one because the model
  didn't re-read the current state.
- Stripping `annotations:` blocks because they're not in the friendly
  schema.

The build path's verify gate doesn't catch these because they're not
*errors* — the resulting playbook compiles green and runs. They're
*regressions* vs the prior version.

### Phasing

| Phase | Status | Notes |
|---|---|---|
| C1 — Detect intent | ✅ done | `_detect_intent` in `web/backend/routes/chat.py` stamps `tags["intent"] = "build" \| "enhance"` at chat-start. Defaults to `enhance` when YAML is present and verbs are ambiguous (over-rewrite is the failure mode). Flows through `tags` → chat_turns + usage.jsonl. |
| C2 — Enhance-mode system prompt | ✅ done | `python/agent/enhance_addendum.md` (~2.1 KB) appended after the main prompt when `intent == "enhance"`. Cache prefix unchanged between modes (static block + main prompt are identical) so prompt-cache hits survive intent flips. `load_system_prompt(intent)` / `build_system_prompt(intent)` are the entry points. |
| C3 — Diff-aware verify | ✅ done | `python/mcp_server/tools_enhancement.py::verify_enhancement(before_yaml, after_yaml, user_message=None, live_probe=False)`. Delegates shape check to `verify_playbook`, IR-diffs both Collections via `_step_projection` + `_annotation_projection`, fires `playbook_dropped` / `step_dropped` / `step_renamed_silently` (error) and `annotation_stripped` / `annotation_modified` / `ui_metadata_lost` / `behavior_changed_outside_diff` (warning). Wired into MCP registry + web SAFE_TOOLS (tier 1). Enhance addendum now mandates this gate instead of `verify_playbook`. |
| C4 — Separate eval bucket | ⏳ not started | New eval task set under `tasks/enhance/`; agent-stats segments by intent tag. |
| C5 — Per-intent metrics | ⏳ not started | agent-stats reports wins/calls ratio separately for build vs enhance. Tag already lands in `tags` JSON via C1, so C5 has retroactive data from any session run after C1's commit. |

### C1 — Intent detection

At chat-start, examine `editor_buffer` + user message:

- Editor empty / user says "build / create / make me / I need a
  playbook that…" → **build mode**.
- Editor has YAML + user says "fix / update / change / add a step /
  make it also / why doesn't this…" → **enhance mode**.
- Editor has YAML + user says "build me…" or "rewrite this for…" →
  **build mode**, but warn before discarding existing content.

The detector lives in `web/backend/routes/chat.py` at session-create
time. It stamps `intent: "build" | "enhance"` into the UsageEvent
tags so agent-stats can segment.

### C2 — Enhance-mode system prompt

Loaded only when `intent == "enhance"`. Replaces the "Required
workflow" section with:

> The user has an existing playbook. Your job is the **smallest patch
> that achieves the user's goal**, not a rewrite.
>
> 1. Re-read the current YAML. If you're unsure what's there, call
>    `analyze_playbook` first.
> 2. Identify the *minimum* set of steps that need to change.
> 3. Propose the diff in plain language *before* emitting YAML.
> 4. When emitting, preserve every step the user didn't ask you to
>    touch. Preserve `annotations:` blocks even if you don't
>    understand them.
> 5. Call `verify_enhancement(before, after)` instead of
>    `verify_playbook` — it gates on shape *and* on
>    not-introducing-regressions.
> 6. If the user asks you to "rewrite" or "refactor," ask which
>    behaviors to preserve before proceeding.

### C3 — `verify_enhancement` MCP tool

```python
verify_enhancement(before_yaml: str, after_yaml: str) -> {
    ok: bool,
    ready_to_push: bool,
    required_fixes: [...],          # from verify_playbook on after_yaml
    regressions: [{                 # NEW — what got dropped or changed beyond the diff
        kind: "step_dropped" | "annotation_stripped" |
              "ui_metadata_lost" | "behavior_changed_outside_diff",
        step: str | None,
        before: str | None,
        after: str | None,
        severity: "error" | "warning",
    }],
    diff_summary: {
        steps_added: [str], steps_removed: [str],
        steps_modified: [str], unchanged: int,
    },
}
```

Internals: run `verify_playbook` on `after`, then structurally diff
`before` vs `after` and flag any change to a step the user didn't
explicitly reference in their message. (The "didn't explicitly
reference" check is heuristic — fuzzy match step names against the
user's most-recent message.)

### C4 — Separate eval bucket

New task directory `python/evals/tasks/enhance/` with 8–10 tasks:

- "Add a Slack notification to the alert-ingestion playbook."
- "Change the severity threshold in the decision branch from 7 to 8."
- "Replace the SendMail step with a Teams message."
- "Why is this playbook failing on the IP filter step?"
- Etc.

Each task has a `before_yaml_path` + a `gold_after_yaml_path` and
the scoring checks both `verify_enhancement` shape *and* the
specific user-asked change landed.

### C5 — Per-intent metrics

`fsrpb agent-stats --by-intent` segments every metric by build /
enhance. Watch for:

- **Tool-call coupling differs.** Enhance sessions should show
  `analyze_playbook` first, build sessions should show
  `find_step_recipe` first.
- **Token budget differs.** Enhance sessions should cost *less*
  because the work is smaller — if they're costing more, the agent
  is over-rewriting.
- **Verify→fix iteration count differs.** Enhance loops with high
  iteration counts indicate the agent is fighting the diff.

**Estimated effort**: 1 day for C1+C2 (mostly prompt + tag plumbing),
2 days for C3 (the regression detector is the meaty part), 1 day
each for C4 + C5.

---

## Order of work

Each refinement is independent; pick by ROI.

1. **A first** (1–2 days). Pure win, no behavior risk, the agent
   stops paying the recurring lookup tax. Re-run `agent-stats` and
   you'll see the call counts shift.
2. **C next** (~5 days). Highest impact on real chat sessions —
   today's "enhance" sessions are silently the highest-cost-per-win
   bucket and you don't even see it because metrics are aggregated.
3. **B last** (5+ days). Biggest engineering investment; biggest
   token-and-iteration win. Worth doing after A + C have established
   the new baseline so the gains are visible.

---

## Risks / what could be wrong

- **Prompt caching may not help LM Studio users.** They pay the
  static block every turn. If LM Studio is a primary user channel,
  reconsider A's ROI for that population — the agent there will see
  bigger context but no caching savings.
- **Constrained generation removes a learning loop.** Today the
  validate→fix loop is also how the agent learns "the schema is X."
  When emit-tools handle shape correctness, the model never *sees*
  the wrong shape, which is fine functionally but means the
  free-author path may degrade silently. Mitigation: keep the free
  path; measure correctness on free vs constrained tasks.
- **Enhance-mode misdetection** could put the agent into "minimal
  diff" mode when the user wanted a rewrite. The bias is toward
  asking — annoying but safer than over-rewriting.
- **Per-op schema generation cost.** 6,000+ ops × per-op schema
  generation at startup could be slow. Lazy-generate on first
  `emit_connector_step(connector, op)` and cache.

---

## Success criteria

- **A**: `get_step_type` call count drops ≥60%. Net session tokens
  drop 15–30%. No regression in eval scores.
- **B**: `validate_yaml → validate_yaml` chain length p95 drops from
  current (24×) to ≤5×. Final eval pass rate on hot-shape tasks
  improves.
- **C**: Enhance sessions cost less than build sessions per win.
  Agent stops rewriting steps the user didn't reference (regression
  count in `verify_enhancement.regressions` near zero on the enhance
  eval set).

---

## Cross-references

- `AGENT_QUALITY_PLAN.md` — the data this plan acts on
  (`docs/AGENT_TOOL_USAGE.md`, `AGENT_DATA_GAPS.md`,
  `AGENT_PROMPT_ADHERENCE.md`).
- `VERIFY_PLAYBOOK_PLAN.md` — `verify_enhancement` (C3) is a
  superset of `verify_playbook` with a regression detector.
- `CONNECTOR_INTEGRATION_PLAN.md` — the per-op schemas generated for
  B3 are the same shapes Phase 0.5's `propose_http_fallback` reads.
  Shared dependency on `operations.parameters_json` quality.
