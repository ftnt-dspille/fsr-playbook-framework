from __future__ import annotations

import csv
import io
import json

from fsr_playbooks.helpers import csv_report


def test_build_csv_explicit_columns():
    rows = [
        {"serial": "SN1", "name": "fw-a", "location": "DC1"},
        {"serial": "SN2", "name": "fw-b", "location": "DC2"},
    ]
    text = csv_report.build_csv(rows, columns=["serial", "name", "location"])
    out = list(csv.reader(io.StringIO(text)))
    assert out[0] == ["serial", "name", "location"]
    assert out[1] == ["SN1", "fw-a", "DC1"]
    assert out[2] == ["SN2", "fw-b", "DC2"]


def test_build_csv_infers_columns_from_union_of_keys_in_first_seen_order():
    rows = [
        {"serial": "SN1", "name": "fw-a"},
        {"serial": "SN2", "location": "DC2"},
    ]
    text = csv_report.build_csv(rows)
    header = next(csv.reader(io.StringIO(text)))
    assert header == ["serial", "name", "location"]


def test_build_csv_missing_values_become_empty_cells():
    rows = [{"serial": "SN1", "name": "fw-a"}, {"serial": "SN2"}]
    text = csv_report.build_csv(rows, columns=["serial", "name"])
    out = list(csv.reader(io.StringIO(text)))
    assert out[2] == ["SN2", ""]


def test_build_csv_non_scalar_values_json_encoded_into_one_cell():
    rows = [{"serial": "SN1", "tags": ["a", "b"], "meta": {"k": 1}}]
    text = csv_report.build_csv(rows, columns=["serial", "tags", "meta"])
    out = list(csv.reader(io.StringIO(text)))
    assert out[1][0] == "SN1"
    assert out[1][1] == '["a", "b"]'
    assert out[1][2] == '{"k": 1}'


def test_build_csv_bool_renders_as_true_false_not_Python_True():
    rows = [{"serial": "SN1", "active": True}, {"serial": "SN2", "active": False}]
    text = csv_report.build_csv(rows, columns=["serial", "active"])
    out = list(csv.reader(io.StringIO(text)))
    assert out[1] == ["SN1", "true"]
    assert out[2] == ["SN2", "false"]


def test_build_csv_empty_rows_with_columns_yields_header_only():
    text = csv_report.build_csv([], columns=["serial", "name"])
    assert next(csv.reader(io.StringIO(text))) == ["serial", "name"]


def test_write_csv_writes_file_and_returns_path(tmp_path):
    rows = [{"serial": "SN1", "name": "fw-a"}]
    path = csv_report.write_csv(
        tmp_path / "recon.csv", rows, columns=["serial", "name"]
    )
    body = (tmp_path / "recon.csv").read_text()
    assert path.endswith("recon.csv")
    assert list(csv.reader(io.StringIO(body))) == [["serial", "name"], ["SN1", "fw-a"]]


def test_write_csv_output_round_trips_through_json_for_step_vars(tmp_path):
    # the file content is plain CSV text; ensure no surprise binary/encoding
    rows = [{"serial": "SN1", "name": "fw-a"}]
    csv_report.write_csv(tmp_path / "r.csv", rows, columns=["serial", "name"])
    text = (tmp_path / "r.csv").read_text(encoding="utf-8")
    assert text.splitlines() == ["serial,name", "SN1,fw-a"]
    json.dumps(text)  # must be JSON-safe as a step var
