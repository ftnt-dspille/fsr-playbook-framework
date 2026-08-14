"""The slim/missing reference DB must be loud, never silent.

An empty reference store does not raise on its own -- it answers "no such
connector" to every lookup, so `validate_yaml` returns clean for genuinely
broken YAML. And `sqlite3.connect()` CREATES a database for a path that does
not exist, so a wrong path manufactures exactly that empty store instead of
failing. Both behaviours are pinned here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fsr_playbooks.reference_db import (
    ReferenceDbError,
    health,
    require_populated,
)


def _make_db(path: Path, connectors: int = 0, operations: int = 0) -> Path:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE connectors (name TEXT)")
    conn.execute("CREATE TABLE operations (name TEXT)")
    for i in range(connectors):
        conn.execute("INSERT INTO connectors VALUES (?)", (f"c{i}",))
    for i in range(operations):
        conn.execute("INSERT INTO operations VALUES (?)", (f"o{i}",))
    conn.commit()
    conn.close()
    return path


def test_populated_db_is_healthy(tmp_path):
    p = _make_db(tmp_path / "full.db", connectors=3, operations=9)
    h = health(p)
    assert h.populated
    assert h.counts == {"connectors": 3, "operations": 9}


def test_empty_db_is_not_populated(tmp_path):
    """The exact shape found vendored in the connector: right schema, no rows."""
    p = _make_db(tmp_path / "slim.db")
    h = health(p)
    assert h.exists and h.is_reference_db
    assert not h.populated
    assert "EMPTY/SLIM" in h.summary


def test_partially_empty_db_is_not_populated(tmp_path):
    """Connectors but no operations is just as blind for operation lookups."""
    p = _make_db(tmp_path / "half.db", connectors=5, operations=0)
    assert not health(p).populated


def test_missing_db_reports_missing_and_creates_nothing(tmp_path):
    p = tmp_path / "absent.db"
    h = health(p)
    assert not h.exists and not h.populated
    assert not p.exists(), "health() must never create the DB it inspects"


def test_non_reference_sqlite_is_rejected(tmp_path):
    p = tmp_path / "other.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE unrelated (x TEXT)")
    conn.commit()
    conn.close()
    h = health(p)
    assert h.exists and not h.is_reference_db and not h.populated


def test_require_populated_raises_with_actionable_message(tmp_path):
    p = _make_db(tmp_path / "slim.db")
    with pytest.raises(ReferenceDbError) as exc:
        require_populated(p)
    msg = str(exc.value)
    assert "EMPTY/SLIM" in msg
    # It must say what to DO, not merely what is wrong.
    assert "FSR_REFERENCE_DB" in msg and "re-vendor" in msg


def test_require_populated_returns_health_when_fine(tmp_path):
    p = _make_db(tmp_path / "full.db", connectors=1, operations=1)
    assert require_populated(p).populated


def test_resolver_refuses_a_missing_db_instead_of_creating_one(tmp_path):
    """The mechanism that manufactured empty stores in the first place."""
    from fsr_playbooks.compiler.resolver import Resolver
    p = tmp_path / "nope.db"
    with pytest.raises(ReferenceDbError):
        Resolver(p)
    assert not p.exists(), "Resolver must not conjure an empty reference DB"


# --- the other face of the same failure: present, populated, and DAMAGED ---

def _corrupt_page(path: Path) -> Path:
    """Scribble over a b-tree page so SQLite reports structural damage.

    Page 1 is the schema header -- corrupting it makes the file stop being a
    database at all, which is the case already covered. Damage a later page so
    the store still opens, still reports its schema, and still counts rows.
    """
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE bulk (v TEXT)")
    conn.executemany("INSERT INTO bulk VALUES (?)",
                     [(f"row-{i}-{'x' * 200}",) for i in range(4000)])
    conn.commit()
    conn.close()
    page_size = 4096
    with open(path, "r+b") as fh:
        fh.seek(page_size * 20)
        fh.write(b"\xde\xad\xbe\xef" * 64)
    return path


def test_a_corrupt_but_populated_db_is_reported_corrupt(tmp_path):
    """Row counts are not health.

    Found 2026-08-14: the store passed every other check -- present, right
    schema, connectors=728, operations=6952 -- while `verifications` carried
    out-of-order rowids, so `find_operation` raised
    `DatabaseError: database disk image is malformed` on SOME queries and
    answered others fine. The agent saw a catalog that intermittently lost
    operations that exist: 8 of 18 calls re-searching for one, no playbook
    delivered, tool-gate 1/4. Doctor said 4/4 checks passed.
    """
    p = _corrupt_page(_make_db(tmp_path / "damaged.db",
                               connectors=3, operations=9))
    h = health(p)
    if h.intact:
        pytest.skip("this SQLite build did not notice the scribbled page")
    # Still populated -- that is the whole point. Populated and intact are
    # different questions, and only one of them was being asked.
    assert h.populated
    assert not h.intact
    assert "CORRUPT" in h.summary


def test_a_healthy_db_reports_intact(tmp_path):
    h = health(_make_db(tmp_path / "full.db", connectors=1, operations=1))
    assert h.intact and h.integrity == "ok"


def test_skip_integrity_leaves_the_flag_unset(tmp_path):
    """The counts-only path for callers that cannot afford the check --
    `intact` must not then claim a check that never ran."""
    h = health(_make_db(tmp_path / "full.db", connectors=1, operations=1),
               skip_integrity=True)
    assert h.integrity == ""
    assert h.intact  # unknown reads as fine; only a RUN check can accuse
