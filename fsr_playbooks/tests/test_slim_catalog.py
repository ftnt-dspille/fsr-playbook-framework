"""Pins the shipped slim compile catalog (Phase 3b).

The wheel ships ``fsr_playbooks/_data/fsr_reference.db`` — the stable-tables-only
catalog built by ``tooling/catalog/build_compile_catalog.py``. A fresh install
has no probed ``data/`` DB, so this packaged slim DB is what compiles run
against. These tests assert the contract the slim DB must satisfy:

* it exists and ships the stable catalog (step types populated);
* the per-install tables ship EMPTY (so they're warmed, not stale-shipped);
* a stable-only playbook compiles clean against it;
* a connector-referencing playbook fails with a clear ``CompileError`` (the
  resolver has no live fallback — see ``fsr_playbooks/_db.py``), NOT a crash.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_slim_db_is_present_and_shaped():
    assert PACKAGED_SLIM_DB.exists(), f"slim catalog missing: {PACKAGED_SLIM_DB}"
    # Comfortably under the heavy probed DB; a regression that re-ships corpus
    # or per-install tables would blow past this.
    assert PACKAGED_SLIM_DB.stat().st_size < 5_000_000
    conn = sqlite3.connect(f"file:{PACKAGED_SLIM_DB}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM step_types").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM jinja_macros").fetchone()[0] > 0
        # Per-install tables ship empty — schema present, zero rows.
        for t in ("connectors", "operations", "picklists", "modules"):
            assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    finally:
        conn.close()


def test_stable_only_playbook_compiles_against_slim_db():
    yaml_text = (_EXAMPLES / "decision_branch.yaml").read_text()
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    blocking = [e.message for e in res.errors if e.severity != "warning"]
    assert res.ok, f"stable-only compile failed: {blocking}"


def test_connector_playbook_fails_clean_against_slim_db():
    yaml_text = (_EXAMPLES / "demo_virustotal_ip.yaml").read_text()
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    blocking = [e.message for e in res.errors if e.severity != "warning"]
    assert not res.ok, "expected a blocking error: slim DB has no connectors"
    assert any("connector" in m.lower() for m in blocking), blocking
