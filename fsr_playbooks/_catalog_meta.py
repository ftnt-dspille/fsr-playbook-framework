"""Catalog provenance & freshness metadata — the ``_catalog_meta`` table.

The offline compiler reads a cached reference DB (see :mod:`fsr_playbooks._db`).
That cache is *warmed* from one specific live SOAR. Two failure classes follow:

1. **Cross-instance mistakes** — compiling against a catalog warmed from a
   *different* SOAR. Instance A's picklist IRIs / connector configs mis-resolve
   on B, producing a playbook that looks valid but silently misbehaves. Today
   this is a silent-wrong-answer class.
2. **Staleness** — the live SOAR drifts (a publish adds a module/field, a
   picklist value is edited) after the catalog was warmed.

``_catalog_meta`` is a small key/value table that records *where* and *when* the
catalog was warmed so both classes become detectable. It is the **current
state** used by freshness checks; ``_probe_runs`` remains the per-run audit log.

Keys written by :func:`stamp_instance` and the freshness probes:

==========================  ==============================================
key                         meaning
==========================  ==============================================
``instance_label``          human label of the warmed instance (e.g. ``dev``)
``base_url``                normalized base URL the catalog was warmed from
``base_url_hash``           short hash of ``base_url`` (cheap identity check)
``fsr_version``             ``GET /api/version`` build at warm time (Tier-0)
``last_publish_time``       ``GET /api/publish/error`` epoch (Tier-1 watermark)
``structural_warmed_at``    ISO-8601 UTC of the last Tier-1 warm
``data_warmed_at``          ISO-8601 UTC of the last Tier-2 warm
``count:<coll>``            ``$limit=0`` ``hydra:totalItems`` per collection
``etag:<coll>``             last seen response ETag per collection
``schema_version``          ``_catalog_meta`` layout version
==========================  ==============================================

This module ships in the wheel: the multi-instance guard runs at *compile*
time, so the read side must live in the package, not in dev-only ``tooling/``.
It has no third-party dependencies and never hits the network.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = "1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create ``_catalog_meta`` if absent. Safe on shipped/already-built DBs."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _catalog_meta ("
        "  key        TEXT PRIMARY KEY,"
        "  value      TEXT,"
        "  updated_at TEXT NOT NULL)"
    )


def get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    try:
        row = conn.execute(
            "SELECT value FROM _catalog_meta WHERE key = ?", (key,)
        ).fetchone()
    except sqlite3.OperationalError:
        # Table absent on an old/slim DB — treat as unstamped.
        return default
    if row is None:
        return default
    return row[0]


def get_all(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        rows = conn.execute("SELECT key, value FROM _catalog_meta").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r[0]: r[1] for r in rows}


def set_(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    ensure_table(conn)
    conn.execute(
        "INSERT INTO _catalog_meta (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, value, _utcnow()),
    )


# ----------------------- instance identity -----------------------

def normalize_base_url(url: str) -> str:
    """Canonicalize a base URL for stable identity comparison.

    Lowercases the host, drops the scheme and any trailing slash. Two configs
    that differ only by ``http`` vs ``https`` or a trailing ``/`` are the same
    instance for catalog purposes.
    """
    u = (url or "").strip()
    for prefix in ("https://", "http://"):
        if u.lower().startswith(prefix):
            u = u[len(prefix):]
            break
    return u.rstrip("/").lower()


def base_url_hash(url: str) -> str:
    return hashlib.sha256(normalize_base_url(url).encode()).hexdigest()[:16]


def stamp_instance(
    conn: sqlite3.Connection,
    *,
    instance_label: str | None,
    base_url: str,
    fsr_version: str | None = None,
    last_publish_time: str | int | None = None,
) -> None:
    """Record which instance (and version/watermark) the catalog was warmed
    from. Called by the Tier-1 structural warmup (``probe_modules`` et al.)."""
    ensure_table(conn)
    set_(conn, "instance_label", instance_label or "")
    set_(conn, "base_url", normalize_base_url(base_url))
    set_(conn, "base_url_hash", base_url_hash(base_url))
    set_(conn, "schema_version", SCHEMA_VERSION)
    set_(conn, "structural_warmed_at", _utcnow())
    if fsr_version is not None:
        set_(conn, "fsr_version", str(fsr_version))
    if last_publish_time is not None:
        set_(conn, "last_publish_time", str(last_publish_time))


def record_count(conn: sqlite3.Connection, collection: str, total: int) -> None:
    set_(conn, f"count:{collection}", str(total))


def record_etag(conn: sqlite3.Connection, collection: str, etag: str) -> None:
    set_(conn, f"etag:{collection}", etag)


def record_data_warmed_at(conn: sqlite3.Connection) -> None:
    """Record the current UTC timestamp as the last Tier-2 warm time."""
    set_(conn, "data_warmed_at", _utcnow())


# ----------------------- the multi-instance guard -----------------------

def check_instance(conn: sqlite3.Connection, base_url: str) -> tuple[str, str, str]:
    """Compare ``base_url`` against the instance the catalog was warmed from.

    Returns ``(status, stamped_label, stamped_hash)`` where status is one of:

    - ``"ok"``        — the catalog was warmed from this instance.
    - ``"mismatch"``  — warmed from a *different* instance (silent-wrong risk).
    - ``"unstamped"`` — catalog carries no instance stamp (slim/unwarmed DB);
                        nothing to validate against, so callers pass silently.
    """
    stamped_hash = get(conn, "base_url_hash") or ""
    stamped_label = get(conn, "instance_label") or ""
    if not stamped_hash:
        return "unstamped", stamped_label, stamped_hash
    if base_url_hash(base_url) == stamped_hash:
        return "ok", stamped_label, stamped_hash
    return "mismatch", stamped_label, stamped_hash


def instance_guard(conn: sqlite3.Connection, errors: list) -> None:
    """Append a compile diagnostic if the configured target instance differs
    from the one the catalog was warmed from.

    The intended target is read from ``$FSR_BASE_URL`` (the same var the warmup
    tooling uses). When it is unset there is no "intended" instance to compare
    against, so this is a no-op — offline compiles stay clean. When set:

    - mismatch → a *warning* by default (the author may genuinely intend to
      compile portable, stable-only playbooks), escalated to a blocking *error*
      when ``$FSRPB_STRICT_INSTANCE`` is truthy.
    - unstamped catalog → silent (no basis to complain).

    Imported lazily by the resolver so this module stays free of compiler deps.
    """
    target = os.environ.get("FSR_BASE_URL", "").strip()
    if not target:
        return
    status, label, _ = check_instance(conn, target)
    if status != "mismatch":
        return
    from .compiler.errors import CompileError, ErrorCode

    strict = (os.environ.get("FSRPB_STRICT_INSTANCE", "") or "").strip().lower() \
        in ("1", "true", "yes", "on")
    warmed_from = f" (warmed from {label!r})" if label else ""
    errors.append(CompileError(
        code=ErrorCode.INSTANCE_MISMATCH,
        message=(
            f"reference catalog was warmed from a DIFFERENT SOAR{warmed_from} "
            f"than the configured target {normalize_base_url(target)!r}; "
            f"picklist IRIs / connector configs may mis-resolve"
        ),
        path="",
        suggestion="re-run warmup against the target instance, "
                   "or unset FSR_BASE_URL to compile stable-only",
        severity="error" if strict else "warning",
    ))
