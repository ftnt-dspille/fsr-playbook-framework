#!/usr/bin/env python3
"""Rewrite internal infra strings out of a committed sqlite reference DB.

The reference DBs are assembled from a dev cache that is itself synced from a
live lab appliance, so live URLs ride along into anything built from it:
`playbook_steps.source_path` alone carried 7,000+ live appliance URLs into the
public mirror. This is the counterpart to `check_infra_leaks.py` -- the guard
refuses them, this removes the ones already there. Both read their patterns
from the same gitignored overlay, so neither states a lab host itself.

Two things make a naive scrub insufficient, and both are handled here:

* **Free pages.** sqlite does not zero a deleted row; the bytes stay in the
  file until the space is reused. A DB can therefore scan dirty on its raw
  bytes while every live cell is clean, so the rewrite ends with VACUUM to
  rebuild the file and drop the residue.
* **Framing.** The verification pass reads raw bytes rather than cell values,
  because that is the only view that sees free pages -- and it is the same
  check the pre-commit guard applies, so "scrubbed" and "will pass the guard"
  cannot drift apart.

Run standalone, or import `scrub()` from a fixture builder to make regeneration
self-cleaning:

    python scripts/scrub_infra_from_db.py path/to.db [--dry-run]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_infra_leaks import overlay_replacements, scan_blob  # noqa: E402

# The pattern/replacement pairs live in the gitignored overlay
# (`scripts/infra_patterns.local.json`, key `replace`) alongside the deny
# patterns they answer. They used to be hardcoded here -- which meant this
# script, whose job is to keep lab hosts off the public mirror, was itself
# publishing the lab subnet, the appliance domain, and the admin account name
# on every clone. Templates are ordinary `re.sub` replacements, so a captured
# group (e.g. a preserved last octet, which keeps distinct fixture appliances
# distinct rather than collapsing them onto one address) rides through as `\1`.
#
# Empty without the overlay: nothing local is named, so there is nothing to
# rewrite. `scrub()` says so rather than reporting a clean run it did not do.
REPLACEMENTS = overlay_replacements()


def _rewrite(s: str) -> str:
    for rx, template in REPLACEMENTS:
        s = rx.sub(template, s)
    return s


def _text_columns(db: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]


def scrub(path: str | Path, *, dry_run: bool = False, quiet: bool = False) -> int:
    """Rewrite infra strings in every text cell. Returns the cells changed."""
    path = Path(path)
    if not REPLACEMENTS:
        # Silence here would read as "scrubbed, nothing found" on a clone where
        # the overlay is simply absent -- the one case where the scrub is a
        # no-op for a reason that has nothing to do with the file's contents.
        raise SystemExit(
            "no replacement patterns loaded: scripts/infra_patterns.local.json "
            "is missing or has no 'replace' key. Nothing was scrubbed.")
    db = sqlite3.connect(path)
    db.text_factory = str
    changed = 0

    # FTS5 virtual tables and the shadow tables behind them (<name>_data/_idx/
    # _docsize/_config/_content) are derived storage, not source of truth. The
    # ones here are declared `content=''` -- contentless, so they hold tokenized
    # postings and never the original text, cannot be UPDATEd, and split an
    # address on punctuation so it is never contiguous to begin with (a MATCH
    # for a lab IP returns 0 rows). Scrubbing the base tables is what matters;
    # the raw-byte verification at the end is what proves it.
    virtual = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE sql LIKE 'CREATE VIRTUAL TABLE%'")]
    shadow = tuple(f"{v}_" for v in virtual)

    tables = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")]
    tables = [t for t in tables
              if t not in virtual and not t.startswith(shadow)]
    for table in tables:
        # WITHOUT ROWID tables have no rowid to address a row by; none exist in
        # these DBs today, but fail loudly rather than silently skipping them.
        has_rowid = True
        try:
            db.execute(f'SELECT rowid FROM "{table}" LIMIT 1').fetchone()
        except sqlite3.OperationalError:
            has_rowid = False
        if not has_rowid:
            raise SystemExit(
                f"{table!r} is WITHOUT ROWID; scrub cannot address its rows. "
                "Add an explicit key path before regenerating.")

        for col in _text_columns(db, table):
            rows = db.execute(
                f'SELECT rowid, "{col}" FROM "{table}" WHERE typeof("{col}")=\'text\''
            ).fetchall()
            for rowid, val in rows:
                new = _rewrite(val)
                if new != val:
                    changed += 1
                    if not dry_run:
                        db.execute(
                            f'UPDATE "{table}" SET "{col}"=? WHERE rowid=?',
                            (new, rowid))
            if not dry_run:
                db.commit()

    if dry_run:
        db.close()
        if not quiet:
            print(f"{path.name}: {changed} cell(s) would change (dry run)")
        return changed

    db.commit()
    # Rebuild the file so deleted/overwritten rows stop lingering in free pages.
    db.execute("VACUUM")
    db.commit()
    db.close()

    residue = scan_blob(path.read_bytes())
    if residue:
        raise SystemExit(
            f"{path}: still dirty after scrub + VACUUM: {', '.join(residue)}\n"
            "A pattern in BINARY_DENY has no REPLACEMENTS entry, or the value "
            "lives somewhere the cell walk does not reach.")
    if not quiet:
        print(f"{path.name}: scrubbed {changed} cell(s); raw-byte scan clean")
    return changed


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 2
    dry = "--dry-run" in argv
    for p in args:
        scrub(p, dry_run=dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
