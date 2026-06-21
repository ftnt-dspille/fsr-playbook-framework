---
title: Manual Input — Full Variant Catalog
category: playbook-authoring
status: reference
source: live-verified
topics:
- manual-input
- approval-steps
- form-builder
- variants
canonical: true
summary: 'Full variant catalog for ManualInput + ApprovalManualInput steps: 166 +
  4 examples from live appliance + UI form-builder.'
---

# Manual Input — full variant catalog

Sources:
- 166 `ManualInput` + 4 `ApprovalManualInput` step records on the live appliance (probed 2026-05-03 via `POST /api/query/workflow_steps`).
- FSR UI bundle `fsr_src/app.unmin.js` — form-builder + manual-input editor.
- `WorkflowStep` entity definition (PHP, see `store/incoming/recon_*/E_workflow_entities/WorkflowStep.php`).
- Canonical resume flow in `store/QUERY_API.md` and the `fsrpb inputs` CLI in `python/cli.py`.

## 1. Two top-level types

The `arguments.type` field switches the prompt's behavior:

| `type` | Live count | Meaning |
|---|---:|---|
| `InputBased` | 140 | User submits a form (any inputVariables) and/or picks a button. Default for almost all flows. |
| `DecisionBased` | 26 | Pure routing — user picks a button; **no input form is presented**. Each button is a branch. |

`is_approval: true` overlays the prompt with Approve/Reject styling but otherwise uses `InputBased` (the 4 `ApprovalManualInput` step-type records exist for legacy reasons; modern playbooks just set `is_approval=true` on a normal `ManualInput` step).

## 2. Top-level `arguments` keys

Stable across the corpus:

| Key | Always present? | Type | Notes |
|---|---|---|---|
| `type` | yes | `InputBased`/`DecisionBased` | See §1 |
| `input` | yes | `{schema: {title, description, inputVariables: []}}` | Title + description are jinja-templated; description is HTML-allowed |
| `record` | yes | string | `""` or `{{ vars.input.records[0]["@id"] }}` to attach the prompt to a record |
| `owner_detail` | yes | dict | See §4 (Assignment) |
| `step_variables` | yes | list | Variables exposed to downstream steps (typically empty for ManualInput) |
| `response_mapping` | yes | `{options: [...], duplicateOption, customSuccessMessage}` | See §3 |
| `email_notification` | 140/166 | `{enabled, smtpParameters}` | Send notification email when prompt opens |
| `isRecordLinked` | 137/166 | bool | Show on the linked record's "Tasks" panel |
| `inline_channel_list` | 136/166 | list of picklist IRIs | In-app notification channels (Slack-style mention sources) |
| `external_channel_list` | 136/166 | list of picklist IRIs | External notification channels (email-style) |
| `unauthenticated_input` | 136/166 | bool | Generate a public link the recipient can use without logging in |
| `resources` | 133/166 | string | Module name (`alerts`, `incidents`, `indicators`, …) |
| `agent_id` | 118/166 | uuid or null | Route to a specific agent (multi-tenant / remote) |
| `is_approval` | 88/166 | bool | UI styling: Approve/Reject buttons, approval audit trail |
| `external_email_subject`, `internal_email_subject` | 74/166 | string | Notification subject overrides |
| `customEmailExternal`, `custom_email_body_external`, `external_email_attachments` | ~73/166 | string/list | Custom external email body |
| `internal_email_attachments`, `custom_email_body_internal`, `customEmailInternal` | varies | string/list | Custom internal email body |
| `inputExternalUser` | 12/166 | bool | Allow non-FSR users to respond (paired with `unauthenticated_input` and external channels) |
| `timeout` | 22/166 | `{days, hours, minutes, step_iri}` | Auto-route to step_iri if no response within window |

## 3. `response_mapping` (the buttons)

```jsonc
"response_mapping": {
  "options": [
    {"option": "Block Completed", "primary": true,  "step_iri": "/api/3/workflow_steps/<uuid>"},
    {"option": "Unable to Block",                    "step_iri": "/api/3/workflow_steps/<uuid>"}
  ],
  "duplicateOption": false,           // allow same answer to fire multiple times?
  "customSuccessMessage": "Awaiting Playbook resumed successfully.",
  "connecteStepsLength": 0            // (typo in source) UI counter; 0 = unwired
}
```

- `option` is the button label the user clicks AND the value sent back as `response.response`.
- `primary: true` styles the button as the default action.
- `step_iri` is the next step that fires when this option is chosen — this is how `DecisionBased` branching is wired. Can be `null` (terminal — playbook ends after the answer).
- Live counts: 82 steps with 1 option, 81 with 2, 3 with 3 options. Three or more options is rare.

## 4. Assignment — `owner_detail`

```jsonc
"owner_detail": {
  "isAssigned": true|false,
  "assignedToTeam":   [{"iri": "/api/3/teams/<uuid>",  "teamname":  "SOC Team"}],
  "assignedToPerson": [{"iri": "/api/3/people/<uuid>", "firstname":"…", "lastname":"…"}],
  "assignedToRecord": false,           // route to record's owner field
  "assignedToField":  null,            // or a specific user field on the record
  "emailRecipients":  ""               // free-form email list
}
```

Either `assignedToTeam`, `assignedToPerson`, `assignedToRecord`, or `assignedToField` should be populated when `isAssigned=true`. The four are mutually exclusive for routing.

## 5. `input.schema.inputVariables` — the form

**No example in the live corpus** uses inputVariables; all 166 ManualInput steps have `inputVariables: []`. So all observed prompts are button-only (decision/confirmation) flows.

The UI's form-builder accepts these field types (registered via `getFormAttributes` in `app.unmin.js:26301`):

| Type | Notes |
|---|---|
| `text` | Single-line text |
| `textarea` | Multi-line text |
| `richtext` / `html` | WYSIWYG |
| `password` | Hidden text |
| `email`, `url`, `domain`, `filehash`, `phone` | Validated text variants |
| `integer`, `decimal` | Numeric |
| `checkbox` | Boolean |
| `datetime`, `date` | Date pickers |
| `select`, `multiselect` | Static enum |
| `picklist`, `multiselectpicklist` | FSR picklist-backed |
| `lookup` | Reference to another record (FSR module) |
| `array`, `json`, `object` | Structured |
| `file`, `image` | File upload |
| `tags`, `certificate`, `livesync`, `label` | Specialized |

The shape of a single inputVariable item (per UI bundle):
```jsonc
{
  "name":         "patch_id",         // var name; downstream as vars.input.<name>
  "type":         "text",             // any of the above
  "label":        "Patch ID",         // UI label
  "description":  "…",                // help text
  "required":     true,
  "defaultValue": "",
  "options":      [...],              // for select/multiselect/picklist
  "renderWidget": "text"              // rare override
}
```

**Worth verifying live:** since the corpus has no `inputVariables[]` examples, the exact field-shape semantics (especially `picklist`/`lookup` payload formats) are best confirmed by building a one-off test playbook with each type and reading `retrieve_wfinput`'s response.

## 6. `email_notification` and channels

```jsonc
"email_notification": {
  "enabled":       true|false,
  "smtpParameters": [
    {"name": "smtp_server", "value": "smtp.example.com"},
    ...
  ]
}
"inline_channel_list":   ["/api/3/picklists/<uuid>", ...],   // in-app notif channels
"external_channel_list": ["/api/3/picklists/<uuid>", ...],   // email channels
"unauthenticated_input": true|false,                          // public link?
"inputExternalUser":     true|false,                          // allow non-FSR users?

// Subject + body overrides (when enabled)
"internal_email_subject": "A FortiSOAR playbook is requesting your input",
"external_email_subject": null,
"customEmailInternal":    false,    // toggle: use the default internal email or override below
"customEmailExternal":    false,
"custom_email_body_internal": null,
"custom_email_body_external": null,
"internal_email_attachments": null,
"external_email_attachments": null
```

Channel IRIs point at `picklist` records — likely a "Channels" picklist namespace in your appliance. List them via `GET /api/3/picklists?listName=…&name=…`.

## 7. `timeout` — auto-route on no response

```jsonc
"timeout": {
  "days":     0,
  "hours":    0,
  "minutes":  1,
  "step_iri": "/api/3/workflow_steps/<uuid>"   // step that runs if timeout elapses
}
```

Total wait = `days + hours + minutes` (no seconds). 22/166 corpus steps use this, mostly with very short minute-range timeouts for testing or sub-1-hour SLA gates.

## 8. Resume body — what gets sent back

**CORRECTED 2026-05-03 after end-to-end test.** The earlier guidance to PUT `/api/wf/api/manual-wf-input/<pk>/` returns 200 but does **NOT** actually resume the playbook — it only updates the input record. The canonical mechanism (per `fsr_src/app.unmin.js:52478` + `:37731`) is:

```
POST /api/wf/api/workflows/<workflow_pk>/wfinput_resume/?format=json
```

Body:
```jsonc
{
  "input": {                              // values keyed by inputVariables[].name
    "<var_name>": <value>,                // empty {} when prompt is button-only
    ...
  },
  "step_iri":         "/api/3/workflow_steps/<uuid>",  // chosen option's step_iri
  "step_id":          <int>,              // pending input's step_id (from list_wfinput)
  "manual_input_id":  <int>,              // pending input's pk
  "approved":         true|false,         // ONLY when is_approval=true: true if primary option chosen
  "user":             "/api/3/people/<uuid>"  // current user IRI; omit for unauthenticated
}
```

`step_iri` carries the routing decision: it's the chosen option's `step_iri` from `response_mapping.options[]` — the step the playbook will run next. The **compiler must populate `step_iri`** on each option at emit time (auto-derived from the step's `next:` for single-option, `branches: {label: target}` for multi-option). Without it FSR's manual-input handler emits a malformed-URL error and the run fails.

Verified live in `python/tests/integration/test_e2e_runs.py::test_stage4_manual_input_resume` — start → set_variable → manual_input(InputBased, single option) → terminal cycle, fired and resumed via `fsrpb run-playbook` + `fsrpb inputs respond`, finishes cleanly.

**Other gotchas discovered live:**

- `POST /api/wf/api/manual-wf-input/list_wfinput/` requires a **`limit` query parameter**. Without it the endpoint 500s. The UI uses `?format=json&limit=1`. Use a generous value (e.g., `limit=200`) for full enumeration.
- DELETE on a stuck input record (`DELETE /api/wf/api/manual-wf-input/<pk>/`) returns 204 and silently terminates that prompt — useful for cleaning up orphaned awaiting runs from earlier failed resume attempts.
- A single broken-state input record can cause `list_wfinput` to 500 when `limit` includes it; bisect to find the bad pk and DELETE.

## 9. CLI coverage

`fsrpb inputs list` → table of pending prompts (id, age, type, title, owner).
`fsrpb inputs show <id>` → full schema + button options.
`fsrpb inputs respond <id> [--option <label>] [--vars '<json>'] [--task-id …]` → submit + resume.

Auto-defaults: `--option` defaults to the primary, then the first option. `--vars` is required only when the prompt has `inputVariables` (none in the corpus today).

## 10. Open probes (worth doing)

- Build a test playbook with one of each `inputVariables[].type` to confirm the wire shape per type (especially `lookup`, `picklist`, `file`).
- Submit through the unauthenticated link path — verify the public URL grammar.
- Trigger a timeout and confirm the timeout step_iri is taken.
- Probe `WorkflowViewSet.approval` action — likely a shortcut for `is_approval=true` prompts that takes `{decision: approve|reject, comment}`.
- Confirm what `inline_channel_list`/`external_channel_list` picklists look like when populated (none on dev corpus).
