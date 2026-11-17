"""Record fields and picklist values are checked wherever a step names them.

A find_record on a field the module does not have, or on a picklist value from
the wrong list, used to compile and verify clean and then quietly match nothing
at run time. The case that surfaced it was an agent-built SLA playbook:
`state eq "Open"` on incidents (`Open` is an IncidentStatus; `state` is the
AlertState list) and a filter on `slaDueDate`, which no module has. Trigger
filters already went through `FieldValueValidator`; find_record now does too.

Every check reads the one field lookup, `module_schema.field_names`, which
adds the implicit system fields the metadata API leaves out -- without them a
filter on `createDate` or a write to `recordTags` (thousands of shipped steps)
reads as unknown, which is why all of this had to stay a warning.

Severity follows the catalog's provenance: warmed from the target box -> error.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from fsr_playbooks import module_schema
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError
from fsr_playbooks.compiler.record_op_checks import check_unknown_record_fields
from fsr_playbooks.compiler.typed_args import FieldValueValidator

_STATUS_OPEN = "/api/3/picklists/11111111-1111-1111-1111-111111111111"
_STATE_NEW = "/api/3/picklists/22222222-2222-2222-2222-222222222222"


def _seed(conn: sqlite3.Connection, *, stamped: bool) -> None:
    """A small `incidents` module: two picklist fields on different lists."""
    conn.execute("DELETE FROM module_fields WHERE module_name='incidents'")
    conn.execute("DELETE FROM picklists WHERE list_name IN "
                 "('IncidentStatus','AlertState')")
    conn.executemany(
        "INSERT INTO module_fields (module_name, field_name, title, type, "
        "required, picklist_options, tooltip, picklist_name) "
        "VALUES ('incidents', ?, ?, ?, 0, NULL, NULL, ?)",
        [("name", "Name", "text", None),
         ("resDueBy", "Resolution Due", "datetime", None),
         ("status", "Status", "picklists", "IncidentStatus"),
         ("state", "State", "picklists", "AlertState")])
    conn.executemany(
        "INSERT INTO picklists (list_name, item_value, item_iri) VALUES (?,?,?)",
        [("IncidentStatus", "Open", _STATUS_OPEN),
         ("IncidentStatus", "Closed", ""),
         ("AlertState", "New", _STATE_NEW)])
    from fsr_playbooks import _catalog_meta
    _catalog_meta.ensure_table(conn)
    conn.execute("DELETE FROM _catalog_meta WHERE key IN "
                 "('base_url_hash', 'modules_warmed_at')")
    if stamped:
        _catalog_meta.set_(conn, "base_url_hash", "deadbeef")
    conn.commit()


@pytest.fixture(scope="module")
def _base_copy(db_path, tmp_path_factory):
    dst = tmp_path_factory.mktemp("fields") / "base.db"
    shutil.copyfile(db_path, dst)
    return dst


@pytest.fixture(params=[True, False], ids=["stamped", "unstamped"])
def catalog(request, _base_copy, tmp_path):
    path = tmp_path / "catalog.db"
    shutil.copyfile(_base_copy, path)
    conn = sqlite3.connect(path)
    _seed(conn, stamped=request.param)
    yield path, conn, ("error" if request.param else "warning")
    conn.close()


# ---------------------------------------------------------------- the lookup

def test_system_fields_are_known_but_only_on_a_known_module(catalog):
    _, conn, _ = catalog
    names = module_schema.field_names(conn, "incidents")
    assert {"name", "status"} <= names
    assert {"createDate", "recordTags", "owners", "id"} <= names
    # Un-warmed module: empty, so callers keep "can't check, don't flag".
    assert module_schema.field_names(conn, "no_such_module_xyz") == set()


def test_module_name_strips_what_steps_carry():
    assert module_schema.module_name("incidents?$limit=100") == "incidents"
    assert module_schema.module_name("/api/3/incidents") == "incidents"
    assert module_schema.module_name("/api/3/upsert/alerts") == "alerts"
    assert module_schema.module_name("{{ vars.m }}") is None


# ---------------------------------------------------------- filter validation

def _filter_errs(conn, filters) -> list[CompileError]:
    errs: list[CompileError] = []
    FieldValueValidator(conn).validate_filters(filters, "incidents", "p", errs)
    return errs


def test_unknown_field_severity_follows_provenance(catalog):
    _, conn, severity = catalog
    errs = _filter_errs(conn, [{"field": "slaDueDate", "operator": "lt",
                                "value": "1"}])
    assert len(errs) == 1 and errs[0].severity == severity
    assert errs[0].check == "unknown_record_field"
    assert errs[0].path == "p.filters[0].field"


def test_system_and_dotted_fields_pass(catalog):
    _, conn, _ = catalog
    assert _filter_errs(conn, [
        {"field": "createDate", "operator": "gt", "value": "1"},
        {"field": "recordTags", "operator": "in", "value": ["/api/3/tags/x"]},
        {"field": "name.anything", "operator": "eq", "value": "x"},
    ]) == []


def test_wrong_list_value_names_the_field_it_belongs_to(catalog):
    _, conn, severity = catalog
    errs = _filter_errs(conn, [{"field": "state", "operator": "eq",
                                "value": "Open"}])
    assert len(errs) == 1 and errs[0].severity == severity
    assert "'Open' is a value of 'status'" in errs[0].message
    assert errs[0].near == "status"


def test_bare_uuid_picklist_value_is_the_editor_form(catalog):
    _, conn, _ = catalog
    assert _filter_errs(conn, [{"field": "status", "operator": "eq",
                                "value": _STATUS_OPEN.rsplit("/", 1)[1]}]) == []


def test_tags_points_at_record_tags(catalog):
    _, conn, _ = catalog
    errs = _filter_errs(conn, [{"field": "tags", "operator": "eq",
                                "value": "x"}])
    assert len(errs) == 1 and "recordTags" in (errs[0].suggestion or "")


# ------------------------------------------------------- find_record compiles

_SLA = """
collection: T
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
        next: Find
      - name: Find
        type: find_record
        module: incidents
        limit: 100
        filters:
          - field: {field}
            operator: eq
            value: {value}
        sort:
          - field: {sort}
"""


def _diags(path, **kw):
    out = compile_yaml(_SLA.format(**kw), path)
    return [e for e in out.errors
            if e.check in ("unknown_record_field", "picklist_drift")]


def test_find_record_flags_the_sla_defects(catalog):
    path, _, severity = catalog
    bad = _diags(path, field="state", value="Open", sort="slaDueDate")
    by = {e.path.rsplit(".", 1)[-1] if "sort" not in e.path else "sort": e
          for e in bad}
    assert set(by) == {"value", "sort"}, [e.to_dict() for e in bad]
    assert by["value"].path.endswith("arguments.filters[0].value")
    assert all(e.severity == severity for e in bad)


def test_find_record_clean_on_real_fields(catalog):
    path, _, _ = catalog
    assert _diags(path, field="status", value="Open", sort="createDate") == []


# ---------------------------------------------------------- resource writes

def test_unknown_write_field_strict_and_directives(catalog):
    _, conn, _ = catalog
    known = module_schema.field_names(conn, "incidents")
    res = {"name": "x", "recordTags": ["a"], "__replace": "true",
           "slaDueDate": 1}
    loose = check_unknown_record_fields(module="incidents", resource=res,
                                        known_fields=known)
    strict = check_unknown_record_fields(module="incidents", resource=res,
                                         known_fields=known, strict=True)
    assert [i["message"] for i in loose] == [
        "module 'incidents' has no field 'slaDueDate'"]
    assert loose[0]["severity"] == "warning"
    assert strict[0]["severity"] == "error"


def test_on_platform_warm_counts_as_the_box(catalog):
    """The connector's on-platform warm has no base URL to stamp (it reaches
    its own appliance), so it records `modules_warmed_at` instead. Found live:
    the box verified the SLA playbook ready_to_push with both defects as
    warnings, because only `base_url_hash` was consulted."""
    from fsr_playbooks import _catalog_meta
    _, conn, _ = catalog
    conn.execute("DELETE FROM _catalog_meta WHERE key='base_url_hash'")
    assert not module_schema.catalog_is_instance(conn)
    _catalog_meta.record_modules_warmed(conn)
    assert module_schema.catalog_is_instance(conn)
    errs = _filter_errs(conn, [{"field": "slaDueDate", "operator": "lt",
                                "value": "1"}])
    assert errs[0].severity == "error"
