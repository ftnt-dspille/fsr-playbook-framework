"""Warm levels: a playbook warms only what it uses, a full warm reads everything,
connector definitions are cached by version, and independent reads run at once.

Uses the fake box from ``test_warmup``, with a session that honours the
``type$in`` / ``name$in`` filters a targeted warm sends. No network.
"""
from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pytest

from fsr_playbooks import warmup
from fsr_playbooks.playbook_needs import playbook_needs
from fsr_playbooks.tests import test_warmup as tw

PLAYBOOK = """
name: Enrich alert
steps:
  - id: s1
    type: connector
    connector: fortinet-soc
    operation: get_incident
    config: ""
  - id: s2
    type: update_record
    module: alerts
    fields:
      status: "{{ 'AlertStatus' | picklist('Closed') }}"
"""


class _FilteringSession(tw._Session):
    def get(self, url, params=None, headers=None, verify=None, **kw):
        resp = super().get(url, params=params, headers=headers, verify=verify, **kw)
        params = params or {}
        self._box.data_reads.append((url.split("?")[0].rsplit("/api/3/", 1)[-1], params.get("type$in") or params.get("name$in")))
        for key, field in (("type$in", "type"), ("name$in", "name")):
            if key in params:
                wanted = set(params[key].split("|"))
                body = resp.json()
                return tw._Resp({"hydra:member": [m for m in body["hydra:member"] if m.get(field) in wanted]})
        return resp


class Box(tw.FakeBox):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.session = _FilteringSession(self)
        self.totals = {"model_metadatas": 7}
        self.connectors = copy.deepcopy(tw.CONNECTORS)
        self.details = copy.deepcopy(tw.DETAILS)
        self.data_reads: list[tuple[str, str | None]] = []

    def get(self, path, params=None, **kw):
        if "$limit=0" in path:
            base = path.split("?")[0]
            self.calls.append(base)
            return {"hydra:totalItems": self.totals.get(base.rsplit("/", 1)[-1], 7)}
        if path.split("?")[0] == "/api/integration/connectors/" and not (params or {}).get("agent"):
            self.calls.append("/api/integration/connectors/")
            return self.connectors
        return super().get(path, params=params, **kw)

    def post(self, path, data=None, **kw):
        parts = path.split("?")[0].strip("/").split("/")
        self.calls.append("/api/integration/connectors/{name}/{version}/")
        return copy.deepcopy(self.details[(parts[3], parts[4])])

    def reset(self):
        self.calls = []
        self.data_reads = []


@pytest.fixture
def box(monkeypatch):
    monkeypatch.setenv("FSRPB_WARM_RECHECK", "30")
    return Box()


def _rows(db: Path, sql: str) -> list:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------- needs
def test_playbook_needs_reads_connectors_modules_and_picklists():
    n = playbook_needs(PLAYBOOK)
    assert n.connectors == {"fortinet-soc"}
    assert n.modules == {"alerts"}
    assert n.picklists == {"AlertStatus"}


def test_playbook_needs_finds_modules_in_iris_and_survives_bad_yaml():
    n = playbook_needs('steps:\n  - args: {ref: "/api/3/incidents/{{ vars.id }}"}\n')
    assert "incidents" in n.modules
    bad = playbook_needs("steps: [\n  connector: smtp\n  module: alerts\n")
    assert bad.connectors == {"smtp"} and bad.modules == {"alerts"}


# ---------------------------------------------------------------- definition cache
def test_fortinet_rpm_definitions_are_shared_others_are_per_box():
    shared = warmup._def_cache_path({"name": "smtp", "version": "2.0.0", "rpm_installed": True,
                                      "publisher": "Fortinet"}, tw.BASE)
    local = warmup._def_cache_path({"name": "code-runner", "version": "1.0.0", "rpm_installed": False,
                                     "publisher": "Internal", "modified": "t1"}, tw.BASE)
    assert shared.parent.name == "shared"
    assert local.parent.name != "shared" and "code-runner@1.0.0@" in local.name


@pytest.mark.parametrize("name", ["../x", "a/b", "..", ""])
def test_unsafe_connector_names_are_never_cache_paths(name):
    assert warmup._def_cache_path({"name": name, "version": "1.0.0"}, tw.BASE) is None


def test_cached_definitions_are_not_refetched_and_keep_this_boxs_fields(box):
    summaries = box.connectors["data"]
    warmup.fetch_connector_details(box, summaries)
    box.reset()
    details, errors, stats = warmup.fetch_connector_details(box, summaries)
    assert stats == {"cached": 2, "fetched": 0} and not errors and box.calls == []
    soc = next(d for d in details if d["name"] == "fortinet-soc")
    assert soc["configuration"] == summaries[0]["configuration"] and soc["operations"]


# ---------------------------------------------------------------- targeted warm
def test_a_playbook_warms_only_what_it_uses(tmp_path, box):
    path = warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert ("staging_model_metadatas", "alerts") in box.data_reads
    assert ("picklist_names", "AlertStatus") in box.data_reads
    assert not [r for r in box.data_reads if r[1] is None and r[0] in ("staging_model_metadatas", "picklist_names")]
    assert _rows(path, "SELECT item_iri FROM picklists WHERE list_name='AlertStatus' AND item_value='Closed'") == [
        ("/api/3/picklists/p2",)]
    live = {r[0] for r in _rows(path, "SELECT name FROM connectors WHERE source = 'live_api_get'")}
    assert live == {"fortinet-soc"}
    assert box.calls.count("/api/integration/connectors/{name}/{version}/") == 1


def test_compiling_again_inside_the_recheck_window_makes_no_calls(tmp_path, box):
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    box.reset()
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert box.calls == []


def test_after_the_window_an_unchanged_box_costs_only_the_cheap_checks(tmp_path, box, monkeypatch):
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    monkeypatch.setenv("FSRPB_WARM_RECHECK", "0")
    box.reset()
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert [r for r in box.data_reads if r[0] in ("staging_model_metadatas", "picklist_names")] == []
    assert "/api/integration/connectors/{name}/{version}/" not in box.calls


def test_a_second_playbook_fetches_only_what_is_new(tmp_path, box):
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    box.reset()
    other = "steps:\n  - {type: connector, connector: smtp, operation: send_email}\n  - {type: create_record, module: incidents}\n"
    path = warmup.box_catalog(box, tmp_path, playbook=other)
    assert box.calls.count("/api/integration/connectors/{name}/{version}/") == 1
    assert {r[0] for r in _rows(path, "SELECT name FROM modules WHERE name IN ('alerts','incidents')")} == {
        "alerts", "incidents"}


def test_an_upgraded_connector_is_refetched_alone(tmp_path, box, monkeypatch):
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    monkeypatch.setenv("FSRPB_WARM_RECHECK", "0")
    box.connectors["data"][0]["version"] = "1.1.0"
    box.details[("fortinet-soc", "1.1.0")] = {**tw.DETAILS[("fortinet-soc", "1.0.0")], "version": "1.1.0"}
    box.reset()
    path = warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert box.calls.count("/api/integration/connectors/{name}/{version}/") == 1
    assert _rows(path, "SELECT version FROM connectors WHERE name = 'fortinet-soc'") == [("1.1.0",)]


def test_a_module_change_on_the_box_refetches_the_playbooks_modules(tmp_path, box, monkeypatch):
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    monkeypatch.setenv("FSRPB_WARM_RECHECK", "0")
    box.totals["model_metadatas"] = 8
    box.reset()
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert "/api/3/staging_model_metadatas" in box.calls


def test_configs_record_allow_imports_and_health(tmp_path, box, monkeypatch):
    configs = copy.deepcopy(tw.CONFIGURATIONS)
    configs["data"][0].update(config={"allow_imports": True}, health_status={"status": "Available"})
    monkeypatch.setattr(tw, "CONFIGURATIONS", configs)
    path = warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    rows = _rows(path, "SELECT allow_imports, health_status FROM connector_configs "
                       "WHERE connector='fortinet-soc' AND config_name='Default'")
    assert rows == [(1, "Available")]


# ---------------------------------------------------------------- full warm
def test_full_reads_everything_and_then_a_playbook_needs_no_fetches(tmp_path, box):
    path = warmup.box_catalog(box, tmp_path, full=True)
    assert {r[0] for r in _rows(path, "SELECT name FROM modules WHERE name IN ('alerts','incidents')")} == {
        "alerts", "incidents"}
    box.reset()
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert box.calls == []


def test_one_box_has_one_file_whatever_the_url_spelling(tmp_path):
    a = warmup.box_catalog_path("https://fsr.example.com", tmp_path)
    b = warmup.box_catalog_path("HTTPS://FSR.example.com:443/", tmp_path)
    assert a == b


def test_new_box_files_seed_from_the_packaged_catalog(tmp_path, box, monkeypatch):
    seeded = []
    real = warmup._seed_if_absent
    monkeypatch.setattr(warmup, "_seed_if_absent", lambda t, s: (seeded.append(s), real(t, s))[1])
    warmup.box_catalog(box, tmp_path, playbook=PLAYBOOK)
    assert seeded == [warmup.PACKAGED_SLIM_DB]


def test_a_full_check_inside_the_recheck_window_makes_no_calls(tmp_path, box):
    warmup.box_catalog(box, tmp_path, full=True)
    box.reset()
    warmup.box_catalog(box, tmp_path)
    assert box.calls == []
