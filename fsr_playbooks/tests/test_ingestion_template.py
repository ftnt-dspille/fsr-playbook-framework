"""fsr_playbooks.ingestion_template emits a wizard-ready collection that compiles clean."""
from __future__ import annotations

import json

import pytest
import yaml

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler import rulesets as rs
from fsr_playbooks.ingestion_template import IngestionSpec, render_ingestion_yaml


def _spec(**kw):
    base = dict(slug="acme-edr", label="Acme EDR",
                url="https://edr.example.com/api/v1/detections", records_path="items")
    base.update(kw)
    return IngestionSpec(**base)


def _compile(spec):
    res = compile_yaml(render_ingestion_yaml(spec), default_db_path())
    assert res.ok, [str(e) for e in res.errors]
    return res


@pytest.mark.parametrize("module", ["alerts", "incidents"])
def test_compiles_without_diagnostics_or_ruleset_issues(module):
    res = _compile(_spec(module=module))
    assert [e for e in res.errors if e.severity == "error"] == []
    assert not getattr(res, "warnings", [])
    doc = res.fsr_json
    assert rs.detect_rulesets(doc) == ["data-ingest"]
    assert rs.validate(doc, ["data-ingest"]) == []


def test_wizard_contract():
    doc = yaml.safe_load(render_ingestion_yaml(_spec()))
    init, fetch, ingest = doc["playbooks"]
    assert set(doc["exported_tags"]) >= {"acme-edr", "dataingestion", "fetch", "create", "ingest"}
    assert {"fetch", "dataingestion", "acme-edr"} <= set(fetch["tags"])
    assert {"ingest", "create", "dataingestion", "acme-edr"} <= set(ingest["tags"])
    names = [s["name"] for s in fetch["steps"]]
    assert "Fetch" in names and "Configuration" in names
    assert fetch["steps"][0]["configuration_schema"]

    step = {s["name"]: s for s in ingest["steps"]}
    create = step["Create Record"]
    assert create["is_upsert"] and create["fields"]["sourceId"]
    assert "__bulk" not in create["for_each"], "bulk create skips on-create alert playbooks"
    upd = create["fields"]["__fieldsToUpdate"]
    assert upd.startswith("{{ [") and "'sourceId'" in upd
    # create-only triage fields: set on create, never refreshed on update
    assert "AlertState" in create["fields"]["state"] and "'state'" not in upd and "'status'" not in upd
    assert create["fields"]["sourcedata"] == "{{ vars.item | toJSON }}"
    # watermark advances last
    assert ingest["steps"][-1]["operation"] == "updatemacro"


def test_fetch_is_utilities_rest_standin_with_mock():
    doc = yaml.safe_load(render_ingestion_yaml(_spec(method="post")))
    fetch = {s["name"]: s for s in doc["playbooks"][1]["steps"]}["Fetch"]
    assert (fetch["connector"], fetch["operation"]) == ("cyops_utilities", "api_call")
    assert fetch["params"]["method"] == "POST"
    mock = json.loads(fetch["mock_result"])
    assert mock["data"]["items"][0]["id"] == "sample-0001"


def test_bulk_is_opt_in():
    doc = yaml.safe_load(render_ingestion_yaml(_spec(bulk=True)))
    create = {s["name"]: s for s in doc["playbooks"][2]["steps"]}["Create Record"]
    assert create["for_each"]["__bulk"] is True


@pytest.mark.parametrize("kw", [{"slug": "Acme EDR"}, {"module": "indicators"}])
def test_rejects_bad_spec(kw):
    with pytest.raises(ValueError):
        _spec(**kw)


def test_init_macros_creates_with_post_like_fortiedr():
    doc = yaml.safe_load(render_ingestion_yaml(_spec()))
    steps = {s["name"]: s for s in doc["playbooks"][0]["steps"]}
    assert steps["Create Macro"]["params"]["method"] == "POST"


def test_window_over_cap_fails_before_save():
    doc = yaml.safe_load(render_ingestion_yaml(_spec()))
    steps = {s["name"]: s for s in doc["playbooks"][1]["steps"]}
    assert steps["Fetch"]["next"] == "Within Cap"
    over = steps["Window Over Cap"]
    assert over["operation"] == "raise_exception" and "next" not in over
    assert doc["playbooks"][1]["steps"][-1]["name"] == "Save Result"


def test_incidents_have_no_alert_create_only_fields():
    doc = yaml.safe_load(render_ingestion_yaml(_spec(module="incidents")))
    fields = {s["name"]: s for s in doc["playbooks"][2]["steps"]}["Create Record"]["fields"]
    assert "state" not in fields


_VARIANTS = {
    "paging": dict(page_param="offset", page_size_param="limit", page_size=200, total_path="meta.total"),
    "status": dict(status_field="state", status_map={"new": "Open", "closed": "Closed"}),
    "tenant": dict(tenant="Acme"),
    "tenant_map": dict(tenant_field="customer", tenant_mapping={"c1": "Tenant One"}),
    "bulk": dict(bulk=True),
}


@pytest.mark.parametrize("name", sorted(_VARIANTS))
def test_variants_compile_clean(name):
    res = _compile(_spec(**_VARIANTS[name]))
    assert not getattr(res, "warnings", [])
    assert rs.validate(res.fsr_json, ["data-ingest"]) == []


def _steps(doc, i):
    return {s["name"]: s for s in doc["playbooks"][i]["steps"]}


def test_paging_reads_every_page_and_caps_on_true_total():
    import jinja2

    doc = yaml.safe_load(render_ingestion_yaml(_spec(**_VARIANTS["paging"])))
    st = _steps(doc, 1)
    assert st["Fetch"]["next"] == "Paging Plan"
    assert json.loads(st["Fetch"]["params"]["params"])["offset"] == "0"
    assert st["Fetch Remaining Pages"]["for_each"]["item"] == "{{ vars.offset_list }}"
    assert ">" in st["Within Cap"]["conditions"][0]["when"] and ">=" not in st["Within Cap"]["conditions"][0]["when"]

    class V(dict):
        __getattr__ = dict.get

    env = jinja2.Environment()
    fetch = {"data": {"items": [{"id": 1}], "meta": {"total": 450}}}
    plan = env.from_string(st["Paging Plan"]["vars"]["offset_list"]).render(vars=V(steps=V(Fetch=fetch)))
    assert plan == "[200, 400]"
    pages = [{"data": {"items": [{"id": 2}]}}, {"data": {"items": [{"id": 3}]}}]
    out = env.from_string(st["Save Result"]["vars"]["data"]).render(
        vars=V(steps=V(Fetch=fetch, Fetch_Remaining_Pages=pages)))
    assert out == "[{'id': 1}, {'id': 2}, {'id': 3}]"


def test_paging_requires_total_path():
    with pytest.raises(ValueError):
        _spec(page_param="offset")


def test_severity_and_status_use_resolverange_mapping():
    doc = yaml.safe_load(render_ingestion_yaml(_spec(**_VARIANTS["status"])))
    st = _steps(doc, 2)
    cfg, fields = st["Configuration"]["vars"], st["Create Record"]["fields"]
    assert "picklist('High')" in cfg["severity_map"] and "AlertStatus" in cfg["status_map"]
    assert "resolveRange(vars.severity_map)" in fields["severity"]
    assert "resolveRange(vars.status_map)" in fields["status"]
    # a mapped status follows the vendor, so it is refreshed on update
    assert "'status'" in fields["__fieldsToUpdate"] and "'state'" not in fields["__fieldsToUpdate"]


def test_tenant_lookup_runs_before_configuration():
    doc = yaml.safe_load(render_ingestion_yaml(_spec(**_VARIANTS["tenant_map"])))
    st = _steps(doc, 2)
    assert st["Mapping Preview"]["conditions"][1]["next"] == "Get Tenants"
    assert st["Get Tenants"]["next"] == "Configuration"
    assert "tenant_mapping" in st["Configuration"]["vars"]
    assert "'tenant'" in st["Create Record"]["fields"]["__fieldsToUpdate"]
    with pytest.raises(ValueError):
        _spec(tenant="A", tenant_field="customer")
