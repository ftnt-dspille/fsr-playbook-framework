"""Shared helpers for probes.

Probes are idempotent: drop+repopulate the tables they own per run, then write
an `_probe_runs` audit row. Use `probe_session()` as a context manager.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
STORE_DIR = REPO_ROOT / "data"
DB_PATH = STORE_DIR / "fsr_reference.db"
SCHEMA_PATH = STORE_DIR / "schema.sql"

import os

# External DB we ATTACH read-only for enrichment (cross-vendor API examples
# + extracted FortiSOAR connector method bodies). Env override
# `FSRPB_API_CATALOG` lets a deploy point at a different file without
# editing code. Default tracks the current location under
# `Miscellaneous/fortisoar/corpus_builder/` (moved 2026-05 from
# `Miscellaneous/api_examples_catalog/`).
CATALOG_DB_PATH = Path(os.environ.get("FSRPB_API_CATALOG") or (
    Path.home()
    / "PycharmProjects"
    / "Miscellaneous"
    / "fortisoar"
    / "corpus_builder"
    / "catalog.sqlite"
))

# Canonical source roots for the probes. Kept here so a single edit moves all
# probes if a directory is renamed.
RPM_EXTRACTED_DIR = (
    Path.home()
    / "PycharmProjects"
    / "Miscellaneous"
    / "fortisoar"
    / "corpus_builder"
    / "repos"
    / "fortisoar-rpm-extracted"
)
SCHEMA_JSON_PATH = (
    Path.home() / "PycharmProjects" / "Miscellaneous" / "fortisoar" / "schema.json"
)
FSR_SCHEMA_TS_PATH = (
    Path.home() / "PycharmProjects" / "FSRPlaybookConversion" / "fsr-schema.ts"
)
PB_EXAMPLES_GLOB = "pb_examples/**/*.json"  # resolved by callers

# Modules in scope for v1 (Phase 0 lock).
IN_SCOPE_MODULES = {"threat_intel_feeds", "indicators", "alerts", "incidents"}


def open_db(create: bool = True) -> sqlite3.Connection:
    """Open the reference DB, applying schema.sql on first use."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    fresh = create and not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if fresh:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    # Always attach catalog read-only when present; probes can ignore if not needed.
    if CATALOG_DB_PATH.exists():
        conn.execute(
            f"ATTACH DATABASE '{CATALOG_DB_PATH}' AS catalog"  # noqa: S608 - fixed path
        )
    return conn


@contextmanager
def probe_session(probe_name: str, source_paths: Iterable[Path], version: str = "1"):
    """Context manager: opens DB, yields conn, records `_probe_runs` row on success."""
    conn = open_db()
    try:
        yield conn
        row_counts = _row_counts_for(conn, probe_name)
        conn.execute(
            "INSERT INTO _probe_runs (probe_name, ts, source_paths, row_counts, version) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                probe_name,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                json.dumps([str(p) for p in source_paths]),
                json.dumps(row_counts),
                version,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# Each probe declares the tables it owns so we can both wipe-on-rerun and
# report row counts in `_probe_runs`.
PROBE_TABLES: dict[str, tuple[str, ...]] = {
    "probe_step_types": ("step_types", "step_examples"),
    "probe_connectors": ("connectors", "operations", "operation_params", "operation_examples"),
    "probe_modules": ("modules", "module_fields", "picklists"),
    "probe_connector_configs": ("connector_configs",),
    "probe_jinja": ("jinja_macros", "jinja_context_vars"),
    # 'probe_jinja' is the live name; alias retained for any old refs.
    "probe_playbook_patterns": ("recipes", "playbooks_seen"),
    "probe_api_endpoints": ("api_endpoints", "api_endpoint_params", "api_endpoint_examples"),
    "probe_playbooks": ("step_types", "step_examples", "playbooks_seen", "recipes"),
    "probe_jinja_backend": ("jinja_globals", "jinja_tests"),
    "probe_step_handlers": ("step_handlers",),
    # probe_playbook_constraints owns no permanent rows — only writes
    # verification records — so it has an empty table tuple.
    "probe_playbook_constraints": (),
    "probe_cleanup": (),
    "probe_jinja_corpus": ("jinja_expressions", "jinja_filter_usage"),
    "probe_playbook_steps": ("playbook_steps",),
    "probe_op_safety": ("op_safety",),
    # probe_param_types UPDATEs columns on operation_params in place,
    # plus owns the param_type_probes ledger. We don't wipe the ledger
    # on every run — Phase 2.2 re-runs are deliberately incremental.
    "probe_param_types": (),
}


def wipe_probe_tables(conn: sqlite3.Connection, probe_name: str) -> None:
    for table in PROBE_TABLES[probe_name]:
        conn.execute(f"DELETE FROM {table}")
    # FTS rows tagged with kind owned by this probe get cleared by the probe
    # itself when it rewrites them — keep that explicit, not magical here.


def record_verification(
    conn: sqlite3.Connection,
    kind: str,
    key: str,
    method: str,
    status: str = "seen",
    notes: str | None = None,
) -> None:
    """Record a verification fact.

    Reminder: anything sourced from a local file (rpm info.json, schema.json,
    fsr-schema.ts, widget constants) is `status='seen'` — it does NOT count as
    trusted. Only live_* / playbook_e2e methods with status='tested_pass' make
    an entity trusted in `v_verification_state`.
    """
    conn.execute(
        "INSERT OR REPLACE INTO verifications (kind, key, method, status, ts, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            kind,
            key,
            method,
            status,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            notes,
        ),
    )


def conditional_refetch(
    client,
    *,
    url: str,
    conn: sqlite3.Connection,
    collection: str,
    params: dict | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, object]:
    """Tier-2 freshness refresh: refetch ``collection`` only when stale.

    The warmup probes capture an ETag (``record_etag``) and a warm timestamp
    (``record_data_warmed_at``). This consumes both: it short-circuits while the
    catalog is within its TTL, and otherwise issues a conditional GET
    (``If-None-Match`` with the stored ETag) so an unchanged collection costs a
    cheap 304 instead of a full re-pull.

    Returns ``(outcome, payload)``:

    - ``("fresh", None)``      — within TTL; no request made.
    - ``("unchanged", None)``  — TTL expired, server returned **304** (ETag
      matched). ``data_warmed_at`` is bumped (content is still current).
    - ``("refreshed", body)``  — TTL expired, server returned **200**. The new
      ETag (if any) is recorded and ``data_warmed_at`` bumped; the caller is
      responsible for writing ``body`` into the catalog tables.
    - ``("error", message)``   — the request failed or returned an unexpected
      status; nothing is written.

    Pure protocol/bookkeeping — the caller owns per-collection table writes,
    which differ by shape (picklists vs connector_configs vs …).

    **Live behavior on FortiSOAR 8.0 (probed 2026-07-02 on .159):** the 304
    ``unchanged`` path is effectively dead. FSR's Hydra collections
    (``picklist_names`` / ``teams`` / ``staging_model_metadatas``) return an
    ``ETag`` but **do not honor ``If-None-Match``** — a conditional GET always
    comes back 200 with the full body, so this helper records the (re-)fetched
    ETag + bumps ``data_warmed_at`` and returns ``"refreshed"``. The non-Hydra
    endpoints (``/api/integration/connectors/`` / ``/api/3/``) return no ETag at
    all. So on FSR today the only working arm is the TTL ``fresh``
    short-circuit, which trades freshness (a catalog warmed again within the TTL
    window skips the fetch and may miss a just-published picklist value / field)
    for fewer requests — which is why the wiring stays **opt-in / default OFF**.
    If a future FSR version honors ``If-None-Match``, the 304 arm revives with no
    code change.
    """
    from fsr_playbooks import _catalog_meta

    ttl = _catalog_meta.DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    if not _catalog_meta.is_ttl_expired(conn, ttl):
        return "fresh", None

    headers = {}
    etag = _catalog_meta.get_etag(conn, collection)
    if etag:
        headers["If-None-Match"] = etag

    try:
        resp = client.session.get(
            client.base_url + url,
            params=params,
            headers=headers or None,
            verify=client.verify_ssl,
        )
    except Exception as exc:  # noqa: BLE001
        return "error", f"{collection}: {exc!r}"

    if resp.status_code == 304:
        _catalog_meta.record_data_warmed_at(conn)
        return "unchanged", None
    if resp.status_code == 200:
        new_etag = resp.headers.get("ETag")
        if new_etag:
            _catalog_meta.record_etag(conn, collection, new_etag)
        _catalog_meta.record_data_warmed_at(conn)
        return "refreshed", resp.json()
    return "error", f"{collection}: unexpected status {resp.status_code}"


LOCAL_SOURCE_METHODS = frozenset({
    "rpm_info_json",
    "schema_json",
    "schema_ts",
    "widget_constants",
})

LIVE_TRUSTED_METHODS = frozenset({
    "live_api_get",
    "live_api_render",
    "live_op_exec",
    "playbook_e2e",
})


def _row_counts_for(conn: sqlite3.Connection, probe_name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in PROBE_TABLES.get(probe_name, ()):  # tolerate ad-hoc probes
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        out[table] = cur.fetchone()[0]
    return out
