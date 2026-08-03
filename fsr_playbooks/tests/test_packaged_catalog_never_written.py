"""An ordinary test run must leave the packaged slim catalog byte-identical.

`_db.writable_reference_db()` exists precisely so opportunistic enrichment
writes never land on `fsr_playbooks/_data/fsr_reference.db`: in a checkout that
dirties a tracked file, and in a wheel install it writes into site-packages.
Its docstring says a `None` return means "skip the write".

`_persist_precheck_verification` did not ask. It wrote to `_shared.DB_PATH`
directly and wrapped the whole thing in `except Exception: pass`, so the write
was both wrong and silent. The visible damage was not corruption -- the rows
are logically identical, only a `ts` column moved -- but every run rewrote the
tracked DB, which made pre-commit report "files were modified by this hook" and
blocked every commit in the repo. The swallowed exception is why nothing
surfaced: making the file read-only produced no error, just no write.

Guarding the property (the file does not change) rather than the mechanism,
so any future writer that forgets the guard is caught too.
"""
from __future__ import annotations

import hashlib
import pathlib

from fsr_playbooks._db import PACKAGED_SLIM_DB, writable_reference_db


def _digest() -> str:
    return hashlib.sha256(pathlib.Path(PACKAGED_SLIM_DB).read_bytes()).hexdigest()


def test_precheck_verification_does_not_touch_the_packaged_catalog():
    from fsr_playbooks.mcp_server.tools_picklists import _persist_precheck_verification

    before = _digest()
    # Both branches that produce a row: ok True -> tested_pass, False -> tested_fail.
    _persist_precheck_verification(
        "picklist", "AlertStatus:Open", "reference_db", {"ok": True},
    )
    _persist_precheck_verification(
        "picklist", "AlertStatus:Nope", "reference_db",
        {"ok": False, "code": "not_a_value", "message": "nope"},
    )
    assert _digest() == before, (
        "the packaged catalog was modified by a verification write"
    )


def test_writable_reference_db_is_none_when_it_resolves_to_the_package():
    # The guard the writers depend on. If default_db_path() resolves to a dev
    # cache instead, this is vacuous -- and so is the test above -- so assert
    # the contract rather than the environment.
    target = writable_reference_db()
    assert target is None or pathlib.Path(target) != pathlib.Path(PACKAGED_SLIM_DB)
