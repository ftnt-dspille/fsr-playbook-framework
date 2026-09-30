"""The reference store must not change while it is being measured (#139).

`data/fsr_reference.db` is the pinned substrate an eval run is scored against.
`make doctor` gates on it, and the whole argument of #128 is that numbers taken
against a bad store are void -- so a store that MUTATES during the run it is
measuring is not pinned, and two runs of the same fixture are not comparable.

It really did mutate: the store's md5 changed mid-run on 2026-08-15
(`b411f188…` -> `fdd5af49…`). The writer was the `connector_op_defs` cache in
`tools_execution`, which opened `DB_PATH` read-write while every other reader
opens the same file `mode=ro`. In a source checkout `runtime_cache_db_path()`
deliberately resolves to that same DB -- it is writable and instance-scoped, so
by design it keeps taking runtime caches -- which is why redirecting the cache
inside `tools_execution` alone does NOT fix this. `offline.install()` has to
divert the cache for the duration of the run.

This store also has a corruption history (three times in three days), so any
extra writer is worth keeping out on those grounds alone.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "fsr_reference.db"


def _digest(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_op_defs_table() -> bool:
    conn = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='connector_op_defs'").fetchone() is not None
    finally:
        conn.close()


@pytest.fixture
def _clean_env(monkeypatch):
    monkeypatch.delenv("FSRPB_CACHE_DB", raising=False)
    return monkeypatch


def test_offline_install_diverts_the_runtime_cache_off_the_store(_clean_env):
    """`offline.install()` must point mutable caches somewhere else."""
    from evals import offline

    saved = offline.install()
    try:
        chosen = os.environ.get("FSRPB_CACHE_DB")
        assert chosen, "offline.install() left the runtime cache unset"
        assert Path(chosen).resolve() != STORE.resolve(), (
            "the runtime cache still resolves to the reference store; an eval "
            "run would write to the substrate it is being measured against")
    finally:
        offline.uninstall(saved)


@pytest.mark.skipif(not STORE.exists(), reason="no probed reference DB here")
def test_caching_op_defs_does_not_touch_the_reference_store(_clean_env):
    """The op-def cache round-trip must not land in the reference store.

    Exercises the read path too: `_op_defs_table` is DDL that runs on a cache
    LOOKUP, so a miss wrote to the store just as surely as a store did.

    Asserts on the ROW this test writes, not only that the digest held. The
    digest alone is a weak gate here and was observed passing while the fix was
    disabled: the store is WAL-mode, so a write lands in `-wal` and the `.db`
    file's bytes do not move until a checkpoint. A SELECT does see the `-wal`,
    so the row check is deterministic; the digest rides along as a second
    opinion.

    Not on the table's absence: outside an eval run a source checkout caches
    into the store BY DESIGN, so any dev store the Studio has ever served
    already holds `connector_op_defs`. Asserting absence made this test fail
    forever on such a store while the diversion was working. The table is
    still required to stay absent when it was absent to begin with -- that is
    what catches the lookup-path DDL.
    """
    from evals import offline

    saved = offline.install()
    try:
        from fsr_playbooks.mcp_server import tools_execution as te

        had_table = _has_op_defs_table()
        before = _digest(STORE)
        te._cached_op_defs("acme-widgets", "1.0.0")          # read path
        te._store_op_defs("acme-widgets", "1.0.0",
                          [{"operation": "noop", "title": "No op"}])
        assert te._cached_op_defs("acme-widgets", "1.0.0"), \
            "cache round-trip did not come back -- the diversion broke it"

        if not had_table:
            assert not _has_op_defs_table(), (
                "`connector_op_defs` was created in the reference store: the "
                "runtime cache is still writing to the substrate evals are "
                "measured against")
        else:
            conn = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
            try:
                landed = conn.execute(
                    "SELECT 1 FROM connector_op_defs "
                    "WHERE connector='acme-widgets'").fetchone()
            finally:
                conn.close()
            assert landed is None, (
                "the op-def cache wrote its row into the reference store: the "
                "runtime cache is still writing to the substrate evals are "
                "measured against")
        assert _digest(STORE) == before, (
            "the reference store changed while the op-def cache was used")
    finally:
        offline.uninstall(saved)


@pytest.mark.skipif(not STORE.exists(), reason="no probed reference DB here")
def test_the_reference_store_is_intact():
    """A corrupt store makes every eval number void -- fail loudly, not later.

    `make doctor` checks this too, but a test run that quietly scores against a
    damaged store is exactly how `find_operation` intermittently raising got
    read as the agent being unable to find operations that exist.
    """
    conn = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok", (
            "reference DB is malformed -- restore with `make db-restore` "
            "(never a plain `cp`: it is WAL-mode, and a stale -wal/-shm "
            "replays into the fresh file on the next open)")
    finally:
        conn.close()
