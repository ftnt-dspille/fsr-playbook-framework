"""An upsert with nothing to match on inserts a new record every run.

`/api/3/upsert/<m>` reconciles duplicates by the module's UNIQUE CONSTRAINT --
`sourceId` on alerts, `cVEID` on CVEs. Omit those columns from the payload and
there is no natural key to match against, so every run INSERTS.

This is worth a compile-time check because of how it presents. Nothing errors,
the run is green, and the records look almost right -- each one carrying
whatever that single run wrote. Diagnosed from the outside it reads as "the
update isn't applying" or "tags aren't appending", which sends you looking at
merge semantics rather than at a field that isn't there. Found exactly that way
on a live box: three identical alerts, one tag each, from a playbook whose
upsert never set `sourceId`.

Warned, never blocked -- the constraint may be satisfied by a Jinja value the
compiler cannot see through -- and SILENT whenever the catalog cannot answer,
because a check that fires on missing catalog data teaches authors to ignore it.
"""
from __future__ import annotations

import json
import shutil
import sqlite3

import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

# The resolved catalog, not the gitignored dev cache: CI has only the packaged one.
_REFERENCE_DB = str(default_db_path())


@pytest.fixture
def db_with_constraints(tmp_path):
    """A catalog that knows alerts dedupe on `sourceId`."""
    db = tmp_path / "catalog.db"
    shutil.copy(_REFERENCE_DB, db)
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(modules)").fetchall()}
    if "unique_constraint" not in cols:
        conn.execute("ALTER TABLE modules ADD COLUMN unique_constraint TEXT")
    conn.execute("UPDATE modules SET unique_constraint = ? WHERE name = ?",
                 (json.dumps(["sourceId"]), "alerts"))
    conn.commit()
    conn.close()
    return str(db)


def _compile(extra: str, db: str):
    return compile_yaml(f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        module: alerts
        button_label: B
        next: C
      - name: C
        type: create_record
        module: alerts
        is_upsert: true
        fields:
          name: "x"
{extra}""", db)


def _warnings(extra: str, db: str) -> list[str]:
    return [e.message for e in _compile(extra, db).errors
            if e.severity == "warning" and "natural key" in e.message]


def test_upsert_without_the_natural_key_warns(db_with_constraints):
    warns = _warnings("", db_with_constraints)
    assert warns, "expected a warning about the missing natural key"
    assert "sourceId" in warns[0]


def test_upsert_with_the_natural_key_is_quiet(db_with_constraints):
    assert not _warnings('          sourceId: "abc"\n', db_with_constraints)


def test_a_jinja_natural_key_is_accepted(db_with_constraints):
    # The compiler cannot evaluate it, and refusing to accept it would make
    # the check unusable for every real intake.
    assert not _warnings('          sourceId: "{{ vars.item.id }}"\n',
                         db_with_constraints)


def test_the_warning_does_not_block(db_with_constraints):
    assert _compile("", db_with_constraints).ok


def test_plain_create_is_never_warned_about(db_with_constraints):
    # Without the upsert endpoint there is no dedup being attempted, so a
    # missing sourceId is simply a field the author chose not to set.
    r = compile_yaml("""
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        module: alerts
        button_label: B
        next: C
      - name: C
        type: create_record
        module: alerts
        fields:
          name: "x"
""", db_with_constraints)
    assert not [e for e in r.errors if "natural key" in e.message]


def test_silent_when_the_column_is_absent(tmp_path):
    # An older catalog, warmed before the column existed. It cannot say whether
    # a natural key is missing, so it must not imply one is.
    db = tmp_path / "old.db"
    shutil.copy(_REFERENCE_DB, db)
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(modules)").fetchall()}
    if "unique_constraint" in cols:
        conn.execute("ALTER TABLE modules DROP COLUMN unique_constraint")
    conn.commit()
    conn.close()
    assert not _warnings("", str(db))


def test_silent_when_the_module_records_no_constraint(tmp_path):
    # Warmed catalog, but this module genuinely has no unique constraint --
    # every create is meant to be a new record, so there is nothing to warn on.
    db = tmp_path / "nokey.db"
    shutil.copy(_REFERENCE_DB, db)
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(modules)").fetchall()}
    if "unique_constraint" not in cols:
        conn.execute("ALTER TABLE modules ADD COLUMN unique_constraint TEXT")
    conn.execute("UPDATE modules SET unique_constraint = NULL WHERE name = ?",
                 ("alerts",))
    conn.commit()
    conn.close()
    assert not _warnings("", str(db))


def test_the_warmed_reference_catalog_can_answer():
    # Guards the backfill itself: if the catalog loses the column or the data,
    # the check silently stops working and every test above still passes
    # because they build their own DB.
    #
    # Only a WARMED catalog carries the data. The packaged slim catalog (all CI
    # has) is not warmed, so the check is dormant there until the modules probe
    # runs on a box -- skip for exactly that file, assert for any other.
    from pathlib import Path

    from fsr_playbooks._db import PACKAGED_SLIM_DB
    if Path(_REFERENCE_DB).resolve() == PACKAGED_SLIM_DB.resolve():
        pytest.skip("packaged slim catalog is not warmed with modules.unique_constraint")
    assert _warnings("", _REFERENCE_DB), (
        "reference catalog has no natural key for alerts -- re-warm it "
        "(tooling/cli.py probe modules) or the check is dormant"
    )
