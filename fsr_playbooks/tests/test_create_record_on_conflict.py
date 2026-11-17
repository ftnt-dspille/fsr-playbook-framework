"""`on_conflict:` / `update_fields:` -- what happens when the record exists.

An upsert is a PUT: every field in the payload overwrites, so a field the run
could not fetch is ERASED rather than left alone. The step editor settles that
with its "Uniqueness conflict settings", which ride INSIDE `resource` as
`__replace` (a STRING) and `__fieldsToUpdate`.

Behaviour these keys compile to, measured on a live 8.0 appliance with each
case run twice -- once with no record present, once against a seeded one:

    plain /api/3/<m>            collision -> 409, the step FAILS and halts
    upsert + __replace "false"  existing record left untouched
    upsert + __replace "true"   existing record fully overwritten
    upsert + __fieldsToUpdate   only the listed fields are written

Two results worth keeping in a test rather than a comment:

* the first position is a DIFFERENT ENDPOINT, not a `__replace` value, and
* OMITTING `__replace` on the upsert endpoint does not mean "fail" -- it
  overwrites everything, which is why `on_conflict:` exists at all.
"""
from __future__ import annotations

import yaml

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile_to_yaml

# The resolved catalog, not the gitignored dev cache: CI has only the packaged one.
DB = str(default_db_path())


def _compile(extra: str, step_type: str = "create_record"):
    return compile_yaml(f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        module: alerts
        button_label: B
        next: C
      - name: C
        type: {step_type}
        module: alerts
        fields:
          name: "x"
{extra}""", DB)


def _args(extra: str) -> dict:
    r = _compile(extra)
    assert r.ok, [e.to_dict() for e in r.errors]
    for s in r.fsr_json["data"][0]["workflows"][0]["steps"]:
        if s["name"] == "C":
            return s["arguments"]
    raise AssertionError("step not found")


def _messages(extra: str, step_type: str = "create_record") -> str:
    return " ".join(e.message for e in _compile(extra, step_type).errors)


def test_update_all_routes_at_upsert_and_sets_replace_true():
    a = _args("        on_conflict: update_all\n")
    assert a["collection"] == "/api/3/upsert/alerts"
    # A STRING, not a boolean -- the platform compares it as text.
    assert a["resource"]["__replace"] == "true"
    assert "__fieldsToUpdate" not in a["resource"]


def test_keep_existing_sets_replace_false():
    a = _args("        on_conflict: keep_existing\n")
    assert a["collection"] == "/api/3/upsert/alerts"
    assert a["resource"]["__replace"] == "false"


def test_update_listed_carries_the_field_list():
    a = _args("        on_conflict: update_listed\n"
              "        update_fields: [severity, status]\n")
    assert a["resource"]["__replace"] == "true"
    assert a["resource"]["__fieldsToUpdate"] == ["severity", "status"]


def test_update_fields_alone_implies_update_listed():
    # Naming the fields IS the intent; requiring `on_conflict:` too is ceremony.
    a = _args("        update_fields: [severity]\n")
    assert a["resource"]["__replace"] == "true"
    assert a["resource"]["__fieldsToUpdate"] == ["severity"]


def test_update_fields_may_be_an_interpolation():
    # Measured on 8.0: a templated list resolves to a real list at runtime, so
    # the set can mean "the fields THIS run actually filled" rather than a
    # fixed author-time allowlist. Keeping it un-coerced is load-bearing.
    a = _args('        update_fields: "{{ vars.item.updatable }}"\n')
    assert a["resource"]["__fieldsToUpdate"] == "{{ vars.item.updatable }}"


def test_fail_stays_on_the_plain_endpoint():
    # "Stop the create process" is not a __replace value -- it is the plain
    # collection, where a collision is a 409 that fails the step.
    a = _args("        on_conflict: fail\n")
    assert a["collection"] == "/api/3/alerts"
    assert "__replace" not in a.get("resource", {})


def test_no_conflict_setting_leaves_the_payload_untouched():
    # Back-compat: a plain create is unchanged by the new keys existing.
    a = _args("")
    assert a["collection"] == "/api/3/alerts"
    assert "__replace" not in a.get("resource", {})


def test_is_upsert_alone_still_works_and_adds_no_replace():
    # The pre-existing lever keeps its exact behaviour -- and this is the
    # silently-destructive default the new keys exist to make explicit.
    a = _args("        is_upsert: true\n")
    assert a["collection"] == "/api/3/upsert/alerts"
    assert "__replace" not in a.get("resource", {})


def test_fail_contradicts_is_upsert():
    msg = _messages("        is_upsert: true\n        on_conflict: fail\n")
    assert "contradict" in msg


def test_unknown_setting_is_rejected_with_the_valid_set():
    msg = _messages("        on_conflict: nope\n")
    assert "not a valid setting" in msg
    for value in ("fail", "keep_existing", "update_all", "update_listed"):
        assert value in msg


def test_update_listed_without_a_list_is_rejected():
    msg = _messages("        on_conflict: update_listed\n")
    assert "update_fields" in msg


def test_rejected_on_update_record():
    # update_record already targets one record by IRI; there is no uniqueness
    # conflict to settle, so accepting the key would only mislead.
    msg = _messages("        on_conflict: update_all\n", step_type="update_record")
    assert "create_record only" in msg


def test_field_operations_warns_but_does_not_block():
    # Re-measured on 8.0: every combination of operation / fieldOperation /
    # tagsOperation REPLACED the tag list, including on the upsert endpoint
    # with __replace "true". It compiles green and runs green while silently
    # dropping every tag already on the record, so it has to say so.
    r = _compile("        field_operations:\n          recordTags: Append\n")
    assert r.ok
    warn = [e for e in r.errors if e.severity == "warning"
            and "field_operations" in e.message]
    assert warn, [e.to_dict() for e in r.errors]
    assert "link:" in (warn[0].suggestion or "")


def test_tags_operation_warns_but_does_not_block():
    r = _compile("        tags_operation: OverwriteTags\n")
    assert r.ok
    assert [e for e in r.errors if e.severity == "warning"
            and "tags_operation" in e.message]


def test_link_is_not_warned_about():
    # `link:` is the mechanism that actually appends; warning on it would
    # push authors straight back to the destructive path.
    r = _compile("        link:\n          recordTags:\n            - \"src:tipper\"\n")
    assert r.ok
    assert not [e for e in r.errors if "no effect on 8.0" in e.message]


# --------------------------------------------------------------- round trip
# `__replace` / `__fieldsToUpdate` live INSIDE the payload on the wire, so a
# pulled playbook would otherwise show them as two double-underscored strings
# sitting among the record's real fields. The decompiler lifts them back out to
# the friendly keys. Driven through a genuine compile -> decompile round trip
# rather than a hand-built fixture, so the wire shape is the compiler's own.

def _roundtrip(extra: str) -> dict:
    r = _compile(extra)
    assert r.ok, [e.to_dict() for e in r.errors]
    back = yaml.safe_load(decompile_to_yaml(r.fsr_json, DB))
    for st in back["playbooks"][0]["steps"]:
        if st.get("name") == "C":
            return st
    raise AssertionError("step not found")


def test_decompile_lifts_update_all_out_of_the_payload():
    st = _roundtrip("        on_conflict: update_all\n")
    assert st.get("on_conflict") == "update_all"
    assert "__replace" not in (st.get("fields") or {})
    # `on_conflict:` implies the upsert routing, so emitting both would be
    # redundant and would read as if the two keys were independent.
    assert "is_upsert" not in st


def test_decompile_lifts_keep_existing():
    st = _roundtrip("        on_conflict: keep_existing\n")
    assert st.get("on_conflict") == "keep_existing"
    assert "__replace" not in (st.get("fields") or {})


def test_decompile_lifts_the_field_list():
    st = _roundtrip("        update_fields: [severity, status]\n")
    assert st.get("update_fields") == ["severity", "status"]
    fields = st.get("fields") or {}
    assert "__fieldsToUpdate" not in fields
    assert "__replace" not in fields


def test_decompile_keeps_is_upsert_when_no_conflict_setting():
    # The pre-existing shape must round-trip exactly as it did before.
    st = _roundtrip("        is_upsert: true\n")
    assert st.get("is_upsert") is True
    assert "on_conflict" not in st


def test_decompile_leaves_a_plain_create_alone():
    st = _roundtrip("")
    assert "on_conflict" not in st
    assert "is_upsert" not in st


def test_raw_wire_keys_still_survive_a_plain_create():
    # `__replace` is IGNORED on the plain endpoint, so inventing a setting for
    # it would misreport what the step does -- it must ride through as written.
    st = _roundtrip('        fields:\n          __replace: "true"\n')
    assert "on_conflict" not in st
    assert (st.get("fields") or {}).get("__replace") == "true"
