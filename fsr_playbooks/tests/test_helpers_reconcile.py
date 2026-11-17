from __future__ import annotations

import json

from fsr_playbooks.helpers import reconcile


def _source_a():
    return [
        {"serial": "SN1", "name": "fw-a", "location": "DC1"},  # matched
        {"serial": "SN2", "name": "fw-b", "location": "DC2"},  # matched
        {"serial": "SN3", "name": "fw-c", "location": "DC3"},  # only in A
        {"serial": "SN4", "name": "fw-d", "location": "DC4"},  # mismatch (location)
    ]


def _source_b():
    return [
        {"serial": "SN1", "name": "fw-a", "location": "DC1"},  # matched
        {"serial": "SN2", "name": "fw-b", "location": "DC2"},  # matched
        {"serial": "SN4", "name": "fw-d", "location": "DC9"},  # mismatch
        {"serial": "SN9", "name": "fw-z", "location": "DC9"},  # only in B
    ]


def test_only_in_each_side():
    r = reconcile(_source_a(), _source_b(), key="serial", fields=["name", "location"])
    assert [x["serial"] for x in r["only_in_a"]] == ["SN3"]
    assert [x["serial"] for x in r["only_in_b"]] == ["SN9"]


def test_mismatches_classify_differing_fields_and_keep_both_records():
    r = reconcile(_source_a(), _source_b(), key="serial", fields=["name", "location"])
    mm = r["mismatches"]
    assert len(mm) == 1
    assert mm[0]["key"] == "SN4"
    assert mm[0]["fields"] == {"location": {"a": "DC4", "b": "DC9"}}
    assert mm[0]["record_a"]["serial"] == "SN4"
    assert mm[0]["record_b"]["location"] == "DC9"


def test_matched_count_excludes_mismatches():
    r = reconcile(_source_a(), _source_b(), key="serial", fields=["name", "location"])
    assert r["matched"] == 2  # SN1, SN2


def test_summary_counts():
    r = reconcile(_source_a(), _source_b(), key="serial", fields=["name", "location"])
    assert r["summary"] == {
        "only_in_a": 1,
        "only_in_b": 1,
        "mismatches": 1,
        "matched": 2,
        "total_a": 4,
        "total_b": 4,
    }


def test_fields_defaults_to_keys_common_to_both_records():
    # without `fields`, compare the common keys (name, location); serial is the
    # key and is excluded from mismatch reporting.
    r = reconcile(_source_a(), _source_b(), key="serial")
    assert r["summary"]["mismatches"] == 1
    assert r["matched"] == 2


def test_key_field_is_never_reported_as_a_mismatch():
    # both sides share serial=SN4; even if `fields` lists it, it must not appear
    r = reconcile(_source_a(), _source_b(), key="serial", fields=["serial", "location"])
    mm = r["mismatches"][0]
    assert "serial" not in mm["fields"]
    assert list(mm["fields"]) == ["location"]


def test_result_is_json_serializable_for_step_vars():
    r = reconcile(_source_a(), _source_b(), key="serial", fields=["name", "location"])
    json.dumps(r)  # must not raise -- this dict becomes a playbook step variable


def test_non_string_keys_match_via_string_coercion():
    a = [{"id": 100, "name": "x"}]
    b = [{"id": "100", "name": "x"}]  # same key, different type
    r = reconcile(a, b, key="id", fields=["name"])
    assert r["matched"] == 1
    assert r["summary"]["mismatches"] == 0
