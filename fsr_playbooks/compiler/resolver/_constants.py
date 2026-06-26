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
    # SMTP SendEmail. Friendly `body`/`from` map to canonical `content`/
    # `from_str`; to/cc/bcc/subject pass through (Phase-2 coverage).
    "send_email": "SendEmail",
    # ManualTask — editor hardcodes `collection: tasks` and wraps the task
    # module fields into `resource`.
    "create_task": "ManualTask",
    # SetAPIKeys — niche; `public_key`/`private_key` (jinja-capable).
    "set_api_keys": "SetAPIKeys",
    "workflow_reference": "WorkflowReference",
    # `stop` / `end` — first-class no-op terminals. Compile to a connector
    # step calling `cyops_utilities.no_op` (FSR's canonical "Utils: No
    # Operation" idiom), so a decision branch that should do nothing has
    # an obvious YAML keyword instead of dangling or filler set_variable.
    "stop": "Connectors",
    "end": "Connectors",
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
