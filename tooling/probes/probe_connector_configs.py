"""probe_connector_configs -- warm the per-instance `connector_configs` table.

Connector-configuration records (the `config` UUID a connector step needs) are
created out-of-band on each FSR box and are NOT portable, so they're warmed into
the reference DB rather than shipped. The compiler reads them offline via
``Resolver.resolve_config_id`` -- never by importing this `tooling/` tree or
hitting the network. This probe is the only writer.

Live source:
  GET /api/integration/connectors/?page_size=1000
      → every installed connector + its `configuration[]` (config_id, name,
        default). Django-REST paginates on page_size (not crudhub $limit).

The read and the write live in `fsr_playbooks.warmup` (shipped), so
`fsrpb warmup` and this probe share one ingest. This module keeps the
probe-only conditional refetch.

For each connector we write one row per named config plus a synthetic
``__default__`` row pointing at the instance default (or the sole config), so
``resolve_config_id(connector, None)`` resolves offline.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

from fsr_playbooks import warmup

from . import _env
from .common import (
    conditional_refetch,
    probe_session,
    wipe_probe_tables,
)

PROBE_NAME = "probe_connector_configs"
CONNECTORS_URL = warmup.CONNECTORS_URL


def _live(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, 0, ["env not configured"]

    # Tier-2 conditional refetch (opt-in via FSR_CONDITIONAL_REFETCH). Within TTL
    # or on a 304 the catalog is current and nothing is rewritten. On a 200 the
    # write replaces the table. An error leaves the catalog as it was.
    # conditional_refetch owns the ETag and warm time on this path.
    conditional = _env.is_conditional_enabled()
    if conditional:
        outcome, payload = conditional_refetch(
            client,
            url=CONNECTORS_URL,
            conn=conn,
            collection="connector_configs",
            params=warmup.CONFIG_LIST_PARAMS,
        )
        if outcome in ("fresh", "unchanged"):
            print(f"[{PROBE_NAME}] conditional_refetch: {outcome} "
                  f"(catalog current; skipped rewrite)")
            return 0, 0, []
        if outcome == "error":
            return 0, 0, [str(payload)]
        members = (payload or {}).get("data") or []
        etag = None
    else:
        try:
            members, etag = warmup.fetch_connector_configs(client)
        except Exception as e:  # noqa: BLE001
            return 0, 0, [f"connectors: {e!r}"]

    n_conn, n_rows = warmup.write_connector_configs(conn, members)
    if not conditional:
        # Legacy path records the ETag and Tier-2 warm time itself.
        warmup.record_warm_markers(conn, {"connector_configs": etag} if etag else {})
    return n_conn, n_rows, []


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
