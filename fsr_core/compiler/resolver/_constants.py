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
}

__all__ = ["_looks_like_uuid", "SHORT_TYPE_TO_FSR"]
