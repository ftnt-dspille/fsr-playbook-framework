"""`limit:` on a find_record step must ride on the module as `?$limit=N`.

query.limit alone is ignored at execution. The handler pages the module
endpoint and takes the page size from the query string, so a body-only limit
leaves the default 30 in force -- the step then processes the first 30 matches
and reports success, which is the worst kind of wrong: the playbook validates
clean, runs green, and silently truncates.

Live-verified against a lab appliance by seeding 120 matching records:
`query.limit: 5000` closed 30, a `limit` at argument level closed 30, and
`module: incidents?$limit=1000` closed all 120.

The limit is emitted in BOTH places on purpose -- the body value keeps the wire
shape faithful to what the editor round-trips, the suffix is what takes effect.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml


def _find_step(result, name_fragment: str = "Find") -> dict:
    assert result.ok, [e.to_dict() for e in result.errors]
    wf = result.fsr_json["data"][0]["workflows"][0]
    for s in wf["steps"]:
        if name_fragment in s["name"]:
            return s["arguments"]
    raise AssertionError(f"no step matching {name_fragment!r}")


_YAML = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Find rows
      - name: Find rows
        type: find_record
        module: incidents
        limit: {limit}
        logic: AND
        filters:
          - type: primitive
            field: name
            value: x
            operator: eq
            _operator: eq
"""


def test_limit_appended_to_module(db_path):
    out = compile_yaml(_YAML.format(limit=1000), db_path)
    args = _find_step(out)
    assert args["module"] == "incidents?$limit=1000"
    # body limit retained for wire fidelity
    assert args["query"]["limit"] == 1000


def test_default_limit_leaves_module_bare(db_path):
    # 30 is the platform default; no suffix needed, and adding one would make
    # every unremarkable step's module string noisy.
    out = compile_yaml(_YAML.format(limit=30), db_path)
    args = _find_step(out)
    assert args["module"] == "incidents"


def test_limit_composes_with_relationships(db_path):
    y = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Find rows
      - name: Find rows
        type: find_record
        module: alerts
        limit: 500
        relationships: true
        logic: AND
        filters:
          - type: primitive
            field: name
            value: x
            operator: eq
            _operator: eq
"""
    out = compile_yaml(y, db_path)
    args = _find_step(out)
    mod = args["module"]
    # relationships is applied first, so the limit must join with `&`
    assert mod.startswith("alerts?")
    assert "$relationships=true" in mod
    assert "$limit=500" in mod
    assert mod.count("?") == 1


def test_author_supplied_suffix_is_not_doubled(db_path):
    y = _YAML.format(limit=1000).replace(
        "module: incidents", "module: incidents?$limit=250")
    out = compile_yaml(y, db_path)
    args = _find_step(out)
    # an explicit suffix wins; we must not append a second one
    assert args["module"] == "incidents?$limit=250"
    assert args["module"].count("$limit=") == 1


# --- sort / select -------------------------------------------------------
# Both are used by every shipped Solution Pack find step (12/12 use sort,
# 10/12 use __selectFields) but neither had a friendly key, so authors had to
# abandon the friendly form and hand-write the whole `query:` envelope.

_SORTED = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Find rows
      - name: Find rows
        type: find_record
        module: alerts
        limit: 100
        logic: AND
        sort:
          - field: createDate
            direction: DESC
        select: [name, status]
        filters:
          - type: primitive
            field: name
            value: x
            operator: eq
            _operator: eq
"""


def test_sort_fills_editor_fields(db_path):
    args = _find_step(compile_yaml(_SORTED, db_path))
    assert args["query"]["sort"] == [{
        "field": "createDate",
        "direction": "DESC",
        # the designer renders these; a bare {field,direction} row shows blank
        "_fieldName": "createDate",
        "_fieldTitle": "createDate",
    }]


def test_select_turns_on_checkbox_fields(db_path):
    # __selectFields is stripped later when checkboxFields is falsy, so asking
    # for a projection has to set the flag or the projection is silently lost.
    args = _find_step(compile_yaml(_SORTED, db_path))
    assert args["query"]["__selectFields"] == ["name", "status"]
    assert args["checkboxFields"] is True


def test_sort_shorthand_string_and_default_direction(db_path):
    y = _SORTED.replace(
        "        sort:\n          - field: createDate\n            direction: DESC\n",
        "        sort: [createDate]\n")
    args = _find_step(compile_yaml(y, db_path))
    assert args["query"]["sort"][0]["field"] == "createDate"
    assert args["query"]["sort"][0]["direction"] == "ASC"


def test_no_select_leaves_projection_absent(db_path):
    y = _SORTED.replace("        select: [name, status]\n", "")
    args = _find_step(compile_yaml(y, db_path))
    assert "__selectFields" not in args["query"]
    assert args["checkboxFields"] is False
