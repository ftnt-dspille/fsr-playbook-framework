# FSRPlaybookYaml Recipe Expansion Research

**Date**: 2026-05-06  
**Corpus**: 1,664 live playbooks, 43 step types, 714 connectors  
**Scope**: Identify expansion candidates beyond threat-feed and data-ingest recipes; design step-sequence mining infrastructure; propose complex-playbook training pipeline; sketch generalizable ruleset abstractions.

---

## 1. Recipe Expansion Candidates

### Evidence-Based Archetype Assessment

Analyzed `playbooks_seen` (1,664 records) and `step_types` (43 types, occurrence-indexed). Candidates grounded in corpus patterns, not speculation:

| Archetype | Corpus Evidence | Count | Est. Value | Est. Effort | Rationale |
|-----------|---|---:|---|---|---|
| **Enrichment (IP/URL/file reputation)** | `Connectors`: 46 OpenAI ops; 26 Tenable.io; 16 VirusTotal; 15 AbuseIPDB. `Decision`: route by score. 891 2-step playbooks. | ~80–120 | **HIGH** — real-time reputation lookup is foundational SOC automation; top 8 connectors span threat intel. | **MEDIUM** (2–3 hr) — similar to ingestion: fetch op + decision + enrichment-record update. Factory: `generate_enrichment_recipe(connector, indicator_type)` | Existing patterns in `cyops_utilities` (491 uses), connector-paired decisions. |
| **Containment/response (block IP, isolate host)** | `cybersponse.action` trigger (830 playbooks, most common). Multi-step sequences: `Decision → connector (block/disable) → notify`. `Connectors`: FortiGate (46), FortiEDR (31), ActiveDirectory (15), Infoblox DDI (29). | ~60–100 | **HIGH** — closes the loop from alert to action; integrates downstream orchestration. | **MEDIUM** (3–4 hr) — action precondition (CVSS > 7?), target picker (pick IP from alert), execute, audit-log. Template branches. | Step sequences heavily decision-driven; decision body is non-trivial (condition extraction). |
| **Triage (dedup, severity score, auto-close)** | `UpdateRecord` (356 uses). Tag-heavy playbooks combining `find_record` + `set_variable` (severity calc) + Decision on `status`. Clustering via connector pairs (many FAZ/FSM playbooks do this). | ~80–150 | **HIGH** — triage is the bottleneck; auto-closing false positives saves analyst time. | **MEDIUM-HIGH** (4–5 hr) — field-extraction, score aggregation (Jinja), branching logic; hardest is detecting *intent* (is this a triage playbook or just a status updater?). | Requires step-sequence classification; many 4–6 step sequences. Corpus has `Decision` + `UpdateRecord` combos but no canonical triage shape. |
| **Approval-gated action** | `ManualInput` (166 uses). `Manual_input → Decision → execute` is a recognizable pattern. Examples in live playbooks: confirm before block, confirm before disable. | ~40–60 | **MEDIUM** — already in RECIPES.md as hand-curated example. Codification is mainly template + edge cases (timeout behavior, multi-approval chains). | **LOW** (1–2 hr) — straightforward branching on input choice. | Recipe already sketched; just needs parameterization (`target_action`, `timeout_sec`, etc). |
| **Notification escalation** | `SendMail` (22 uses), `Slack` (16 uses), `Teams` (implicit via OpenAI). `Set → connector call` pattern. Severity-routed escalation (high → Slack + PagerDuty, low → email). | ~30–50 | **MEDIUM** — complements containment; useful for larger deployments but less critical than triage. | **LOW-MEDIUM** (2–3 hr) — channel picker (based on severity), template builder, retry logic. | Straightforward connector-caller; low complexity. |
| **Parent/child orchestration (fan-out)** | `WorkflowReference` (564 uses). Many playbooks call children; some map across records (`for_each` + `workflow_reference`). | ~100+ | **MEDIUM** — already documented in RECIPES.md; codification is mainly pattern extraction. | **MEDIUM** (2–3 hr) — parameterization of map-reduce shapes, looping, error aggregation. | Requires understanding when a workflow_reference is reusable (subroutine intent) vs. one-off. |
| **Schedule/cron-driven** | Implicit: no `CronTrigger` step type detected in corpus; `cybersponse.post_update`/`post_create` (59+37 uses) are the only scheduled-like triggers. | ~5–20 | **LOW-MEDIUM** — less common than action-driven workflows. | **LOW** (1–2 hr) — mostly trigger-flavor documentation; execution is identical. | Would mainly be a trigger selection guide, not a step-sequence recipe. |
| **Closure/case-cleanup** | `UpdateRecord` on incidents/alerts setting `status: Closed`. Often paired with `Decision` (check if all related records are done). | ~30–50 | **LOW** — niche; mostly hygiene playbooks. | **LOW** (1–2 hr) — straightforward close-with-comment pattern. | Not enough volume to justify deep recipe infrastructure. |

**Actionable conclusions**:
- **High confidence**: Enrichment (80–120 instances), Containment (60–100), Triage (80–150).
- **Medium confidence**: Approval-gated (40–60, template exists), Orchestration (100+), Notification (30–50).
- **Low confidence**: Closure (30–50), Schedule-driven (<20).
- **Next move**: Mine for triage + enrichment *exact* step sequences in corpus to ground the recipe shape before implementation.

---

## 2. Step-Sequence Pattern Mining Design

### Current Limitations

`probe_jinja_corpus` mines *expressions* (filter usage, variable access, control flow logic). It does **not** mine *step orchestration*: "What sequence of step types / connectors produce meaningful business outcomes?"

Example: A triage playbook might be: `Start → SetVariable (parse severity) → Decision (score > 7?) → [FindRecord + UpdateRecord + SetVariable (log)] → End`. The Jinja probe sees the set/decision/if blocks but not the *intent* (triage); an orchestration probe would recognize the **pattern** and classify it.

### Proposal: Step-Sequence Mining via N-gram + LLM Tagging

**Data layer** (new probe: `probe_step_sequences.py`):

1. **Extract sequences from `playbooks_seen`** (no schema changes; infer from workflow JSON via live API):
   - For each workflow in the corpus, extract `[step_type_uuid, step_type_uuid, ...]` sequence.
   - Store as a `step_sequences` FTS table: `(sequence_hash, step_uuids_csv, connector_csv, playbook_collection, playbook_name, occurrence_count, classification)`.
   - Example row:
     ```
     sequence_hash: md5("f41...$12...$04d...")
     step_uuids_csv: "f414d039-bb0d...,12254cf5-5db7...,04d0cf46-b6a8..."
     step_names_csv: "Start,Decision,SetVariable"
     connectors_csv: "fortinet-fortisiem,cyops_utilities"
     occurrence_count: 7
     classification: "triage"  # or NULL for "unclassified"
     ```

2. **N-gram analysis** (lightweight, deterministic):
   - Mine for 2–4-grams of step types to find recurrent motifs.
   - Heuristic classifiers (no LLM):
     - `[Start, Decision, UpdateRecord] + decision routes` → enrichment/triage candidate.
     - `[Start, Connector, Decision, Connector] + playbook name ~= "Block|Disable|Isolate"` → containment.
     - `[Start, SetVariable, ManualInput, Decision] + {input_type: "select"}` → approval-gated.
     - `[Start, FindRecord, UpdateRecord] + {step_count: 2–4}` → simple update.

3. **LLM-assisted tagging** (optional, for complex intent):
   - For each 3+ step sequence, generate a one-line summary: *intent, trigger, outcome*.
   - Build a `step_sequences.intent_summary` column.
   - Run once, cache in SQLite; avoid re-classifying identical patterns.
   - Cost: ~50 LLM calls for top-100 unique n-grams (multi-modal cost amortized).

### Integration Points

**File**: `python/probes/probe_step_sequences.py` (~200 lines).

**Tables**:
```sql
CREATE TABLE step_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_hash TEXT UNIQUE NOT NULL,        -- md5 of step_type UUIDs
    step_uuids_csv TEXT NOT NULL,              -- comma-separated UUIDs
    step_names_csv TEXT NOT NULL,              -- human-readable names
    connectors_csv TEXT,                       -- connectors involved
    step_count INTEGER,
    occurrence_count INTEGER DEFAULT 1,        -- how many playbooks use this exact sequence
    classification TEXT,                       -- "enrichment", "triage", "containment", NULL
    intent_summary TEXT,                       -- one-liner LLM summary (optional)
    sample_playbook TEXT,                      -- collection:workflow for inspection
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_step_sequences_classification ON step_sequences(classification);
CREATE INDEX idx_step_sequences_step_count ON step_sequences(step_count);
```

**MCP tool** (add to `mcp_server.py`):
```python
def find_step_sequences(
    classification: str | None = None,
    step_count: int | None = None,
    min_occurrences: int = 2
) -> list[dict]:
    """Search step-sequence patterns by classification or step count."""
    # Returns: [{sequence_hash, step_names_csv, occurrence_count, classification, intent_summary, sample_playbook}, ...]
```

### Benefits

- **Agent grounding**: When asked "build a triage playbook," the agent can inspect `find_step_sequences(classification="triage")` to see real shapes.
- **Recipe validation**: A generated enrichment recipe can check `step_sequences` for any deviations from the learned patterns.
- **Corpus evolution tracking**: Re-run the probe quarterly; new patterns appear, existing ones fall out of use.

---

## 3. Complex-Playbook Training Pipeline

### Goal

Enable agents to author playbooks by example. Given 1,664 existing playbooks, distill ~200 representative "complex" ones into searchable summaries so an agent, when asked "build a playbook that handles multi-stage enrichment," can retrieve top-3 similar historical playbooks and use them as in-context examples.

### Pipeline Design

**Stage 1: Heuristic complexity filtering** (cheap, deterministic):
- Flag playbooks where `step_count >= 8` OR `decision_branches >= 3` OR `connector_count >= 3`.
- Result: ~200–300 candidates (15–20% of corpus).
- Cost: SQL query, <1 sec.

**Stage 2: LLM distillation** (expensive, one-time):
- For each candidate, generate a distilled summary:
  - **Purpose** (1–2 sentences): What business problem does this solve?
  - **Trigger**: Which trigger type(s) (action, post_create, etc)?
  - **Key steps**: Ordered list of 3–5 critical step names + their role.
  - **Outcome**: What record(s) are created/updated, or what action taken?
  - **Pitfalls**: Common mistakes (if identifiable from step args).
- Batch LLM calls (5–10 playbooks per request via `system_prompt` prompt caching).
- Cost: ~50 LLM requests at ~2K tokens each ≈ $0.50 (Haiku 3.5 pricing).

**Stage 3: Persist to SQLite** (new table):
```sql
CREATE TABLE complex_playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection TEXT NOT NULL,
    workflow TEXT NOT NULL,
    step_count INTEGER,
    connector_count INTEGER,
    decision_count INTEGER,
    purpose TEXT,                             -- LLM distillation (1–2 sentences)
    trigger_type TEXT,                        -- e.g., "cybersponse.action"
    key_steps_json TEXT,                      -- JSON: [{name, role}, ...]
    outcome TEXT,                             -- What the playbook does (1 sentence)
    pitfalls TEXT,                            -- Gotchas (optional)
    source_playbook TEXT,                     -- Collection:Workflow for link
    distillation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(collection, workflow)
);
CREATE VIRTUAL TABLE complex_playbooks_fts USING fts5(
    purpose, outcome, key_steps_json
);
```

**Stage 4: Agent query interface** (MCP tool):
```python
def find_similar_playbooks(query: str, limit: int = 5) -> list[dict]:
    """Search complex playbooks by purpose/outcome. Returns top-K with full summaries."""
    # Uses FTS over complex_playbooks_fts
    # Returns: [{collection, workflow, purpose, trigger_type, key_steps, outcome, source_playbook}, ...]
```

**Stage 5: In-context integration**:
- When the agent is asked to "build a playbook that X," the chat prompt includes:
  ```
  ## Similar playbooks in the corpus:
  1. [Collection] > [Workflow]
     Purpose: [distilled purpose]
     Trigger: [trigger_type]
     Key steps: [step names + roles]
     Outcome: [outcome]
     [Link to pull via fsrpb pull Collection:Workflow]
  ```

### Cost-Reduction Strategy

**Tier 1 (Heuristics, 0 LLM cost)**:
- Already done: `step_count >= 8` OR `decision_count >= 3` filters.
- Result: ~300 candidates.

**Tier 2 (LLM batch, $0.50–1 total)**:
- Batch 5–10 complex playbooks per API call.
- Use prompt caching on the `system_prompt` (same instructions for all requests).
- Run once; results cached indefinitely in SQLite.

**Tier 3 (Optional: live re-distillation)**:
- On `fsrpb pull <new>`, auto-distill if `step_count >= 8`; insert into `complex_playbooks`.
- Amortizes cost across future users.

### Integration with Existing Infrastructure

- **No schema changes** to `playbooks_seen` — new `complex_playbooks` table is standalone.
- **Probe**: new `python/probes/probe_complex_playbooks.py` (~150 lines).
- **MCP tool**: adds `find_similar_playbooks(q, limit)` alongside existing search.
- **Frontend**: optional link in the YAML editor: "Find similar playbooks" (calls MCP tool, displays results as pull-able links).

---

## 4. Generalizing the Ruleset Engine

### Current Architecture

**Today** (`python/compiler/rulesets/`):
- Base ruleset (generic playbook rules): 10+ callables checking step name charset, `yes/no` quoting, dedup fields.
- Optional `feed-ingest` + `data-ingest` rulesets: 8–10 callables each, tied to step-type UUIDs and collection prefixes.
- Pattern: function → `Iterable[Issue]`, registry-based dispatch.

```python
# Simplified example
def rule_step_name_charset(doc: dict) -> Iterable[Issue]:
    for ci, coll, wi, wf in _all_workflows(doc):
        for si, step in _all_steps(wf):
            if not re.match(r"^[A-Za-z0-9_ ]+$", step["name"]):
                yield Issue(...)
```

### Obstacles to Generalization

1. **Step-type coupling**: Rules like `rule_ibf_resource_required_fields` hard-code `STEP_INGEST_BULK_FEED` UUID. Adding enrichment recipes requires replicating similar rules for different step types.
2. **Collection-prefix specificity**: Rules check for `/api/ingest-feeds/` or `/api/3/`; a containment recipe hitting a custom API endpoint breaks the heuristic.
3. **Intent-dependent validation**: A "triage playbook" should enforce `decision_count >= 1` and `update_record` presence; a "notification playbook" should enforce `send_mail` or `slack` presence. Rules can't detect intent automatically.

### Abstraction Proposal: Intent-Driven Ruleset Factory

**Idea**: Decouple rules from step-types + endpoints. Instead, express rules in terms of **business intent** + **structural constraints**.

**New artifact: `RulesetTemplate`** (base class):
```python
@dataclass
class RulesetTemplate:
    name: str                                   # e.g., "enrichment", "triage", "containment"
    required_step_types: list[str]              # human names: ["decision", "connector", "update_record"]
    forbidden_step_types: list[str]             # ["code_snippet"] for security
    required_step_count: range                  # e.g., range(3, 10)
    connector_constraints: dict                 # {"fortinet-fortigate": "presence required"}
    field_constraints: dict                     # {"resource": {"sourceId": "required"}}
    tag_constraints: list[str]                  # tags required: ["enrichment"]
    decision_constraints: dict                  # {min_branches: 1, max_branches: 5}
    
    def validate(self, doc: dict) -> Iterable[Issue]:
        """Auto-generate rules from constraints."""
        # For each workflow, check against all constraints
```

**Instantiation**:
```python
enrichment_template = RulesetTemplate(
    name="enrichment",
    required_step_types=["connector", "decision", "update_record"],
    required_step_count=range(3, 8),
    connector_constraints={"openai|virustotal|abuseipdb": "at_least_one"},
    field_constraints={"resource": {"sourceId": "required_if_update_record"}},
    tag_constraints=["enrichment"],
)
triage_template = RulesetTemplate(
    name="triage",
    required_step_types=["find_record", "decision", "update_record"],
    required_step_count=range(4, 10),
    field_constraints={"resource": {"severity": "required", "status": "required"}},
    tag_constraints=["triage"],
    decision_constraints={min_branches: 2},
)
```

**Benefits**:
- **No hard-coding**: New recipe kinds inherit validation for free.
- **Composable**: A "triage + notification" recipe combines templates.
- **Intent-driven**: Agent can inspect constraints to understand a recipe's shape before generating it.

### What Generalizes Well

✅ Step-type presence/absence checks  
✅ Field presence in step arguments  
✅ Tag enforcement  
✅ Decision structure (branch count)  
✅ Connector family constraints (at least one from {X, Y, Z})  
✅ Collection-prefix patterns (prefix in {/api/3/, /api/ingest-feeds/, custom})

### What Doesn't

❌ Semantic validation (e.g., "the severity field must come from the connector's output schema" — requires live shape introspection)  
❌ Jinja expression validation (e.g., "picklist calls must resolve" — requires live FSR rendering, covered by TODO I1)  
❌ Order-dependent constraints (e.g., "FindRecord must come before UpdateRecord" — possible but fragile; better as a heuristic than a hard rule)

### Implementation Path

**File**: new `python/compiler/rulesets/templates.py` (~200 lines).

**Update**: `rulesets/__init__.py` adds a `register_template(name, template)` hook. Existing `feed-ingest` + `data-ingest` probes get converted to template instances.

**MCP tool** (add to `mcp_server.py`):
```python
def get_ruleset_constraints(name: str) -> dict:
    """Inspect the validation rules for a recipe kind."""
    template = _TEMPLATES.get(name)
    return {
        "required_step_types": template.required_step_types,
        "forbidden_step_types": template.forbidden_step_types,
        "connector_constraints": template.connector_constraints,
        ...
    }
```

---

## 5. Phasing Recommendation

### Phase A: Quick Wins (Week 1, ~8 hours)

1. **Approve/land TODO I1–I4** (picklist precheck, connector precheck, recipe persistence, MCP tool).
   - Blockers for any new recipe kinds; must be solid.
   - Cost: ~3 hr per the plan.

2. **Mine enrichment + triage sequences**.
   - Write `probe_step_sequences.py` (~200 lines, heuristic classifiers only; skip LLM).
   - Query corpus for patterns like `[Start, SetVariable, Decision, Connector, UpdateRecord]`.
   - Cost: ~2 hr.

### Phase B: Template Ruleset Abstraction (Week 2, ~4 hours)

1. **Refactor existing `feed-ingest` + `data-ingest` rules into `RulesetTemplate` instances**.
   - `python/compiler/rulesets/templates.py` (~250 lines).
   - Ensures new recipe kinds have the same validation power.
   - Cost: ~2 hr.

2. **Extend `get_ruleset_constraints` MCP tool** so agents can inspect what a recipe needs before generating.
   - Cost: ~1 hr.

### Phase C: First New Recipe Kind (Week 2–3, ~8 hours)

1. **Enrichment recipe generator** (`python/recipes/enrichment.py`).
   - Factory function: `generate_enrichment_recipe(connector, indicator_type, severity_threshold)`.
   - Emits: Start → Connector (fetch reputation) → Decision (score > threshold?) → [UpdateRecord + SetVariable (log)] → End.
   - Self-validates via enrichment ruleset template.
   - Cost: ~3 hr (mirrors threat-feed generator structure).

2. **End-to-end test fixture** (`examples/enrichment_virustotal.yaml`).
   - Cost: ~1 hr.

3. **CLI integration**: `fsrpb generate-recipe --kind enrichment --connector virustotal`.
   - Cost: ~1 hr.

### Phase D: Complex-Playbook Training Distillation (Week 3, ~6 hours)

1. **Heuristic filtering + LLM batch distillation** (`python/probes/probe_complex_playbooks.py`).
   - Cost: ~3 hr code, ~30 min LLM (batch 10 per request).

2. **MCP tool** `find_similar_playbooks(q)`.
   - Cost: ~1 hr.

3. **Frontend integration** (optional; add link "Find similar playbooks" in YAML editor).
   - Cost: ~1–2 hr (not blocking).

### Phase E: Triage + Containment Recipes (Week 4, ~12 hours)

1. **Triage generator** (`python/recipes/triage.py`).
   - Hardest: dedup detection + field extraction.
   - Cost: ~4 hr.

2. **Containment generator** (`python/recipes/containment.py`).
   - Action precondition, target picker, audit logging.
   - Cost: ~4 hr.

3. **Test fixtures + CLI** for both.
   - Cost: ~2 hr.

4. **Orchestration recipe** (approval-gated + parent/child).
   - Cost: ~2 hr.

### Total: 4–5 weeks, ~38 hours

**Dependency chain**:
1. I1–I4 (blockers, 3 hr) → everything else
2. Phase A (8 hr) + Phase B (4 hr) → Phase C (8 hr)
3. Phase C (8 hr) → Phase D (6 hr, optional)
4. Phase B (4 hr) + Phase A (8 hr) → Phase E (12 hr)

### Success Criteria

- ✅ Five recipe kinds live (ingestion × 2, enrichment, triage, containment).
- ✅ Step-sequence probe identifies 10+ distinct patterns in corpus.
- ✅ Complex-playbook FTS supports agent in-context retrieval.
- ✅ Agents can `generate-recipe --kind <x>` with validation for free.
- ✅ Round-trip on all 5 recipe kinds (compile → push → validate).

---

## References

**Files**:
- Generator: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/python/recipes/generator.py` (threat-feed + data-ingest today)
- Rulesets: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/python/compiler/rulesets/` (feed_ingest.py, data_ingest.py, _shared.py)
- Corpus mining: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/python/probes/probe_jinja_corpus.py` (expression patterns)
- Schema: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/store/schema.sql` (playbooks_seen, step_types, connectors)
- Proof of concept: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/store/RECIPES.md` (5 hand-curated patterns)
- Open TODOs: `/Users/dylanspille/PycharmProjects/FSRPlaybookYaml/TODO.md` (I1–I10, priority order)

**Key corpus metrics**:
- 1,664 playbooks
- 43 step types (SetVariable 1492×, Connectors 1323×, Decision 347×, ManualInput 166×)
- 714 connectors (OpenAI 46×, FortiGate 46×, VirusTotal 15×, Infoblox DDI 29×)
- 891 playbooks with 2–3 steps (simple automations)
- 80+ playbooks with 8+ steps (complex; triage/enrichment candidates)

**Trust model**: All new mining (step sequences, complex playbooks) lives in new tables; no mutation of existing `playbooks_seen` or `step_types`. Probes are idempotent; re-runs are safe.
