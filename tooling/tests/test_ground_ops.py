"""ground_ops: run a connector op live, fold its envelope shape in, leak nothing.

A fake client stands in for the box so the mechanics (typed-not-dict coercion,
value-free hygiene, success gating) are pinned without a live appliance."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tooling"))

import ground_ops as go  # noqa: E402


class _TypedResult:
    """Stand-in for pyfsr's ExecuteResult (pydantic): a model, not a dict."""

    def __init__(self, data, status="Success", message=""):
        self._d = {"operation": None, "status": status, "message": message,
                   "data": data}

    def model_dump(self):
        return dict(self._d)


class _FakeConnectors:
    def __init__(self, by_op):
        self._by_op = by_op

    def execute(self, *, connector, operation, params=None):
        return self._by_op[f"{connector}:{operation}"]


class _FakeClient:
    def __init__(self, by_op):
        self.connectors = _FakeConnectors(by_op)


def test_envelope_coerces_typed_result():
    env = go.envelope_of(_TypedResult({"formatted_string": "x"}))
    assert env["data"] == {"formatted_string": "x"}
    assert env["status"] == "Success"


def test_assert_value_free_passes_structure_and_catches_a_value():
    good = {"kind": "object", "keys": {
        "data": {"kind": "object", "keys": {
            "asn": {"kind": "scalar", "type": "string"}}}}}
    go.assert_value_free(good)  # no raise
    bad = {"kind": "object", "keys": {
        "asn": {"kind": "scalar", "type": "string", "example": "15169"}}}
    with pytest.raises(AssertionError):
        go.assert_value_free(bad)


def test_ground_ops_grounds_success_and_is_value_free(tmp_path):
    store_path = tmp_path / "s.json"
    store_path.write_text("{}")
    client = _FakeClient({
        "whois-rdap:whois_ip": _TypedResult(
            {"asn": "15169", "network": {"cidr": "8.8.8.0/24"}}),
    })
    report, store = go.ground_ops(
        [("whois-rdap", "whois_ip", {"ip": "8.8.8.8"})],
        store_path=store_path, client=client)
    assert report[0]["result"] == "grounded"
    shape = store.shape_for("whois-rdap", "whois_ip")
    assert shape["kind"] == "object"
    # the captured scalar VALUE "15169" is gone; only its type survives
    go.assert_value_free(shape)
    assert "15169" not in store_path.read_text()
    assert "8.8.8.0/24" not in store_path.read_text()


def test_failed_op_is_skipped_not_grounded(tmp_path):
    store_path = tmp_path / "s.json"
    store_path.write_text("{}")
    client = _FakeClient({
        "file-content-extraction:extract_indicators_from_file":
            _TypedResult(None, status="Failure", message="File IRI blank"),
    })
    report, store = go.ground_ops(
        [("file-content-extraction", "extract_indicators_from_file", {})],
        store_path=store_path, client=client)
    assert report[0]["result"] == "skip"
    assert store.shape_for("file-content-extraction",
                           "extract_indicators_from_file") is None


def test_parse_spec():
    assert go._parse_spec("whois-rdap:whois_ip:{\"ip\":\"8.8.8.8\"}") == \
        ("whois-rdap", "whois_ip", {"ip": "8.8.8.8"})
    assert go._parse_spec("cyops_utilities:get_macro_list") == \
        ("cyops_utilities", "get_macro_list", {})
