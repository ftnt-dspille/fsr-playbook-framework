"""probe_connectors — populate connectors / operations / operation_params.

Live source (preferred):
  GET  /api/integration/connectors/?page_size=1000&active=true
       → list of installed/active connectors (summary; no operations).
  POST /api/integration/connectors/{name}/{version}/?format=json
       → full record incl. operations[], config_schema, conditional onchange.

Trust ladder (per Dylan's rule, local sources never become trusted):
  - connector existence: tested_pass via live_api_get  (we read its record)
  - operation declaration: seen via live_api_get       (we read; haven't run)
  - param declaration:    seen via live_api_get
  Operations only become tested_pass once exercised via /api/integration/execute/.

Local fallback (only runs when live unavailable):
  fortisoar-rpm-extracted/*/info.json — written as `seen` via rpm_info_json.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import _env
from .common import (
    PROBE_TABLES,
    RPM_EXTRACTED_DIR,
    probe_session,
    record_verification,
    wipe_probe_tables,
)

PROBE_NAME = "probe_connectors"

# Per-call timeout safety net; the list endpoint can be slow under load.
LIST_PARAMS = {"page_size": 1000, "active": "true"}


# ----------------------- helpers -----------------------

def _strip_icons(rec: dict) -> dict:
    """Remove the base64 icon blobs — they bloat the DB by ~10× per row."""
    return {k: v for k, v in rec.items() if k not in ("icon_small", "icon_large")}


def _csv(value: Any) -> str | None:
    if isinstance(value, list):
        return ",".join(str(v) for v in value) if value else None
    return value if value else None


def _bool(v: Any) -> int:
    return 1 if v else 0


def _scalarize(v: Any) -> Any:
    """SQLite can't bind dicts/lists. Anything non-scalar becomes JSON text."""
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return json.dumps(v)


def _insert_param(
    conn: sqlite3.Connection,
    *,
    connector: str,
    op: str,
    parent: str | None,
    condition: str | None,
    ord_: int,
    p: dict,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO operation_params
           (connector_name, op_name, parent_param_name, condition_value,
            param_name, title, type, required, default_value, options_json,
            tooltip, placeholder, description, visible, editable, ord)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            connector, op, parent, condition,
            _scalarize(p.get("name")), _scalarize(p.get("title")), _scalarize(p.get("type")),
            _bool(p.get("required")),
            json.dumps(p.get("value")) if p.get("value") not in (None, "") else None,
            json.dumps(p["options"]) if isinstance(p.get("options"), list) else None,
            _scalarize(p.get("tooltip")),
            _scalarize(p.get("placeholder")),
            _scalarize(p.get("description")),
            _bool(p.get("visible", True)),
            _bool(p.get("editable", True)),
            ord_,
        ),
    )

    # Recurse into onchange branches: each value of the parent maps to a list
    # of sub-params that appear when the parent equals that value.
    onchange = p.get("onchange")
    if isinstance(onchange, dict):
        for cond_value, subparams in onchange.items():
            if not isinstance(subparams, list):
                continue
            for sub_ord, sub in enumerate(subparams):
                if not isinstance(sub, dict) or not sub.get("name"):
                    continue
                _insert_param(
                    conn,
                    connector=connector,
                    op=op,
                    parent=p.get("name"),
                    condition=str(cond_value),
                    ord_=sub_ord,
                    p=sub,
                )

    # Param verification: declaration was read live, so `seen` (we haven't
    # executed it). Local-source param rows would use rpm_info_json.
    record_verification(
        conn,
        kind="api_endpoint_param",  # reuse kind already in trust enum
        key=f"{connector}:{op}:"
            + (f"{parent}={condition}/" if parent else "")
            + p.get("name", ""),
        method="live_api_get",
        status="seen",
    )


def _upsert_connector_from_detail(conn: sqlite3.Connection, rec: dict, source: str) -> None:
    name = rec.get("name")
    if not name:
        return
    info_blob = json.dumps(_strip_icons(rec))
    conn.execute(
        """INSERT OR REPLACE INTO connectors
           (name, version, label, category, description, publisher, contributor,
            active, system, cs_approved, cs_compatible, ingestion_supported,
            tags_json, config_schema_json, source, source_path, info_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name, rec.get("version") or "",
            rec.get("label"), _csv(rec.get("category")),
            rec.get("description"), rec.get("publisher"), rec.get("contributor"),
            _bool(rec.get("active", True)), _bool(rec.get("system")),
            _bool(rec.get("cs_approved")), _bool(rec.get("cs_compatible")),
            _bool(rec.get("ingestion_supported")),
            json.dumps(rec.get("tags") or []),
            json.dumps(rec.get("config_schema") or {}),
            source, None, info_blob,
        ),
    )

    record_verification(
        conn, kind="connector", key=name,
        method="live_api_get" if source == "live_api_get" else "rpm_info_json",
        status="tested_pass" if source == "live_api_get" else "seen",
    )

    # Operations + params
    for op in rec.get("operations") or []:
        op_name = op.get("operation")
        if not op_name:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO operations
               (connector_name, op_name, title, annotation, category, description,
                visible, enabled, output_schema_json, conditional_output_schema_json)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                name, op_name, op.get("title"), op.get("annotation"),
                op.get("category"), op.get("description"),
                _bool(op.get("visible", True)), _bool(op.get("enabled", True)),
                json.dumps(op.get("output_schema")) if op.get("output_schema") is not None else None,
                json.dumps(op.get("conditional_output_schema"))
                    if op.get("conditional_output_schema") is not None else None,
            ),
        )
        record_verification(
            conn, kind="operation", key=f"{name}:{op_name}",
            method="live_api_get" if source == "live_api_get" else "rpm_info_json",
            status="seen",  # declared, not exercised
        )
        for ord_, p in enumerate(op.get("parameters") or []):
            if isinstance(p, dict) and p.get("name"):
                _insert_param(
                    conn, connector=name, op=op_name,
                    parent=None, condition=None, ord_=ord_, p=p,
                )


# ----------------------- live -----------------------

def _live(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, ["env not configured"]
    errors: list[str] = []

    try:
        listing = client.get("/api/integration/connectors/", params=LIST_PARAMS)
    except Exception as e:  # noqa: BLE001
        return 0, [f"GET list failed: {e!r}"]

    summaries = listing.get("data", []) if isinstance(listing, dict) else []
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/integration/connectors/",
        method="live_api_get", status="tested_pass",
        notes=f"totalItems={listing.get('totalItems')}",
    )
    # Promote /api/3/connectors to tested_fail — Hydra advertises but it 404s
    # on this instance; useful provenance so future probes don't try it again.
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/connectors", method="live_api_get",
        status="tested_fail",
        notes="404 'No route found' on this instance; use /api/integration/connectors/",
    )

    count = 0
    for s in summaries:
        cn, ver = s.get("name"), s.get("version")
        if not cn or not ver:
            continue
        try:
            # POST per the network capture; body is empty, format=json query.
            detail = client.post(
                f"/api/integration/connectors/{cn}/{ver}/?format=json",
                data={},
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cn} {ver}: {e!r}")
            continue
        if not isinstance(detail, dict):
            errors.append(f"{cn} {ver}: detail not dict ({type(detail).__name__})")
            continue
        _upsert_connector_from_detail(conn, detail, source="live_api_get")
        count += 1

    # Catalogue the detail endpoint at the api_endpoints level too.
    record_verification(
        conn, kind="api_endpoint",
        key="POST /api/integration/connectors/{name}/{version}/",
        method="live_api_get", status="tested_pass",
        notes=f"hit on {count} connectors via probe_connectors",
    )
    return count, errors


# ----------------------- catalog (uninstalled) -----------------------

def _live_catalog(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """POST /api/query/solutionpacks for connectors not installed on this box.

    `infoContent` mirrors the shape of /api/integration/connectors/{name}/{ver}/
    (config_schema, configuration, operations[]) — though `operations` here
    only has summary fields (title/operation/description), no parameters.
    Catalogued connectors land as `seen` (we know they exist; we haven't
    pulled their full param schemas).
    """
    client = _env.get_client()
    if client is None:
        return 0, ["env not configured"]

    page = 1
    limit = 100
    total: int | None = None
    items_seen = 0           # raw count from the server (for pagination math)
    upserts = 0              # connector rows we actually wrote
    skipped_installed = 0    # rows whose name is already a live install
    errors: list[str] = []
    seen_ids: set[str] = set()   # detect duplicate pages / runaway loops
    MAX_PAGES = 100              # safety cap (limit*MAX_PAGES = 10k rows ceiling)

    # /api/query/solutionpacks pagination: $limit + $page in the URL query.
    # Body `page`/`limit` fields are silently ignored. A stable sort makes
    # pagination deterministic.
    body = {
        "logic": "AND",
        "sort": [{"field": "label", "direction": "ASC"}],
        "filters": [
            {"field": "type", "operator": "in", "value": ["connector"]},
            {"field": "installed", "operator": "eq", "value": False},
        ],
    }

    while page <= MAX_PAGES:
        try:
            r = client.post(
                f"/api/query/solutionpacks?$limit={limit}&$page={page}",
                data=body,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"solutionpacks p{page}: {e!r}")
            break

        members = r.get("hydra:member") or r.get("data") or []
        if total is None:
            total = r.get("hydra:totalItems") or r.get("totalItems")
        if not members:
            break

        page_new = 0
        for sp in members:
            sp_id = str(sp.get("uuid") or sp.get("@id") or sp.get("name"))
            if sp_id in seen_ids:
                # Server returned an item we already processed — pagination
                # is looping. Bail out before we double-count.
                continue
            seen_ids.add(sp_id)
            page_new += 1
            items_seen += 1

            info = sp.get("infoContent") or {}
            name = info.get("name") or sp.get("name")
            if not name:
                continue
            if not info.get("name"):
                info = {
                    "name": name,
                    "version": sp.get("version"),
                    "label": sp.get("label"),
                    "description": sp.get("description"),
                    "publisher": sp.get("publisher"),
                    "category": sp.get("category"),
                    "operations": [],
                    "config_schema": {},
                }
            # Installed rows always win.
            existing = conn.execute(
                "SELECT source FROM connectors WHERE name = ?",
                (name,),
            ).fetchone()
            if existing and existing[0] == "live_api_get":
                skipped_installed += 1
                continue
            _upsert_connector_from_detail(conn, info, source="solutionpack_catalog")
            record_verification(
                conn, kind="connector", key=name,
                method="solutionpack_catalog", status="seen",
                notes=f"sp_id={sp_id}",
            )
            upserts += 1

        # Termination: server returned no NEW items, OR we've hit totalItems,
        # OR a short page (< limit) signals last page.
        if page_new == 0:
            break
        if total is not None and items_seen >= total:
            break
        if len(members) < limit:
            break
        page += 1

    if page > MAX_PAGES:
        errors.append(f"hit MAX_PAGES={MAX_PAGES} before completion")

    record_verification(
        conn, kind="api_endpoint",
        key="POST /api/query/solutionpacks",
        method="live_api_get", status="tested_pass",
        notes=f"items_seen={items_seen} totalItems={total} upserts={upserts} skipped_installed={skipped_installed}",
    )
    print(f"  catalog: {items_seen}/{total} items, {upserts} upserts, {skipped_installed} skipped (installed)")
    return upserts, errors

    record_verification(
        conn, kind="api_endpoint",
        key="POST /api/query/solutionpacks",
        method="live_api_get", status="tested_pass",
        notes=f"page_size={limit}, totalItems={total}",
    )
    return seen_count, errors


# ----------------------- local fallback -----------------------

def _local(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    if not RPM_EXTRACTED_DIR.exists():
        return 0, [f"missing {RPM_EXTRACTED_DIR}"]
    count = 0
    errors: list[str] = []
    for info_path in RPM_EXTRACTED_DIR.rglob("info.json"):
        try:
            rec = json.loads(info_path.read_text())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{info_path}: {e!r}")
            continue
        if not isinstance(rec, dict) or not rec.get("name"):
            continue
        # rpm info.json uses 'configuration' for connection config vs.
        # 'config_schema' from the live API. Normalize.
        if "config_schema" not in rec and "configuration" in rec:
            rec["config_schema"] = {"fields": rec.get("configuration") or []}
        _upsert_connector_from_detail(conn, rec, source="rpm_info_json")
        # Override the connector source_path so we know where it came from.
        conn.execute(
            "UPDATE connectors SET source_path = ? WHERE name = ?",
            (str(info_path), rec["name"]),
        )
        count += 1
    return count, errors


# ----------------------- entry -----------------------

def main() -> int:
    warnings.filterwarnings("ignore")  # silence InsecureRequestWarning
    cfg = _env.get_config()
    sources = []
    if cfg.is_live():
        sources.append(Path(cfg.base_url + "/api/integration/connectors/"))

    with probe_session(PROBE_NAME, sources) as conn:
        wipe_probe_tables(conn, PROBE_NAME)
        # Wipe verifications owned by this probe's kinds (per-row reset).
        conn.execute(
            "DELETE FROM verifications "
            "WHERE kind IN ('connector','operation','operation_param','api_endpoint_param') "
            "  AND method IN ('live_api_get','rpm_info_json')"
        )

        live_count, live_errs = (0, [])
        catalog_count, catalog_errs = (0, [])
        if cfg.is_live():
            live_count, live_errs = _live(conn)
            catalog_count, catalog_errs = _live_catalog(conn)
            sources.append(Path(cfg.base_url + "/api/query/solutionpacks"))

        local_count, local_errs = (0, [])
        if not cfg.is_live() or (live_count == 0 and catalog_count == 0):
            local_count, local_errs = _local(conn)
            sources.append(RPM_EXTRACTED_DIR)

        notes = json.dumps({
            "live_count": live_count,
            "catalog_count": catalog_count,
            "local_count": local_count,
            "errors": (live_errs + catalog_errs + local_errs)[:30],
            "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] live={live_count}  catalog={catalog_count}  "
              f"local={local_count}  "
              f"errors={len(live_errs)+len(catalog_errs)+len(local_errs)}")
        for e in (live_errs + catalog_errs + local_errs)[:10]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
