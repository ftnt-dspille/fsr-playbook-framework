"""Solution-pack catalog: ingest + the `find_solution_packs` lookup.

The pack zips carry no Content Hub metadata, so `harvest_solution_packs`
writes `data/solution_packs/_catalog.json` and `probe_playbook_steps` loads it
into `solution_packs` / `solution_pack_connectors` / `solution_pack_deps`.
These tests pin the two things that broke while wiring it up:

  1. Schema additions must reach an ALREADY-BUILT database. `open_db` used to
     apply schema.sql only when the file did not exist, so a new table was
     invisible until someone deleted the 63M corpus and rebuilt it.
  2. The catalog must cover EVERY pack, not just the downloaded ones -- the
     download filter drops the ~59 outbreak variants, and narrowing the
     connector edges to match would silently under-report which packs use a
     connector.
"""
import json
import sqlite3

import pytest

from tooling.probes import common
from tooling.probes.probe_playbook_steps import _ingest_pack_catalog

CATALOG = {
    "phishingEmailResponse": {
        "version": "1.0.3",
        "label": "Phishing Email Response",
        # Arrives as a list in the real record; must not reach sqlite as one.
        "category": ["Email Security", "SOC"],
        "fsrMinCompatibility": "7.4.0",
        "dependencies": [
            {"name": "sOARFramework", "type": "solutionpack",
             "label": "SOAR Framework", "version": "1.1.0", "minVersion": None},
        ],
        "connectors": [
            {"name": "Active Directory", "apiName": "activedirectory"},
            {"name": "VirusTotal", "apiName": "virustotal"},
        ],
    },
    # A pack that ships no playbooks and no connectors -- common for
    # module/dashboard-only packs, and it must survive ingest, not crash it.
    "knowledgeBase": {
        "version": "1.0.1", "label": "Knowledge Base", "category": None,
        "fsrMinCompatibility": None, "dependencies": [], "connectors": [],
    },
}


@pytest.fixture()
def catalog_db(tmp_path, monkeypatch):
    """A real DB built from schema.sql with the sidecar in place."""
    packs_dir = tmp_path / "solution_packs"
    packs_dir.mkdir()
    (packs_dir / "_catalog.json").write_text(json.dumps(CATALOG))

    db = tmp_path / "ref.db"
    monkeypatch.setattr(common, "DB_PATH", db)
    monkeypatch.setattr(common, "STORE_DIR", tmp_path)
    monkeypatch.setattr(
        "tooling.probes.probe_playbook_steps.HARVESTED_PACKS_DIR", packs_dir)
    conn = common.open_db()
    _ingest_pack_catalog(conn, "2026-07-31T00:00:00+00:00")
    conn.commit()
    yield conn
    conn.close()


def test_open_db_applies_schema_to_an_existing_database(tmp_path, monkeypatch):
    """The regression that made the new tables unreachable."""
    db = tmp_path / "ref.db"
    monkeypatch.setattr(common, "DB_PATH", db)
    monkeypatch.setattr(common, "STORE_DIR", tmp_path)
    # Pre-create the file so it is NOT "fresh" -- the old gate skipped
    # schema.sql entirely in exactly this case.
    sqlite3.connect(db).close()
    conn = common.open_db()
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "solution_packs" in names
    assert "solution_pack_connectors" in names
    conn.close()


def test_open_db_does_not_rewrite_schema_on_every_open(tmp_path, monkeypatch):
    """Applying schema.sql on every open corrupted the database.

    The first fix for the missing-table bug ran `executescript` unconditionally,
    turning every read-only open into a write. Under the suite's rapid repeated
    opens one run failed 313 tests with `database disk image is malformed` and
    the next two passed -- the worst kind of regression. Steady state must be a
    read.
    """
    db = tmp_path / "ref.db"
    monkeypatch.setattr(common, "DB_PATH", db)
    monkeypatch.setattr(common, "STORE_DIR", tmp_path)
    common.open_db().close()          # builds it
    mtime = db.stat().st_mtime_ns
    for _ in range(5):
        common.open_db().close()
    assert db.stat().st_mtime_ns == mtime, "open_db wrote to an up-to-date database"


def test_list_category_is_flattened_not_bound_raw(catalog_db):
    row = catalog_db.execute(
        "SELECT category, dir_name, min_fsr FROM solution_packs "
        "WHERE name = 'phishingEmailResponse'").fetchone()
    assert row["category"] == "Email Security, SOC"
    # dir_name is the join key back to playbook_steps.source_path.
    assert row["dir_name"] == "phishingEmailResponse-1.0.3"
    assert row["min_fsr"] == "7.4.0"


def test_connector_and_dependency_edges_land(catalog_db):
    conns = [r[0] for r in catalog_db.execute(
        "SELECT connector FROM solution_pack_connectors "
        "WHERE pack_name = 'phishingEmailResponse' ORDER BY connector")]
    assert conns == ["activedirectory", "virustotal"]
    deps = [r[0] for r in catalog_db.execute(
        "SELECT depends_on FROM solution_pack_deps "
        "WHERE pack_name = 'phishingEmailResponse'")]
    assert deps == ["sOARFramework"]


def test_pack_with_no_connectors_still_ingests(catalog_db):
    n = catalog_db.execute(
        "SELECT COUNT(*) FROM solution_packs WHERE name = 'knowledgeBase'"
    ).fetchone()[0]
    assert n == 1


def test_reingest_is_idempotent(catalog_db):
    """Probes rerun constantly; a second pass must not double the edges."""
    _ingest_pack_catalog(catalog_db, "2026-07-31T01:00:00+00:00")
    catalog_db.commit()
    assert catalog_db.execute(
        "SELECT COUNT(*) FROM solution_packs").fetchone()[0] == 2
    assert catalog_db.execute(
        "SELECT COUNT(*) FROM solution_pack_connectors").fetchone()[0] == 2


def test_missing_sidecar_is_a_no_op_not_a_crash(tmp_path, monkeypatch):
    """A corpus built before the harvest ran must still ingest playbooks."""
    db = tmp_path / "ref.db"
    monkeypatch.setattr(common, "DB_PATH", db)
    monkeypatch.setattr(common, "STORE_DIR", tmp_path)
    monkeypatch.setattr(
        "tooling.probes.probe_playbook_steps.HARVESTED_PACKS_DIR",
        tmp_path / "does-not-exist")
    conn = common.open_db()
    assert _ingest_pack_catalog(conn, "2026-07-31T00:00:00+00:00") == {
        "packs": 0, "connectors": 0, "deps": 0}
    conn.close()
