# Skill-based playbook compilation plan — reliable session→YAML

**Why this exists.** Today a playbook is built by having the LLM **hand-author FSRPB YAML** at
the end of a triage session (the `build_playbook_from_session` / `chat_resume accept` path), guided
by schema-lookup tools and the long string of jinja warnings in `fsr_core/mcp_server/tools_compile.py`
(lines ~155–345). The dominant failure mode is **variable wiring** — the model guessing the output
shape of a connector op and writing the wrong jinja path (`vars.steps.enrich['hydra:member'][0].x`).
The second is **branch flattening** — an interactive triage (a `choice_card` / `capability_gap` the
analyst clicked through) compiles to the single path taken, not an encoded conditional.

A **skill** is a typed, tested playbook-block descriptor (same registry shape as the c3charts
connector framework): `id`, the FSR step-type it compiles to, the connector op, an **input schema**,
and a `compile()` hook. The reliability win comes from the fact that **the agent already executed
the connector steps**, so their real outputs are captured in-session. Recording each action as a
`SkillCall{resolved_inputs, observed_output}` lets `build_playbook_from_session` compile the **typed
trace** instead of the prose transcript — recovering step wiring by **static value-match over the
captured outputs**, then proving every `vars.steps.X.y` reference with the validation tools that
already exist (`render_jinja`, the static undefined-path checker, `step_through_playbook`). No
hand-guessed jinja paths; no net-new validator.

**Chosen architecture: compile-layer only.** Live triage stays on raw `run_op` and is untouched. We
add a `SkillCall` recorder + provenance tracker that observes the existing tool loop, and rewrite the
session→YAML compile to consume the typed trace. This is the lowest-risk path and attacks the #1
failure (jinja wiring) directly. Skills-as-agent-tools (acting through skills live) is a possible
later evolution, explicitly out of scope here.

**Bar:** "a saved playbook from a clean triage session compiles, resolves every jinja path, and runs
without a wiring fix." Effort: `small (1–3h)`, `medium (4–12h)`, `large (1–3d)`.

**Where edits land:** all `fsr_core` changes go in **`fsr-playbook-framework/fsr_core`** (canonical); the
connector vendors it via `scripts/build.sh` (never edit the vendored copy). After landing, re-vendor
+ bump `info.json` + `scripts/install_to_fsr.py`. No widget or contract change is required — the
output is still FSRPB YAML pushed via the existing `chat_resume accept` path (contract §4, §5
`playbook_offer`), so the wire shape is unchanged.

---

## ✅ CLOSED (2026-06-08)

**Capability SHIPPED and LIVE — task closed; the default-flip is NOT being pursued.**
The trace→YAML compiler (`build_playbook_from_trace`) is in `SAFE_TOOLS`, is the live
offer-accept authoring path (`operations.py`), and is live-proven at action_coverage 1.0 +
grounding 1.0; it's also offline-pinned (B4 + c2_containment + enrich_then_block fixtures via
`python/evals/build_trace_fixture.py`). The one remaining item — a side-by-side baseline to
justify **removing the hand-author fallback** — was judged low value (2026-06-08): the
deterministic compiler already ships and the fallback is a useful safety net for
trace-uncovered scenarios, so keeping both paths is the right call. Reopen only if the
hand-author path is observed producing bad playbooks in practice.

---

## SESSION RESUME (2026-06-01) — read this first after a clear

**Status: Phases 1–5 shipped & green** (`make verify` = 99 fsr_core + 126 connector, ruff clean).
Branch `feat/skill-based-playbook` in fsr-playbook-framework; connector changes on
`feat/action-based-streaming` (commit `62762cf`). Neither merged to main yet.

**Commits (fsr-playbook-framework):** `89dda67` P1 · `31c3712` P2 · `b108ae8` P3 · `7e690d0` P4 ·
`352b2fb` P5 tool+eval · `79c590a` P5 active-trace+prompt · `fdd3b3f` plan update.

**Files that exist now (all in `fsr_core`, source — connector symlinks it, no re-vendor needed in dev):**
- `compiler/skills.py` — 4 demo-core skill descriptors + registry (P1).
- `agent/skill_trace.py` — `SkillCall`/`SkillTrace`, `record_run_op`, process-local active trace (P2).
- `compiler/skill_compiler.py` — `compile_trace`, `wire_inputs` (value-match), `render_context`,
  `assemble_playbook`, `to_yaml` (P3).
- `compiler/skill_verify.py` — `compile_and_verify`, `verify_wire` (StrictUndefined Jinja2 or injected
  live `render_jinja`), reuses `validator._check_jinja_paths` (P4).
- `mcp_server/tools_compile.py::build_playbook_from_trace` — entry point; **defaults `trace_json=""`
  → reads the active session trace** (P5). Build-only (in `intents.py::BUILD_ONLY_TOOLS` + connector's
  `_BUILD_ONLY_TOOLS`). Build agent advertises it via `tools=[]` full-registry expansion.
- `agent/system_prompt_build.md` — steers build agent: call `build_playbook_from_trace` FIRST,
  hand-author only on `empty_trace`.
- `python/evals/scoring.py::score_wiring_resolution` + `score(skill_trace_json=...)` → informational
  `wiring_resolves` level (P5).
- Connector: `storage.py` `session_trace` table + `set/get_session_trace`; `operations.py`
  `_session_trace_scope` installed across chat_turn / Model-A resume / suspended resume / approved
  action_card execute. `tests/test_storage.py` covers it.

**Key facts / gotchas to not relearn:**
- FSR keys `vars.steps.<Name_with_spaces→underscores>`. Connector payloads nest under `.data`
  sometimes (VirusTotal) and directly other times (AbuseIPDB, crudhub `hydra:member`) — handled by
  `SkillCall.ref_prefix`, set in `run_op` from whether the raw resp had a `data` key.
- `build_playbook_from_session` (in the original plan prose) **does not exist as a function** — the
  session→YAML compile is the build-intent agent loop in `fsr_core/llm/run_turn.py`; the trace path is
  the new `build_playbook_from_trace` tool.
- Active trace is process-local module state; `_session_trace_scope` clears it in `finally` (concurrency
  caveat noted — fine for one-op-per-worker, revisit with contextvars if needed).

**DONE (2026-06-05) — trace fixtures for the parity campaign.** `python/evals/
build_trace_fixture.py` replays two coherent investigations (`c2_containment`,
`enrich_then_block`) through `run_op` in SIM mode with the recorder on and dumps
`SkillTrace.to_json()` → `store/trace_fixtures/*.json`. Each is gated on a real
cross-step value coincidence, then fed through `score_wiring_resolution`: **both
resolve every wire, zero static errors.** Regression test
`python/tests/test_build_trace_fixture.py`. This is the trace-compiler side of
the parity evidence; the remaining analytical step for the actual default-flip
is the side-by-side vs the hand-author baseline (commit `039dfa0`).

**(historical) NEXT STEP — trace fixtures for the parity campaign (decided):**
- **Best method = replay a coherent investigation through `run_op` in SIM mode with the recorder on,
  then dump `SkillTrace.to_json()`.** Do NOT hand-author trace JSON (reintroduces the guess-the-output
  failure mode). Sim fixtures in `fsr_core/mcp_server/_sim_fixtures.py` already encode a C2 investigation
  with **cross-referenced values** (`_C2_IP` in `search_events.destIpAddr` → `block_ip_new` input;
  `_HOST_IP` from `get_ip_context` → `get_host_context` input; owner/user link) — exactly what
  value-match must recover. Deterministic + offline → CI-safe.
- Sim-covered ops (`_EXECUTE` map): fortisiem get_ip_context/get_host_context/get_user_context/
  search_events/get_incidents, virustotal query_ip, shodan host_information/query_ip, abuseipdb check_ip,
  fortigate-firewall block_ip_new/block_ip.
- **TODO:** write `python/evals/build_trace_fixture.py` — force sim mode, replay 1–2 scenarios
  (C2 containment; enrich-then-block), assert the cross-step value coincidence is present, write
  `store/trace_fixtures/<scenario>.json`. Then point `wiring_resolves` at them vs the hand-author
  baseline to produce the evidence the **default-flip** (remove hand-author fallback) gates on.
- Highest-fidelity validation (separate, needs live FSR): one real triage→build session, read
  `session_trace` from the connector DB → live smoke test (deploy via `scripts/deploy.sh`).

---

## Design

### 1. Skill descriptor schema — *small*

A registry of skill descriptors, one per playbook-block class. Atomic at the FSR step boundary
(**1 skill ↔ 1 step type** — non-negotiable; a skill that enriches *and* decides cannot map to one
step).

```
Skill = {
  id:            str,                  # "run_connector_action", "decision", "set_variable", ...
  step_type:     str,                  # one of the 21 FSR step types (UUID via get_step_type)
  needs:         {connector?, op?},    # for RunConnectorAction skills
  input_schema:  {param: {type, jinja_bindable: bool, required: bool}},
  compile:       (resolved_inputs, wired_refs) -> yaml_step_dict,
}
```

**Demo-core skill set** (the four blocks that make a compelling, branching playbook):

| Skill class            | FSR step type        | Demo role                                              | Source of schema                     |
|------------------------|----------------------|--------------------------------------------------------|--------------------------------------|
| `run_connector_action` | RunConnectorAction   | the real work — maps 1:1 to a `run_op` call's I/O      | `get_op_schema(op)` (input); **observed `run_op` output** (output) |
| `set_variable`         | SetVariable          | stage/normalize a value for downstream steps           | static                               |
| `manual_input`         | ManualTask           | (a) collect extra input the playbook needs, **or** (b) a yes/no **confirmation that routes** | `emit_manual_input` shape |
| `decision`             | Decision (branch)    | route on a true/false condition over prior outputs     | `emit_decision_step` shape           |

`run_connector_action` is parameterized by `get_op_schema`, so the connector long tail is covered by
one generic skill. **`manual_input` has two modes:** an extra-input form, and a yes/no confirmation
whose answer is consumed by a following `decision` step to fork the playbook — that confirmation→fork
pair is the most demo-legible branching pattern. `ref_playbook` is deferred (not demo-core).

### 2. SkillCall trace — *small* (lighter than first drafted)

The agent **already ran the connector steps**, so their real outputs are sitting in the tool loop's
`run_op` `tool_result`s. We don't need a bespoke provenance tracker — we need a thin recorder that
captures, per action, what's already there:

```
SkillCall = {
  skill_id:        str,
  step_name:       str,                  # stable; becomes the YAML step name
  resolved_inputs: {param: value},       # the args the agent actually passed
  observed_output: <the real run_op result>,   # already captured by the loop
}
```

`observed_output` is the asset that makes everything else reliable: it is both the **wiring source**
(§3) and the **render context** for verification (§4). No `output_schema` declaration is required up
front — the real output *is* the schema for this session.

### 3. Wiring by value-match, then verify — *medium*

The agent ran the ops in dependency order, so wiring is recoverable by static analysis over the
trace rather than guessed by the model:

1. Emit one candidate YAML step per `SkillCall` (via the skill's `compile()` + `get_step_type`).
2. For each step's input args, scan earlier `SkillCall.observed_output`s for the same value and
   back-derive a jinja path → replace the literal with `{{ vars.steps.<source>.<path> }}`.
3. Decision steps get their branch conditions from the recorded `choice`/`capability_gap`/manual-input
   `value`s, so **branch logic is preserved, not flattened**.

Value-match will produce candidate wiring with some false positives (a literal that happens to equal a
prior output). That's fine — we don't trust it; we **verify** it in §4. The LLM's residual job is to
confirm ordering and author branch *display* text, not to invent jinja paths.

### 4. Verify/repair with the tools we already have — *medium*

This is the key simplification: we don't build new validation — we **reuse the existing tooling**,
feeding it the captured real outputs as context.

| Concern | Existing tool | How we use it |
|---|---|---|
| Does each jinja path resolve to real data? | `render_jinja(template, context)` — `tools_jinja.py:156` | render every step's args with prior `observed_output`s as `vars.steps.*` context; a non-evaluating path = a bad wire |
| Does any reference point at something undefined in the DAG? | `validator._check_jinja_paths` (`validator.py:201-269`) + `typed_walker` branch/filter-chain checks | **static** undefined-reference detection across the step graph — exactly "tell me statically if a variable references something undefined" |
| Does it run end-to-end in order? | `step_through_playbook` (`tools_analysis.py:35`), `dry_run_playbook` (`tools_execution.py:1847`) | simulate the walk; confirm DAG ordering and that each step's inputs are satisfied |
| Did a wire degrade at runtime? | `render_analyzer.py:683-877` | catches refs that resolve to undefined at runtime |

The compile loop becomes: **candidate wiring → `_check_jinja_paths` (static) → `render_jinja` with
real captured outputs (does it evaluate?) → `step_through_playbook` (does it walk?)**, repairing any
flagged reference before push. Because the render context is the *actual* op output, "evaluates
cleanly" is strong evidence the wire is correct — not a guess against a declared schema.

Keep the current hand-author path behind a flag as fallback for sessions with an empty/partial trace.

---

## 5. UI / UX — reviewable draft in the offer card — *medium*

The widget entry point already exists: the **`playbook_offer` card** (contract §5,
`awaiting_playbook_offer`) is the end-of-triage "Save as Playbook" CTA. Today it renders a *flat*
`ops_summary` list + editable title + Save/Not now — it can't express what the skill compiler now
produces (branches, manual inputs, set-variables) or whether the wiring was verified. The UX work is
**enriching that card into a reviewable draft**, not building a new surface — keep it in the
conversational drawer (a full DAG editor fights the chat form factor).

**Design principle: progressive disclosure.** The card stays compact (summary + count); an
expandable **"Review steps"** reveals the structured draft. What it shows:

1. **Real structure, human-readable.** Not raw jinja (`vars.steps.enrich['hydra:member'][0].ip`) but
   a step row per node with a type icon and plain-English wiring — *"Block IP — uses the IP from
   **Enrich Indicator**."* The `decision`/`manual_input` fork renders as a visible branch
   (*"If malicious → Block + Isolate · else → Create ticket"*). This branch view is the demo's
   wow-moment: a *branching* playbook built from the conversation.
2. **Per-step trust badge.** Fed by the §4 verify loop: ✓ when `render_jinja` (against the captured
   real output) **and** `step_through_playbook` pass for that step. A single amber line when a value
   couldn't be auto-wired — surfaced as an inline field that becomes a `set_variable`/`manual_input`.
   This puts risk #1/#2 in the analyst's hands instead of failing silently after push.
3. **Safe inline edits only.** Title (exists today), `manual_input` prompt text, `decision` branch
   labels — edits that **don't** change wiring. Structural edits (toggle/reorder) change the DAG and
   would need a recompile round-trip; **disabled for the demo**, flagged as a later phase.
4. **Unchanged accept plumbing.** Primary "Save as Playbook" → `chat_resume({decision:"accept",
   offer_id, title, edits?})` → `build_playbook_from_session` → push. "Not now" declines as today.

**Contract impact (additive, ~2.6.0 minor, backward-compatible):** extend `playbook_offer` so each
`ops_summary` entry can carry `{skill_id, step_type, wiring_label, verified, branch?}`, plus an
optional top-level `draft_steps` tree for the branch view. A pre-2.6.0 widget ignores the new fields
and renders the flat list it shows today (still safe). Mirror the new shape in §5 and add a
`capability`-style reference fixture (`playbook_draft_branching.json`) so mock mode exercises it.

**Widget test coverage** (per repo convention — controller→jest, template/DOM→playwright e2e): a
`fsrPlaybookBuilder.playbookDraft.spec.js` driving the new fixture must assert the branch view
renders, verify badges show, an inline prompt edit round-trips into the accept payload, and the flat
fallback still renders when the new fields are absent.

---

## Risks / open questions

1. **Value-match false positives.** A literal that coincidentally equals a prior output (port,
   boolean, common string) mis-wires. Mitigation: require non-trivial values (len ≥ N, or
   structured/IOC-shaped); and the §4 verify loop catches a wrong wire when `render_jinja` /
   `step_through_playbook` disagree with the recorded `observed_output`.
2. **Sparse output for a needed downstream input.** If a later step needs a value no prior step
   produced, there's nothing to wire — surface it as a `set_variable` or `manual_input` gap for the
   LLM-confirm step rather than emitting a dangling ref.
3. **Granularity creep.** Resist any skill that spans >1 step type — it breaks the 1:1 compile.
4. **Selection/ordering stays model-driven.** Wiring is now deterministic + verified, but *which*
   skills and *what branch conditions* still need eval coverage — add "compiled playbook: all paths
   resolve under `render_jinja` + `step_through`" as a scored eval dimension.

---

## Phased rollout

- **Phase 1 (small) — ✅ DONE (`89dda67`):** Skill descriptor schema + the 4 demo-core descriptors
  (§1) in `fsr_core/compiler/skills.py`. Pure registry; 1:1 step-type rule enforced.
- **Phase 2 (small) — ✅ DONE (`31c3712`):** `SkillCall` trace recorder (§2) in
  `fsr_core/agent/skill_trace.py`. `record_run_op` hooked into both `run_op` success paths (direct +
  agent-routed), capturing the FULL output + a `ref_prefix` flag; no-op without an active trace.
- **Phase 3 (large) — ✅ DONE (`b108ae8`):** `fsr_core/compiler/skill_compiler.py` — candidate steps
  + value-match wiring (trivial-value rejection, bracket-quoting, `ref_prefix`-aware paths) + render
  context that mirrors runtime nesting. (The plan's `build_playbook_from_session` name resolved to the
  build-intent agent loop, which lives in `fsr_core`; entry point shipped in Phase 5.)
- **Phase 4 (medium) — ✅ DONE (`7e690d0`):** `fsr_core/compiler/skill_verify.py` — verify/repair via
  StrictUndefined local Jinja (or injected live `render_jinja`) + reused `parser`/`validator`
  `_check_jinja_paths`; bad wires repaired to literal + recorded as a gap.
- **Phase 5 (small) — ✅ DONE (`352b2fb`, `79c590a`; connector `62762cf`):** `build_playbook_from_trace`
  MCP tool (reads the active session trace; flag-gated, build-only) + `assemble_playbook`/`to_yaml`;
  `wiring_resolves` eval dimension (`evals.scoring`). Connector enablement: `session_trace` storage +
  `_session_trace_scope` installed across chat_turn / resume / suspended-resume / approved-execute;
  build prompt steers to the trace compiler first. **Default-flip — deterministic half DONE
  (2026-06-05, `927a43e`):** `python/evals/parity_report.py` builds each sim-replayed trace fixture
  into a playbook and verifies it on the SAME `verify_playbook.ready_to_push` bar a hand-author
  playbook is judged on — 2/2 ready_to_push, 0 static errors, 0 repaired, all wires verified; 7/7
  hand-authored gold examples also ready_to_push (parity, no regression). Baseline snapshot in
  `store/eval_runs/parity_*.md`; CI gate `python/tests/test_parity_report.py`. **Live half DONE
  (2026-06-05, `08fd08e`):** sampled the hand-author baseline — 4 connector-authoring tasks through
  the agentic build loop (sonnet-4-6). FINDING (nuanced): all 4 ALSO reach `ready_to_push`, but only
  via an agentic verify→repair loop (35 tool calls, ~22.5k output tokens across the sample). So the
  default-flip case is **cost + determinism, not a correctness gap**: the trace path reaches the same
  bar in 0 LLM turns / 0 tool calls / 0 verify-repair iterations, deterministically. ⇒ **trace-first,
  keep the hand-author loop as the fallback for sessions with no usable trace** (don't fully remove
  it). Artifact `store/eval_runs/live_handauthor_*.json`; combined report `parity_*.md`.
- **Phase 6 (medium) — contract + connector ◑ DONE; widget rendering TODO (out-of-repo):**
  Decision: surfacing model **(B) offer card** (not the manual Build-action handoff) — accept rides
  the existing `chat_resume` path on the SAME `session_id`, so the trace-handoff (#1 linchpin) is
  solved by construction, no fresh-session orphaning.
  - **Contract `2.6.0` shipped** in `FSR_PLAYBOOK_BUILDER_CONNECTOR_CONTRACT.md` (widget repo):
    `playbook_offer` enriched with per-entry `{skill_id, step_type, wiring_label, verified, branch?}`
    + optional `draft_steps` tree + safe inline `edits` on accept; §4/§5/§6/§9 (T17/T18) updated.
  - **fsr_core:** `emit_playbook_offer` tool (`tools_emit.py`) — model-triggered, but the card body is
    compiled HERE from the active trace via `skill_compiler.summarize_for_offer` (never hand-written
    wiring). Registered in `mcp_server/__init__` + `llm/tools.py` (SAFE_TOOLS, tier 0); triage prompt
    steers the offer. Tests: `fsr_core/tests/test_playbook_offer.py` (5).
  - **connector:** `_CARD_*` maps + `awaiting_playbook_offer`; decision whitelist `accept|decline`;
    `_resume_playbook_offer_accept` (compile trace → `compile_yaml` → `push_playbook` → `playbook_pushed`
    info_card; never dead-ends on empty/compile/push failure); direct `decline` end_turn; `CONTRACT_VERSION
    = "2.6.0"`. Tests: 3 in `test_chat_operations.py` + 1 replay in `test_mock_replay.py`; fixture
    `playbook_draft_branching.json`. `make verify` green (104 fsr_core + 130 connector).
  - **Still TODO (WebStorm widget repo):** render the reviewable draft (compact → "Review steps"
    expand, verify badges, `draft_steps` branch view, safe inline edits folding into the accept
    payload) + `fsrPlaybookBuilder.playbookDraft.spec.js` e2e. Ship via `scripts/ship.sh`.
