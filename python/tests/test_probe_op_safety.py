"""Unit tests for probes.probe_op_safety classifier layers."""
from __future__ import annotations

import sqlite3

import pytest

from probes import probe_op_safety as ps


class _Row:
    """Stand-in for sqlite3.Row that supports __getitem__ by key."""
    def __init__(self, **kw): self._d = kw
    def __getitem__(self, k): return self._d[k]


def _params(**kw) -> list[_Row]:
    return [_Row(param_name=k, default_value=v) for k, v in kw.items()]


def test_unsafe_prefix_trumps_safe_signals():
    safety, _, ev = ps.classify("create_block_rule", [], "threat-intel")
    assert safety == "unsafe"
    assert ev["source"] == "name_unsafe"


def test_safe_prefix_get():
    safety, _, ev = ps.classify("get_indicators", [], None)
    assert safety == "safe"
    assert ev["matched_pattern"] == "prefix:get"


def test_safe_suffix_status():
    safety, _, ev = ps.classify("scan_status", [], None)
    assert safety == "safe"
    assert ev["matched_pattern"] == "suffix:_status"


def test_http_method_get_is_safe():
    safety, _, ev = ps.classify("generic_request", _params(method="GET"), None)
    assert safety == "safe"
    assert ev["method"] == "GET"


def test_http_method_post_is_unsafe_when_name_neutral():
    safety, _, _ = ps.classify("generic_request", _params(method="POST"), None)
    assert safety == "unsafe"


def test_category_bias_only_when_unknown_name():
    # neutral name + unsafe category nudges to unsafe
    s, _, ev = ps.classify("do_thing", [], "firewall")
    assert s == "unsafe"
    assert ev["source"] == "category_bias"
    # safe-category nudges to safe
    s, _, _ = ps.classify("do_thing", [], "enrichment")
    assert s == "safe"


def test_unclassified_is_unknown():
    s, _, ev = ps.classify("xyz_thing", [], None)
    assert s == "unknown"
    assert ev["source"] == "unclassified"


def test_unsafe_prefix_overrides_category_bias():
    s, _, _ = ps.classify("delete_indicator", [], "enrichment")
    assert s == "unsafe"


def test_end_to_end_writes_rows(tmp_path, monkeypatch):
    db = tmp_path / "ref.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE connectors (name TEXT PRIMARY KEY, category TEXT);
    CREATE TABLE operations (
        connector_name TEXT, op_name TEXT, title TEXT, annotation TEXT,
        category TEXT, description TEXT, visible INT, enabled INT,
        output_schema_json TEXT, conditional_output_schema_json TEXT,
        PRIMARY KEY (connector_name, op_name)
    );
    CREATE TABLE operation_params (
        connector_name TEXT, op_name TEXT, parent_param_name TEXT,
        condition_value TEXT, param_name TEXT, title TEXT, type TEXT,
        required INT, default_value TEXT, options_json TEXT,
        tooltip TEXT, placeholder TEXT, description TEXT,
        visible INT, editable INT, ord INT,
        PRIMARY KEY (connector_name, op_name, parent_param_name, condition_value, param_name)
    );
    CREATE TABLE op_safety (
        connector_name TEXT, op_name TEXT, safety TEXT,
        reason TEXT, evidence TEXT, classifier_version INT, updated_at TEXT,
        PRIMARY KEY (connector_name, op_name)
    );
    """)
    conn.execute("INSERT INTO connectors VALUES ('fortigate', 'firewall')")
    conn.execute("INSERT INTO connectors VALUES ('virustotal', 'threat-intel')")
    conn.executemany(
        "INSERT INTO operations(connector_name, op_name) VALUES (?, ?)",
        [("fortigate", "block_ip"), ("virustotal", "get_file_report"),
         ("fortigate", "do_thing")],
    )

    counts = ps.run(conn)
    rows = {(r["connector_name"], r["op_name"]): r["safety"]
            for r in conn.execute("SELECT * FROM op_safety")}
    assert rows[("fortigate", "block_ip")] == "unsafe"
    assert rows[("virustotal", "get_file_report")] == "safe"
    # Neutral name + firewall category bias → unsafe
    assert rows[("fortigate", "do_thing")] == "unsafe"
    assert counts["unsafe"] >= 1 and counts["safe"] >= 1
