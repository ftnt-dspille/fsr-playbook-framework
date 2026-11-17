"""Generate a Data Ingestion Wizard playbook collection as fsr_playbooks YAML.

The output is the canonical three-playbook ingestion chain (the shape the
FortiSIEM v2 / FortiAIGate sample collections use and the ``data-ingest``
ruleset checks), with the vendor fetch stubbed by the Utilities connector's
"Make REST API Call" (``cyops_utilities`` / ``api_call``). Swap that one step
for the real connector action once the connector exists; everything else is
the finished pattern.

Playbooks emitted::

    >> <Label> > Init Macros   creates the last-pull-time macro if missing
    >  <Label> > Fetch         Start carries the wizard's configuration form,
                               "Configuration" set_variable, macro read,
                               "Fetch" step (REST stand-in), "Save Result"
       <Label> > Ingest        env_setup -> Return Sample for the Data Mapping
                               preview; else "Create Record" (bulk upsert keyed
                               on the module's natural key), then advance the
                               macro LAST so a failed write re-reads its window

Best practices baked in (each one cost a real run somewhere):

* tags: every playbook carries ``dataingestion`` + the connector slug; Fetch
  ``fetch``, Ingest ``ingest`` + ``create``; the collection exports them all.
* the create step is named exactly "Create Record" (the wizard hides the Data
  Mapping page otherwise) and targets ``/api/3/<module>``.
* ``is_upsert`` + the natural key (``sourceId`` for alerts/incidents): without
  it every run inserts a new record and looks like a failing update.
* ``__fieldsToUpdate`` so an update never wipes fields the mapping does not set.
* ``sourcedata`` is ``| toJSON`` (a bare dict renders as the string "Array").
* the watermark macro is scoped to the Fetch playbook's UUID, so two ingestion
  configurations never share a high-water mark; ``updatemacro`` upserts.
* the window end is captured BEFORE the fetch, lagged behind the clock, and is
  written back only after Create Record succeeds (at-least-once).
* a window that reaches Maximum Records Per Run fails the run instead of
  advancing the watermark past records the API's limit cut off.
* state/status are create-only: an update never resets an analyst's triage.
* a cold start (macro missing or ``'0'``) reads a bounded backfill, never the
  epoch.
* Create Record is NOT bulk by default: bulk create skips on-create playbooks
  (most shipped ingesters do bulk; ``bulk=True`` opts in).
* severity (and optionally status) map through a picklist mapping variable read
  with ``resolveRange``, the shipped M365 Defender / Elasticsearch shape.
* optional paging (``page_param`` + ``total_path``): first page reports the total,
  the rest are fetched in one for_each over an offset list (FortiAnalyzer's shape).
* optional MSSP tenant, fixed or mapped per record (FortiSIEM's shape).
* the Fetch step carries a ``mock_result`` (the sample record) so
  ``fsrpb run-playbook --mock`` exercises the chain before any endpoint exists.
* the env_setup preview never writes records and falls back to a sample record
  so the mapping page renders even on an empty window.

Example::

    from fsr_playbooks.ingestion_template import IngestionSpec, render_ingestion_yaml

    yaml_text = render_ingestion_yaml(IngestionSpec(
        slug="acme-edr", label="Acme EDR",
        url="https://edr.example.com/api/v1/detections",
        query_params={"since": "{{ vars.last_pull_time }}", "limit": "{{ vars.max_items }}"},
        records_path="items",
        source_id_field="id",
    ))
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

__all__ = ["IngestionSpec", "render_ingestion_yaml", "ingestion_template"]

# Natural (unique-constraint) key per module for the upsert. Read from
# /api/3/model_metadatas uniqueConstraint on a live 8.0 box.
_NATURAL_KEY = {"alerts": "sourceId", "incidents": "sourceId"}

_STATUS_PICKLIST = {"alerts": "AlertStatus", "incidents": "IncidentStatus"}

_CREATE_ONLY = {"alerts": {
    "state": '{{ "AlertState" | picklist("New") }}',
    "status": '{{ "AlertStatus" | picklist("Open") }}',
}}

_DEFAULT_SAMPLE = {
    "id": "sample-0001",
    "title": "Sample detection",
    "severity": "high",
    "created": "2026-01-01T00:00:00Z",
    "description": "Representative record for the Data Mapping preview.",
}


@dataclass
class IngestionSpec:
    """Everything the template needs. Only ``slug``, ``label`` and ``url`` are required.

    Jinja in ``url`` / ``query_params`` / ``headers`` / ``body`` may use
    ``vars.window_from`` (watermark, or now minus the backfill on a cold start),
    ``vars.curr_timestamp`` (window end), ``vars.backfill_days`` and ``vars.max_items``.
    """

    slug: str
    """Connector API name, used as the discovery tag (e.g. ``acme-edr``)."""
    label: str
    """Human name used in playbook names (e.g. ``Acme EDR``)."""
    url: str
    """Stand-in REST endpoint for Utilities > Make REST API Call."""
    method: str = "GET"
    query_params: dict[str, str] = field(default_factory=lambda: {
        "since": "{{ vars.window_from }}",
        "until": "{{ vars.curr_timestamp }}",
        "limit": "{{ vars.max_items }}",
    })
    time_format: str = "YYYY-MM-DDTHH:mm:ss[Z]"
    """arrow format for ``window_from`` / ``curr_timestamp`` (the API's native format)."""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    verify_ssl: bool = True
    records_path: str = ""
    """Dotted path into the response body to the record list (``""`` = body is the list)."""
    module: str = "alerts"
    source_id_field: str = "id"
    """Record key that becomes the natural key (``sourceId``)."""
    name_template: str = "{{ vars.item.title | default('Untitled') | truncate(250) }}"
    description_template: str = "{{ vars.item.description | default('') | e }}"
    severity_field: str | None = "severity"
    severity_map: dict[str, str] = field(default_factory=lambda: {
        "critical": "Critical", "high": "High", "medium": "Medium", "low": "Low",
    })
    """Vendor value (lower-cased) -> FortiSOAR Severity picklist item."""
    default_severity: str = "Medium"
    severity_expr: str | None = None
    """Jinja expression (no braces) for the vendor severity when it is nested or
    optional, e.g. ``(vars.item.metrics.cvss or [{}])[0].get('severity')``.
    Overrides ``severity_field``."""
    status_field: str | None = None
    """Record key holding the vendor's own state. When set (or ``status_expr``),
    status is MAPPED and refreshed on every update instead of create-only New/Open."""
    status_expr: str | None = None
    status_map: dict[str, str] = field(default_factory=dict)
    """Vendor value (lower-cased) -> AlertStatus / IncidentStatus picklist item."""
    default_status: str = "Open"
    tenant: str | None = None
    """MSSP: one FortiSOAR tenant name every record belongs to."""
    tenant_field: str | None = None
    """MSSP: record key naming the vendor's customer; mapped through ``tenant_mapping``."""
    tenant_mapping: dict[str, str] = field(default_factory=dict)
    """Vendor customer value -> FortiSOAR tenant name (with ``tenant_field``)."""
    page_param: str | None = None
    """Offset query parameter (``startIndex``, ``offset``). Enables paging: the first
    page reports the total (``total_path``), the rest are fetched in one for_each."""
    page_size_param: str | None = None
    """Page-size query parameter (``resultsPerPage``, ``limit``)."""
    page_size: int = 100
    page_start: int = 0
    total_path: str | None = None
    """Dotted path in the response body to the window's total record count."""
    extra_fields: dict[str, str] = field(default_factory=dict)
    """Additional module field -> Jinja over ``vars.item`` (refreshed on every update)."""
    create_only_fields: dict[str, str] | None = None
    """Fields set on create but never on update, so a re-read never resets an
    analyst's triage. ``None`` = alerts: state New / status Open; incidents: none."""
    bulk: bool = False
    """Bulk create (``__bulk``, batches of 100) -- what most shipped ingesters use
    (FortiSIEM, M365 Defender, Elasticsearch). OFF by default: a bulk create does
    not fire on-create playbooks (enrichment, escalation, dedupe), and an alert
    pipeline usually depends on them. Turn it on for high-volume windows where
    nothing downstream triggers on create."""
    backfill_days: int = 7
    max_items: int = 500
    lag_seconds: int = 60
    sample_record: dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_SAMPLE))
    version: str = "1.0.0"
    collection: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.slug):
            raise ValueError(f"slug must be a connector API name (lowercase, -, _): {self.slug!r}")
        if self.module not in _NATURAL_KEY:
            raise ValueError(
                f"module {self.module!r} has no known natural key; supported: {sorted(_NATURAL_KEY)}"
            )
        self.method = self.method.upper()
        if self.create_only_fields is None:
            self.create_only_fields = dict(_CREATE_ONLY.get(self.module, {}))
            if self.status_field or self.status_expr:
                self.create_only_fields.pop("status", None)
        if self.page_param and not self.total_path:
            raise ValueError("page_param needs total_path (where the response reports the total)")
        if self.tenant and self.tenant_field:
            raise ValueError("pass tenant (one fixed tenant) or tenant_field (+ tenant_mapping), not both")


class _Literal(str):
    """Rendered as a YAML block scalar for readability."""


def _repr_literal(dumper: yaml.SafeDumper, value: _Literal) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(_Literal, _repr_literal)


def _path(base: str, dotted: str) -> str:
    for part in [p for p in dotted.split(".") if p]:
        base += f"[{part!r}]" if not part.isdigit() else f"[{part}]"
    return base


def _records_expr(spec: IngestionSpec) -> str:
    """Save Result's ``data``: the first page's records, plus every later page when paging."""
    first = _path("vars.steps.Fetch.data", spec.records_path)
    if not spec.page_param:
        return "{{ " + first + " | default([]) }}"
    # FortiAnalyzer's list.append idiom: proven in shipped ingestion playbooks.
    page = _path("env.data", spec.records_path)
    return ("{% set out = [] %}"
            f"{{% for r in ({first} | default([]) or []) %}}{{% set _ = out.append(r) %}}{{% endfor %}}"
            "{% for env in (vars.steps.Fetch_Remaining_Pages | default([]) or []) %}"
            f"{{% for r in ({page} | default([]) or []) %}}{{% set _ = out.append(r) %}}{{% endfor %}}"
            "{% endfor %}{{ out }}")


def _mock_body(spec: IngestionSpec) -> Any:
    """The sample record wrapped at ``records_path``: what ``fsrpb run-playbook --mock`` returns."""
    body: Any = [spec.sample_record]
    for part in reversed([p for p in spec.records_path.split(".") if p]):
        body = {part: body}
    return body


def _picklist_map(picklist: str, table: dict[str, str]) -> str:
    """The shipped mapping-variable shape (M365 Defender, Elasticsearch):
    ``{'high': {{'Severity' | picklist('High')}}, ...}``, read with resolveRange."""
    items = ", ".join(f"{k.lower()!r}: {{{{ {picklist!r} | picklist({v!r}) }}}}" for k, v in table.items())
    return "{" + items + "}"


def _mapped(src: str, map_var: str, picklist: str, default: str) -> str:
    return (f"{{{{ (({src}) | default('') | string | lower | resolveRange(vars.{map_var})) "
            f"or ({picklist!r} | picklist({default!r})) }}}}")


def _severity_expr(spec: IngestionSpec) -> str:
    if not (spec.severity_field or spec.severity_expr):
        return f"{{{{ 'Severity' | picklist({spec.default_severity!r}) }}}}"
    src = spec.severity_expr or f"vars.item.{spec.severity_field}"
    return _mapped(src, "severity_map", "Severity", spec.default_severity)


def ingestion_template(spec: IngestionSpec) -> dict[str, Any]:
    """Return the collection as a plain dict in fsr_playbooks YAML shape.

    Step-for-step this follows the shipped FortiEDR v2 / FortiAIGate chains
    (ConnectorsV2/fortinet-fortiedrv2/playbooks/playbooks.yaml), live-verified
    with the Data Ingestion Wizard on 8.0.
    """
    lbl, slug = spec.label, spec.slug
    stem = re.sub(r"[^A-Za-z0-9]", "", lbl)
    mname, mval = f"{stem}MacroName", f"{stem}MacroValue"
    init_name = f">> {lbl} > Init Macros"
    fetch_name = f"> {lbl} > Fetch"
    ingest_name = f"{lbl} > Ingest"
    key = _NATURAL_KEY[spec.module]
    ip = "vars.input.params"
    dv = "/api/wf/api/dynamic-variable/"

    def utils(name, op, params, **kw):
        return {"name": name, "type": "connector", "connector": "cyops_utilities",
                "operation": op, "config": "", **kw, "params": params}

    macro_body = f"{{ 'name': '{{{{{ip}.{mname}}}}}', 'value': '{{{{{ip}.{mval}}}}}' }}"
    init = {
        "name": init_name,
        "description": f"Creates the {lbl} last-pull-time macro if it does not already exist. "
                       "Called by Fetch during the wizard's environment-setup pass, and by Fetch "
                       "whenever the macro is missing.",
        "tags": [slug, "dataingestion"],
        "is_active": True,
        "parameters": [mname, mval, "overrideIfNoMatch"],
        "steps": [
            {"name": "Start", "type": "start", "next": "Get Macros"},
            utils("Get Macros", "make_cyops_request",
                  {"iri": f"{dv}?format=json&name={{{{{ip}.{mname}}}}}", "body": "", "method": "GET"},
                  next="Macro Exists"),
            {"name": "Macro Exists", "type": "decision", "conditions": [
                {"display": "Not Exist", "when": "{{ vars.steps.Get_Macros.data['hydra:totalItems'] == 0 }}",
                 "next": "Create Macro"},
                {"display": "Exist", "default": True, "next": "Fetch Macro Current Value"},
            ]},
            utils("Create Macro", "make_cyops_request",
                  {"iri": f"{dv}?format=json", "body": macro_body, "method": "POST"}),
            {"name": "Fetch Macro Current Value", "type": "set_variable",
             "vars": {"macroExistingRecord": "{{vars.steps.Get_Macros.data['hydra:member'][0]}}"},
             "next": "Update Macro If Required"},
            utils("Update Macro If Required", "make_cyops_request",
                  {"iri": f"{dv}{{{{ vars.macroExistingRecord.id }}}}/", "body": macro_body, "method": "PUT"},
                  when=f"{{{{ ({ip}.overrideIfNoMatch == true) and "
                       f"(vars.macroExistingRecord.value != {ip}.{mval}) }}}}"),
        ],
    }

    count = ("(vars.total | int)" if spec.page_param
             else f"({_path('vars.steps.Fetch.data', spec.records_path)} | default([]) | length)")

    total_src = f"{_path('vars.steps.Fetch.data', spec.total_path or '')} | default(0) | int"

    def rest_params(offset: Any) -> dict[str, Any]:
        query = dict(spec.query_params)
        if spec.page_param:
            query[spec.page_param] = str(offset)
            if spec.page_size_param:
                query[spec.page_size_param] = str(spec.page_size)
        return {k: v for k, v in {
            "url": spec.url, "method": spec.method,
            "params": json.dumps(query) if query else "",
            "body": spec.body,
            "headers": json.dumps(spec.headers) if spec.headers else "",
            "verify": spec.verify_ssl,
        }.items() if v != ""}
    fetch = {
        "name": fetch_name,
        "description": f"Reads the last-pull-time watermark and fetches {lbl} records since then. "
                       "STAND-IN: the Fetch step is Utilities > Make REST API Call; replace it with "
                       f"the {lbl} connector action when one exists and keep the step name.",
        "tags": [slug, "fetch", "dataingestion"],
        "is_active": True,
        "steps": [
            {"name": "Start", "type": "start", "configuration_schema": [
                {"title": "Initial Backfill (Days)", "required": True, "editable": True, "visible": True,
                 "type": "text", "name": "backfill_days", "value": str(spec.backfill_days),
                 "tooltip": "How many days back the first run reads, before a last-pull-time "
                            "watermark exists. Later runs read from the watermark."},
                {"title": "Maximum Records Per Run", "required": False, "editable": True, "visible": True,
                 "type": "text", "name": "max_items", "value": str(spec.max_items),
                 "tooltip": "Safety cap. A window that reaches it FAILS the run instead of silently "
                            "skipping records; raise it or shorten the schedule rather than let it bind."},
             ], "next": "Configuration"},
            {"name": "Configuration", "type": "set_variable",
             "comment": "Wizard-editable defaults; the schema field names map 1:1 onto these keys "
                        "(the wizard writes the analyst's values here). The macro name is scoped to "
                        "this playbook's UUID so two ingestion configurations never share a watermark.",
             "vars": {
                 "backfill_days": str(spec.backfill_days),
                 "max_items": str(spec.max_items),
                 mname: f"{stem}LastPullTime_{{{{vars['audit_info']['cyops_playbook_iri'].split('/')[-1].replace('-','_')}}}}",
             }, "next": "Get Macro Value"},
            utils("Get Macro Value", "make_cyops_request",
                  {"iri": f"{dv}?format=json&name={{{{vars.{mname}}}}}", "body": "", "method": "GET"},
                  next="Environment Setup"),
            {"name": "Environment Setup", "type": "workflow_reference",
             "comment": "Runs on the wizard's env_setup pass AND whenever the macro is missing: "
                        "Update Last Pull Time does not create it, so a missing macro would re-read the "
                        "backfill forever. Primed to '0', read as a cold start.",
             "when": '{{ vars.request.env_setup or not vars.steps.Get_Macro_Value.data["hydra:member"] }}',
             "target": init_name,
             mname: f"{{{{vars.{mname}}}}}", mval: "0", "overrideIfNoMatch": "false",
             "apply_async": False, "pass_parent_env": False, "pass_input_record": False,
             "next": "Set Time Configuration"},
            {"name": "Set Time Configuration", "type": "set_variable",
             "comment": f"The window end is {spec.lag_seconds}s behind the clock and written back only "
                        "after Create Record succeeds. A cold start (macro missing or '0') reads "
                        "now minus the backfill instead of the watermark.",
             "vars": {
                 "curr_timestamp": f"{{{{ arrow.utcnow().shift(seconds=-{spec.lag_seconds}).format('{spec.time_format}') }}}}",
                 "last_pull_time": "{% if vars.request.env_setup or not vars.steps.Get_Macro_Value.data['hydra:member'] "
                                   "or vars.steps.Get_Macro_Value.data['hydra:member'][0].value == '0' %}{% else %}"
                                   "{{ vars.steps.Get_Macro_Value.data['hydra:member'][0].value }}{% endif %}",
                 "window_from": "{% if vars.last_pull_time %}{{ vars.last_pull_time }}{% else %}"
                                f"{{{{ arrow.utcnow().shift(days=-(vars.backfill_days|int)).format('{spec.time_format}') }}}}{{% endif %}}",
             }, "next": "Fetch"},
            utils("Fetch", "api_call", rest_params(spec.page_start),
                  comment=f"STAND-IN for the {lbl} connector: Utilities > Make REST API Call. "
                          "Replace with the connector's fetch action and keep the step name 'Fetch'."
                          + (" This is the FIRST page; it also reports the window's total."
                             if spec.page_param else ""),
                  mock_result=_Literal(json.dumps({"data": _mock_body(spec)}, indent=2) + "\n"),
                  next="Paging Plan" if spec.page_param else "Within Cap"),
            *([{"name": "Paging Plan", "type": "set_variable",
                "comment": "The window's true total (from the first page) and the offsets of the "
                           "remaining pages (FortiAnalyzer's offset-list pattern).",
                "vars": {
                    "total": f"{{{{ {total_src} }}}}",
                    # Reads the total inline: a set_variable step's vars are not
                    # guaranteed to see each other.
                    "offset_list": f"{{% set out = [] %}}{{% for n in range({spec.page_start + spec.page_size}, "
                                   f"{spec.page_start} + ({total_src}), {spec.page_size}) %}}"
                                   "{% set _ = out.append(n) %}{% endfor %}{{ out }}",
                }, "next": "Within Cap"}] if spec.page_param else []),
            {"name": "Within Cap", "type": "decision",
             "comment": ("A window over Maximum Records Per Run fails the run rather than advance the "
                         "watermark past records it never read (FortiEDR v2's count-verified window). "
                         + ("With paging the count is the API's own total, so every page up to the "
                            "cap is read." if spec.page_param else
                            "Without paging, reaching the cap means the API's limit may have cut the "
                            "window short, so reaching it fails too.")),
             "conditions": [
                 {"display": "Over Cap",
                  "when": f"{{{{ {count} {'>' if spec.page_param else '>='} (vars.max_items | int) }}}}",
                  "next": "Window Over Cap"},
                 {"display": "Within Cap", "default": True,
                  "next": "Fetch Remaining Pages" if spec.page_param else "Save Result"},
             ]},
            utils("Window Over Cap", "raise_exception",
                  {"msg": f"{{{{ {count} }}}} {lbl} records in the window from {{{{vars.window_from}}}} "
                          "reach Maximum Records Per Run ({{vars.max_items}}); the watermark was not "
                          "advanced. Raise the cap or shorten the schedule."},
                  mock_result=_Literal(json.dumps({"error": "window over Maximum Records Per Run"}) + "\n")),
            *([utils("Fetch Remaining Pages", "api_call", rest_params("{{ vars.item }}"),
                     comment="One request per remaining offset; for_each keeps every page's "
                             "envelope, in order, for Save Result to concatenate.",
                     when="{{ vars.offset_list | length > 0 }}",
                     for_each={"item": "{{ vars.offset_list }}", "condition": ""},
                     mock_result=_Literal(json.dumps({"data": _mock_body(spec)}, indent=2) + "\n"),
                     next="Save Result")] if spec.page_param else []),
            {"name": "Save Result", "type": "set_variable",
             "comment": "The Fetch -> Ingest contract; Ingest reads these off its workflow_reference step.",
             "vars": {"data": _records_expr(spec), "current_time": "{{vars.curr_timestamp}}",
                      mname: f"{{{{vars.{mname}}}}}"}},
        ],
    }

    fields: dict[str, Any] = {
        "name": spec.name_template,
        "source": lbl,
        key: f"{{{{ vars.item.{spec.source_id_field} | string }}}}",
        "severity": _severity_expr(spec),
        "description": spec.description_template,
        "sourcedata": "{{ vars.item | toJSON }}",
    }
    mapping_vars: dict[str, str] = {}
    if spec.severity_field or spec.severity_expr:
        mapping_vars["severity_map"] = _picklist_map("Severity", spec.severity_map)
    if spec.status_field or spec.status_expr:
        sp = _STATUS_PICKLIST[spec.module]
        mapping_vars["status_map"] = _picklist_map(sp, spec.status_map)
        fields["status"] = _mapped(spec.status_expr or f"vars.item.{spec.status_field}",
                                   "status_map", sp, spec.default_status)
    tenant_steps: list[dict[str, Any]] = []
    if spec.tenant or spec.tenant_field:
        tenant_steps = [utils("Get Tenants", "make_cyops_request",
                              {"iri": "/api/3/tenants?$limit=1000", "body": "", "method": "GET"},
                              comment="MSSP: tenant name -> IRI for the records' tenant field.",
                              next="Configuration")]
        mapping_vars["tenant_ids"] = ("{% set out = {} %}{% for t in vars.steps.Get_Tenants.data['hydra:member'] %}"
                                      "{% set _ = out.update({t.name: t['@id']}) %}{% endfor %}{{ out }}")
        if spec.tenant:
            fields["tenant"] = f"{{{{ vars.tenant_ids.get({spec.tenant!r}) }}}}"
        else:
            mapping_vars["tenant_mapping"] = json.dumps(spec.tenant_mapping)
            fields["tenant"] = (f"{{{{ vars.tenant_ids.get(vars.tenant_mapping.get(vars.item.{spec.tenant_field} "
                                "| default('') | string)) }}")
    fields.update(spec.extra_fields)
    updatable = list(fields)
    fields.update(spec.create_only_fields or {})
    fields["__replace"] = "true"
    fields["__fieldsToUpdate"] = "{{ " + repr(updatable) + " }}"

    ingest = {
        "name": ingest_name,
        "description": "Orchestrator: calls Fetch, then either returns a sample record for the "
                       "wizard's Data Mapping preview (env_setup) or upserts one "
                       f"{spec.module} record per item and advances the last-pull-time watermark.",
        "tags": [slug, "ingest", "dataingestion", "create"],
        "is_active": True,
        "steps": [
            {"name": "Start", "type": "start", "module": spec.module,
             "button_label": ingest_name, "requires_record": False, "next": "Fetch Records"},
            {"name": "Fetch Records", "type": "workflow_reference", "target": fetch_name,
             "apply_async": False, "pass_parent_env": False, "pass_input_record": False,
             "next": "Mapping Preview"},
            {"name": "Mapping Preview", "type": "decision",
             "comment": "The wizard runs Ingest with vars.request.env_setup == true while the "
                        "analyst maps fields; return a sample and write nothing.",
             "conditions": [
                 {"display": "Mapping Preview", "when": "{{ vars.request.env_setup | default(false) | bool }}",
                  "next": "Return Sample"},
                 {"display": "Ingest", "default": True,
                  "next": "Get Tenants" if tenant_steps else "Configuration"},
             ]},
            {"name": "Return Sample", "type": "set_variable", "vars": {
                "sample": "{% if vars.steps.Fetch_Records.data | default([]) | length > 0 %}"
                          "{{ vars.steps.Fetch_Records.data[0] }}{% else %}"
                          f"{{{{ {json.dumps(spec.sample_record)} }}}}{{% endif %}}",
            }},
            *tenant_steps,
            {"name": "Configuration", "type": "set_variable",
             "comment": "The window's records, the macro holding its watermark, and the vendor -> "
                        "picklist mappings Create Record reads with resolveRange (the shipped "
                        "M365 Defender / Elasticsearch shape). Edit the mappings here.",
             "vars": {
                "incident_source_data": "{{ vars.steps.Fetch_Records.data }}",
                mname: f"{{{{ vars.steps.Fetch_Records.{mname} }}}}",
                **mapping_vars,
             }, "next": "Create Record"},
            {"name": "Create Record", "type": "create_record", "module": spec.module,
             "operation": "Overwrite", "is_upsert": True,
             "comment": "Named exactly 'Create Record': the wizard shows the Data Mapping page only "
                        f"for a step of that name. Upsert keyed on {key} so a re-read window updates "
                        "rather than duplicates. __fieldsToUpdate leaves the create-only fields "
                        "(state/status) alone on an update, so a re-read never resets triage.",
             "for_each": ({"item": "{{ vars.incident_source_data }}", "__bulk": True,
                           "batch_size": 100, "condition": ""} if spec.bulk
                          else {"item": "{{ vars.incident_source_data }}", "condition": ""}),
             "fields": fields,
             "next": "Update Last Pull Time"},
            utils("Update Last Pull Time", "updatemacro",
                  {"macro": f"{{{{vars.{mname}}}}}", "value": "{{vars.steps.Fetch_Records.current_time}}"},
                  operationTitle="FSR: Update Global Variables",
                  comment="Advance the watermark LAST, only after the records are written."),
        ],
    }

    tags = [slug, "dataingestion"]
    return {
        "collection": spec.collection or f"Sample - {lbl} - {spec.version}",
        "description": f"Data ingestion playbooks for {lbl}. Generated by "
                       "fsr_playbooks.ingestion_template; clone before customising.",
        "visible": True,
        "tags": tags,
        "exported_tags": tags + ["fetch", "create", "ingest"],
        "playbooks": [init, fetch, ingest],
    }


def render_ingestion_yaml(spec: IngestionSpec) -> str:
    """Render :func:`ingestion_template` as fsr_playbooks YAML text."""
    header = (
        f"# Data ingestion playbooks for {spec.label} ({spec.slug}).\n"
        "# Generated by fsr_playbooks.ingestion_template. The 'Fetch' step is a\n"
        "# Utilities > Make REST API Call stand-in: swap in the connector action.\n\n"
    )
    return header + yaml.dump(ingestion_template(spec), Dumper=_Dumper, sort_keys=False,
                              allow_unicode=True, width=100)
