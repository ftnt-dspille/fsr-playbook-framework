"""Threat-feed recipe generator.

Reads a connector's info.json and emits the three-workflow ingestion collection
(Get Indicators / > <Conn> > Fetch and Create / <Conn> > Ingest) using the
Ingest Bulk Feed step type. Output validates clean under the feed-ingest ruleset.

Inputs read from info.json:
- name, label, version, tags
- ingestion_config_schema (drives _configuration_schema on Start step)
- ingest_mapping_template (used as a structural hint; we still emit the canonical IBF resource shape)
- operations[].operation, parameters (used to find the fetch op + incremental param)

Outputs FSR `workflow_collections` JSON.
"""
from __future__ import annotations

import json
import re
import uuid as _uuid
from typing import Any

# Step type UUIDs (canonical)
ST_START_TRIGGER = "f414d039-bb0d-4e59-9c39-a8f1e880b18a"        # manual Start with route+resources
ST_START_REF = "b348f017-9a94-471f-87f8-ce88b6a7ad62"             # workflow_reference Start
ST_SET_VAR = "04d0cf46-b6a8-42c4-8683-60a7eaa69e8f"
ST_DECISION = "12254cf5-5db7-4b1a-8cb1-3af081924b28"
ST_WF_REF = "74932bdc-b8b6-4d24-88c4-1a4dfbc524f3"
ST_CONNECTORS = "0bfed618-0316-11e7-93ae-92361f002671"
ST_CREATE_RECORD = "2597053c-e718-44b4-8394-4d40fe26d357"
ST_INGEST_BULK_FEED = "7b221880-716b-4726-a2ca-5e568d330b3e"

# Heuristics
_INCREMENTAL_PARAM_NAMES = {"last_pull_time", "modified_since", "added_after", "since", "from", "start_time", "timeFrom", "start"}
# Op title hints for alert/incident fetch ops (FAZ/FSM patterns)
_ALERT_FETCH_TITLES = {
    "list incidents", "fetch incidents", "get incidents",
    "list alerts", "fetch alerts", "get alerts",
    "list events", "fetch events", "search events",
}
# Vendor field names that commonly carry the natural primary key for dedup
_DEDUP_FIELD_HINTS = ("incidentId", "incident_id", "alertId", "alert_id", "alertid",
                      "eventId", "event_id", "id", "uuid", "ticket_id", "externalId")


def _camel(slug: str) -> str:
    """recorded-future-feed -> RecordedFutureFeed."""
    return "".join(w.capitalize() for w in re.split(r"[-_\s]+", slug) if w)


def _uuid_from(seed: str) -> str:
    """Deterministic UUID from a seed (so re-generating the same recipe yields stable IDs)."""
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"fsrpb-recipe:{seed}"))


def _find_fetch_op(info: dict) -> tuple[str, dict]:
    """Find the operation that produces an indicator list. Heuristic order:
    1. Op with `annotation == 'fetch_indicators'`.
    2. Op named `fetch_indicators` / `get_indicators` / `list_indicators`.
    3. First op whose output_schema mentions `indicators` or returns a list.
    """
    ops = info.get("operations") or []
    # 1. annotation hint
    for o in ops:
        if (o.get("annotation") or "").lower() == "fetch_indicators":
            return o["operation"], o
    # 2. operation name
    by_name = {o.get("operation"): o for o in ops}
    for cand in ("fetch_indicators", "get_indicators", "list_indicators"):
        if cand in by_name:
            return cand, by_name[cand]
    # 3. title match — TAXII2's op is named get_objects_by_collection_id
    #    but its title is literally "Fetch Indicators"
    for o in ops:
        if (o.get("title") or "").strip().lower() in ("fetch indicators", "get indicators", "list indicators"):
            return o["operation"], o
    # 4. fallback: any op whose output schema mentions an indicator-shaped list
    for o in ops:
        out = o.get("output_schema") or {}
        if "indicators" in out or "objects" in out or (isinstance(out, list) and out and isinstance(out[0], dict)):
            return o["operation"], o
    raise ValueError("no fetch-style operation found on connector; expected one annotated 'fetch_indicators', named 'fetch_indicators'/'get_indicators', or titled 'Fetch Indicators'")


def _detect_incremental_param(op: dict) -> str | None:
    """Return the param name that accepts a last-pull cursor, or None."""
    for p in op.get("parameters") or []:
        n = p.get("name") or ""
        if n.lower() in _INCREMENTAL_PARAM_NAMES:
            return n
    return None


def _picklist_maps(connector_slug: str) -> dict[str, str]:
    """Canonical picklist maps using the runtime `picklist` filter."""
    return {
        "tlp_map": "{'Red': {{'TrafficLightProtocol' | picklist('Red') }}, 'Amber': {{'TrafficLightProtocol' | picklist('Amber') }}, 'Green': {{'TrafficLightProtocol' | picklist('Green') }}, 'White': {{'TrafficLightProtocol' | picklist('White') }}}",
        "reputation_map": "{'Good': {{'IndicatorReputation' | picklist('Good') }}, 'Malicious': {{'IndicatorReputation' | picklist('Malicious') }}, 'Suspicious': {{'IndicatorReputation' | picklist('Suspicious') }}, 'TBD': {{'IndicatorReputation' | picklist('TBD') }}, 'No Reputation Available': {{'IndicatorReputation' | picklist('No Reputation Available') }}}",
        "type_of_feed_map": "{'ip': {{'ThreatIntelFeedType' | picklist('IPv4 Address') }}, 'domain': {{'ThreatIntelFeedType' | picklist('Domain') }}, 'url': {{'ThreatIntelFeedType' | picklist('URL') }}, 'hash': {{'ThreatIntelFeedType' | picklist('FileHash-SHA256') }}, 'vulnerability': {{'ThreatIntelFeedType' | picklist('CVE') }}}",
    }


def _find_alert_fetch_op(info: dict) -> tuple[str, dict]:
    """Find the operation that produces an alert/incident list."""
    ops = info.get("operations") or []
    for o in ops:
        if (o.get("annotation") or "").lower() in ("fetch_alerts", "fetch_incidents", "list_incidents", "get_incidents"):
            return o["operation"], o
    by_name = {o.get("operation"): o for o in ops}
    for cand in ("list_incidents", "get_incidents", "fetch_alerts", "list_alerts", "get_alerts", "search_events"):
        if cand in by_name:
            return cand, by_name[cand]
    for o in ops:
        if (o.get("title") or "").strip().lower() in _ALERT_FETCH_TITLES:
            return o["operation"], o
    raise ValueError(
        "no alert/incident-fetch operation found; expected one named "
        "'list_incidents'/'get_incidents'/'fetch_alerts' or titled accordingly. "
        "Pass --fetch-op <name> to override."
    )


def _detect_dedup_field(op: dict, override: str | None) -> str:
    if override:
        return override
    schema = op.get("output_schema") or {}
    # output_schema may be {data: [{...}]} or [{...}] or {field: ...}
    sample = None
    if isinstance(schema, dict):
        for _, v in schema.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                sample = v[0]
                break
            if isinstance(v, dict):
                sample = v
                break
        if sample is None:
            sample = schema
    elif isinstance(schema, list) and schema and isinstance(schema[0], dict):
        sample = schema[0]
    sample = sample or {}
    for cand in _DEDUP_FIELD_HINTS:
        if cand in sample:
            return cand
    return "id"  # last-resort fallback


def generate_data_ingest_recipe(
    info: dict,
    *,
    target_module: str = "alerts",
    fetch_op_name: str | None = None,
    dedup_field: str | None = None,
    severity_field: str = "severity",
    status_field: str = "status",
    severity_enum: list[str] | None = None,
    status_enum: list[str] | None = None,
    connector_config_uuid: str = "REPLACE_WITH_CONFIG_UUID",
) -> dict:
    """Build the FSR JSON for alert/incident ingestion.

    Patterned after FortiAnalyzer + FortiSIEM playbooks. Emits Create Record
    (NOT Ingest Bulk Feed) targeting /api/3/<target_module>, with sourceId
    dedup, severity/status picklist mapping via resolveRange, and the same
    macro plumbing as threat-feed ingestion.

    Required behavior on output:
    - Validates clean under the data-ingest ruleset.
    - Step type: Create Record (2597053c…), NOT Ingest Bulk Feed.
    - Collection: /api/3/upsert/<target_module> with operation: Overwrite.
    - sourceId set to dedup_field (auto-detected from output schema if omitted).
    """
    slug = info["name"]
    label = info.get("label") or slug
    version = info.get("version") or "1.0.0"
    camel = _camel(slug)

    # Pick op
    if fetch_op_name:
        ops = info.get("operations") or []
        match = next((o for o in ops if o.get("operation") == fetch_op_name), None)
        if match is None:
            raise ValueError(f"fetch_op_name {fetch_op_name!r} not found in info.json operations")
        fetch_name, fetch_op = fetch_op_name, match
    else:
        fetch_name, fetch_op = _find_alert_fetch_op(info)

    incremental_param = _detect_incremental_param(fetch_op)
    dedup = _detect_dedup_field(fetch_op, dedup_field)
    sev_enum = severity_enum or ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    stat_enum = status_enum or ["Open", "Investigating", "Resolved", "Closed"]

    # Picklist maps for severity/status (vendor enum -> FSR picklist via filter)
    severity_map = "{" + ", ".join(
        f"'{v}': {{{{'Severity' | picklist({v.title()!r}) }}}}" for v in sev_enum
    ) + "}"
    status_map = "{" + ", ".join(
        f"'{v}': {{{{'AlertStatus' | picklist({v!r}) }}}}" for v in stat_enum
    ) + "}"

    coll_uuid = _uuid_from(f"{slug}:di:collection")
    wf_get_uuid = _uuid_from(f"{slug}:di:wf:get")
    wf_fc_uuid = _uuid_from(f"{slug}:di:wf:fc")
    wf_ingest_uuid = _uuid_from(f"{slug}:di:wf:ingest")

    def U(seed: str) -> str:
        return _uuid_from(f"{slug}:di:{seed}")

    cfg_schema = info.get("ingestion_config_schema") or [
        {"title": "Pull Updates From Last X Minutes", "name": "minutes",
         "type": "integer", "required": True, "value": 5,
         "tooltip": "Backfill window on first run; subsequent runs use the last-pull macro."},
        {"title": "Per-Run Limit", "name": "limit", "type": "integer", "value": 1000},
        {"title": "Severity Filter (Optional)", "name": "severity_filter",
         "type": "multiselect", "options": sev_enum},
        {"title": "Status Filter (Optional)", "name": "status_filter",
         "type": "multiselect", "options": stat_enum},
    ]
    config_args: dict[str, Any] = {}
    for f in cfg_schema:
        config_args[f["name"]] = f.get("value", "" if f.get("type") in ("text", "select") else 0)
    config_args["alerts_severity_map"] = severity_map
    config_args["alerts_status_map"] = status_map

    macro_name = f"{camel}LastPullTime_{{{{vars['audit_info']['cyops_playbook_iri'].split('/')[-1].replace('-','_')}}}}"

    fetch_params: dict[str, Any] = {}
    for p in fetch_op.get("parameters") or []:
        n = p["name"]
        if n == incremental_param:
            fetch_params[n] = "{{vars.input.params.lastPullTime}}"
        elif n in config_args:
            fetch_params[n] = f"{{{{vars.{n}}}}}"
        else:
            v = p.get("value")
            if v not in (None, ""):
                fetch_params[n] = v

    sample_data = json.dumps([
        {dedup: "INC-1001", severity_field: sev_enum[1], status_field: stat_enum[0],
         "name": "Sample event 1", "description": "Sample alert for mapping"},
        {dedup: "INC-1002", severity_field: sev_enum[2], status_field: stat_enum[0],
         "name": "Sample event 2", "description": "Sample alert for mapping"},
    ], indent=2)

    # ----- Workflow 1: Get (manual diagnostic) -----
    wf_get = {
        "@type": "Workflow",
        "name": "Get Alerts",
        "description": f"Manually fetch a sample of alerts from {label}.",
        "isActive": False, "debug": True, "parameters": [], "synchronous": False,
        "triggerStep": f"/api/3/workflow_steps/{U('get:start')}",
        "uuid": wf_get_uuid,
        "recordTags": [slug],
        "steps": [
            {"@type": "WorkflowStep", "name": "Start",
             "arguments": {
                 "route": U("get:route"), "title": f"{label}: Get Alerts",
                 "resources": ["alerts"], "inputVariables": [],
                 "step_variables": {"input": {"params": [], "records": "{{vars.input.records}}"}},
                 "executeButtonText": "Fetch", "noRecordExecution": True,
                 "singleRecordExecution": False,
             },
             "top": "40", "left": "40",
             "stepType": f"/api/3/workflow_step_types/{ST_START_TRIGGER}",
             "uuid": U("get:start")},
            {"@type": "WorkflowStep", "name": fetch_op.get("title") or "Fetch Alerts",
             "arguments": {
                 "name": label, "config": connector_config_uuid,
                 "params": {p["name"]: p.get("value", "") for p in (fetch_op.get("parameters") or []) if p.get("required")},
                 "version": version, "connector": slug,
                 "operation": fetch_name,
                 "operationTitle": fetch_op.get("title") or fetch_name,
                 "pickFromTenant": False, "step_variables": [],
             },
             "top": "200", "left": "300",
             "stepType": f"/api/3/workflow_step_types/{ST_CONNECTORS}",
             "uuid": U("get:fetch")},
        ],
        "routes": [
            {"@type": "WorkflowRoute", "name": "Start -> Fetch",
             "sourceStep": f"/api/3/workflow_steps/{U('get:start')}",
             "targetStep": f"/api/3/workflow_steps/{U('get:fetch')}",
             "label": None, "isExecuted": False, "uuid": U("get:r1")},
        ],
    }

    # ----- Workflow 2: Fetch and Create (child) -----
    wf_fc = {
        "@type": "Workflow",
        "name": f"> {label} > Fetch and Create",
        "description": f"Fetch and create alerts/incidents from {label}.",
        "isActive": False, "debug": True,
        "parameters": ["lastPullTime"],
        "synchronous": False,
        "triggerStep": f"/api/3/workflow_steps/{U('fc:start')}",
        "uuid": wf_fc_uuid,
        "recordTags": ["dataingestion", "fetch", "create", slug],
        "steps": [
            {"@type": "WorkflowStep", "name": "Start",
             "arguments": {"step_variables": {"input": {"params": []},
                                              "_configuration_schema": json.dumps(cfg_schema)}},
             "top": "40", "left": "40",
             "stepType": f"/api/3/workflow_step_types/{ST_START_REF}",
             "uuid": U("fc:start")},
            {"@type": "WorkflowStep", "name": "Configuration",
             "arguments": config_args,
             "top": "160", "left": "40",
             "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
             "uuid": U("fc:config")},
            {"@type": "WorkflowStep", "name": "Is Data Only For Mapping",
             "arguments": {"conditions": [
                 {"option": "Yes For Mapping",
                  "step_iri": f"/api/3/workflow_steps/{U('fc:sample')}",
                  "condition": "{{ vars.request.env_setup == true }}",
                  "step_name": "Return Sample Data"},
                 {"option": "No For Ingestion", "default": True,
                  "step_iri": f"/api/3/workflow_steps/{U('fc:fetch')}",
                  "step_name": "Fetch Alerts"},
             ]},
             "top": "300", "left": "40",
             "stepType": f"/api/3/workflow_step_types/{ST_DECISION}",
             "uuid": U("fc:decision")},
            {"@type": "WorkflowStep", "name": "Return Sample Data",
             "arguments": {"data": sample_data},
             "top": "300", "left": "320",
             "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
             "uuid": U("fc:sample")},
            {"@type": "WorkflowStep", "name": "Fetch Alerts",
             "arguments": {
                 "name": label, "config": connector_config_uuid,
                 "params": fetch_params, "version": version,
                 "connector": slug, "operation": fetch_name,
                 "operationTitle": fetch_op.get("title") or fetch_name,
                 "pickFromTenant": False, "step_variables": [],
             },
             "top": "300", "left": "600",
             "stepType": f"/api/3/workflow_step_types/{ST_CONNECTORS}",
             "uuid": U("fc:fetch")},
            {"@type": "WorkflowStep", "name": "Build Alert List",
             "arguments": {
                 "data": "{{vars.steps.Fetch_Alerts.data | default(vars.steps.Fetch_Alerts) }}",
                 "currentPullTime": "{{ arrow.utcnow().isoformat() }}",
             },
             "top": "440", "left": "600",
             "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
             "uuid": U("fc:build")},
            {"@type": "WorkflowStep", "name": "Create Record",
             "arguments": {
                 "when": "{{vars.data | length > 0}}",
                 "for_each": {"item": "{{vars.data}}", "__bulk": True,
                              "condition": "", "batch_size": 100},
                 "resource": {
                     "name": "{{vars.item.name | default(vars.item.subject) | default('Untitled') }}",
                     "sourceId": "{{vars.item." + dedup + "}}",
                     "source": label,
                     "severity": "{{ vars.item." + severity_field + " | resolveRange(vars.alerts_severity_map) }}",
                     "status": "{{ vars.item." + status_field + " | resolveRange(vars.alerts_status_map) }}",
                     "description": "{{vars.item.description | default('') }}",
                     "sourcedata": "{{vars.item | toJSON}}",
                     "__replace": "",
                 },
                 "_showJson": False,
                 "collection": f"/api/3/upsert/{target_module}",
                 "operation": "Overwrite",
                 "__recommend": [],
                 "fieldOperation": [],
                 "step_variables": [],
             },
             "top": "560", "left": "600",
             "stepType": f"/api/3/workflow_step_types/{ST_CREATE_RECORD}",
             "uuid": U("fc:create")},
            {"@type": "WorkflowStep", "name": "Save Result",
             "arguments": {"currentPullTime": "{{vars.currentPullTime}}"},
             "top": "680", "left": "600",
             "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
             "uuid": U("fc:save")},
        ],
        "routes": [
            {"@type": "WorkflowRoute", "name": "Start -> Configuration",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:start')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:config')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r1")},
            {"@type": "WorkflowRoute", "name": "Configuration -> Decision",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:config')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:decision')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r2")},
            {"@type": "WorkflowRoute", "name": "Decision -> Sample",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:decision')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:sample')}",
             "label": "Yes For Mapping", "isExecuted": False, "uuid": U("fc:r3")},
            {"@type": "WorkflowRoute", "name": "Decision -> Fetch",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:decision')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:fetch')}",
             "label": "No For Ingestion", "isExecuted": False, "uuid": U("fc:r4")},
            {"@type": "WorkflowRoute", "name": "Fetch -> Build",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:fetch')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:build')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r5")},
            {"@type": "WorkflowRoute", "name": "Build -> Create",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:build')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:create')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r6")},
            {"@type": "WorkflowRoute", "name": "Create -> Save",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:create')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:save')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r7")},
        ],
    }

    # ----- Workflow 3: Ingest orchestrator -----
    wf_ingest = {
        "@type": "Workflow",
        "name": f"{label} > Ingest",
        "description": f"Scheduled ingestion orchestrator for {label}.",
        "isActive": False, "debug": True, "parameters": [], "synchronous": False,
        "triggerStep": f"/api/3/workflow_steps/{U('in:start')}",
        "uuid": wf_ingest_uuid,
        "recordTags": ["dataingestion", "ingest", slug],
        "steps": [
            {"@type": "WorkflowStep", "name": "Start",
             "arguments": {"step_variables": {"input": {"params": []}}},
             "top": "20", "left": "20",
             "stepType": f"/api/3/workflow_step_types/{ST_START_REF}",
             "uuid": U("in:start")},
            {"@type": "WorkflowStep", "name": "Configuration",
             "arguments": {"fetchTime": "0", "pullTimeMacro": macro_name},
             "top": "100", "left": "180",
             "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
             "uuid": U("in:config")},
            {"@type": "WorkflowStep", "name": "Get Macro Value",
             "arguments": {
                 "params": {"iri": "/api/wf/api/dynamic-variable/?name={{vars.pullTimeMacro}}",
                            "body": "", "method": "GET"},
                 "version": "3.2.0", "connector": "cyops_utilities",
                 "operation": "make_cyops_request",
                 "operationTitle": "FSR: Make FortiSOAR API Call",
                 "step_variables": [],
             },
             "top": "180", "left": "380",
             "stepType": "/api/3/workflow_step_types/0109f35d-090b-4a2b-bd8a-94cbc3508562",
             "uuid": U("in:getmacro")},
            {"@type": "WorkflowStep", "name": "Extract Value from Response",
             "arguments": {
                 "lastPullTime": "{% if (vars.steps.Get_Macro_Value.data['hydra:member'] | length) > 0 %}{{ vars.steps.Get_Macro_Value.data['hydra:member'][0].value }}{% else %}0{% endif %}"
             },
             "top": "260", "left": "560",
             "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
             "uuid": U("in:extract")},
            {"@type": "WorkflowStep", "name": "Fetch Alerts",
             "arguments": {
                 "arguments": {"lastPullTime": "{{vars.lastPullTime}}"},
                 "apply_async": False,
                 "step_variables": [],
                 "workflowReference": f"/api/3/workflows/{wf_fc_uuid}",
             },
             "top": "360", "left": "760",
             "stepType": f"/api/3/workflow_step_types/{ST_WF_REF}",
             "uuid": U("in:invoke")},
            {"@type": "WorkflowStep", "name": "Update Pull Time",
             "arguments": {
                 "params": {"macro": "{{vars.pullTimeMacro}}",
                            "value": "{{vars.steps.Fetch_Alerts.currentPullTime}}"},
                 "version": "3.2.0", "connector": "cyops_utilities",
                 "operation": "updatemacro",
                 "operationTitle": "CyOPs: Update Macro",
                 "step_variables": [],
             },
             "top": "460", "left": "960",
             "stepType": "/api/3/workflow_step_types/0109f35d-090b-4a2b-bd8a-94cbc3508562",
             "uuid": U("in:updatemacro")},
        ],
        "routes": [
            {"@type": "WorkflowRoute", "name": "Start -> Configuration",
             "sourceStep": f"/api/3/workflow_steps/{U('in:start')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:config')}",
             "label": None, "isExecuted": False, "uuid": U("in:r1")},
            {"@type": "WorkflowRoute", "name": "Configuration -> Get Macro",
             "sourceStep": f"/api/3/workflow_steps/{U('in:config')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:getmacro')}",
             "label": None, "isExecuted": False, "uuid": U("in:r2")},
            {"@type": "WorkflowRoute", "name": "Get Macro -> Extract",
             "sourceStep": f"/api/3/workflow_steps/{U('in:getmacro')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:extract')}",
             "label": None, "isExecuted": False, "uuid": U("in:r3")},
            {"@type": "WorkflowRoute", "name": "Extract -> Invoke",
             "sourceStep": f"/api/3/workflow_steps/{U('in:extract')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:invoke')}",
             "label": None, "isExecuted": False, "uuid": U("in:r4")},
            {"@type": "WorkflowRoute", "name": "Invoke -> Update Macro",
             "sourceStep": f"/api/3/workflow_steps/{U('in:invoke')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:updatemacro')}",
             "label": None, "isExecuted": False, "uuid": U("in:r5")},
        ],
    }

    return {
        "type": "workflow_collections",
        "data": [{
            "@type": "WorkflowCollection",
            "name": f"Sample - {label} Data Ingestion - {version}",
            "description": (
                f"Sample data ingestion playbooks for {label}. Clone before customizing — "
                f"the sample collection is replaced on connector upgrade."
            ),
            "visible": True,
            "uuid": coll_uuid,
            "recordTags": [slug],
            "workflows": [wf_get, wf_fc, wf_ingest],
        }],
        "exported_tags": sorted({slug, "dataingestion", "ingest", "fetch", "create"}),
        "_recipe": {
            "kind": "data-ingest",
            "connector": slug,
            "fetch_op": fetch_name,
            "incremental_param": incremental_param,
            "dedup_field": dedup,
            "target_module": target_module,
            "notes": (
                "Replace REPLACE_WITH_CONFIG_UUID with the connector instance UUID after import. "
                + ("" if incremental_param else
                   "No incremental cursor detected on the fetch op; macro plumbed but unused. "
                   "Pass --incremental-param if your op accepts a cursor under a non-canonical name.")
                + " On-create alert triggers fire normally; __bulk is a batching flag only."
            ),
        },
    }


def generate_threat_feed_recipe(
    info: dict,
    *,
    connector_config_uuid: str = "REPLACE_WITH_CONFIG_UUID",
) -> dict:
    """Build the FSR workflow_collections JSON for threat-feed ingestion.

    Parameters
    ----------
    info: parsed info.json contents.
    connector_config_uuid: the FSR config UUID for the connector (visible at
        /api/3/connector_instances). The generator can't auto-resolve this
        without a live FSR; user replaces it post-import.

    Returns the full {"type": "workflow_collections", "data": [...]} dict.
    """
    slug = info["name"]
    label = info.get("label") or slug
    version = info.get("version") or "1.0.0"
    camel = _camel(slug)

    fetch_name, fetch_op = _find_fetch_op(info)
    incremental_param = _detect_incremental_param(fetch_op)

    # Stable uuids (deterministic per slug)
    coll_uuid = _uuid_from(f"{slug}:collection")
    wf_get_uuid = _uuid_from(f"{slug}:wf:get-indicators")
    wf_fc_uuid = _uuid_from(f"{slug}:wf:fetch-and-create")
    wf_ingest_uuid = _uuid_from(f"{slug}:wf:ingest")

    def U(seed: str) -> str:
        return _uuid_from(f"{slug}:{seed}")

    # Configuration schema for the wizard (pulled directly from info.json
    # if present, else built from sensible defaults)
    cfg_schema = info.get("ingestion_config_schema") or [
        {"title": "Reputation", "name": "reputation", "type": "select", "required": True,
         "options": ["Good", "Suspicious", "Malicious", "No Reputation Available", "TBD"], "value": "Suspicious"},
        {"title": "TLP", "name": "tlp", "type": "select",
         "options": ["Red", "Amber", "Green", "White"], "value": "Amber"},
        {"title": "Confidence", "name": "confidence", "type": "integer", "value": 75},
        {"title": "Maximum Age (in days)", "name": "expiry", "type": "integer", "value": 30},
    ]

    # Configuration step args: defaults from cfg_schema + picklist maps
    config_args: dict[str, Any] = {}
    for f in cfg_schema:
        config_args[f["name"]] = f.get("value", "" if f.get("type") in ("text", "select") else 0)
    config_args.update(_picklist_maps(slug))

    # Sample data for the env_setup branch
    sample_data = json.dumps([
        {"value": "192.0.2.1", "type": "ip", "score": 80, "risk_string": "sample"},
        {"value": "203.0.113.5", "type": "ip", "score": 65, "risk_string": "sample"},
    ], indent=2)

    # Macro name per-install (validates feed_ingest.macro_name_per_install)
    macro_name = f"{camel}LastPullTime_{{{{vars['audit_info']['cyops_playbook_iri'].split('/')[-1].replace('-','_')}}}}"

    # Fetch params: pass lastPullTime through if the op has an incremental param
    fetch_params: dict[str, Any] = {}
    for p in fetch_op.get("parameters") or []:
        n = p["name"]
        if n == incremental_param:
            fetch_params[n] = "{{vars.input.params.lastPullTime}}"
        elif n in config_args:
            fetch_params[n] = f"{{{{vars.{n}}}}}"
        else:
            v = p.get("value")
            if v not in (None, ""):
                fetch_params[n] = v

    # ------------ Workflow 1: Get Indicators (manual diagnostic) ------------
    wf_get = {
        "@type": "Workflow",
        "name": "Get Indicators",
        "description": f"Manually fetch indicators from {label}. Diagnostic / on-demand.",
        "isActive": False,
        "debug": True,
        "parameters": [],
        "synchronous": False,
        "triggerStep": f"/api/3/workflow_steps/{U('get:start')}",
        "uuid": wf_get_uuid,
        "recordTags": [slug],
        "steps": [
            {
                "@type": "WorkflowStep",
                "name": "Start",
                "arguments": {
                    "route": U("get:route"),
                    "title": f"{label}: Get Indicators",
                    "resources": ["alerts"],
                    "inputVariables": [],
                    "step_variables": {"input": {"params": [], "records": "{{vars.input.records}}"}},
                    "executeButtonText": "Fetch",
                    "noRecordExecution": True,
                    "singleRecordExecution": False,
                },
                "top": "40", "left": "40",
                "stepType": f"/api/3/workflow_step_types/{ST_START_TRIGGER}",
                "uuid": U("get:start"),
            },
            {
                "@type": "WorkflowStep",
                "name": fetch_op.get("title") or "Fetch Indicators",
                "arguments": {
                    "name": label,
                    "config": connector_config_uuid,
                    "params": {p["name"]: p.get("value", "") for p in (fetch_op.get("parameters") or []) if p.get("required")},
                    "version": version,
                    "connector": slug,
                    "operation": fetch_name,
                    "operationTitle": fetch_op.get("title") or fetch_name,
                    "pickFromTenant": False,
                    "step_variables": [],
                },
                "top": "200", "left": "300",
                "stepType": f"/api/3/workflow_step_types/{ST_CONNECTORS}",
                "uuid": U("get:fetch"),
            },
        ],
        "routes": [
            {"@type": "WorkflowRoute", "name": "Start -> Fetch",
             "sourceStep": f"/api/3/workflow_steps/{U('get:start')}",
             "targetStep": f"/api/3/workflow_steps/{U('get:fetch')}",
             "label": None, "isExecuted": False, "uuid": U("get:r1")},
        ],
    }

    # ------------ Workflow 2: Fetch and Create (child) ------------
    indicators_path = "vars.steps.Fetch_Indicators.indicators"
    wf_fc = {
        "@type": "Workflow",
        "name": f"> {label} > Fetch and Create",
        "description": f"Fetch and create indicators from {label}. Called as a child workflow.",
        "isActive": False,
        "debug": True,
        "parameters": ["lastPullTime"],
        "synchronous": False,
        "triggerStep": f"/api/3/workflow_steps/{U('fc:start')}",
        "uuid": wf_fc_uuid,
        "recordTags": ["dataingestion", "fetch", "create", slug],
        "steps": [
            {
                "@type": "WorkflowStep",
                "name": "Start",
                "arguments": {
                    "step_variables": {
                        "input": {"params": []},
                        "_configuration_schema": json.dumps(cfg_schema),
                    },
                },
                "top": "40", "left": "40",
                "stepType": f"/api/3/workflow_step_types/{ST_START_REF}",
                "uuid": U("fc:start"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Configuration",
                "arguments": config_args,
                "top": "160", "left": "40",
                "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
                "uuid": U("fc:config"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Is Data Only For Mapping",
                "arguments": {
                    "conditions": [
                        {"option": "Yes For Mapping",
                         "step_iri": f"/api/3/workflow_steps/{U('fc:sample')}",
                         "condition": "{{ vars.request.env_setup == true }}",
                         "step_name": "Return Sample Data"},
                        {"option": "No For Ingestion", "default": True,
                         "step_iri": f"/api/3/workflow_steps/{U('fc:fetch')}",
                         "step_name": "Fetch Indicators"},
                    ]
                },
                "top": "300", "left": "40",
                "stepType": f"/api/3/workflow_step_types/{ST_DECISION}",
                "uuid": U("fc:decision"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Return Sample Data",
                "arguments": {"data": sample_data},
                "top": "300", "left": "320",
                "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
                "uuid": U("fc:sample"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Fetch Indicators",
                "arguments": {
                    "name": label,
                    "config": connector_config_uuid,
                    "params": fetch_params,
                    "version": version,
                    "connector": slug,
                    "operation": fetch_name,
                    "operationTitle": fetch_op.get("title") or fetch_name,
                    "pickFromTenant": False,
                    "step_variables": [],
                },
                "top": "300", "left": "600",
                "stepType": f"/api/3/workflow_step_types/{ST_CONNECTORS}",
                "uuid": U("fc:fetch"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Build Feed List",
                "arguments": {
                    "data": "{{" + indicators_path + "}}",
                    "currentPullTime": "{{ arrow.utcnow().isoformat() }}",
                },
                "top": "440", "left": "600",
                "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
                "uuid": U("fc:build"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Create Record",
                "arguments": {
                    "when": "{{vars.data | length > 0}}",
                    "for_each": {"item": "{{vars.data}}", "__bulk": True, "condition": "", "batch_size": 100},
                    "resource": {
                        "value": "{{vars.item.value}}",
                        "typeOfFeed": "{{ vars.item.type | resolveRange(vars.type_of_feed_map) }}",
                        "source": label,
                        "sourceId": "{{vars.item.value}}",
                        "tLP": "{% if vars.tlp %}{{ vars.tlp | resolveRange(vars.tlp_map) }}{% else %}None{% endif %}",
                        "reputation": "{% if vars.reputation %}{{ vars.reputation | resolveRange(vars.reputation_map) }}{% else %}None{% endif %}",
                        "confidence": "{% if vars.confidence %}{{ vars.confidence }}{% else %}{{ (vars.item.score | int) }}{% endif %}",
                        "expiresOn": "{% if vars.expiry %}{{ arrow.utcnow().int_timestamp + (vars.expiry | int)*24*60*60 }}{% else %}None{% endif %}",
                        "sourceData": "{{vars.item | toJSON}}",
                        "description": f"{{% if vars.item.risk_string %}}{label}: {{{{vars.item.risk_string}}}}{{% else %}}{label} indicator{{% endif %}}",
                        "__replace": "",
                    },
                    "_showJson": False,
                    "collection": "/api/ingest-feeds/threat_intel_feeds",
                    "__recommend": [],
                    "step_variables": [],
                },
                "top": "560", "left": "600",
                "stepType": f"/api/3/workflow_step_types/{ST_INGEST_BULK_FEED}",
                "uuid": U("fc:ibf"),
            },
            {
                "@type": "WorkflowStep",
                "name": "Save Result",
                "arguments": {"currentPullTime": "{{vars.currentPullTime}}"},
                "top": "680", "left": "600",
                "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
                "uuid": U("fc:save"),
            },
        ],
        "routes": [
            {"@type": "WorkflowRoute", "name": "Start -> Configuration",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:start')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:config')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r1")},
            {"@type": "WorkflowRoute", "name": "Configuration -> Decision",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:config')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:decision')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r2")},
            {"@type": "WorkflowRoute", "name": "Decision -> Sample",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:decision')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:sample')}",
             "label": "Yes For Mapping", "isExecuted": False, "uuid": U("fc:r3")},
            {"@type": "WorkflowRoute", "name": "Decision -> Fetch",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:decision')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:fetch')}",
             "label": "No For Ingestion", "isExecuted": False, "uuid": U("fc:r4")},
            {"@type": "WorkflowRoute", "name": "Fetch -> Build",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:fetch')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:build')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r5")},
            {"@type": "WorkflowRoute", "name": "Build -> Create",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:build')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:ibf')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r6")},
            {"@type": "WorkflowRoute", "name": "Create -> Save",
             "sourceStep": f"/api/3/workflow_steps/{U('fc:ibf')}",
             "targetStep": f"/api/3/workflow_steps/{U('fc:save')}",
             "label": None, "isExecuted": False, "uuid": U("fc:r7")},
        ],
    }

    # ------------ Workflow 3: Ingest (orchestrator) ------------
    wf_ingest = {
        "@type": "Workflow",
        "name": f"{label} > Ingest",
        "description": f"Scheduled ingestion orchestrator for {label}. Maintains per-install LastPullTime macro.",
        "isActive": False,
        "debug": True,
        "parameters": [],
        "synchronous": False,
        "triggerStep": f"/api/3/workflow_steps/{U('in:start')}",
        "uuid": wf_ingest_uuid,
        "recordTags": ["dataingestion", "ingest", slug],
        "steps": [
            {
                "@type": "WorkflowStep", "name": "Start",
                "arguments": {"step_variables": {"input": {"params": []}}},
                "top": "20", "left": "20",
                "stepType": f"/api/3/workflow_step_types/{ST_START_REF}",
                "uuid": U("in:start"),
            },
            {
                "@type": "WorkflowStep", "name": "Configuration",
                "arguments": {"fetchTime": "0", "pullTimeMacro": macro_name},
                "top": "100", "left": "180",
                "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
                "uuid": U("in:config"),
            },
            {
                "@type": "WorkflowStep", "name": "Get Macro Value",
                "arguments": {
                    "params": {"iri": "/api/wf/api/dynamic-variable/?name={{vars.pullTimeMacro}}",
                               "body": "", "method": "GET"},
                    "version": "3.2.0", "connector": "cyops_utilities",
                    "operation": "make_cyops_request",
                    "operationTitle": "FSR: Make FortiSOAR API Call",
                    "step_variables": [],
                },
                "top": "180", "left": "380",
                "stepType": "/api/3/workflow_step_types/0109f35d-090b-4a2b-bd8a-94cbc3508562",
                "uuid": U("in:getmacro"),
            },
            {
                "@type": "WorkflowStep", "name": "Extract Value from Response",
                "arguments": {
                    "lastPullTime": "{% if (vars.steps.Get_Macro_Value.data['hydra:member'] | length) > 0 %}{{ vars.steps.Get_Macro_Value.data['hydra:member'][0].value }}{% else %}0{% endif %}"
                },
                "top": "260", "left": "560",
                "stepType": f"/api/3/workflow_step_types/{ST_SET_VAR}",
                "uuid": U("in:extract"),
            },
            {
                "@type": "WorkflowStep", "name": "Fetch Indicators",
                "arguments": {
                    "arguments": {"lastPullTime": "{{vars.lastPullTime}}"},
                    "apply_async": False,
                    "step_variables": [],
                    "workflowReference": f"/api/3/workflows/{wf_fc_uuid}",
                },
                "top": "360", "left": "760",
                "stepType": f"/api/3/workflow_step_types/{ST_WF_REF}",
                "uuid": U("in:invoke"),
            },
            {
                "@type": "WorkflowStep", "name": "Update Pull Time",
                "arguments": {
                    "params": {"macro": "{{vars.pullTimeMacro}}",
                               "value": "{{vars.steps.Fetch_Indicators.currentPullTime}}"},
                    "version": "3.2.0", "connector": "cyops_utilities",
                    "operation": "updatemacro",
                    "operationTitle": "CyOPs: Update Macro",
                    "step_variables": [],
                },
                "top": "460", "left": "960",
                "stepType": "/api/3/workflow_step_types/0109f35d-090b-4a2b-bd8a-94cbc3508562",
                "uuid": U("in:updatemacro"),
            },
        ],
        "routes": [
            {"@type": "WorkflowRoute", "name": "Start -> Configuration",
             "sourceStep": f"/api/3/workflow_steps/{U('in:start')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:config')}",
             "label": None, "isExecuted": False, "uuid": U("in:r1")},
            {"@type": "WorkflowRoute", "name": "Configuration -> Get Macro",
             "sourceStep": f"/api/3/workflow_steps/{U('in:config')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:getmacro')}",
             "label": None, "isExecuted": False, "uuid": U("in:r2")},
            {"@type": "WorkflowRoute", "name": "Get Macro -> Extract",
             "sourceStep": f"/api/3/workflow_steps/{U('in:getmacro')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:extract')}",
             "label": None, "isExecuted": False, "uuid": U("in:r3")},
            {"@type": "WorkflowRoute", "name": "Extract -> Invoke",
             "sourceStep": f"/api/3/workflow_steps/{U('in:extract')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:invoke')}",
             "label": None, "isExecuted": False, "uuid": U("in:r4")},
            {"@type": "WorkflowRoute", "name": "Invoke -> Update Macro",
             "sourceStep": f"/api/3/workflow_steps/{U('in:invoke')}",
             "targetStep": f"/api/3/workflow_steps/{U('in:updatemacro')}",
             "label": None, "isExecuted": False, "uuid": U("in:r5")},
        ],
    }

    collection_tags = [slug]
    if "ThreatIntel" in (info.get("tags") or []):
        collection_tags.append("ThreatIntel")

    return {
        "type": "workflow_collections",
        "data": [{
            "@type": "WorkflowCollection",
            "name": f"Sample - {label} - {version}",
            "description": (
                f"Sample playbooks for {label}. Clone these into a separate "
                f"collection before customizing — the sample collection is "
                f"replaced on connector upgrade."
            ),
            "visible": True,
            "uuid": coll_uuid,
            "recordTags": collection_tags,
            "workflows": [wf_get, wf_fc, wf_ingest],
        }],
        "exported_tags": sorted({slug, "dataingestion", "ingest", "fetch", "create", *collection_tags}),
        "_recipe": {
            "kind": "threat-feed",
            "connector": slug,
            "fetch_op": fetch_name,
            "incremental_param": incremental_param,
            "notes": (
                "Replace REPLACE_WITH_CONFIG_UUID with the connector instance UUID after import. "
                + ("" if incremental_param else
                   "This connector exposes no incremental cursor; the macro is plumbed structurally but unused. "
                   "Dedup relies on `__replace: \"\"` in the IBF resource."))
        },
    }
