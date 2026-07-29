"""Friendly keys for `update_record`'s merge semantics.

`fieldOperation` and `tagsOperation` were accepted raw but had no friendly
alias, so authors either wrote the wire key or omitted them entirely. 349 of
370 update steps on a live 7.x box set fieldOperation, almost all for
recordTags, so the keys are clearly load-bearing in practice.

These tests cover the MAPPING only -- friendly key to wire key. They do not
assert platform behaviour, because a 12-combination matrix on an 8.0 lab box
(update_record_matrix.py in the fortisoar troubleshooting tree) found that a
`resource.recordTags` write REPLACES the tag list regardless of operation,
fieldOperation or tagsOperation. Writing recordTags is destructive on 8.0 and
none of these keys prevented it.

Live `operation` distribution across those 370 steps, which is what the enum
guard is calibrated against:
    Append 230 | Overwrite 127 | Replace 4 | Create New 2
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml


def _args(result, frag="U"):
    assert result.ok, [e.to_dict() for e in result.errors]
    wf = result.fsr_json["data"][0]["workflows"][0]
    for s in wf["steps"]:
        if s["name"] == frag:
            return s["arguments"]
    raise AssertionError("step not found")


_Y = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: U
      - name: U
        type: update_record
        module: alerts
        record: "{{{{ vars.item['@id'] }}}}"
        operation: {op}
        field_operations:
          recordTags: Append
        tags_operation: OverwriteTags
        fields:
          status: /api/3/picklists/x
"""


def test_friendly_merge_keys_map_to_wire(db_path):
    a = _args(compile_yaml(_Y.format(op="Append"), db_path))
    assert a["fieldOperation"] == {"recordTags": "Append"}
    assert a["tagsOperation"] == "OverwriteTags"
    # and the pre-existing friendly mapping still holds
    assert a["collectionType"] == "/api/3/alerts"
    assert a["collection"] == "{{ vars.item['@id'] }}"
    assert a["resource"] == {"status": "/api/3/picklists/x"}
    # friendly spellings must not leak to the wire
    assert "field_operations" not in a
    assert "tags_operation" not in a


def test_explicit_wire_key_wins(db_path):
    y = _Y.format(op="Append").replace(
        "        field_operations:\n          recordTags: Append\n",
        "        fieldOperation:\n          recordTags: Overwrite\n")
    a = _args(compile_yaml(y, db_path))
    assert a["fieldOperation"] == {"recordTags": "Overwrite"}


# operation-enum drift is the corpus validator's check (it also supplies a
# near-match suggestion and skips Jinja-valued operations) -- see
# test_corpus_validator.py. Not re-tested here.


def test_known_operations_do_not_warn(db_path):
    for op in ("Append", "Overwrite", "Replace", "Create New"):
        r = compile_yaml(_Y.format(op=op), db_path)
        assert not any("not one of" in e.message for e in r.errors), \
            f"{op} should be accepted"


def test_bad_field_operations_type_errors(db_path):
    y = _Y.format(op="Append").replace(
        "        field_operations:\n          recordTags: Append\n",
        "        field_operations: Append\n")
    r = compile_yaml(y, db_path)
    assert any("field_operations" in e.message for e in r.errors), \
        [e.message for e in r.errors]


# --- link: the append primitive -----------------------------------------
# Measured on live 7.x and 8.0 boxes: a `fields:` write REPLACES a multi-value
# field (2 linked indicators + write 1 => 1 remains), and no combination of
# operation / fieldOperation / tagsOperation changes that -- 15 combinations
# tested, all destructive. `__link` is the only mechanism that appends
# (2 + link 1 => 3, unrelated tags untouched), and is what the platform's own
# escalation engine uses to attach records to a case.

_LINK_Y = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: U
      - name: U
        type: update_record
        module: alerts
        record: "/api/3/alerts/abc"
        link:
          indicators: ["11111111-2222-3333-4444-555555555555"]
"""


def test_link_lands_inside_resource(db_path):
    a = _args(compile_yaml(_LINK_Y, db_path))
    # __link rides in the resource payload, because that dict is the PUT body
    assert a["resource"] == {
        "__link": {"indicators": ["11111111-2222-3333-4444-555555555555"]}}
    assert "link" not in a


def test_link_merges_with_explicit_fields(db_path):
    y = _LINK_Y.replace(
        '        link:\n',
        '        fields:\n          status: /api/3/picklists/x\n        link:\n')
    a = _args(compile_yaml(y, db_path))
    assert a["resource"]["status"] == "/api/3/picklists/x"
    assert "__link" in a["resource"]


def test_link_must_be_a_mapping(db_path):
    y = _LINK_Y.replace(
        '        link:\n          indicators: ["11111111-2222-3333-4444-555555555555"]\n',
        '        link: indicators\n')
    r = compile_yaml(y, db_path)
    assert any("link" in e.message for e in r.errors), [e.message for e in r.errors]


# --- unlink: the detach counterpart --------------------------------------
# `__unlink` was measured on 8.0 alongside `__link`: seed an alert with 2
# indicators, unlink 1, and 1 remains. Without it, detaching means reading the
# collection, dropping one entry and writing the rest back through `fields:` --
# which races anything else touching that record and, if the read comes back
# short, silently discards the difference.

_UNLINK_Y = _LINK_Y.replace("        link:\n", "        unlink:\n")


def test_unlink_lands_inside_resource(db_path):
    a = _args(compile_yaml(_UNLINK_Y, db_path))
    assert a["resource"] == {
        "__unlink": {"indicators": ["11111111-2222-3333-4444-555555555555"]}}
    assert "unlink" not in a


def test_unlink_merges_with_explicit_fields(db_path):
    y = _UNLINK_Y.replace(
        '        unlink:\n',
        '        fields:\n          status: /api/3/picklists/x\n        unlink:\n')
    a = _args(compile_yaml(y, db_path))
    assert a["resource"]["status"] == "/api/3/picklists/x"
    assert "__unlink" in a["resource"]


def test_link_and_unlink_coexist_in_one_step(db_path):
    """Attaching and detaching in a single write is one PUT, not two steps --
    both primitives ride in the same resource payload."""
    y = _LINK_Y + (
        '        unlink:\n'
        '          assets: ["66666666-7777-8888-9999-000000000000"]\n')
    a = _args(compile_yaml(y, db_path))
    assert set(a["resource"]) == {"__link", "__unlink"}
    assert a["resource"]["__unlink"]["assets"] == [
        "66666666-7777-8888-9999-000000000000"]


def test_unlink_must_be_a_mapping(db_path):
    y = _UNLINK_Y.replace(
        '        unlink:\n          indicators: ["11111111-2222-3333-4444-555555555555"]\n',
        '        unlink: indicators\n')
    r = compile_yaml(y, db_path)
    assert any("unlink" in e.message for e in r.errors), [e.message for e in r.errors]


def test_explicit_wire_unlink_is_not_clobbered(db_path):
    """An author who already writes the wire shape under `fields:` keeps it."""
    y = _LINK_Y.replace(
        '        link:\n          indicators: ["11111111-2222-3333-4444-555555555555"]\n',
        '        fields:\n'
        '          __unlink:\n'
        '            indicators: ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]\n')
    a = _args(compile_yaml(y, db_path))
    assert a["resource"]["__unlink"]["indicators"] == [
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]
