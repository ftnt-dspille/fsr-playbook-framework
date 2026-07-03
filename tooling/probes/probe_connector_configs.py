"""probe_connector_configs — warm the per-instance `connector_configs` table.

Connector-configuration records (the `config` UUID a connector step needs) are
created out-of-band on each FSR box and are NOT portable, so they're warmed into
the reference DB rather than shipped. The compiler reads them offline via
``Resolver.resolve_config_id`` — never by importing this `tooling/` tree or
hitting the network. This probe is the only writer.

Live source:
  GET /api/integration/connectors/?page_size=1000
      → every installed connector + its `configuration[]` (config_id, name,
        default). Django-REST paginates on page_size (not crudhub $limit).

For each connector we write one row per named config plus a synthetic
``__default__`` row pointing at the instance default (or the sole config), so
``resolve_config_id(connector, None)`` resolves offline.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

from . import _env
from .common import (
    conditional_refetch,
    probe_session,
    record_verification,
    wipe_probe_tables,
)

PROBE_NAME = "probe_connector_configs"
CONNECTORS_URL = "/api/integration/connectors/"


def _fetch(client) -> tuple[list[dict], str | None]:
    """Fetch connector configs; return (data, etag_header).

    The ETag response header (if present) can be used for conditional refetches
    in a future Tier-2 freshness check.
    """
    r = client.session.get(
        client.base_url + CONNECTORS_URL,
        params={"page_size": 1000},
        verify=client.verify_ssl,
    )
    if r.status_code != 200:
        return [], None
    etag = r.headers.get("ETag")
    return r.json().get("data") or [], etag


def _rows_for(connector: str, configs: list[dict]) -> list[tuple]:
    rows: list[tuple] = []
    default = None
    for c in configs:
        cid = c.get("config_id")
        name = c.get("name")
        is_def = bool(c.get("default"))
        if name is None:
            continue
        rows.append((connector, name, cid, 1 if is_def else 0))
        if is_def and default is None:
            default = cid
    if default is None and configs:
        default = configs[0].get("config_id")
    if default is not None or configs:
        rows.append((connector, "__default__", default, 1))
    return rows


def _live(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, 0, ["env not configured"]

    # Tier-2 conditional refetch (opt-in via FSR_CONDITIONAL_REFETCH). When on,
    # fetch via conditional_refetch: within TTL -> skip (catalog current); 304 ->
    # skip (unchanged); 200 -> wipe + rewrite; error -> keep catalog. The wipe
    # moves HERE (only on a refreshed 200) so a fresh/unchanged outcome never
    # empties the table. conditional_refetch owns ETag + data_warmed_at recording,
    # so the legacy recording below is skipped on this path.
    conditional = _env.is_conditional_enabled()
    etag: str | None = None
    if conditional:
        outcome, payload = conditional_refetch(
            client,
            url=CONNECTORS_URL,
            conn=conn,
            collection="connector_configs",
            params={"page_size": 1000},
        )
        if outcome in ("fresh", "unchanged"):
            print(f"[{PROBE_NAME}] conditional_refetch: {outcome} "
                  f"(catalog current; skipped rewrite)")
            return 0, 0, []  # catalog current; no wipe, no rewrite
        if outcome == "error":
            return 0, 0, [str(payload)]
        # outcome == "refreshed": payload is the decoded JSON body.
        members = (payload or {}).get("data") or []
        wipe_probe_tables(conn, PROBE_NAME)
    else:
        try:
            members, etag = _fetch(client)
        except Exception as e:  # noqa: BLE001
            return 0, 0, [f"connectors: {e!r}"]

    n_conn = 0
    all_rows: list[tuple] = []
    for m in members:
        name = m.get("name")
        configs = m.get("configuration") or []
        if not name or not configs:
            continue
        rows = _rows_for(name, configs)
        if rows:
            n_conn += 1
            all_rows.extend(rows)
    conn.executemany(
        "INSERT OR REPLACE INTO connector_configs "
        "(connector, config_name, config_id, is_default) VALUES (?, ?, ?, ?)",
        all_rows,
    )
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/integration/connectors/",
        method="live_api_get", status="tested_pass",
        notes=f"connectors_with_config={n_conn}, rows={len(all_rows)}",
    )
    if not conditional:
        # Legacy path records the ETag + Tier-2 warm time (conditional_refetch
        # already did both on the refreshed 200 / unchanged 304).
        from fsr_playbooks import _catalog_meta
        if etag:
            _catalog_meta.record_etag(conn, "connector_configs", etag)
        _catalog_meta.record_data_warmed_at(conn)
    return n_conn, len(all_rows), []


def main() -> int:
    warnings.filterwarnings("ignore")
    cfg = _env.get_config()
    sources: list[Path] = []
    if cfg.is_live():
        sources.append(Path(cfg.base_url + CONNECTORS_URL))

    with probe_session(PROBE_NAME, sources) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS connector_configs ("
            "  connector TEXT NOT NULL,"
            "  config_name TEXT NOT NULL,"
            "  config_id TEXT,"
            "  is_default INTEGER DEFAULT 0,"
            "  PRIMARY KEY (connector, config_name))"
        )
        # Default (always-re-pull) path wipes before _live rewrites. When
        # FSR_CONDITIONAL_REFETCH is on, _live owns the wipe (only on a refreshed
        # 200) so a fresh/unchanged outcome leaves existing rows intact.
        if not _env.is_conditional_enabled():
            wipe_probe_tables(conn, PROBE_NAME)
        n_conn = n_rows = 0
        errs: list[str] = []
        if cfg.is_live():
            n_conn, n_rows, errs = _live(conn)
        notes = json.dumps({
            "connectors": n_conn, "rows": n_rows,
            "errors": errs[:30], "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] connectors={n_conn}  rows={n_rows}  "
              f"errors={len(errs)}")
        for e in errs[:10]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
