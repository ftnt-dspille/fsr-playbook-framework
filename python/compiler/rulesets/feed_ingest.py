"""Validation rules for threat-feed ingestion (typical bulk-ingest pattern).

Pattern reference: AWS Feed, TAXII2 Threat Intel Feed, Recorded Future Feed.
Step type: Ingest Bulk Feed (7b221880-716b-4726-a2ca-5e568d330b3e).
Target: /api/ingest-feeds/<module>; on-create triggers intentionally bypassed.
"""
from __future__ import annotations

import json
from typing import Iterable

from . import (
    STEP_INGEST_BULK_FEED,
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
    rule_connector_slug_uniform,
    rule_dataingestion_workflow_tags,
    rule_exported_tags_consistency,
    rule_step_type_collection_consistency,
    rule_tag_typos,
    rule_three_workflow_split_or_env_setup,
)


def rule_threatintel_tag_in_sibling_info_json(doc: dict, info_json_path: "str | None" = None) -> Iterable[Issue]:
    """Per the official guide TIM section, the canonical place for the
    `ThreatIntel` tag is the connector's `info.json`, NOT playbook recordTags.
    TAXII2 and AWS Feed prove this — neither tags any playbook, both work.

    If validate-ingestion is given an --info-json path (or one is found
    next to the playbooks file), check it. Otherwise this rule is a no-op
    (we don't fail on missing info.json since the validator may be run
    against a YAML or pulled JSON without one nearby).
    """
    import json as _json
    import os as _os
    has_ibf = False
    for _, _, _, wf in _all_workflows(doc):
        for _, step in _all_steps(wf):
            if _step_type_uuid(step) == STEP_INGEST_BULK_FEED:
                has_ibf = True
                break
        if has_ibf:
            break
    if not has_ibf:
        return
    path = info_json_path or _os.environ.get("FSRPB_INFO_JSON")
    if not path or not _os.path.exists(path):
        return
    try:
        info = _json.load(open(path))
    except Exception:
        return
    tags = info.get("tags") or []
    if "ThreatIntel" not in tags:
        yield Issue(
            rule_id="feed_ingest.info_json_missing_threatintel",
            severity="warn",
            message=f"info.json at {path} does not include 'ThreatIntel' tag; TIM module won't surface this connector",
            path="info.json:tags",
            suggestion="Add 'ThreatIntel' (and typically 'ThreatFeedsIngestion') to info.json.tags",
        )


# `value` is the natural unique constraint on threat_intel_feeds, so sourceId
# is not strictly required for IBF (AWS Feed omits it). `sourceData` is the
# audit trail for re-mapping if the feed schema changes.
_REQUIRED_IBF_RESOURCE_FIELDS = ("value", "source", "sourceData")


def rule_ibf_resource_required_fields(doc: dict) -> Iterable[Issue]:
    """Ingest Bulk Feed resource block should set the minimum dedup/audit fields."""
    for ci, _coll, wi, wf in _all_workflows(doc):
        for si, step in _all_steps(wf):
            if _step_type_uuid(step) != STEP_INGEST_BULK_FEED:
                continue
            resource = ((step.get("arguments") or {}).get("resource") or {})
            missing = [f for f in _REQUIRED_IBF_RESOURCE_FIELDS if f not in resource]
            if missing:
                yield Issue(
                    rule_id="feed_ingest.ibf_resource_required_fields",
                    severity="warn",
                    message=f"Ingest Bulk Feed resource missing recommended fields: {missing}",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]({step.get('name')!r})",
                    suggestion="Add value, source, sourceId, sourceData (JSON dump of vars.item) for dedup + audit",
                )


def rule_create_step_guards_empty_data(doc: dict) -> Iterable[Issue]:
    """Fetch+Create workflow should not call Ingest Bulk Feed unconditionally —
    either the IBF step itself has a `when` clause, or an upstream Decision
    branches on data presence. Otherwise empty fetches silently no-op (or worse,
    error out on for_each over None).
    """
    for ci, _coll, wi, wf in _all_workflows(doc):
        tags = set(wf.get("recordTags") or [])
        if not ({"fetch", "create"} <= tags):
            continue
        steps = wf.get("steps", []) or []
        has_decision = any(_step_type_uuid(s) == "12254cf5-5db7-4b1a-8cb1-3af081924b28" for s in steps)
        for si, step in enumerate(steps):
            if _step_type_uuid(step) != STEP_INGEST_BULK_FEED:
                continue
            args = step.get("arguments") or {}
            has_when = bool(args.get("when"))
            if not (has_when or has_decision):
                yield Issue(
                    rule_id="feed_ingest.empty_data_unguarded",
                    severity="warn",
                    message="Ingest Bulk Feed has no `when` guard and no upstream Decision; empty fetch will error or silently no-op",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]",
                    suggestion='Add `when: "{{vars.data | length > 0}}"` to the IBF step or branch via Decision',
                )


def rule_lastpulltime_passed_to_fetch(doc: dict) -> Iterable[Issue]:
    """Fetch+Create workflow with `parameters: [lastPullTime]` should reference
    `vars.input.params.lastPullTime` somewhere in its connector-fetch step args
    OR in the Configuration step (so it's plumbed even if RF-style feeds don't
    consume it directly).
    """
    for ci, _coll, wi, wf in _all_workflows(doc):
        if "lastPullTime" not in (wf.get("parameters") or []):
            continue
        blob = json.dumps(wf.get("steps", []) or [])
        if "lastPullTime" not in blob:
            yield Issue(
                rule_id="feed_ingest.lastpulltime_unused",
                severity="warn",
                message="Workflow declares parameters: ['lastPullTime'] but no step references vars.input.params.lastPullTime",
                path=f"data[{ci}].workflows[{wi}]({wf.get('name')!r})",
            )


def rule_config_step_has_picklist_maps(doc: dict) -> Iterable[Issue]:
    """Fetch+Create workflow's Configuration step should define tlp_map,
    reputation_map, and a type_of_feed map (any name ending in _map containing
    `picklist(`). These feed `resolveRange` in the IBF resource block.
    """
    for ci, _coll, wi, wf in _all_workflows(doc):
        tags = set(wf.get("recordTags") or [])
        if not ({"fetch", "create"} <= tags):
            continue
        # Find the Configuration set_variable step (by name)
        config_step = None
        for step in wf.get("steps", []) or []:
            if step.get("name") == "Configuration" and _step_type_uuid(step) == "04d0cf46-b6a8-42c4-8683-60a7eaa69e8f":
                config_step = step
                break
        if config_step is None:
            continue  # rule_canonical_step_names already warned
        args = config_step.get("arguments") or {}
        blob = json.dumps(args)
        for needed, hint in (
            ("tlp_map", "TrafficLightProtocol picklist"),
            ("reputation_map", "IndicatorReputation picklist"),
        ):
            if needed not in args:
                yield Issue(
                    rule_id=f"feed_ingest.config_missing_{needed}",
                    severity="warn",
                    message=f"Configuration step missing {needed}",
                    path=f"data[{ci}].workflows[{wi}]({wf.get('name')!r}).Configuration",
                    suggestion=f"Add {needed} mapping vendor enum -> {{{{ '{hint.split()[0]}' | picklist(...) }}}} IRIs",
                )
        if "picklist(" not in blob:
            yield Issue(
                rule_id="feed_ingest.config_no_picklist_filter",
                severity="warn",
                message="Configuration step has no `picklist(` filter calls; picklist UUIDs likely hard-coded (drift risk)",
                path=f"data[{ci}].workflows[{wi}]({wf.get('name')!r}).Configuration",
            )


def rule_ibf_for_each_bulk_required(doc: dict) -> Iterable[Issue]:
    """Ingest Bulk Feed must use for_each with __bulk: true."""
    for ci, _coll, wi, wf in _all_workflows(doc):
        for si, step in _all_steps(wf):
            if _step_type_uuid(step) != STEP_INGEST_BULK_FEED:
                continue
            for_each = (step.get("arguments") or {}).get("for_each") or {}
            if for_each.get("__bulk") is not True:
                yield Issue(
                    rule_id="feed_ingest.ibf_bulk_true_required",
                    severity="fail",
                    message="Ingest Bulk Feed step must set for_each.__bulk = true",
                    path=f"data[{ci}].workflows[{wi}].steps[{si}]",
                )


def rule_macro_plumbing_present(doc: dict) -> Iterable[Issue]:
    """Ingest workflow should fetch a LastPullTime macro and update it after fetch.

    Detects via cyops_utilities make_cyops_request to /api/wf/api/dynamic-variable
    AND a cyops_utilities updatemacro op call.
    """
    for ci, coll, wi, wf in _all_workflows(doc):
        if "ingest" not in (wf.get("recordTags") or []):
            continue
        gets = updates = 0
        for _, step in _all_steps(wf):
            args = step.get("arguments") or {}
            op = args.get("operation")
            if op == "make_cyops_request":
                iri = (args.get("params") or {}).get("iri") or ""
                if "dynamic-variable" in iri:
                    gets += 1
            elif op == "updatemacro":
                updates += 1
        if gets == 0 or updates == 0:
            yield Issue(
                rule_id="feed_ingest.macro_plumbing",
                severity="fail",
                message=(
                    f"Ingest workflow missing macro plumbing "
                    f"(get={gets}, update={updates}) — incremental fetch will not persist"
                ),
                path=f"data[{ci}].workflows[{wi}]({wf.get('name')!r})",
                suggestion="Add a make_cyops_request GET on /api/wf/api/dynamic-variable + a cyops_utilities.updatemacro after the fetch",
            )


def rule_macro_name_per_install(doc: dict) -> Iterable[Issue]:
    """Macro name must include playbook IRI suffix to avoid cross-install collisions."""
    NEEDLE = "cyops_playbook_iri"
    for ci, _coll, wi, wf in _all_workflows(doc):
        if "ingest" not in (wf.get("recordTags") or []):
            continue
        # Look for any string in any step that defines the macro name
        for si, step in _all_steps(wf):
            args = step.get("arguments") or {}
            blob = json.dumps(args)
            if "LastPullTime" in blob or "Macro" in blob:
                if "LastPullTime" in blob and NEEDLE not in blob:
                    yield Issue(
                        rule_id="feed_ingest.macro_name_per_install",
                        severity="warn",
                        message="Macro name appears not to include playbook IRI suffix; cross-install collisions likely",
                        path=f"data[{ci}].workflows[{wi}].steps[{si}]",
                        suggestion="Use \"<Connector>LastPullTime_{{ vars['audit_info']['cyops_playbook_iri'].split('/')[-1].replace('-','_') }}\"",
                    )
                    break


register("feed-ingest", [
    rule_step_type_collection_consistency,
    rule_dataingestion_workflow_tags,
    rule_three_workflow_split_or_env_setup,
    rule_canonical_step_names,
    rule_configuration_schema_on_start,
    rule_tag_typos,
    rule_exported_tags_consistency,
    rule_connector_slug_uniform,
    rule_collection_or_workflow_has_slug,
    rule_threatintel_tag_in_sibling_info_json,
    rule_ibf_for_each_bulk_required,
    rule_ibf_resource_required_fields,
    rule_create_step_guards_empty_data,
    rule_macro_plumbing_present,
    rule_macro_name_per_install,
    rule_lastpulltime_passed_to_fetch,
    rule_config_step_has_picklist_maps,
])
