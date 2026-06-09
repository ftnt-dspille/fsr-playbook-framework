"""Validation rules for alert/incident/vuln data ingestion.

Pattern reference: FortiAnalyzer + FortiSIEM connector playbooks.
Step type: Create Record (2597053c-e718-44b4-8394-4d40fe26d357).
Target: /api/3/<module> or /api/3/upsert/<module>, operation: Overwrite.
"""
from __future__ import annotations

from typing import Iterable

from . import (
    STEP_CREATE_RECORD,
    Issue,
    _all_steps,
    _all_workflows,
    _step_type_uuid,
    register,
)
from ._shared import (
    rule_canonical_step_names,
    rule_collection_or_workflow_has_slug,
    rule_configuration_schema_on_start,
    rule_connector_param_visibility,
    rule_connector_slug_uniform,
    rule_dataingestion_workflow_tags,
    rule_exported_tags_consistency,
    rule_step_type_collection_consistency,
    rule_tag_typos,
    rule_three_workflow_split_or_env_setup,
)


def rule_picklist_mapping_for_severity_status(doc: dict) -> Iterable[Issue]:
    """Alert/incident Create Record commonly maps vendor severity/status to FSR
    picklist IRIs via resolveRange. Warn if neither severity nor status is set
    on the resource (likely incomplete mapping).
    """
    import json
    for ci, _coll, wi, wf in _all_workflows(doc):
        if "dataingestion" not in (wf.get("recordTags") or []):
            continue
        for si, step in _all_steps(wf):
            if _step_type_uuid(step) != STEP_CREATE_RECORD:
                continue
            args = step.get("arguments") or {}
            coll = args.get("collection") or ""
            if not coll.startswith("/api/3/"):
                continue
            resource = args.get("resource") or {}
            blob = json.dumps(resource)
            if "severity" not in resource and "status" not in resource and "state" not in resource:
                yield Issue(
                    rule_id="data_ingest.severity_status_unset",
                    severity="warn",
                    message="Create Record resource sets neither severity nor status/state — alert mapping likely incomplete",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]({step.get('name')!r})",
                )
            elif "resolveRange" not in blob and "/api/3/picklists/" not in blob:
                yield Issue(
                    rule_id="data_ingest.severity_status_no_picklist_resolution",
                    severity="warn",
                    message="severity/status/state set but no resolveRange or picklist IRI seen — vendor enum may not resolve to FSR picklist",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]({step.get('name')!r})",
                )


def rule_create_record_has_dedup(doc: dict) -> Iterable[Issue]:
    """Alert/incident Create Record should set sourceId (or externalId) for dedup."""
    for ci, _coll, wi, wf in _all_workflows(doc):
        if "dataingestion" not in (wf.get("recordTags") or []):
            continue
        for si, step in _all_steps(wf):
            if _step_type_uuid(step) != STEP_CREATE_RECORD:
                continue
            args = step.get("arguments") or {}
            coll = args.get("collection") or ""
            if not coll.startswith("/api/3/"):
                continue
            resource = args.get("resource") or {}
            if not (resource.get("sourceId") or resource.get("externalId")):
                yield Issue(
                    rule_id="data_ingest.dedup_field_required",
                    severity="warn",
                    message="Create Record on dataingestion workflow has no sourceId/externalId — duplicates likely on re-run",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]({step.get('name')!r})",
                    suggestion='Set resource.sourceId to vendor native id, e.g. "{{vars.item.alertid}}"',
                )


def rule_create_record_operation_is_overwrite(doc: dict) -> Iterable[Issue]:
    """For ingest patterns, operation should be Overwrite (idempotent upsert)."""
    for ci, _coll, wi, wf in _all_workflows(doc):
        if "dataingestion" not in (wf.get("recordTags") or []):
            continue
        for si, step in _all_steps(wf):
            if _step_type_uuid(step) != STEP_CREATE_RECORD:
                continue
            args = step.get("arguments") or {}
            op = args.get("operation")
            if op and op != "Overwrite":
                yield Issue(
                    rule_id="data_ingest.operation_should_be_overwrite",
                    severity="warn",
                    message=f"Create Record operation is {op!r}; Overwrite is recommended for idempotent ingest",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]",
                )


register("data-ingest", [
    rule_step_type_collection_consistency,
    rule_dataingestion_workflow_tags,
    rule_three_workflow_split_or_env_setup,
    rule_canonical_step_names,
    rule_configuration_schema_on_start,
    rule_tag_typos,
    rule_exported_tags_consistency,
    rule_connector_slug_uniform,
    rule_collection_or_workflow_has_slug,
    rule_connector_param_visibility,
    rule_create_record_has_dedup,
    rule_create_record_operation_is_overwrite,
    rule_picklist_mapping_for_severity_status,
])
