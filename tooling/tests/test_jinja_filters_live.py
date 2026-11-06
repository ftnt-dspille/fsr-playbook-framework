"""Replay every Jinja filter probe case against a live FortiSOAR (`make jinja-verify`).

Each `jinja_filter_probes` row is a proven fact from a past run on a named
build: this template, with this input, rendered (or raised) and returned this
Python type. Re-rendering every row on a box proves all filters still work
there -- after an upgrade, or on a different box -- and names exactly which
filter changed behaviour.

    make jinja-verify INSTANCE=<pyfsr instance alias>

Deselected by default (`live` marker); needs FSRPB_JINJA_INSTANCE.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from tooling.probes.probe_jinja_filter_io import render_case

pytestmark = pytest.mark.live

_DB = Path(__file__).resolve().parents[2] / "data" / "fsr_reference.db"


def _rows() -> list[sqlite3.Row]:
    if not _DB.exists():
        return []
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM jinja_filter_probes ORDER BY filter_name, case_id").fetchall()
    except sqlite3.OperationalError:
        return []


_ROWS = _rows()


@pytest.fixture(scope="module")
def client():
    alias = os.environ.get("FSRPB_JINJA_INSTANCE")
    if not alias:
        pytest.skip("set FSRPB_JINJA_INSTANCE (make jinja-verify INSTANCE=<alias>)")
    from pyfsr.instances import InstanceRegistry

    return InstanceRegistry.load().client(alias)


@pytest.mark.skipif(not _ROWS, reason="no jinja_filter_probes evidence: run `make jinja-probe` first")
@pytest.mark.parametrize("row", _ROWS, ids=[f"{r['filter_name']}[{r['case_id']}]" for r in _ROWS])
def test_filter_case_still_behaves(client, row):
    args = ""
    marker = f"| {row['filter_name']}("
    if marker in row["template"]:
        args = row["template"].split(marker, 1)[1].rsplit(")) | type_debug", 1)[0]
    now = render_case(client, row["filter_name"],
                      {"case_id": row["case_id"], "input": json.loads(row["input_json"]), "args": args})
    assert now["template"] == row["template"], "replay rebuilt a different template"
    assert bool(now["ok"]) == bool(row["ok"]), (
        f"{row['filter_name']} [{row['case_id']}] used to {'render' if row['ok'] else 'raise'} "
        f"on {row['fsr_build']}; now: {now['error'] or now['output_type']}")
    if row["ok"]:
        assert now["output_type"] == row["output_type"], (
            f"{row['filter_name']} [{row['case_id']}] returned {row['output_type']} on "
            f"{row['fsr_build']}, now returns {now['output_type']}")
