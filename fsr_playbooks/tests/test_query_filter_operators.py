"""Substring operators on record-step query filters compile to SQL LIKE.

`/api/query/<module>` has no scalar `contains`. On 8.0 it does not merely fail
to match -- `contains`, `startswith` and `sw` all return HTTP 500, so a step
authored with the obvious operator takes the playbook down rather than
returning nothing. `like` with an explicit `%` is the one substring match the
query layer honours, which is what these rewrites emit.

The trigger layer has always done this for `when:`; these cover the record
steps, which passed the author's operator through verbatim.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fsr_playbooks.compiler import compile_yaml

DB = Path(__file__).resolve().parents[2] / "tooling" / "tests" / "fixtures" / "tooling_reference.db"

_HEAD = """
collection: X
visible: true
playbooks:
  - name: T
    is_active: true
    steps:
      - name: trigger
        type: start
        next: S1
"""


def _filters(steps_yaml: str, step_name: str = "S1") -> list[dict]:
    res = compile_yaml(_HEAD + steps_yaml, DB)
    assert res.ok, [e.message for e in res.errors if e.severity == "error"]
    for s in res.fsr_json["data"][0]["workflows"][0]["steps"]:
        if s["name"] == step_name:
            return s["arguments"]["query"]["filters"]
    raise AssertionError(f"step {step_name} not found")


def _find(op: str, value: str = "test") -> list[dict]:
    return _filters(f"""
      - name: S1
        type: find_record
        module: alerts
        filters:
          - field: description
            operator: {op}
            value: "{value}"
""")


@pytest.mark.parametrize("op,expected_op,expected_value", [
    ("contains", "like", "%test%"),
    ("icontains", "like", "%test%"),
    ("startswith", "like", "test%"),
    ("endswith", "like", "%test"),
    ("notcontains", "notlike", "%test%"),
])
def test_substring_operators_become_like(op, expected_op, expected_value):
    f = _find(op)[0]
    assert (f["operator"], f["value"]) == (expected_op, expected_value)
    # The designer reads `_operator`; a step where the two disagree renders
    # with the wrong operator selected.
    assert f["_operator"] == expected_op


def test_author_supplied_pattern_is_left_alone():
    f = _find("contains", "%already%")[0]
    assert (f["operator"], f["value"]) == ("like", "%already%")


def test_exact_operators_untouched():
    f = _find("eq")[0]
    assert (f["operator"], f["value"]) == ("eq", "test")


def test_rewrite_warns_rather_than_failing():
    res = compile_yaml(_HEAD + """
      - name: S1
        type: find_record
        module: alerts
        filters:
          - field: description
            operator: contains
            value: test
""", DB)
    assert res.ok
    warned = [e for e in res.errors
              if "no scalar FSR equivalent" in e.message
              and e.path.endswith("query.filters[0].operator")]
    assert warned and warned[0].severity == "warning"


def test_hand_authored_query_is_rewritten_too():
    """The friendly `filters:` form is not the only way in -- a raw `query:`
    written against the wire shape gets the same treatment."""
    f = _filters("""
      - name: S1
        type: find_record
        module: alerts
        query:
          logic: AND
          limit: 30
          filters:
            - type: primitive
              field: name
              operator: contains
              _operator: contains
              value: junk
""")[0]
    assert (f["operator"], f["_operator"], f["value"]) == ("like", "like", "%junk%")


def test_bulk_delete_query_is_rewritten():
    """delete_record json-encodes its query into the request body, so the
    rewrite has to land before that encoding."""
    res = compile_yaml(_HEAD + """
      - name: S1
        type: delete_record
        module: alerts
        query:
          logic: AND
          filters:
            - type: primitive
              field: name
              operator: contains
              _operator: contains
              value: junk
""", DB)
    assert res.ok, [e.message for e in res.errors if e.severity == "error"]
    step = res.fsr_json["data"][0]["workflows"][0]["steps"][1]
    body = step["arguments"]["params"]["body"]
    assert '"operator": "like"' in body
    assert '"value": "%junk%"' in body
    assert "contains" not in body


def _date_filters(field: str, extra: str = "") -> dict:
    return _filters(f"""
      - name: S1
        type: find_record
        module: alerts
        filters:
          - field: {field}
            operator: gte
            value: "{{{{ arrow.utcnow().shift(days=-1).int_timestamp }}}}"{extra}
""")[0]


def test_date_filters_are_typed_datetime():
    # /api/query answers 400 to a date filter typed `primitive`
    # (live-verified on 8.0.0); the designer always writes `datetime`.
    assert _date_filters("createDate")["type"] == "datetime"
    assert _date_filters("modifyDate")["type"] == "datetime"
    assert _date_filters("description")["type"] == "primitive"


def test_author_filter_type_wins():
    assert _date_filters("createDate", "\n            type: primitive")["type"] == "primitive"


def test_declared_date_fields_come_from_the_store(tmp_path):
    import shutil
    import sqlite3

    from fsr_playbooks import module_schema

    db = tmp_path / "ref.db"
    shutil.copy(DB, db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT OR REPLACE INTO module_fields (module_name, field_name, title, type) "
                 "VALUES ('alerts', 'dueBy', 'Due By', 'datetime')")
    conn.commit()
    assert module_schema.is_datetime_field(conn, "alerts", "dueBy")
    assert not module_schema.is_datetime_field(conn, "alerts", "description")
    assert not module_schema.is_datetime_field(None, "alerts", "dueBy")
    conn.close()
    res = compile_yaml(_HEAD + """
      - name: S1
        type: find_record
        module: alerts
        filters:
          - field: dueBy
            operator: isnull
            value: "true"
""", db)
    steps = res.fsr_json["data"][0]["workflows"][0]["steps"]
    assert next(s for s in steps if s["name"] == "S1")["arguments"]["query"]["filters"][0]["type"] == "datetime"


def test_update_without_a_record_is_an_error():
    res = compile_yaml(_HEAD + """
      - name: S1
        type: update_record
        module: alerts
        fields: {name: x}
""", DB)
    assert not res.ok
    assert any("record:" in e.message for e in res.errors if e.severity == "error")
