"""Reference-DB resolution: what counts as usable, and what may be written.

Two bugs motivated these, and both were silent -- they surfaced as unrelated
tests failing somewhere else entirely.

* A zero-byte `data/fsr_reference.db` satisfied `.exists()` and so won the
  resolution order over the packaged catalog. `sqlite3.connect()` creates
  exactly that file at a missing path, and a tooling test did, so running the
  two suites in one checkout reddened 95 `fsr_playbooks` tests with "no such
  table: picklists" and left nothing in the diff to explain it.

* The packaged catalog was accepted as a write target. The connector-health
  cache writes on its *read* path (`CREATE TABLE IF NOT EXISTS`), so an
  ordinary test run came back with the tracked, shipped
  `_data/fsr_reference.db` modified -- and in a wheel install the same code
  writes into `site-packages`.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks import _db


@pytest.fixture
def no_env(monkeypatch):
    """Resolution must be decided by the files, not an ambient override."""
    for var in ("FSRPB_DB", "FSRPB_CACHE_DB"):
        monkeypatch.delenv(var, raising=False)


# --- what counts as a usable DB ------------------------------------------------

def test_zero_byte_file_is_not_usable(tmp_path):
    """The exact artifact sqlite3.connect() leaves at a missing path."""
    p = tmp_path / "fsr_reference.db"
    p.touch()
    assert p.exists()                    # the check that was not enough
    assert not _db.is_usable_sqlite(p)


def test_non_sqlite_file_is_not_usable(tmp_path):
    p = tmp_path / "fsr_reference.db"
    p.write_text("not a database")
    assert not _db.is_usable_sqlite(p)


def test_missing_file_is_not_usable(tmp_path):
    assert not _db.is_usable_sqlite(tmp_path / "absent.db")


def test_a_real_sqlite_file_is_usable(tmp_path):
    p = tmp_path / "real.db"
    sqlite3.connect(p).execute("CREATE TABLE t (x)")
    assert _db.is_usable_sqlite(p)


def test_connect_alone_leaves_an_unusable_file(tmp_path):
    """Pins the mechanism, so the guard is not just asserting its own logic."""
    p = tmp_path / "fresh.db"
    sqlite3.connect(p).close()
    assert p.exists() and p.stat().st_size == 0
    assert not _db.is_usable_sqlite(p)


# --- resolution ----------------------------------------------------------------

def test_unusable_dev_cache_does_not_shadow_the_packaged_catalog(
        monkeypatch, tmp_path, no_env):
    stray = tmp_path / "fsr_reference.db"
    stray.touch()
    monkeypatch.setattr(_db, "REPO_PROBED_DB", stray)
    assert _db.default_db_path() == _db.PACKAGED_SLIM_DB


def test_a_usable_dev_cache_still_wins(monkeypatch, tmp_path, no_env):
    dev = tmp_path / "fsr_reference.db"
    sqlite3.connect(dev).execute("CREATE TABLE t (x)")
    monkeypatch.setattr(_db, "REPO_PROBED_DB", dev)
    assert _db.default_db_path() == dev


def test_env_override_wins_and_is_taken_verbatim(monkeypatch, tmp_path):
    """$FSRPB_DB is a deliberate choice -- not second-guessed for usability,
    so pointing at a DB you are about to create still works."""
    target = tmp_path / "scratch.db"
    monkeypatch.setenv("FSRPB_DB", str(target))
    assert _db.default_db_path() == target


# --- what may be written -------------------------------------------------------

def test_packaged_catalog_is_never_a_write_target(monkeypatch, tmp_path, no_env):
    stray = tmp_path / "fsr_reference.db"          # unusable -> resolves packaged
    stray.touch()
    monkeypatch.setattr(_db, "REPO_PROBED_DB", stray)
    assert _db.default_db_path() == _db.PACKAGED_SLIM_DB
    assert _db.writable_reference_db() is None


def test_dev_cache_is_a_write_target(monkeypatch, tmp_path, no_env):
    dev = tmp_path / "fsr_reference.db"
    sqlite3.connect(dev).execute("CREATE TABLE t (x)")
    monkeypatch.setattr(_db, "REPO_PROBED_DB", dev)
    assert _db.writable_reference_db() == dev


def test_runtime_cache_never_lands_on_the_packaged_catalog(
        monkeypatch, tmp_path, no_env):
    stray = tmp_path / "fsr_reference.db"
    stray.touch()
    monkeypatch.setattr(_db, "REPO_PROBED_DB", stray)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert _db.runtime_cache_db_path() != _db.PACKAGED_SLIM_DB


def test_runtime_cache_follows_a_writable_db(monkeypatch, tmp_path, no_env):
    """A dev/instance DB is writable and instance-scoped, so the cache stays
    with it rather than splitting across two files."""
    dev = tmp_path / "fsr_reference.db"
    sqlite3.connect(dev).execute("CREATE TABLE t (x)")
    monkeypatch.setattr(_db, "REPO_PROBED_DB", dev)
    assert _db.runtime_cache_db_path() == dev
