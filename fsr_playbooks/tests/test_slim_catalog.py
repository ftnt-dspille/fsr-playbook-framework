"""Pins the shipped slim compile catalog (Phase 3b).

The wheel ships ``fsr_playbooks/_data/fsr_reference.db`` — the stable-tables
catalog built by ``tooling/catalog/build_compile_catalog.py``. A fresh install
has no probed ``data/`` DB, so this packaged slim DB is what compiles run
against. These tests assert the contract the slim DB must satisfy:

* it exists and ships the stable catalog (step types populated);
* the scrubbed **connector baseline** ships (definitions only — the public
  operation/param schema the compiler validates against, so the in-repo
  example/library playbooks compile offline);
* the instance-specific carriers are scrubbed: ``info_json``/``source_code``/
  ``rpm_fingerprint`` NULL on every shipped connector, ``connector_configs``
  (per-instance creds) empty, ``picklists`` empty (warmed, not stale-shipped);
* a stable-only playbook compiles clean against it;
* a baseline-connector playbook compiles clean against it (proves the
  shipped defs are sufficient);
* a NON-baseline connector fails with a clear ``CompileError`` (the resolver
  has no live fallback — see ``fsr_playbooks/_db.py``), NOT a crash.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from tooling.catalog.build_compile_catalog import CONNECTOR_BASELINE

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
        # Module *type names* ship as a stable baseline catalog so the
        # resolver can validate/canonicalize module names offline.
        assert conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0] > 0
        # Scrubbed connector baseline: every name present, with operations +
        # operation_params, but the instance-specific cols NULLed.
        shipped = {r[0] for r in conn.execute(
            "SELECT name FROM connectors ORDER BY name"
        ).fetchall()}
        assert shipped == set(CONNECTOR_BASELINE), (
            f"shipped connectors {sorted(shipped)} != baseline {sorted(CONNECTOR_BASELINE)}"
        )
        for name in CONNECTOR_BASELINE:
            assert conn.execute(
                "SELECT COUNT(*) FROM operations WHERE connector_name = ?", (name,)
            ).fetchone()[0] > 0, f"{name}: no operations shipped"
            row = conn.execute(
                "SELECT info_json, source_code, rpm_fingerprint, source "
                "FROM connectors WHERE name = ?", (name,)
            ).fetchone()
            assert row is not None, f"{name}: connector row missing"
            info_json, source_code, rpm_fingerprint, source = row
            assert info_json is None, f"{name}: info_json not scrubbed (sensitive)"
            assert source_code is None, f"{name}: source_code not scrubbed"
            assert rpm_fingerprint is None, f"{name}: rpm_fingerprint not scrubbed"
            assert source == "packaged", f"{name}: source={source!r} (expected 'packaged')"
        # The per-instance creds table stays empty — warmed, never shipped.
        assert conn.execute(
            "SELECT COUNT(*) FROM connector_configs"
        ).fetchone()[0] == 0, "connector_configs must ship empty (per-instance creds)"
        # picklists are still per-install (instance-specific picklist rows);
        # warmed, not shipped.
        assert conn.execute(
            "SELECT COUNT(*) FROM picklists"
        ).fetchone()[0] == 0, "picklists must ship empty (per-install)"
    finally:
        conn.close()


def test_stable_only_playbook_compiles_against_slim_db():
    yaml_text = (_EXAMPLES / "decision_branch.yaml").read_text()
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    blocking = [e.message for e in res.errors if e.severity != "warning"]
    assert res.ok, f"stable-only compile failed: {blocking}"


def test_baseline_connector_playbook_compiles_against_slim_db():
    # virustotal is in the shipped baseline, so this example must now compile
    # offline — proving the scrubbed connector defs are sufficient.
    yaml_text = (_EXAMPLES / "demo_virustotal_ip.yaml").read_text()
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    blocking = [e.message for e in res.errors if e.severity != "warning"]
    assert res.ok, f"baseline-connector compile failed: {blocking}"


def test_non_baseline_connector_fails_clean_against_slim_db():
    # A connector NOT in the baseline must fail with a clear CompileError
    # (the resolver has no live fallback), never a crash.
    yaml_text = """
name: non-baseline-connector-demo
playbooks:
  - name: P
    steps:
      - name: S
        type: connector
        connector: definitely_not_a_real_connector_xyz
        operation: some_op
        arguments:
          params: {}
"""
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    blocking = [e.message for e in res.errors if e.severity != "warning"]
    assert not res.ok, "expected a blocking error: connector not in baseline"
    assert any("connector" in m.lower() for m in blocking), blocking
