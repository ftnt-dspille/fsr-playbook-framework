"""Locate the reference database.

Resolution order (first hit wins):

1. ``$FSRPB_DB`` — explicit override (e.g. a warmed, instance-specific DB).
2. ``<repo>/data/fsr_reference.db`` — the in-repo probed cache (dev: full ~65 MB,
   gitignored). Present only in a source checkout.
3. ``fsr_playbooks/_data/fsr_reference.db`` — the packaged slim catalog shipped in
   the wheel. Stable tables only (step types/handlers, jinja, recipes, api
   endpoints, plus the ``modules`` *name* catalog — module type names are
   globally stable for an FSR version and carry no per-install UUIDs); the
   UUID-bearing per-install tables (connectors/operations/picklists) ship empty.

A fresh ``pip install fsr_playbooks`` has (3): enough to compile playbooks that
reference solely the stable catalog AND to validate/canonicalize module names
offline (e.g. ``Alerts`` → ``alerts``). A playbook that references a live
connector op / picklist needs ``warmup`` against a target SOAR (which sources
the data through pyfsr) to fill those tables first — until then the resolver
reports a clear ``CompileError`` (it does NOT fall back to a live lookup).
``warmup`` also overwrites the baseline ``modules`` catalog with the target's
own set, picking up any custom modules.
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


class WarmupClobberGuard(RuntimeError):
    """Raised when a warmup/box-sync write would clobber the dev cache."""


def warmup_write_path() -> Path:
    """Resolve where a *warmup* (box-catalog sync) may write, with a guard.

    Warmup replaces the reference DB's connector/operation tables with a target
    SOAR's *installed* catalog. Run in a source checkout with ``$FSRPB_DB``
    unset, that write lands on ``REPO_PROBED_DB`` — the full dev corpus — and a
    small box (e.g. 21 connectors) silently overwrites hundreds, reddening the
    tooling gate and degrading the compiler's grounding. This has bitten us.

    So warmup must NOT default to the canonical dev cache. Callers that sync a
    box catalog should resolve their write target through this function instead
    of ``default_db_path()``:

      * ``$FSRPB_DB`` set  → write there (a scratch/instance DB — the right habit);
      * otherwise          → refuse, unless ``$FSRPB_ALLOW_DEV_DB_CLOBBER=1`` is
        set to deliberately rebuild the dev cache in place.

    Read paths are unaffected — they keep using ``default_db_path()``.
    """
    env = os.environ.get("FSRPB_DB")
    if env:
        return Path(env)
    if os.environ.get("FSRPB_ALLOW_DEV_DB_CLOBBER") == "1":
        return REPO_PROBED_DB
    raise WarmupClobberGuard(
        "refusing to warmup-write the dev cache "
        f"({REPO_PROBED_DB}): a box sync would clobber the full reference "
        "corpus. Set FSRPB_DB to a scratch copy first (recommended), or "
        "FSRPB_ALLOW_DEV_DB_CLOBBER=1 to rebuild the dev cache in place."
    )
