"""Constants used by resolver mixins."""
from __future__ import annotations


def _looks_like_uuid(s: str) -> bool:
    return isinstance(s, str) and len(s) == 36 and s.count("-") == 4


# Friendly short types -> canonical FSR step type names. v1 only covers
# the ones we have full handler signatures for + Start.
SHORT_TYPE_TO_FSR: dict[str, str] = {
    "connector": "Connectors",
    "set_variable": "SetVariable",
    "decision": "Decision",
    "start": "cybersponse.abstract_trigger",
    "find_record": "FindRecords",
    "update_record": "UpdateRecord",
    "create_record": "InsertData",
    # Bulk feed insertion — used by threat-feed ingestion recipes. Bypasses
    # on-create playbook triggers (intentional for high-volume feeds; do
    # NOT use this for Alerts ingestion where triggers must fire).
    "ingest_bulk_feed": "IngestBulkFeed",
    # Legacy alias kept so existing fixtures don't break; emit a hint via
    # the linter when authors use the old name.
    "insert_record": "InsertData",
    "delay": "Delay",
    "manual_input": "ManualInput",
    "code_snippet": "CodeSnippet",
    "approval": "Approval",
    # SMTP SendMail — the connector-dispatcher "Send Email" step (occ=22, live on
    # 8.0). A connector-family alias: the normalizer defaults `connector: smtp` +
    # `operation: send_email` and falls through to `_resolve_connector_args`, so
    # the friendly surface is the email fields (to/subject/body/from/cc/bcc/...),
    # flat ��� the connector resolver auto-lifts them into `params:`. The smtp
    # connector's send_email op takes `body` natively (no rename). NOTE: the
    # dedicated `SendEmail` handler (/wf/workflow/tasks/send_email, occ=0) is
    # also registered on 8.0 but RUNS BUT FAILS ("'smtp'" — can't resolve the
    # configured SMTP connector), so we target SendMail (the working path).
    "send_email": "SendMail",
    # ManualTask — editor hardcodes `collection: tasks` and wraps the task
    # module fields into `resource`.
    "create_task": "ManualTask",
    # SetAPIKeys — niche; `public_key`/`private_key` (jinja-capable).
    "set_api_keys": "SetAPIKeys",
    "workflow_reference": "WorkflowReference",
    # Trigger Tenant Playbook (RemotePlaybookReference) — cross-tenant call to
    # a playbook in another FortiSOAR tenant. Owns a distinct script handler
    # (`/wf/workflow/tasks/remote_workflow_reference`, uuid ab3b2e02-…), so it
    # is a real step type, not a connector-family alias. The local sibling is
    # `workflow_reference` (WorkflowReference, same-collection). Remote
    # requires a `workflowReference:` IRI — the local-name `target:` form
    # can't cross tenants — and carries `pickFromTenant` for dynamic tenant
    # selection.
    "trigger_tenant_playbook": "RemotePlaybookReference",
    # `stop` / `end` — first-class no-op terminals. Compile to a connector
    # step calling `cyops_utilities.no_op` (FSR's canonical "Utils: No
    # Operation" idiom), so a decision branch that should do nothing has
    # an obvious YAML keyword instead of dangling or filler set_variable.
    "stop": "Connectors",
    "end": "Connectors",
    # `utilities` — the editor's "Utilities" palette entry (canonical
    # `CyopsUtilices`). It routes through `ConnectorStepCtrl` + `connector.html`,
    # so its wire shape IS the connector envelope; the only thing that makes
    # it "Utilities" is `connector: cyops_utilities` + one of the 55 utility
    # ops (convert_json_to_csv, make_cyops_request, no_op, compute_hash, …).
    # A connector-family alias: the normalizer defaults `connector` and falls
    # through to `_resolve_connector_args`; reuses the P3 `ConnectorArgs`
    # envelope model. Read is sugar-not-recovered (a pulled Utilities step
    # round-trips as `connector`, same contract as stop/end/delete_record).
    "utilities": "Connectors",
    # `delete_record` — FortiSOAR has no dedicated delete step type (the editor
    # palette exposes Create/Update/Find only). Deletion is done with a
    # connector step calling `cyops_utilities.make_cyops_request` and HTTP
    # `method: DELETE` — verified against 4 real corpus playbooks. We surface it
    # as a friendly short type that compiles to that connector call (single
    # record via `/api/3/<module>/<id>`, or bulk via `delete-with-query`).
    "delete_record": "Connectors",
    # Auto-fired record triggers (genuinely different from manual `start`):
    # event-driven, not invokable from the designer.
    "start_on_create": "cybersponse.post_create",
    "start_on_update": "cybersponse.post_update",
    # Record-deletion trigger. Fires after a record is removed; the deleted
    # record(s) arrive at `vars.input.records`. Field-based `when:` filters
    # match the pre-delete record state.
    "start_on_delete": "cybersponse.post_delete",
    # API Endpoint trigger — the invokable trigger that exposes the playbook
    # at `POST /api/triggers/1/<route>`. Its step `arguments` carry `route`
    # (the endpoint name) and `authentication_methods` (Token Based = `[""]`,
    # No Auth = `["anonymous"]`, Basic = `["Basic"]`). `[""]` is the sane
    # default — it's the only mode that exposes the clean route (no
    # `deferred/` prefix); the normalizer fills it when omitted. Live-grounded
    # on the `cybersponse.api_call` step type (uuid df26c7a2-…, label "Custom
    # API Endpoint"). Recognized as a trigger step by the emitter so the
    # first `api_endpoint` step becomes `triggerStep`.
    "api_endpoint": "cybersponse.api_call",
}

__all__ = ["_looks_like_uuid", "SHORT_TYPE_TO_FSR"]
