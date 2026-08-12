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
