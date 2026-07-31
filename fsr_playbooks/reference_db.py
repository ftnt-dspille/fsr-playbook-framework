"""Health checks for the reference store (`fsr_reference.db`).

The reference DB is the compiler's entire knowledge of the world: connectors,
their operations, operation parameters, picklists. Every lookup the resolver
makes goes through it.

Its failure mode is silence. An empty or truncated DB does not raise -- it just
answers "no such connector" to everything, so:

  * `validate_yaml` returns `{"ok": True, "errors": []}` for genuinely broken
    YAML, because there is no catalog to check against;
  * or every step trips `unknown_connector`, which reads like the playbook is
    wrong rather than the environment.

Both look like product bugs and neither points at the DB. Worse, `sqlite3
.connect()` CREATES an empty file for a path that does not exist, so a typo in
a path or a missing vendor step manufactures a perfectly valid, perfectly empty
reference store on the spot.

This module makes that state nameable and checkable, so callers can fail loudly
instead of quietly producing wrong answers.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Tables whose emptiness makes the compiler blind. `picklists` is deliberately
# NOT here: a valid store can have none.
_CORE_TABLES = ("connectors", "operations")


@dataclass(frozen=True)
class ReferenceDbHealth:
    """What we can say about a candidate reference store."""

    path: Path
    exists: bool
    is_reference_db: bool          # has the expected schema at all
    counts: dict                   # table -> row count (empty if unreadable)
    error: str = ""

    @property
    def populated(self) -> bool:
        """True when every core table has at least one row."""
        if not (self.exists and self.is_reference_db):
            return False
        return all(self.counts.get(t, 0) > 0 for t in _CORE_TABLES)

    @property
    def summary(self) -> str:
        if not self.exists:
            return f"reference DB missing: {self.path}"
        if self.error:
            return f"reference DB unreadable ({self.path}): {self.error}"
        if not self.is_reference_db:
            return (f"not a reference DB (no connectors/operations tables): "
                    f"{self.path}")
        counts = ", ".join(f"{t}={self.counts.get(t, 0)}" for t in _CORE_TABLES)
        state = "populated" if self.populated else "EMPTY/SLIM"
        return f"reference DB {state} ({counts}): {self.path}"


def health(db_path) -> ReferenceDbHealth:
    """Inspect a reference store without creating or modifying it."""
    path = Path(db_path)
    if not path.exists():
        return ReferenceDbHealth(path=path, exists=False,
                                 is_reference_db=False, counts={})
    # `mode=ro` so a health check can never conjure the very file it is
    # checking for -- the failure mode this module exists to catch.
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        return ReferenceDbHealth(path=path, exists=True, is_reference_db=False,
                                 counts={}, error=str(e))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(_CORE_TABLES).issubset(names):
            return ReferenceDbHealth(path=path, exists=True,
                                     is_reference_db=False, counts={})
        counts = {}
        for t in _CORE_TABLES:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
        return ReferenceDbHealth(path=path, exists=True, is_reference_db=True,
                                 counts=counts)
    except sqlite3.Error as e:
        return ReferenceDbHealth(path=path, exists=True, is_reference_db=False,
                                 counts={}, error=str(e))
    finally:
        conn.close()


class ReferenceDbError(RuntimeError):
    """A reference store is missing, malformed, or empty."""


def require_populated(db_path) -> ReferenceDbHealth:
    """Return the health, or raise with an actionable message.

    Use at the top of anything that would otherwise produce confidently wrong
    output against an empty catalog (test suites, CLI entry points). Do NOT use
    on the in-platform runtime path: a freshly deployed connector legitimately
    ships a slim DB and populates it on first warmup, so there the empty state
    is expected and transient.
    """
    h = health(db_path)
    if h.populated:
        return h
    raise ReferenceDbError(
        f"{h.summary}\n"
        f"The compiler resolves connectors/operations from this file; empty "
        f"means every lookup silently misses, so broken YAML can validate "
        f"clean.\n"
        f"Fix: point FSR_REFERENCE_DB at a populated store, or re-vendor the "
        f"full one (a deploy build slims it on purpose)."
    )
