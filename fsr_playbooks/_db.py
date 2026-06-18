"""Locate the reference database.

Resolution order (first hit wins):

1. ``$FSRPB_DB`` — explicit override (e.g. a warmed, instance-specific DB).
2. ``<repo>/data/fsr_reference.db`` — the in-repo probed cache (dev: full ~65 MB,
   gitignored). Present only in a source checkout.
3. ``fsr_playbooks/_data/fsr_reference.db`` — the packaged slim catalog shipped in
   the wheel. Stable tables only (step types/handlers, jinja, recipes, api
   endpoints); the per-install tables (connectors/operations/picklists/modules)
   ship empty.

A fresh ``pip install fsr_playbooks`` has only (3): enough to compile playbooks
that reference solely the stable catalog. A playbook that references a live
connector op / picklist / module needs ``warmup`` against a target SOAR to fill
those tables first — until then the resolver reports a clear ``CompileError``
(it does NOT fall back to a live lookup).
"""
from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
#: Slim catalog shipped inside the wheel (package-data).
PACKAGED_SLIM_DB = _PKG_DIR / "_data" / "fsr_reference.db"
#: Full probed cache in a source checkout (repo root is the package's parent).
REPO_PROBED_DB = _PKG_DIR.parent / "data" / "fsr_reference.db"


def default_db_path() -> Path:
    """Return the reference DB to use, honoring ``$FSRPB_DB`` then dev/packaged.

    Always returns a ``Path`` (never ``None``); the chosen path may not exist if
    neither a probed nor a packaged DB is available, so callers that need a live
    connection should still handle a missing file.
    """
    env = os.environ.get("FSRPB_DB")
    if env:
        return Path(env)
    if REPO_PROBED_DB.exists():
        return REPO_PROBED_DB
    return PACKAGED_SLIM_DB
