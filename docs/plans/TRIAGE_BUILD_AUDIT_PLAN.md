# Triage/Build Export Audit — Living Plan

**Source evidence:** widget export `sess-yq8nhcix-1780261596258` (widget v1.0.47,
contract v2.7.0, connector v0.3.82). Session **intent: `triage`**; user clicked
the **Attack Timeline** quick-action on an incident; the agent authored an
18-step playbook instead of narrating a timeline.

**Status legend:** `TODO` · `IN PROGRESS` · `DONE` · `WONTFIX` · `NEEDS-DECISION`
**Priority:** filled in by Dylan during triage of this doc.

Update this doc in place as findings are confirmed/fixed. Keep file+line refs
current; if a ref drifts, fix it here in the same change.

---

## A. Intent confusion cluster (explains symptoms #1, #4, #6, #6b at once)

The session was in **triage**, the user asked for a **timeline** (a read/
summarize task), and the agent **authored a playbook**. One mismatch, three
compounding bugs.

### A1 — "Build" quick-action prompt — WONTFIX (symptom, not cause)
- **Symptom:** #1 (asked for timeline → started creating a playbook).
- **Evidence:** client event log `quick_action {key:"timeline"}`; prompt text
  `view.controller.js:171-173` ("Build an attack timeline for this case …").
- **DECISION (Dylan):** do NOT reword. If the literal word "build" can flip a
  triage session into authoring a playbook, the system is fragile in a way
  rewording only hides. The word is a red herring. The actual defects are A2
  (authoring tools reachable in triage) and A4 (triage prompt never defined
  what a "timeline" request is). With A2 enforced, the agent *cannot* author
  YAML in triage regardless of prompt wording; with A4 it knows a timeline is a
  narrative. Rewording would mask a recurrence on the next "build/create/make"
  phrasing.
- **Use this as the robustness test:** after A2+A4, the *unchanged* "Build an
  attack timeline…" prompt must yield a narrative timeline with zero
  authoring-tool calls. That is the acceptance criterion for A2/A4.
- **Status:** WONTFIX · **Priority:** n/a

### A2 — Build-only tools leak into the triage tool slice
- **Symptom:** #4 (agent banging its head authoring YAML in a triage session).
- **Evidence:** export shows `validate_yaml`, `compile_yaml`, `get_step_type`,
  `find_operation` all called while `intent: triage`.
- **Files:** `fsr_playbooks/llm/intents.py:29` (`BUILD_ONLY_TOOLS`) +
  `tools_for_intent()` — these are *supposed* to be dropped for triage. The
  connector caller (`operations.py`, vendored) must actually pass that filtered
  slice to the provider; verify it does (build returns `[]` = "provider
  self-fills full registry" — confirm triage isn't also self-filling).
- **Root cause (hypothesis):** connector advertises the full registry for
  triage too, OR provider ignores the filtered list. **NEEDS verification.**
- **Proposed fix:** ensure the triage path advertises only
  `tools_for_intent("triage")`; add a regression test that the triage slice
  excludes every name in `BUILD_ONLY_TOOLS`.
- **Highest-leverage fix in this doc** — with authoring tools gone, the whole
  episode can't happen. A1 is explicitly WONTFIX *because* this is the real
  fix; "build an attack timeline" must be safe with zero prompt changes.
- **Acceptance:** unchanged timeline quick-action → narrative timeline, zero
  `validate_yaml`/`compile_yaml`/`get_step_type` calls in the transcript.
- **Verified:** the triage slice (`tools_for_intent("triage")` / connector
  `_tools_for_intent`) and `_BUILD_ONLY_TOOLS` already exclude every authoring
  tool — so Anthropic never advertised them. The leak therefore required the
  name to arrive some other way (model/widget/replay). **Fix (connector-side
  defense-in-depth):** `anthropic_provider.stream` now builds `allowed_names`
  from the advertised (intent-filtered) tool list and routes BOTH dispatch
  paths through `_guarded_dispatch`, which refuses to execute any tool not in
  that set (returns an `{ok:false}` envelope instead of authoring/mutating).
  **Tests:** `fsr_playbooks/tests/test_intent_slice_and_params.py` asserts the
  triage slice excludes all of `BUILD_ONLY_TOOLS` and keeps the core
  discovery tools.
- **Status:** DONE · **Priority:** _

### A3 — Triage uiIntent hides the YAML pane + Create button
- **Symptom:** #6 (no YAML in editor), #6b (no Create button; "Ready to
  automate this?" shown instead).
- **Evidence:** the agent's final message *did* carry a ```yaml fence (export
  ~line 2231), so `currentYaml` was set — but it never rendered.
- **Files:**
  - `widget/view.html:1788` — `ng-if="currentYaml && uiIntent !== 'triage'"`
    gates the whole `.yaml-pane` (editor + Create Playbook button at :1803).
  - `widget/view.html:1738` — `"Ready to automate this?"` is the triage
    empty-state header the user actually saw.
  - `_extractYaml` `view.controller.js:1634`; `last_assistant_yaml` fallback
    `:1524`.
- **Root cause:** not a YAML-extraction bug — the intent gate suppresses build
  affordances in triage.
- **Proposed fix (NEEDS-DECISION):** options —
  (a) if the agent emits authorable YAML in triage, surface a "switch to Build
  mode to create this" CTA rather than silently hiding it;
  (b) make the YAML pane visible whenever `currentYaml` is set, regardless of
  uiIntent;
  (c) keep triage clean and rely on A1/A2 so YAML is never produced in triage.
  Preference: A1+A2 first (prevent), then decide on a deliberate handoff CTA.
- **DECISION (Dylan):** option (a) — defensive handoff CTA. Implemented widget-side.
- **Implemented (widget):**
  - `view.controller.js` — `hasTriageDraft()` (triage + idle + `currentYaml`) and
    `openDraftInBuild()` (flips `uiIntent` to `build`, revealing the existing
    pane gated at `view.html:1788`). Test probe gains `seedTriageDraft`/
    `openDraftInBuild`/`hasTriageDraft`.
  - `view.html` — `[data-testid="triage-draft-handoff"]` CTA + `open-draft-in-build`
    button, rendered only when `hasTriageDraft()`. Pane gate left unchanged so
    the YAML stays build-only until the analyst opts in.
  - Tests: `widgets-src/fsrPlaybookBuilder/tests/triageDraft.export.test.js` (jest) +
    `tests/e2e/fsrPlaybookBuilder.triageDraft.spec.js` (e2e) — both green.
- **Status:** DONE (widget) · **Priority:** _

### A4 — Triage prompt doesn't explicitly forbid YAML / handle timeline asks
- **File:** `fsr_playbooks/agent/system_prompt_triage.md`
- **Proposed fix:** add an explicit clause: triage never authors YAML; for
  timeline/summary requests, produce a narrative ordered-events summary from
  get_record + enrichment, and offer "save as playbook" only via the
  playbook_offer flow.
- **Done:** added a Hard rule to `system_prompt_triage.md` — "Never author a
  playbook here": no fenced ```yaml, no hand-written steps, no YAML tools; a
  "build/create/make a timeline" ask is a request for a narrative answer; the
  only path to a playbook in triage is `emit_playbook_offer` after a
  containment run.
- **Status:** DONE · **Priority:** _

---

## B. Enrichment discovery is noisy and buries the good connectors (#2)

IP enrichment returned **count: 61**, AlienVault-dominated, and **excluded
VirusTotal despite it being configured + Available** (export line 374) because
`limit:15` + alphabetical sort cut it off.

### B1 — Wrong-indicator + non-enrichment ops match
- **Evidence:** for `target_type=ip` the result included
  `get_domain_reputation`, `get_url_reputation`, `get_file_reputation`,
  `get_pulse_indicators` (not IP), `fortigate get_addresses`,
  `get_blocked_ip`, and the `exploit-prediction-scoring-system` connector.
- **Files:** `fsr_playbooks/mcp_server/tools_triage.py`
  - `_TARGET_KEYWORDS` :297 (`ip → ("ip","address","blacklist")`)
  - `_is_enrichment_op` :337 (generic intel token passes regardless of indicator)
  - `_INTEL_TOKENS` :318 (`"score"` pulls in EPSS; `"address"` pulls in fw addrs)
  - no `get_`/`list_` config-read exclusion (unlike containment's
    `_NON_ACTION_PREFIXES` :290).
- **Proposed fix:** when a `target_type` is given, require the indicator
  keyword match unless the op is connector-agnostic generic (`ioc_search`,
  `get_reputation`); drop generic-token-only ops that name a *different*
  indicator; exclude config-read prefixes + the EPSS connector for IP/host.
- **Done:** `_is_enrichment_op` now takes the `target` type (not the keyword
  tuple) and rejects ops naming only a *different* indicator
  (`get_domain_reputation`/`get_url_reputation`/`get_file_reputation` for ip)
  via a new `_INDICATOR_TOKENS` map. Dropped `"score"` from `_INTEL_TOKENS`
  (no more EPSS) and `"address"` from the ip tokens (no more firewall
  `get_addresses`). Callers updated to the new signature. **Tests** in
  `test_runop_tier_and_enrichment.py` cover the wrong-indicator + EPSS drops.
- **Status:** DONE · **Priority:** _

### B2 — Alphabetical ranking buries preferred connectors
- **Evidence:** `actions.sort(key=lambda a:(deprecated, connector, op))`
  tools_triage.py:787 → AlienVault (a) first, VirusTotal/Shodan/IPQS/FortiGuard
  (v/s/i/f) fall off `limit`.
- **Cross-ref:** memory `agent_no_alienvault_otx` — prefer VT/FortiGuard/Shodan/
  IPQS, de-prioritize AlienVault. Tool currently does the opposite.
- **Proposed fix:** rank by a preference list (VT, FortiGuard, Shodan, IPQS
  high; AlienVault low), and cap per-connector (e.g. ≤3) so one chatty
  connector can't crowd the slate. Same treatment for `find_containment_actions`
  if relevant.
- **Done (enrichment):** added `_ENRICH_CONNECTOR_RANK` + `_enrich_connector_rank`
  (VT/FortiGuard rank 0; Shodan/IPQS/GreyNoise/AbuseIPDB/urlscan rank 1;
  unlisted mid-band 5; AlienVault/OTX rank 9) and sort by it before `limit`,
  then cap at `_ENRICH_PER_CONNECTOR_CAP = 3` per connector. **Tests** assert
  preferred connectors outrank AlienVault and unknowns land mid-band.
  `find_containment_actions` left on alphabetical for now (not implicated).
- **Status:** DONE · **Priority:** _

---

## C. Tool-status + reference-sync papercuts

### C1 — `list_configured_connectors` mislabeled `(error)` with valid data (#3)
- **Evidence:** export tags it `_(error)_` though it returned
  `{configured:[…], count:26}`.
- **Root cause:** `ev.resultStatus` is set server-side; the tool returns no
  `ok:true` (unlike siblings), so the connector's classifier treats missing
  `ok` as failure. Widget side: `view.controller.js:971` only renders the label.
- **File:** `fsr_playbooks/mcp_server/tools_triage.py:842` (`list_configured_connectors`
  returns `{configured, probed, count}` — no `ok`).
- **Proposed fix:** return `{"ok": True, ...}`; OR fix the connector result
  classifier to treat a payload+missing-`ok` as success. Audit other tools that
  omit `ok`.
- **Done:** `list_configured_connectors` now returns `{"ok": True, ...}`.
- **Status:** DONE · **Priority:** _

### C2 — `unknown priority 'High'` is an unsynced picklist, not a model error (#5)
- **Evidence:** `valid: (none synced — run the modules probe)` — the connector
  DB has zero WorkflowPriority rows.
- **File:** `fsr_playbooks/compiler/resolver/__init__.py:43-74` (`_resolve_priority`).
- **Proposed fix:** (a) sync WorkflowPriority into the connector reference DB;
  (b) when the list is empty/unsynced, leave priority unset **silently** (no
  `bad_value` warning) — an unsynced reference table must not read as an
  authoring bug.
- **Done (b):** `_resolve_priority` now returns silently with priority unset
  when the picklist has zero rows (no warning). A synced-but-unknown name still
  warns. **Tests:** `python/tests/test_resolver_priority.py`. (a) syncing
  WorkflowPriority into the connector DB is a separate probe task — not done
  here.
- **Status:** DONE · **Priority:** _

---

## D. Build-quality / authoring scaffold (#4 deep)

The transcript shows the agent rediscovering the schema by failing:
`templates:`→`playbooks:`, `stepType:`/`SetVariables`→`type:`/`set_variable`,
guessed `get_api_response` on cyops_utilities (nonexistent), `get_ip_reputation`
param-set conflict, `block_ip_new` bad `time_to_live`. Each cost a validate
round-trip.

### D1 — Canonical starter template on first authoring turn
- **Proposed fix:** inject a correct skeleton (`start → set_variable →
  connector → decision`) with the right keys when a build session begins with
  no YAML, so the model edits a valid base instead of inventing structure.
- **Done (prompt-level):** added a "Canonical skeleton" section to
  `system_prompt_build.md` (`playbooks:` not `templates:`; `type: start →
  set_variable → connector → decision`) so the model edits a correct base. A
  deterministic code-injected skeleton on the first turn was NOT added — the
  prompt skeleton covers the failure mode (wrong top-level keys / step grammar)
  without new plumbing; revisit if drift persists.
- **Status:** DONE · **Priority:** _

### D2 — "Look up before you write" hard rule in build prompt
- **File:** `fsr_playbooks/agent/system_prompt_build.md`
- **Proposed fix:** mandate `get_step_type` + `find_operation`/`get_op_schema`
  before writing any not-yet-used step/op; never guess an op name. The model
  only learned `set_variable` after 3 failures and guessed `get_api_response`.
- **Done:** added a "Look up before you write — hard rule" to
  `system_prompt_build.md`: resolve any not-yet-confirmed step via
  `get_step_type` and any op via `find_operation`/`get_op_schema` before
  writing it; never guess an op name, step `type`, or param name.
- **Status:** DONE · **Priority:** _

---

## E. My own dig — additional optimizations (beyond the 6 reported)

- **E1 — `required_params` returns duplicates.** `block_ip_new` listed `ip` and
  `ip_group_name` twice (export lines 232-273). `_required_params`
  (tools_triage.py:383) doesn't dedupe across conditional param groups → noisy
  schema hints. Dedupe by `name`. **DONE** — `_required_params` now dedupes by
  name (first occurrence wins, preserves `ord`); test in
  `test_intent_slice_and_params.py`.
- **E2 — Param-set conflicts surface only at validate, not at discovery.**
  `get_ip_reputation` has a parent-param gate (`indicator_type`/`ip_address`
  valid only when parent=`''`). The agent can't know this from
  `find_enrichment_actions`/`required_params`; it learns at validate_yaml.
  Consider surfacing feasible param-sets in `required_params` or op schema
  hints. **TODO**
- **E3 — `get_op_schema` verbose output is enormous** (the AlienVault IP
  reputation `output_schema_json` is ~1000 lines of empty-string keys). It
  bloats both the model context and the export.
  **DECISION (Dylan):** FortiSOAR's static operation output schema isn't typed
  correctly (empty-string scaffold) — exclude it entirely; to learn an op's
  output shape, run the action (if safe) and read the run-derived schema.
  **DONE** — `get_op_schema` (`tools_discovery.py:681,707`) now drops
  `output_schema_json` + `conditional_output_schema_json` from the verbose row
  and keeps only `output_schema_observed`; the slim hint reports `observed` when
  present, else steers a read-only (safe, via `_op_risk`) op to `run_op` to
  observe the real shape. Static scaffold no longer reaches the model.
  Tests: `python/tests/test_op_params.py`
  (`test_get_op_schema_excludes_untyped_static_output_schema`,
  `…_slim_hint_steers_to_run_op_for_safe_ops`,
  `…_slim_hint_reports_observed_when_present`).
  NOTE: `validator.py:125` still reads `output_schema_json` as a *top-level-key*
  fallback for binding validation — key *names* are correct even though types
  aren't, so it's harmless and not surfaced to the model; left as-is.
  The build-prompt "run safe ops to observe output" clause is deferred to avoid
  clobbering the connector agent's concurrent `system_prompt_build.md` edits.
- **E4 — Tier classifier `(False,True)` self-correct path** (`_tier_for_run_op`
  / `_op_presence`, llm/tools.py:216-250) is sound but untested against the
  enrichment leak; confirm guessed ops on known connectors still bounce a
  correction rather than gating. **VERIFIED** — `test_runop_tier_and_enrichment`
  (`test_guessed_op_on_known_connector_does_not_escalate` et al.) still green
  after the B1 changes; guessed ops stay tier 1 → self-correct.
- **E5 — `find_enrichment_actions` ran with `probe:true` over 61 candidates**
  → healthchecks many connectors. The scoped-probe optimization (step 3) only
  probes candidate connectors, but 61 candidates across ~10 connectors is still
  latency. Tightening B1 (fewer candidates) also cuts probe cost. **PARTIAL** —
  B1 (cross-indicator + EPSS/address drops) and B2 (per-connector cap ≤3)
  materially shrink the candidate set, cutting probe fan-out; no dedicated
  probe-budget cap added.

---

## F. Export format for analysis (Dylan's question)

Current export is a full Markdown dump of every event incl. entire tool
results (the AlienVault output schema alone blew the 25k read cap). More
efficient options, in preference order:

1. **Structured JSON sidecar** (`*.events.json`): the raw event list already
   exists (`$scope.form.exportText` is built from it). Emitting the event array
   verbatim lets an analyst/agent grep + slice instead of paging a 2,500-line
   md. Cheapest to add — the data is already in memory.
2. **Trimmed Markdown profile:** keep tool *names*, *inputs*, *ok/error*, and
   *error bodies*; replace large successful tool results with a one-line shape
   summary (`{count:61, first:[…3]}`). Most of the 43k tokens here were
   success-path payloads nobody needs to read.
3. **Per-turn boundaries + a header manifest** (intent, tool-call counts,
   error count, final YAML present y/n) so the failure shape is visible without
   reading the body.

Recommendation: add an opt-in `.events.json` alongside the md (option 1) — zero
information loss, trivially machine-readable — and apply option 2 trimming to
the human-facing md.

- **DECISION (Dylan):** option 1 only (`.events.json` sidecar). Markdown trimming
  (option 2) deferred.
- **Implemented (widget):** `view.controller.js` — `_buildExportEventsJson()`
  emits a `{manifest, messages, currentYaml, clientEventLog}` doc. The
  `manifest` carries intent, `toolCallCount`, per-name `toolCallsByName`,
  `errorCount`, `finalYaml` y/n, usage — so the failure shape is visible without
  reading the body. `$scope.downloadExportJson()` writes
  `fsrpb-chat-<session>.events.json` (same `_scrubSecrets` pass as the md).
  `view.html` export modal gains `[data-testid="export-download-json"]`.
  Tested in `triageDraft.export.test.js` (manifest counts) + the e2e download.
- **Status:** DONE (widget; option 2 deferred) · **Priority:** _
