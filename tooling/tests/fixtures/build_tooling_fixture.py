#!/usr/bin/env python3
"""Build the scoped tooling fixture DB used by ``tooling/tests``.

The tooling gate (``pytest -m "not slow and not live"``) resolves connectors
against a reference DB. Historically that was the mutable dev cache
``data/fsr_reference.db`` — gitignored, and clobbered whenever a local
connector-op probe fires warmup (it re-syncs the box catalog over the dev
corpus). A clobbered dev DB reds ~24 tests, blocking commits for a reason
unrelated to the change under test.

This script assembles a small, committed fixture that contains exactly the
connectors the ``db_path`` tests reference, at full param fidelity, plus the
infra tables the compiler needs (step_types, jinja, modules, op_safety,
picklists). Sources:

  * dev cache  — full infra + op_safety, and a handful of connectors
  * slim catalog (``fsr_playbooks/_data/fsr_reference.db``, committed) — the
    connectors the clobbered dev cache is missing
  * public Fortinet RPM repo — connectors present in neither local DB
    (apivoid, aws-access-analyzer, recorded-future, http), fetched at full
    fidelity via the probe's RPM path (no live box required)

Re-run this to regenerate the fixture when the test connector set changes:
    .venv/bin/python tooling/tests/fixtures/build_tooling_fixture.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tooling"))
from probes import probe_connectors as pc  # noqa: E402

DEV = REPO / "data" / "fsr_reference.db"
SLIM = REPO / "fsr_playbooks" / "_data" / "fsr_reference.db"
OUT = Path(__file__).resolve().parent / "tooling_reference.db"

# Every connector the db_path-using tooling tests reference.
CONN = [
    "fortigate-firewall", "virustotal", "cyops_utilities", "smtp", "ssh",
    "abuseipdb", "activedirectory", "fortinet-fortisiem", "fortinet-fortiedr",
    "apivoid", "aws-access-analyzer", "recorded-future", "http", "claroty-xdome",
]
# Connectors the clobbered dev cache lacks but the committed slim catalog has.
FROM_SLIM = ["abuseipdb", "activedirectory", "fortinet-fortisiem", "ssh"]
# Connectors present in neither local DB — fetched from the public RPM repo.
FROM_REPO = ["apivoid", "aws-access-analyzer", "recorded-future", "http",
             "claroty-xdome"]

# Big analytics tables the compiler never reads — dropped to keep the fixture
# committable (the dev cache is ~66 MB, almost all of it these tables).
# NOTE: playbook_steps / playbooks_seen are KEPT — the corpus validator/audit
# tests learn canonical operations and likely-required keys from them.
STRIP = [
    "verifications", "jinja_expressions", "jinja_filter_usage",
    "warmup_runs", "_probe_runs",
    "api_endpoints", "api_endpoint_params", "api_endpoint_examples",
    "operation_examples",
]


def _cols(db: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in db.execute(f"PRAGMA table_info({table})")]


def _tables(db: sqlite3.Connection) -> list[str]:
    return [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]


def _scoped_tables(db: sqlite3.Connection) -> list[tuple[str, str]]:
    """(table, connector-key-column) for every connector-scoped table."""
    out = []
    for t in _tables(db):
        cols = _cols(db, t)
        if t == "connectors":
            out.append((t, "name"))
        elif "connector_name" in cols:
            out.append((t, "connector_name"))
    return out


def main() -> int:
    if not DEV.exists():
        print(f"dev cache missing: {DEV}", file=sys.stderr)
        return 1
    if OUT.exists():
        OUT.unlink()
    shutil.copy(DEV, OUT)
    db = sqlite3.connect(OUT)

    # 1. strip analytics bloat
    existing = set(_tables(db))
    for t in STRIP:
        if t in existing:
            db.execute(f"DELETE FROM {t}")

    # 2. prune connector-scoped tables to the test set
    scoped = _scoped_tables(db)
    ph = ",".join("?" * len(CONN))
    for t, key in scoped:
        db.execute(f"DELETE FROM {t} WHERE {key} NOT IN ({ph})", CONN)
    db.commit()

    # 3. overlay slim-resident connectors (common columns only, to be robust
    #    against any schema drift between the two DBs)
    db.execute("ATTACH ? AS slim", (str(SLIM),))
    slim_tables = set(r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"))  # main+attached
    ph2 = ",".join("?" * len(FROM_SLIM))
    for t, key in scoped:
        try:
            main_cols = _cols(db, t)
            slim_cols = [r[1] for r in db.execute(f"PRAGMA slim.table_info({t})")]
        except sqlite3.OperationalError:
            continue
        common = [c for c in main_cols if c in slim_cols]
        if not common:
            continue
        collist = ",".join(common)
        db.execute(
            f"INSERT OR REPLACE INTO {t} ({collist}) "
            f"SELECT {collist} FROM slim.{t} WHERE {key} IN ({ph2})",
            FROM_SLIM,
        )
    db.commit()
    db.execute("DETACH slim")

    # 4. probe connectors present in neither local DB, from the public repo
    listing = pc._rpm_dir_listing()
    work = Path(tempfile.mkdtemp(prefix="fixture_rpm_"))
    for name in FROM_REPO:
        hits = sorted(
            f for f in listing
            if f.lower().startswith(f"cyops-connector-{name}".lower())
        )
        if not hits:
            print(f"  {name}: NO RPM on repo", file=sys.stderr)
            return 2
        rpm = hits[-1]  # newest published
        dest = work / rpm
        if not pc._download_rpm(rpm, dest):
            print(f"  {name}: download failed ({rpm})", file=sys.stderr)
            return 3
        info = pc._extract_info_from_rpm(dest, work / (rpm + "_x"))
        if not info:
            print(f"  {name}: extract failed ({rpm})", file=sys.stderr)
            return 4
        pc._upsert_connector_from_detail(db, info, "fortinet_repo_rpm")
        nops = len(info.get("operations") or [])
        print(f"  {name}: seeded v{info.get('version')} ({nops} ops) from {rpm}")
    db.commit()

    # 5. regenerate op_safety with the canonical name/method/category
    #    classifier. The dev cache's op_safety came from the box's category-only
    #    warmup classifier, which mislabels state-changing ops (e.g.
    #    fortinet-fortiedr.isolate_collector) as safe. probe_op_safety is the
    #    source of truth the tier tests are written against.
    from probes import probe_op_safety  # noqa: E402
    db.row_factory = sqlite3.Row  # probe_op_safety.run reads rows by name
    counts = probe_op_safety.run(db)
    db.commit()
    print(f"  op_safety reclassified: {counts}")

    # 6. compact
    db.execute("VACUUM")
    db.commit()
    present = [r[0] for r in db.execute(
        "SELECT name FROM connectors ORDER BY name")]
    db.close()
    size_mb = OUT.stat().st_size / 1e6
    print(f"\nfixture: {OUT}  ({size_mb:.1f} MB)")
    print(f"connectors ({len(present)}): {', '.join(present)}")
    missing = [c for c in CONN if c not in present]
    if missing:
        print(f"WARNING missing from fixture: {missing}", file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
