---
title: Manual Input Channel Delivery -- Teams / Slack / Email internals
category: playbook-authoring
status: reference
source: live-verified
topics:
- manual-input
- channels
- ms-teams
- slack
- approval-steps
canonical: true
summary: 'How FSR delivers manual inputs to the Microsoft Teams / Slack / Email
  channels (rules_engine_channel registry, connector ops, bot listener resume
  path), and the responder-identity gap: the bot channels never tell FortiSOAR
  who clicked.'
---

# Manual Input channel delivery -- Teams / Slack / Email

Companion to `MANUAL_INPUT.md` (step arguments + resume API). This doc covers
the **delivery** side: what happens between a ManualInput step pausing and the
response arriving back, verified live on an 8.0.1 appliance plus the shipped
connector sources (microsoft-teams 3.1.1/3.2.0, slack 3.3.1).

## 1. TL;DR

- A ManualInput step can deliver its prompt through channels. The channel names
  live in the **`External Channel`** picklist: `Email`, `Slack`,
  `Microsoft Teams`.
- Each channel maps to a **connector + operation** in the `rules_engine_channel`
  registry table. Teams/Slack deliver the form as an interactive card via the
  connector's bot listener.
- **The bot channels never identify the responder.** The resume payload contains
  only the submitted form values + routing ids. The connector listener receives
  the clicking user's identity from Teams/Slack and discards it. FortiSOAR
  records the resume against the integrations service principal, not a person.
- The UI (and authenticated email-link) path *does* attribute the response to
  the logged-in user. If you need provable "who approved", keep the approval on
  a FortiSOAR-authenticated surface and use Teams/Slack for notification only.

## 2. The channel registry

Two data pieces join up:

**Picklist `External Channel`** (module data DB, `picklists` where
`listname = <picklist_names.uuid>`):

| orderIndex | itemValue |
|---:|---|
| 0 | Email |
| 1 | Slack |
| 2 | Microsoft Teams |

A ManualInput step stores `inline_channel_list` / `external_channel_list` as
arrays of picklist IRIs (`/api/3/picklists/<uuid>`), each resolving to one of
the three values above.

**Channel registry** (`rules_engine_channel` table in the workflow DB; Django
app `rules_engine`, fixtures `default_channels.json` + rows registered when the
Teams/Slack connectors install):

| name | type | config |
|---|---|---|
| Email Notification | email | `{"connector": "smtp", "operation": "send_email", "config": "<smtp config uuid>", ...}` |
| Microsoft Teams | connector | `{"connector": "microsoft-teams", "operation": "send_message_or_approval_form_to_bot"}`; `default_params: {type: "Manual Input Form", input: ""}` — the embedded form card |
| Microsoft Teams Link | connector | same op; `default_params: {type: "Text Message", message: "", conversation_id: ""}` — a plain text message (the link to the input), not the embedded form |
| Slack | connector | `{"connector": "slack", "operation": "send_input"}` |
| Slack Link Channel | connector | `{"connector": "slack", "operation": "send_message"}` (link variant) |
| In-App Notifications / On Playbook Failure / Queue Notifications / Resume Conditional PB Step | system | `{}` |

Read it live:

```python
client.rules.get_channel("Microsoft Teams")   # pyfsr: .config -> connector/operation mapping
```

```sql
-- workflow (sealab) DB
SELECT name, type, config FROM rules_engine_channel ORDER BY name;
```

The Teams/Slack rows carry no connector-config uuid, so the framework binds the
tenant's connector configuration at execution time.

## 3. Dispatch chain (pause → channel → resume)

Compiled modules, but the symbols are introspectable (`django.setup()` in the
workflow venv, then `dir()`):

```
workflow.eval.manual_input(record, type, unauthenticated_input, input,
                           owner_detail, response_mapping, timeout, ...)
  # saves the WorkflowInput row (module: manual-wf-input)
workflow.eval.prepare_manualinput_payload(id, recipients, timeout, workflowId,
                                          auth_info, baseUri, data, agent_id)
  # builds the connector-facing payload (schema, response_mapping,
  # owner_details, workflow/id/step_id, ...)
workflow.eval.notify_manual_input(manual_input_id, workflow_id, record,
                                  action, data={}, websocket_id=None)
  # channel dispatch; also used with a different `action` on cancel/timeout
  └─ rules_engine.handler.handle_action / Channel
     └─ rules_engine.action_handlers.connector_notification.ConnectorActionHandler
        .connector(connector, operation, version, config, params, agent,
                   pickFromTenant)
           # executes e.g. microsoft-teams.send_message_or_approval_form_to_bot
           # with params.input = the prepared payload
```

Timeout/cleanup celery tasks in `workflow.tasks`: `manual_input_timeout_task`
(fires the `timeout.step_iri` branch), `terminate_pb_waiting_for_user_inputs`.

### What the connector receives (`params.input`)

| key | content |
|---|---|
| `id` | manual input pk (the `<input_id>` in the card context) |
| `step_id` | paused step pk |
| `workflow` | workflow pk |
| `input.schema` | `{title, description, inputVariables[]}` |
| `input.bot_context` | optional `{service_url, conversation_id, source}` — set when the playbook was triggered by a bot command |
| `response_mapping.options` | `[{option, step_iri(, primary)}]` |
| `owner_details` | assignment block; `externalRecipients`/`emailRecipients` carry the Teams conversation id/link or email |

Conversation resolution order in the Teams connector
(`get_conversation_id`): explicit `conversation_id` param →
`input.bot_context.conversation_id` → `owner_details.externalRecipients` /
`emailRecipients`.

## 4. Microsoft Teams end-to-end

Connector: `microsoft-teams` (verified 3.1.1 and 3.2.0 — identical on this
path). Files (relative to the connector package):
`operations.py`, `bot_utils/fsr_msteams_schema_converter.py`,
`listener/bot_activity_handler.py`, `listener/event_handler.py`.

1. **Send** — op `send_message_or_approval_form_to_bot` converts the FSR form
   schema to an Adaptive Card (v1.4). Field mapping: text/textarea/email/url/
   integer/dynamicList/datetime/date/checkbox → the matching `Input.*` elements;
   each `response_mapping.options[]` entry becomes an `Action.Submit` button:
   ```jsonc
   {"type": "Action.Submit", "title": "<option label>",
    "data": {"value": "<step_iri>", "action_id": "<workflow>_<input_id>_<step_id>"}}
   ```
   The card is posted to the resolved conversation through the bot's REST
   endpoint (`bot_handler`/`teams_listener`, nginx-routed `/bot` on the
   appliance).
2. **Click** — Teams posts an activity to the bot. The card's `data` arrives as
   `activity.value`; **`activity.from` carries the clicking user's AAD object
   id and display name** — the listener reads it, then drops it (see §6).
3. **Resume** — the listener treats `activity.value` as the command
   `resume_playbook` and POSTs to
   `/api/wf/api/workflows/<workflow_id>/wfinput_resume/`:
   ```jsonc
   {"input": { "<var>": <value>, ... },   // card values minus value/action_id
    "step_id": <int>, "manual_input_id": <int>,
    "step_iri": "/api/3/workflow_steps/<uuid>"}
   ```
   Auth is the integrations service HMAC (crudhub `make_request`) — a machine
   principal.
4. **Card cleanup** — after a successful submit the listener deletes the card
   message (`delete_activity`). Racing a second click yields
   *"This input request is already submitted or the relevant playbook is
   terminated!"*.
5. **Bot reply** — the playbook's post-resume steps send text back through the
   same op with `type: "Text Message"` (the SP playbooks wire a
   `Set Response`/`Set Bot Response` variable → connector step).

The FortiSOAR-for-Microsoft-Teams app SP (v1.0.0) playbooks
(`Create Alert`, `Create Indicator`, `Enrich IP`) follow exactly this shape:
`owner_detail.externalRecipients = {{vars.conversation_id}}` where
`vars.conversation_id` comes from `vars.bot_context.conversation_id`, captured
by the listener when the user first invoked the bot command.

## 5. Slack end-to-end (same pattern)

Connector `slack` 3.3.1: op `send_input` renders Slack blocks from the same
payload (recipient from `owner_details.externalRecipients` email, or
`bot_context.channel_id`/`ts` when triggered from Slack). On button click the
listener's `resume_playbook` builds the identical resume body
(`input`/`step_id`/`manual_input_id`/`step_iri`) and POSTs `wfinput_resume`.
Slack's interactive payload includes `payload.user.id` — also discarded.

## 6. The responder-identity gap (the important one)

Evidence chain, all live-verified:

- Card buttons carry only `{value: step_iri, action_id: context}` — no identity
  is embedded at send time (`fsr_msteams_schema_converter.convert_action_button_schema`).
- At click time the listener *has* the user (Teams `activity.from` /
  `conversation_reference.user.aad_object_id`; Slack `payload.user.id`) but
  builds `teams_metadata`/resume payload from `card_values` only
  (`bot_activity_handler.on_message_activity` → `event_handler.resume_playbook`).
  The identity never leaves the listener process.
- `wfinput_resume` attributes the response to the authenticated principal of
  the HTTP call. Bot-channel resumes are HMAC machine calls from the connector
  runtime, so the audit trail records the service principal, not a person.

What the audit trail does record (gateway DB, `auditlogs`):

```jsonc
{"component": "sealab", "operation": "Resume",
 "title": "Manual Input Provided To Resume Playbook [<playbook>] on <record>",
 "user_name": "<FSR principal>", "user_id": "<people uuid | playbook uuid>",
 "details": {"user": "/api/3/people/<uuid>",   // present only for user-session resumes
             "input": {…},                      // submitted values ([] when button-only)
             "__TEAMS": ["/api/3/teams/<uuid>", …],  // snapshot of owner teams
             "step_id": <int>, "step_iri": "/api/3/workflow_steps/<uuid>"}}
```

UI resumes show the responding user (`user_name: CS Admin`-style rows);
playbook-driven resumes show a `Playbook` pseudo-principal; bot-channel resumes
show the integrations principal. No Teams/Slack identity anywhere.

**Scope note (live-probed):** every observed `Resume` audit row belongs to a
prompt **linked to a record** (the title carries "on <record>"). Record-less
prompts resumed via the API wrote no `Resume` row at all (checked in both the
gateway `auditlogs` table and `client.audit.activities`). The reliable
attribution surface for a resumed prompt is the step result itself —
`vars.steps.<step>.userid` / `.username` — which is populated on every resume
with the request's principal (or the values a caller injected as extra `input`
keys, per option 1 above).

**What you can still rely on:**

- **Targeting**: the form goes to one conversation (1:1 chat → the recipient is
  the only person who can normally answer; group/channel → anyone in it can).
- **Single-shot**: the card is deleted on submit; double-submits are rejected.

**Options to get the responder identity:**

1. **Patch the connector listener** (small fork): in
   `bot_activity_handler.on_message_activity`, when `turn_context.activity.value`
   is present, copy `member.aad_object_id` / `member.name` into
   `teams_metadata["card_values"]` (e.g. `responder_aad_object_id`,
   `responder_name`) before `resume_playbook`. **Verified live (8.0.1):**
   `wfinput_resume` accepts keys beyond the step's `inputVariables` and they
   land verbatim in `vars.steps.<step>.input` next to the submitted values —
   no core change needed, and the playbook can act on them directly. The
   `userid`/`username` recorded on the step result still show the service
   principal, so treat the injected keys as the identity of record. The
   patch mechanics are also proven offline: running the actual patched
   listener against a simulated card-submit shows pristine 3.2.0 dropping
   the clicker's identity from the resume payload while the patched listener
   injects the two keys with the base payload unchanged. Slack
   equivalent: forward `payload.user.id` in
   `slack/listener/event_handler.resume_playbook`.
2. **Per-recipient delivery**: loop over approvers and send each their own card
   into their own 1:1 chat (connector ops resolve conversation ids from UPN/
   email). The conversation then identifies the responder by construction.
3. **Keep the approval on FortiSOAR**: deliver to internal users via the UI or
   authenticated email (the `user` field of `wfinput_resume` then carries the
   real responder, recorded in `auditlogs.details.user`). Teams/Slack become
   notification-only.
4. **RFE**: make the bot connectors resume **as the responding user** (or send
   a dedicated identity field). Note the resume body's existing `user` key is
   NOT a workaround: on an authenticated call the server ignores it and
   attributes the response to the request's own principal — live-verified by
   resuming with `user` pointing at a different person and reading
   `vars.steps.<step>.userid/username` (still the caller).

**Two more live-verified resume behaviors worth knowing:**

- **Double-submit race** (the bot's double-click case): the second
  `wfinput_resume` on a consumed input is rejected server-side with
  `The linked playbook is either no longer active or has already been
  resumed.` — the message behind the listener's
  *"This input request is already submitted or the relevant playbook is
  terminated!"* reply.
- **workflow/manual-input mismatch hazard**: `wfinput_resume` trusts the URL's
  workflow pk. Posting input N against a *different* run's URL corrupts both —
  the URL run fails with `CS-WF-2: Either the playbook is invalid or the
  playbook's start step is not linked to any other step` and the input's own
  run is left stuck `awaiting` with its input consumed. Always take
  `workflow_id`, `step_id` and `manual_input_id` from the same
  `retrieve_wfinput` row (pyfsr's `manual_input.resume` documents this).

## 7. Approval steps over bot channels

`is_approval: true` prompts work over Teams/Slack because approve/reject is
just `response_mapping` routing: each button's `step_iri` branches the
playbook. The listener never sends the `approved` boolean that
`wfinput_resume` accepts for approval-styled prompts — routing, not the flag,
carries the decision. Same identity caveat as §6 applies: the approval audit
trail will not name the Teams/Slack responder.

## 8. Verification notes

- Appliance: live-verified on 8.0.1 (workflow app `sealab`; compiled `.so`
  modules use Cython string compression — `strings` shows symbols/docstrings
  but not most literals, so introspection via `django.setup()` + `dir()` is the
  reliable route).
- Connector sources: microsoft-teams RPM 3.1.1 and 3.2.0 diffed (no behavior
  change on this path); slack 3.3.1 as installed.
- DB tables read live: `rules_engine_channel`, `workflow_workflowinput`,
  `picklists`, gateway `auditlogs`.
- Resume probes (2026-11-24, via pyfsr `manual_input`): extra `input` keys pass
  through to `vars.steps.<step>.input` (probe A/C); the body `user` field is
  ignored on authenticated calls (probe B2); URL-workflow vs manual-input
  mismatch corrupts both runs (probe B1 — the mismatch was accidental, the
  corruption is documented as a hazard); double-submit rejected with
  "The linked playbook is either no longer active or has already been
  resumed." (probe D); record-less prompts wrote no `Resume` audit row.
