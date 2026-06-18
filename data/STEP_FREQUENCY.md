# Step-type frequency in the FSR playbook corpus

Derived from `pb_examples/all_fsr_evoke_playbooks.json` — 119 collections,
**1,596 playbooks** total, generated 2026-05-03. Used to prioritise which
step types the e2e test harness must exercise.

## Trigger / start steps

| count | % of corpus | type | notes |
|-------:|-----:|---|---|
| 806 | 50.5 % | `cybersponse.action` (record context) | Right-click "Execute" on a record. No YAML short alias; trigger via `/api/triggers/1/action/<wf>` with a record IRI. |
| 690 | 43.2 % | `cybersponse.abstract_trigger` (manual / designer run) | What the YAML compiler emits today as `type: start`. Trigger via `/api/triggers/1/notrigger/<wf>`. |
| 54 | 3.4 % | `cybersponse.post_update` | Auto-runs after a record is saved. Event-driven; no manual trigger endpoint. |
| 36 | 2.3 % | `cybersponse.post_create` | Auto-runs after record creation. |
| 10 | 0.6 % | `cybersponse.api_call` | Triggered by an external REST API call. |

### Abstract-trigger sub-breakdown
- **manual / designer-run**: 690 (100 % of abstract_trigger). Scheduled
  triggers in this corpus are configured via the FSR scheduler tier,
  not as a step-level subtype.

### Top modules for record-context triggers
| count | module |
|------:|---|
| 640 | alerts |
| 52 | incidents |
| 51 | indicators |
| 41 | devices |
| 13 | netshot_targets |
| 12 | managers |
| 10 | netshot_target_outputs |
| 9 | threat_intel_feeds |
| 9 | z_t_p_profiles |
| 7 | assets |
| 7 | netshot_domains |
| 7 | warrooms |
| 6 | attachments |
| 6 | scenario |
| 6 | communication |

The vast majority of record-action playbooks fire on **alerts** (~80 % of
all record-context triggers).

## Main-body step types

| count | type | YAML short |
|-------:|---|---|
| 1386 | SetVariable | `set_variable` |
| 1256 | Connectors | `connector` |
| 539 | WorkflowReference | `workflow_reference` |
| 442 | CyopsUtilites (utility connector ops) | `connector` (connector=cyops_utilities) |
| 334 | UpdateRecord | `update_record` |
| 311 | Decision | `decision` |
| 273 | FindRecords | `find_record` |
| 236 | InsertData | `insert_record` |
| 150 | ManualInput | `manual_input` |
| 30 | Delay | `delay` |
| 24 | CodeSnippet | `code_snippet` |
| 20 | SendMail | (no short alias yet) |
| 10 | IngestBulkFeed | (no short alias) |
| 6 | ManualTask | (no short alias) |
| 3 | ApprovalManualInput | (no short alias) |

## E2E coverage gaps (priority order)

Tag legend: ✅ covered by an existing green fixture · 🔴 not covered.

### Triggers
1. ✅ `abstract_trigger` / `start` — `demo_pure_logic` + `demo_virustotal_ip`.
2. 🔴 `cybersponse.action` — half the corpus. Needs a fixture that
   triggers via record IRI (`fsrpb run-playbook ... --record alerts:<uuid>`).
   The e2e runner needs `--record` support; today it only does
   `/notrigger`.
3. 🔴 `post_update` / `post_create` — event-driven. E2E test needs to
   `POST /api/3/<module>` (or PUT) to provoke the trigger, then poll for
   a child workflow run. Trickier than `/notrigger`.
4. 🔴 `api_call` — external HTTP trigger. Lower priority (0.6 %).

### Main steps
1. 🔴 `workflow_reference` — 34 % of playbooks. Needs parent+child
   fixture; compiler already supports `target: <name>`. High priority.
2. 🔴 `find_record` (17 %) and `update_record` (21 %) — touch real
   module records. Need a fixture that inserts a tagged test record,
   finds it, updates it, asserts, deletes. Combined fixture covers both.
3. 🔴 `insert_record` (15 %) — covered by the find/update fixture above.
4. 🔴 `manual_input` (9 %) — half-async. The runner needs a "pause for
   manual input → respond → resume" mode. CLI tools `inputs list/show/
   respond` already exist; e2e runner needs to glue them in.
5. 🔴 `cyops_utilities` non-`no_op` ops (28 %) — `extract_artifacts_new`,
   `evaluate_email_template`, `make_cyops_request`, `attach_indicators`,
   `format_richtext`, `convert_to_json`. One fixture per top-3.
6. 🔴 `delay` (2 %) — trivial.
7. 🔴 `code_snippet` (1.5 %) — Python inside a step.
