# Frontend handoff — Phase 6: reviewable playbook-draft card

Companion to `SKILL_BASED_PLAYBOOK_PLAN.md` §5. Phases 1–5 (backend trace
compiler) are shipped & green; this is the **only remaining UI work**. It lands
in the **WebStorm Angular widget repo** (separate toolchain — not this repo or
the connector repo).

## Why the card must change

End-of-triage, the agent now compiles a playbook from the **recorded action
trace** (real ops + real outputs), not by hand-authoring YAML. The result can
contain branches, manual-input gates, set-variables, and **per-wire
verification status** — none of which the current flat `playbook_offer` card can
express. The UX work is **enriching the existing card into a reviewable draft**,
not building a new surface. Keep it in the conversational drawer (a full DAG
editor fights the chat form factor).

## Current card shape (what you render today)

`stop_reason: "awaiting_playbook_offer"`, transcript carries:

```json
{
  "type": "playbook_offer",
  "id": "pb-offer-c2-1",
  "summary": "…want me to save this as a repeatable playbook?",
  "title_suggestion": "C2 Containment — 102.220.160.21",
  "ops_summary": [
    {"connector": "fortigate-firewall", "operation": "block_ip_new", "label": "Block 102.220.160.21"}
  ],
  "editable_title": true
}
```

Accept path (unchanged): primary CTA →
`chat_resume({decision:"accept", offer_id, title, edits?})`. "Not now" →
`chat_resume({decision:"decline"})`.

## New additive shape (contract ~2.6.0, backward-compatible)

Each `ops_summary` entry gains, and a new optional top-level `draft_steps` tree
appears:

```json
{
  "type": "playbook_offer",
  "id": "pb-offer-c2-1",
  "summary": "…",
  "title_suggestion": "C2 Containment — 102.220.160.21",
  "editable_title": true,
  "ops_summary": [
    {
      "connector": "fortigate-firewall", "operation": "block_ip_new",
      "label": "Block 102.220.160.21",
      "skill_id": "run_connector_action",   // NEW
      "step_type": "connector",             // NEW: one of the 21 FSR step types
      "wiring_label": "uses the IP from Enrich Indicator",  // NEW: plain-English wiring
      "verified": true                      // NEW: §4 verify result for this step
    }
  ],
  "draft_steps": [                           // NEW (optional): the branch view
    {"name": "Enrich Indicator", "step_type": "connector", "verified": true,
     "wiring_label": null, "gaps": []},
    {"name": "Malicious?", "step_type": "decision",
     "branch": {"if": "malicious → Block + Isolate", "else": "Create ticket"}},
    {"name": "Block IP", "step_type": "connector", "verified": true,
     "wiring_label": "uses the IP from Enrich Indicator", "gaps": []},
    {"name": "Notify", "step_type": "manual_input", "verified": true, "gaps": ["assignee"]}
  ]
}
```

**Backward-compat rule:** a pre-2.6.0 widget ignores the new fields and renders
the flat `ops_summary` list it shows today (still safe). A 2.6.0 widget renders
the rich draft when `draft_steps` is present, flat otherwise. The accept payload
is **unchanged** — only `title` + safe label/prompt `edits?` ride along.

## Where the data comes from (for the backend dev wiring the card)

The trace compiler tool `build_playbook_from_trace` (fsr_core
`mcp_server/tools_compile.py`) already returns:
`{ok, yaml, compile_summary, verified:{step:{param:bool}}, gaps:{step:[param]},
repaired:{step:[param]}, static_errors:[]}`. The structured per-step data
(`skill_id`, `step_type`, branch shape, wiring source) lives in the compiler's
intermediate `compile_trace`/`compile_and_verify` dict (`steps`, `wiring`).
**Backend prerequisite for this card:** have the connector's offer-builder emit
`draft_steps` + the per-entry fields from that dict (skill_id ← SkillCall,
step_type ← skill descriptor, wiring_label ← humanize `wiring[step][param]`,
verified ← collapse `verified[step]`, gaps ← `gaps[step] ∪ repaired[step]`). This
is a small connector change, not a widget one — flag it as the unblock.

## The four UI deliverables (progressive disclosure)

Card stays compact (summary + step count); an expandable **"Review steps"**
reveals the draft.

1. **Real structure, human-readable.** One row per step with a type icon and
   plain-English wiring — *"Block IP — uses the IP from **Enrich Indicator**"* —
   NOT raw jinja. A `decision`/`manual_input` fork renders as a visible branch
   (*"If malicious → Block + Isolate · else → Create ticket"*). This branch view
   is the demo wow-moment.
2. **Per-step trust badge.** ✓ when `verified` is true for that step; a single
   amber line when a value couldn't be auto-wired (a `gaps` entry) — surfaced as
   an inline field the analyst fills, which becomes a `set_variable`/`manual_input`.
   Puts risk in the analyst's hands instead of failing silently after push.
3. **Safe inline edits only.** Title (exists today), `manual_input` prompt text,
   `decision` branch labels — edits that **don't change wiring**. Structural
   edits (toggle/reorder) change the DAG and need a recompile round-trip;
   **disabled for the demo**, flagged as a later phase.
4. **Unchanged accept plumbing.** Primary "Save as Playbook" →
   `chat_resume({decision:"accept", offer_id, title, edits?})`. "Not now" declines.

## Existing widget anchors (per auto-memory)

The widget already renders other rich cards — reuse those patterns:
- `fsrPbRender.js` — the card normalizer (the `capability_gap` card normalizer at
  ~520-536 is the closest precedent for adding a new card type).
- `view.html` — dedicated card templates/CSS (capability_gap lives ~1347-1390;
  the generic fallback excludes known types ~1392). Add a `playbook_offer`
  rich-draft template the same way; keep the flat fallback for pre-2.6.0 data.
- Controller→jest, template/DOM→playwright e2e (repo convention).

## Test coverage required

- Add a mock fixture `playbook_draft_branching.json` (mirror the new shape) so
  mock mode exercises the branch view. Pair it with the existing
  `playbook_offer_decline.json` pattern in the connector `fixtures/`.
- `fsrPlaybookBuilder.playbookDraft.spec.js` (playwright e2e) must assert: the
  branch view renders; verify badges show; an inline prompt edit round-trips into
  the accept payload; the **flat fallback** still renders when the new fields are
  absent.

## ✅ Widget side implemented (2026-06-01) — built to the **contract** (§5), not this sketch

Implemented against `FSR_PLAYBOOK_BUILDER_CONNECTOR_CONTRACT.md` §5 (the
authoritative shapes), which differ from the JSON sketches earlier in this doc.
Where they conflict, **the contract wins** — the field names below are what the
connector must actually emit/consume. Widget bumped to `1.0.43`,
`WIDGET_CONTRACT_VERSION = 2.6.0`. All jest + e2e green in the harness.

**Wire shapes the widget now speaks (contract-exact):**

- `draft_steps[]` nodes use **`node`** (the step name), `step_type`, `verified`,
  and — for a fork — **`branches`** as a *map* `{"<branch label>": ["<op
  label>", …]}`. (Not `name`/`{if,else}`.)
- Each `ops_summary[]` entry may carry `skill_id`, `step_type`, `wiring_label`,
  `verified` (bool), and **`branch`** (the fork label it belongs to). The widget
  JOINs ops↔draft by **label**, so wiring/verify/gap render once, by reference.
- A `verified:false` op (or a `manual_input` step) renders an **amber inline
  field**; what the analyst types there becomes `manual_input_prompts[label]`.

**The `edits` object the connector must consume** (contract §5 / T18; rides on
the unchanged `chat_resume({decision:"accept", offer_id, title, edits?})`;
omitted entirely when nothing changed, so pre-2.6.0 behavior is byte-identical):

```json
{ "edits": {
  "manual_input_prompts": { "<op label>": "<analyst-supplied prompt/value>" },
  "branch_labels":        { "<decision node>": { "<branch key>": "<new label>" } }
} }
```

Only changed keys appear. Wiring/DAG are never touched (structural edits are
out of scope for 2.6.0). `manual_input_prompts[label]` seeds the
`set_variable`/`manual_input` for the value that couldn't be auto-wired.

**Files:** `widgetAssets/js/fsrPbRender.js` (normalizer: `_draftRow`,
`_buildDraftSteps`, enriched `playbook_offer`), `widget/view.html` (rich draft
template + CSS; flat 2.5.0 list still renders when the new fields are absent),
`widget/view.controller.js` (`_collectOfferEdits` → resume payload).

**Tests:** jest `render.pipeline.test.js` (enriched ops, verified:false gap,
ops↔draft join + shared-ref) + e2e `fsrPlaybookBuilder.playbookDraft.spec.js`
(branch view, verify badge vs amber gap, branch-label + gap edits → contract
`edits`, flat fallback). Fixture: `playbook_draft_branching.json` (mirrors the
contract §5 example; registered in the contract fixtures table).

**Still the unblock:** the connector offer-builder must emit `draft_steps` +
the enriched `ops_summary` fields from the compiler dict (§"Where the data comes
from") and apply `edits` on accept. Until it does, real sessions render the flat
fallback. (Dev note: the widget now declares contract 2.6.0; against a 2.5.0
connector it logs a soft minor-version warning — expected until the connector
bumps.)

## Definition of done

A saved playbook from a clean triage session, reviewed in the enriched card,
compiles, resolves every jinja path, and runs without a wiring fix — and the
analyst saw per-step verification + any gap **before** pushing.
