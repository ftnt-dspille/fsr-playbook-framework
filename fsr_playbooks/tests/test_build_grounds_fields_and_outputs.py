"""A build turn can learn the data a step reads without triage tools.

Live (analyst sim, 30 sessions): record reads and run_op are refused on build
turns (by design), and nothing build-side named a module's fields or an op's
real output -- get_op_schema even said "run_op to observe" it. So the model
guessed: `records[0].destIp`, and VirusTotal paths from the vendor's API docs
(`.data.data.attributes...`). Four of six reputation gates could never fire,
and the recorded VirusTotal shape that would have caught them was discarded
because the op's safety label is not "safe".
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from fsr_playbooks.mcp_server import _shared  # noqa: E402
from fsr_playbooks.mcp_server.tools_discovery import (
    _recorded_output_paths,  # noqa: E402
)
from fsr_playbooks.mcp_server.tools_find import find  # noqa: E402
from fsr_playbooks.mcp_server.tools_verify import verify_playbook  # noqa: E402

_GATE = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: VT}
      - name: VT
        type: connector
        connector: virustotal
        operation: query_ip
        params: {ip: 1.2.3.4}
        next: Gate
      - name: Gate
        type: decision
        conditions:
          - {display: Bad, when: "{{ vars.steps.VT.__PATH__ | int > 0 }}", next: Done}
          - {display: Else, default: true, next: Done}
      - {name: Done, type: end}
"""


def _shape_fixes(path: str) -> list[str]:
    r = verify_playbook(_GATE.replace("__PATH__", path))
    return [w["code"] for w in (r.get("required_fixes") or [])
            if w.get("code") == "missing_field_on_step_output"]


def test_the_recorded_shape_catches_a_vendor_docs_path():
    assert _shape_fixes("data.data.attributes.last_analysis_stats.malicious")


def test_the_recorded_path_is_clean():
    assert _shape_fixes("data.attributes.last_analysis_stats.malicious") == []


def test_get_op_schema_names_the_recorded_paths():
    paths = _recorded_output_paths("virustotal", "query_ip")
    assert "data.attributes.last_analysis_stats.malicious (integer)" in paths
    assert "data.attributes.reputation (integer)" in paths  # not crowded out
    assert _recorded_output_paths("virustotal", "no_such_op") == []


@pytest.fixture
def fields_db(tmp_path, monkeypatch):
    db = tmp_path / "ref.db"
    shutil.copy(_shared.DB_PATH, db)
    with sqlite3.connect(db) as c:
        c.executemany(
            "INSERT OR REPLACE INTO module_fields (module_name, field_name, title, type) "
            "VALUES ('alerts', ?, ?, 'text')",
            [("destinationIp", "Destination IP"), ("destinationPort", "Destination Port"),
             ("sourceIp", "Source IP"), ("description", "Description")])
    monkeypatch.setattr(_shared, "DB_PATH", str(db))
    return db


def test_find_field_ranks_the_field_the_analyst_means(fields_db):
    r = find("field", query="dest ip", module="alerts", limit=2)
    assert r["ok"] and r["fields"][0]["name"] == "destinationIp"
    assert "vars.input.records[0]" in r["usage"]


def test_find_field_names_what_is_missing(fields_db):
    assert find("field", module="").get("code") == "missing_module"
    assert find("field", module="nonsense").get("code") == "module_not_in_catalog"


def test_the_build_refusal_points_at_the_field_lookup():
    from fsr_playbooks.llm.turn_plan import _playbook_side_refusal
    r = _playbook_side_refusal("run_op", {})
    assert r and "find(kind='field'" in r["error"]
