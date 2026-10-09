"""Push-deploy guards: native-export input, auto-warm, placeholder refusal,
activation. Each guard regression-tests a failure seen live deploying the
threatconnect 2.1.1 ingestion trio:

- pushing the compiled workflow_collections export died with
  ``[missing_field] playbooks``;
- a catalog warmed from another instance hard-refused an op that EXISTS on
  the target (``unknown_operation 'fetch_indicators'``);
- the generated REPLACE_WITH_CONFIG_UUID placeholder shipped unchecked;
- every workflow landed isActive=false and the first ingest run died with
  ``CS-WF-1: referenced playbook non-existent or Inactive``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cli  # tooling on sys.path via conftest

from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.pipeline import CompileResult


# -- _push_input_text -------------------------------------------------------
def test_push_input_yaml_passes_through_untouched(db_path):
    raw = "collection: x\nplaybooks: []\n"
    assert cli._push_input_text(raw, db_path) == raw


def test_push_input_decompiles_native_workflow_collections_export(db_path, monkeypatch):
    export = json.dumps({
        "type": "workflow_collections",
        "data": [{"name": "C", "uuid": "u", "workflows": []}],
    })
    import fsr_playbooks.compiler.decompiler as dec

    monkeypatch.setattr(dec, "decompile_to_yaml", lambda src, db: "collection: C\nplaybooks: []\n")
    out = cli._push_input_text(export, db_path)
    assert out == "collection: C\nplaybooks: []\n"


def test_push_input_leaves_non_export_json_alone(db_path):
    raw = json.dumps({"not": "an export"})
    assert cli._push_input_text(raw, db_path) == raw


# -- _unknown_connectors_in -------------------------------------------------
def _err(code, msg):
    return CompileError(code=code, message=msg, path="playbooks[0].steps[1]")


def test_unknown_connectors_extracted_from_both_verdict_classes():
    errs = [
        _err(ErrorCode.UNKNOWN_CONNECTOR, "unknown connector: 'threatconnect'"),
        _err(ErrorCode.UNKNOWN_OPERATION, "unknown operation 'fetch_indicators' on connector 'threatconnect'"),
        _err(ErrorCode.MISSING_FIELD, "some other problem"),
    ]
    assert cli._unknown_connectors_in(errs) == ["threatconnect"]


def test_unknown_connectors_deduplicated():
    errs = [
        _err(ErrorCode.UNKNOWN_OPERATION, "unknown operation 'a' on connector 'x'"),
        _err(ErrorCode.UNKNOWN_OPERATION, "unknown operation 'b' on connector 'x'"),
    ]
    assert cli._unknown_connectors_in(errs) == ["x"]


# -- _placeholder_step_holders ---------------------------------------------
def _entity_with_step(step_args):
    return {
        "name": "C",
        "uuid": "u",
        "workflows": [
            {"name": "wf", "isActive": False, "steps": [
                {"name": "badstep", "arguments": step_args},
                {"name": "goodstep", "arguments": {"config": "fed4b33b-fe62-438d-9d55-197f8332e116"}},
            ]},
            {"name": "wf2", "isActive": True, "steps": []},
        ],
    }


def test_placeholder_holders_name_the_offending_steps():
    hits = cli._placeholder_step_holders(_entity_with_step(
        {"config": "REPLACE_WITH_CONFIG_UUID", "x": 1}
    ))
    assert hits == ["wf -> badstep"]


def test_no_placeholders_means_no_hits():
    assert cli._placeholder_step_holders(_entity_with_step({"config": "ok"})) == []


# -- _ensure_workflows_active ----------------------------------------------
def _args(**kw):
    return argparse.Namespace(no_activate=kw.get("no_activate", False))


def test_activation_flips_inactive_workflows_and_names_them(capsys):
    entity = _entity_with_step({"config": "ok"})
    assert [w["isActive"] for w in entity["workflows"]] == [False, True]
    cli._ensure_workflows_active(entity, _args())
    assert all(w["isActive"] for w in entity["workflows"])
    out = capsys.readouterr().err
    assert "wf" in out and "--no-activate" in out


def test_no_activate_leaves_the_entity_as_authored(capsys):
    entity = _entity_with_step({"config": "ok"})
    cli._ensure_workflows_active(entity, _args(no_activate=True))
    assert [w["isActive"] for w in entity["workflows"]] == [False, True]
    assert capsys.readouterr().err == ""


# -- _autowarm_and_recompile: the demote-fallback path ----------------------
def _blocked_result(*errs):
    result = CompileResult(errors=list(errs))
    assert result.fsr_json is None
    return result


def test_autowarm_demotes_to_lax_when_warm_impossible_and_catalog_foreign(
    tmp_path, monkeypatch, db_path, capsys
):
    """Warm impossible + provenance mismatch -> the two verdicts demote via a
    re-compile with lax_codes (which still emits JSON), and the message says so."""
    import probes._env as env_mod
    import provision_connector

    result = _blocked_result(
        _err(ErrorCode.UNKNOWN_OPERATION, "unknown operation 'fetch_indicators' on connector 'threatconnect'"),
    )
    monkeypatch.setattr(env_mod, "get_config", lambda: type("C", (), {"is_live": lambda self: False})())
    monkeypatch.setattr(provision_connector, "_instance_mismatch_warning", lambda conn: "catalog mismatch")
    recompiled = CompileResult(
        fsr_json={"data": [{"name": "C", "uuid": "u", "workflows": []}]},
        errors=[_err(ErrorCode.UNKNOWN_OPERATION, "unknown operation 'fetch_indicators' on connector 'threatconnect'")],
    )
    lax_seen: dict = {}

    import fsr_playbooks.compiler as fsc

    def spy(text, db, **kw):
        lax_seen.update(kw)
        for err in recompiled.errors:
            err.severity = "warning"
        return recompiled

    # the helper's `from fsr_playbooks.compiler import compile_yaml` binds the
    # PACKAGE re-export at call time -- patch there, not on the pipeline module
    monkeypatch.setattr(fsc, "compile_yaml", spy)

    out = cli._autowarm_and_recompile("collection: C\nplaybooks: []", argparse.Namespace(db=str(db_path)), result)
    assert lax_seen.get("lax_codes") == {ErrorCode.UNKNOWN_CONNECTOR, ErrorCode.UNKNOWN_OPERATION}
    assert out is recompiled
    assert capsys.readouterr().err != ""


def test_autowarm_keeps_fatal_when_catalog_matches_and_warm_impossible(tmp_path, monkeypatch, db_path):
    """No provenance mismatch + warm impossible -> unknown stays FATAL: on the
    catalog's own instance, absence in the catalog IS evidence of a typo."""
    import probes._env as env_mod
    import provision_connector

    result = _blocked_result(
        _err(ErrorCode.UNKNOWN_OPERATION, "unknown operation 'nope' on connector 'threatconnect'"),
    )
    monkeypatch.setattr(env_mod, "get_config", lambda: type("C", (), {"is_live": lambda self: False})())
    monkeypatch.setattr(provision_connector, "_instance_mismatch_warning", lambda conn: None)
    out = cli._autowarm_and_recompile("collection: C\n", argparse.Namespace(db=str(db_path)), result)
    assert out is result  # untouched, still blocked


# -- write_connector live-warm provenance -----------------------------------
FXINFO = Path("/Users/dylanspille/PycharmProjects/Miscellaneous/fortisoar/"
              "fsr_connector_toolkit/tests/fixtures/threatconnect/info.json")


def _live_cfg(base_url, label=""):
    class _Cfg:
        pass
    c = _Cfg()
    c.base_url = base_url
    c.instance_label = label
    c.is_live = lambda: True
    return c


def _db_copy(db_path, tmp_path):
    import shutil
    dst = tmp_path / "warm.db"
    shutil.copy(db_path, dst)
    import sqlite3
    conn = sqlite3.connect(dst)
    return conn


def test_live_warm_records_per_connector_provenance_marker(db_path, tmp_path, monkeypatch):
    """SOURCE_LIVE provisioning stamps WHICH box warmed this connector, and a
    blank catalog gets the full instance stamp -- including the license serial,
    the one identity that survives URL/port changes."""
    import probes._env as env_mod
    import provision_connector

    from fsr_playbooks import _catalog_meta

    target = "https://198.51.100.10:13000"
    monkeypatch.setattr(env_mod, "get_config", lambda: _live_cfg(target, "159"))
    conn = _db_copy(db_path, tmp_path)
    try:
        for key in ("instance_label", "base_url", "base_url_hash", "fsr_version",
                    "instance_serial"):
            conn.execute("DELETE FROM _catalog_meta WHERE key = ?", (key,))
        info = {**json.loads(FXINFO.read_text()), "instance_serial": "FSRVMTEST260001"}
        row = provision_connector.write_connector(conn, info,
                                                  provision_connector.SOURCE_LIVE, None)
        assert row["connector"] == info["name"]
        marker = _catalog_meta.get(conn, f"provisioned:{info['name']}")
        expect = f"live_api_get:{row['version']}@{_catalog_meta.base_url_hash(target)}"
        assert marker == expect
        status, label, _ = _catalog_meta.check_instance(conn, target)
        assert status == "ok" and label == "159"  # blank catalog -> stamped
        assert _catalog_meta.get(conn, "instance_serial") == "FSRVMTEST260001"
    finally:
        conn.close()


def test_live_warm_leaves_a_foreign_primary_stamp_alone(db_path, tmp_path, monkeypatch):
    """A catalog already stamped from ANOTHER box keeps that stamp after a
    per-connector live warm -- picklists may still be foreign, and the guard
    must keep saying so honestly."""
    import probes._env as env_mod
    import provision_connector

    from fsr_playbooks import _catalog_meta

    target = "https://198.51.100.10:13000"
    other = "https://198.51.100.99"
    monkeypatch.setattr(env_mod, "get_config", lambda: _live_cfg(target, "159"))
    conn = _db_copy(db_path, tmp_path)
    try:
        _catalog_meta.stamp_instance(conn, instance_label="oldbox", base_url=other)
        info = {**json.loads(FXINFO.read_text()), "instance_serial": "FSRVMTEST260001"}
        provision_connector.write_connector(conn, info,
                                            provision_connector.SOURCE_LIVE, None)
        status, label, _ = _catalog_meta.check_instance(conn, target)
        assert status == "mismatch" and label == "oldbox"
        marker = _catalog_meta.get(conn, f"provisioned:{info['name']}")
        assert marker.endswith(f"@{_catalog_meta.base_url_hash(target)}")
        # identity is STILL recorded per-warm even when the primary stamp holds
        assert _catalog_meta.get(conn, "instance_serial") == "FSRVMTEST260001"
    finally:
        conn.close()


# -- serial-authored instance identity --------------------------------------
SERIAL = "FSRVMTEST260001"


def test_mismatch_warning_suppressed_when_serials_agree(db_path, tmp_path, monkeypatch):
    """URL identity reads :13000 vs bare-host as two boxes; the license serial
    knows better -- same appliance -> no warning, no spurious re-warm."""
    import probes._env as env_mod
    import provision_connector

    from fsr_playbooks import _catalog_meta

    conn = _db_copy(db_path, tmp_path)
    try:
        _catalog_meta.stamp_instance(conn, instance_label="159",
                                     base_url="https://198.51.100.10:13000",
                                     instance_serial=SERIAL)
        monkeypatch.setattr(
            env_mod, "get_config",
            lambda: _live_cfg("https://198.51.100.99", "159"))
        monkeypatch.setattr(env_mod, "live_license_serial", lambda client=None: SERIAL)
        assert provision_connector._instance_mismatch_warning(conn) is None
    finally:
        conn.close()


def test_mismatch_warning_persists_when_serials_differ(db_path, tmp_path, monkeypatch):
    import probes._env as env_mod
    import provision_connector

    from fsr_playbooks import _catalog_meta

    conn = _db_copy(db_path, tmp_path)
    try:
        _catalog_meta.stamp_instance(conn, instance_label="oldbox",
                                     base_url="https://198.51.100.10:13000",
                                     instance_serial=SERIAL)
        monkeypatch.setattr(
            env_mod, "get_config",
            lambda: _live_cfg("https://198.51.100.99", "newbox"))
        monkeypatch.setattr(env_mod, "live_license_serial",
                            lambda client=None: "OTHERSERIAL")
        warn = provision_connector._instance_mismatch_warning(conn)
        assert warn is not None and SERIAL in warn and "oldbox" in warn
    finally:
        conn.close()


def test_mismatch_warning_falls_back_to_urls_without_a_live_serial(db_path, tmp_path, monkeypatch):
    """Offline / serial-unreachable: the URL verdict still stands."""
    import probes._env as env_mod
    import provision_connector

    from fsr_playbooks import _catalog_meta

    conn = _db_copy(db_path, tmp_path)
    try:
        _catalog_meta.stamp_instance(conn, instance_label="oldbox",
                                     base_url="https://198.51.100.10:13000",
                                     instance_serial=SERIAL)
        monkeypatch.setattr(
            env_mod, "get_config",
            lambda: _live_cfg("https://198.51.100.99", "159"))
        monkeypatch.setattr(env_mod, "live_license_serial", lambda client=None: None)
        warn = provision_connector._instance_mismatch_warning(conn)
        assert warn is not None
    finally:
        conn.close()


# -- health helpers ---------------------------------------------------------
class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _StubClient:
    def __init__(self, configs=None, health=None):
        self.base_url = "https://box"
        self.verify_ssl = False
        self._configs = configs or []
        self._health = health or {}
        self.session = self

    def post(self, url, json=None, verify=None):
        assert "/api/integration/connectors/" in url and url.endswith("?format=json")
        return _Resp({"configuration": [
            {"config_id": cid, "name": name} for name, cid in self._configs
        ]})

    def get(self, url, verify=None):
        key = url.split("?config=")[-1] if "?config=" in url else "(default)"
        return _Resp({"status": self._health.get(key, "?")}, status=self._health.get(key) == 404 and 404 or 200)


def test_health_configs_enumerated_from_the_definition_call():
    client = _StubClient(configs=[("dev", "c-dev"), ("prod", "c-prod")])
    assert cli._health_connectors_configs(client, "x", "1.0") == [("dev", "c-dev"), ("prod", "c-prod")]


def test_health_probe_config_targets_one_configuration():
    client = _StubClient(health={"c-prod": "Disconnected", "(default)": "Available"})
    assert cli._health_probe_config(client, "x", "1.0", "c-prod") == "Disconnected"
    assert cli._health_probe_config(client, "x", "1.0") == "Available"
