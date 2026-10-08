"""A read of the trigger record names a field the module really has.

Live (analyst sim): three alert playbooks read `vars.input.records[0].destIp`
or `.destinationAddress` -- the field is `destinationIp`. Each compiled and
verified, and would have queried VirusTotal with an empty value on every run:
the typed walk resolves `vars.steps.*` only, so nothing looked at the record.

Severity is the field validator's own rule: an error against a catalog read
from the target box (the connector's on-platform warm stamps it), a warning
against a generic snapshot a custom field may be missing from.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from fsr_playbooks import _catalog_meta
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.mcp_server._shared import DB_PATH

_PB = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Note}
      - name: Note
        type: set_variable
        vars:
          ip: "{{ vars.input.records[0].__FIELD__ }}"
"""


def _catalog(tmp_path, *, box: bool):
    db = tmp_path / "ref.db"
    shutil.copy(DB_PATH, db)
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM module_fields WHERE module_name='alerts'")
        c.executemany(
            "INSERT INTO module_fields (module_name, field_name, type) VALUES ('alerts', ?, 'text')",
            [("destinationIp",), ("sourceIp",), ("name",)])
        _catalog_meta.ensure_table(c)
        if box:
            _catalog_meta.record_modules_warmed(c)
    return db


def _found(db, field: str):
    res = compile_yaml(_PB.replace("__FIELD__", field), db)
    return [e for e in list(res.errors) + list(res.warnings)
            if getattr(e, "check", None) == "unknown_record_field"]


def test_an_invented_field_blocks_against_the_box_catalog(tmp_path):
    found = _found(_catalog(tmp_path, box=True), "destIp")
    assert found and found[0].severity == "error"
    assert "destinationIp" in (found[0].suggestion or "")


def test_against_a_generic_catalog_it_only_warns(tmp_path):
    found = _found(_catalog(tmp_path, box=False), "destIp")
    assert found and found[0].severity == "warning"


@pytest.mark.parametrize("field", ["destinationIp", "id", "createDate"])
def test_real_and_system_fields_are_clean(tmp_path, field):
    assert _found(_catalog(tmp_path, box=True), field) == []


def test_the_subscript_form_is_checked_too(tmp_path):
    db = _catalog(tmp_path, box=True)
    res = compile_yaml(_PB.replace("records[0].__FIELD__", "records[0]['destIp']"), db)
    assert any(getattr(e, "check", None) == "unknown_record_field"
               for e in res.errors)


def test_an_unwarmed_module_is_not_checked():
    # The packaged catalog has no module fields: nothing to check against.
    assert _found(DB_PATH, "destIp") == []
