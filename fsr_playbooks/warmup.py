"""Warm a reference catalog from a live FortiSOAR box.

The offline compiler resolves picklist IRIs, connector configs, module fields and
connector operations from the reference DB. Those rows are per-install, so they
come from the box itself. This module reads the box through a pyfsr client and
writes the box-owned tables.

:func:`warm_catalog` is the public entry point. When the target DB is absent it
seeds it from the packaged catalog, so the static tables (step types, handlers,
jinja, the corpus) are present. It then replaces the box-owned tables and stamps
provenance, all in one transaction. It reads no environment and imports nothing
from the dev ``tooling/`` tree; the caller supplies the client.

The ``write_*`` helpers are shared with the tooling probes, which keep their own
orchestration (the opt-in conditional refetch and the RPM and catalog tiers).
Each writer fetches its data before it touches its table, so a failed source
never leaves that table empty.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import _catalog_meta
from ._db import PACKAGED_SLIM_DB, REPO_PROBED_DB, default_db_path, is_usable_sqlite

PROBE_NAME = "warm_catalog"

METADATA_URL = (
    "/api/3/staging_model_metadatas"
    "?$limit=2147483647&$orderby=type&$relationships=true"
)
PICKLISTS_URL = (
    "/api/3/picklist_names"
    "?$export=false&$limit=2147483647&$orderby=name&$relationships=true"
)
# No `$orderby`: on 8.0 the collection is plain strings with no `name` column,
# and ordering by it is a server-side QueryException (HTTP 400).
TAGS_URL = "/api/3/tags?$limit=2147483647"
TEAMS_URL = "/api/3/teams?$limit=2147483647&$orderby=name"
CONNECTORS_URL = "/api/integration/connectors/"
INSTALLED_LIST_PARAMS = {"page_size": 1000, "active": "true"}
CONFIG_LIST_PARAMS = {"page_size": 1000}

#: Tables that belong to the box. ``warm_catalog`` replaces their contents.
BOX_TABLES = (
    "modules", "module_fields", "picklists", "tags", "teams",
    "connectors", "operations", "operation_params", "connector_configs",
)
#: Collections whose row count is stamped, so a later freshness check sees drift.
COUNT_COLLECTIONS = ("model_metadatas", "attribute_metadatas", "picklists",
                     "picklist_names", "tags")
# Tables a file must already carry to be a reference catalog. Anything else is
# created by ``apply_migrations``.
_REQUIRED_TABLES = (
    "modules", "module_fields", "connectors", "operations", "operation_params",
    "connector_configs", "verifications", "_probe_runs",
)


class WarmupError(RuntimeError):
    """The target cannot be warmed: a refused path, or not a reference catalog."""


class WarmupFatal(RuntimeError):
    """A source the warm cannot run without (picklists or module metadata) failed.

    Raised before a box-owned table is written, so :func:`warm_catalog` rolls back
    and the catalog keeps its previous contents.
    """


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------- verifications -----------------------

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
    fsr-schema.ts, widget constants) is `status='seen'` -- it does NOT count as
    trusted. Only live_* / playbook_e2e methods with status='tested_pass' make
    an entity trusted in `v_verification_state`.
    """
    conn.execute(
        "INSERT OR REPLACE INTO verifications (kind, key, method, status, ts, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kind, key, method, status, _utcnow(), notes),
    )


# ----------------------- scalar helpers -----------------------

def _scalarize(v: Any) -> Any:
    """SQLite can't bind dicts/lists. Anything non-scalar becomes JSON text."""
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return json.dumps(v)


def _bool(v: Any) -> int:
    return 1 if v else 0


def _csv(value: Any) -> str | None:
    if isinstance(value, list):
        return ",".join(str(v) for v in value) if value else None
    return value if value else None


def _strip_icons(rec: dict) -> dict:
    """Remove the base64 icon blobs -- they bloat the DB by ~10x per row."""
    return {k: v for k, v in rec.items() if k not in ("icon_small", "icon_large")}


# ----------------------- schema -----------------------

def apply_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent DDL for tables and columns added after older catalogs shipped.

    Safe on any reference DB. The probes call it from their ``main()``;
    :func:`ensure_schema` calls it on the warm path.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS picklists ("
        "  list_name TEXT NOT NULL,"
        "  item_value TEXT NOT NULL,"
        "  item_iri TEXT NOT NULL,"
        "  PRIMARY KEY (list_name, item_value))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_picklists_list ON picklists(list_name)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tags ("
        "  name TEXT PRIMARY KEY,"
        "  iri  TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS teams ("
        "  name TEXT PRIMARY KEY,"
        "  iri  TEXT NOT NULL)"
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(module_fields)")}
    if "picklist_name" not in cols:
        conn.execute("ALTER TABLE module_fields ADD COLUMN picklist_name TEXT")
    # The module's natural key: the column(s) an upsert matches on.
    mcols = {r[1] for r in conn.execute("PRAGMA table_info(modules)")}
    if "unique_constraint" not in mcols:
        conn.execute("ALTER TABLE modules ADD COLUMN unique_constraint TEXT")
    _catalog_meta.ensure_table(conn)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Refuse a file that is not a reference catalog, then run the migrations."""
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    missing = [t for t in _REQUIRED_TABLES if t not in have]
    if missing:
        raise WarmupError(
            "not a reference catalog (missing " + ", ".join(missing) + ")")
    apply_migrations(conn)
    conn.commit()


# ----------------------- fetch -----------------------

def _get(client, url: str, params: dict | None = None):
    """GET through the client's session. The raw response keeps the ETag header."""
    resp = client.session.get(
        client.base_url + url, params=params, verify=client.verify_ssl,
    )
    resp.raise_for_status()
    return resp


def _note_etag(etags: dict[str, str], collection: str, resp) -> None:
    etag = resp.headers.get("ETag")
    if etag:
        etags[collection] = etag


# ----------------------- picklists -----------------------

def parse_picklists(body: Any) -> tuple[dict[str, str], dict[str, list[str]],
                                         list[tuple[str, str, str]], int]:
    """Parse a picklist_names body into (item_id_to_value, list_name_to_options,
    items_rows, listCount). Fetch-agnostic so a caller can pass an already
    fetched body.
    """
    members = body.get("hydra:member", []) if isinstance(body, dict) else []
    item_id_to_value: dict[str, str] = {}
    list_name_to_options: dict[str, list[str]] = {}
    items_rows: list[tuple[str, str, str]] = []
    for pl_name in members:
        name = pl_name.get("name")
        items = pl_name.get("picklists") or []
        opts = []
        for it in items:
            iid = it.get("@id")
            iv = it.get("itemValue")
            if iid and iv is not None:
                item_id_to_value[iid] = iv
            if iv is not None:
                opts.append(iv)
            if name and isinstance(iv, str) and isinstance(iid, str):
                items_rows.append((name, iv, iid))
        if name:
            list_name_to_options[name] = opts
    return item_id_to_value, list_name_to_options, items_rows, len(members)


def write_picklists(conn: sqlite3.Connection, items_rows: list, n_lists: int) -> None:
    """Replace the picklists table. ``items_rows`` is (list_name, value, iri)."""
    conn.execute("DELETE FROM picklists")
    conn.executemany(
        "INSERT OR REPLACE INTO picklists (list_name, item_value, item_iri) "
        "VALUES (?, ?, ?)",
        items_rows,
    )
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/picklist_names",
        method="live_api_get", status="tested_pass",
        notes=f"picklists={n_lists}, items={len(items_rows)}",
    )


# ----------------------- tags / teams -----------------------

def _tag_rows(members: list) -> list[tuple[str, str]]:
    """(name, iri) rows from a `/api/3/tags` collection.

    8.0 serves each tag as a bare string; older boxes as an object. Skipping
    the strings wiped the table and left tag validation silently off. A bare
    tag's IRI is the slug form the compiler already emits for an unknown tag.
    """
    rows: list[tuple[str, str]] = []
    for m in members:
        if isinstance(m, str):
            if m:
                rows.append((m, f"/api/3/tags/{m}"))
        elif isinstance(m, dict):
            name = m.get("itemValue") or m.get("name")
            iri = m.get("@id")
            if name and iri:
                rows.append((str(name), str(iri)))
    return rows


def _team_rows(members: list) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for m in members:
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        iri = m.get("@id")
        if name and iri:
            rows.append((str(name), str(iri)))
    return rows


def write_tags(conn: sqlite3.Connection, rows: list[tuple[str, str]]) -> None:
    conn.execute("DELETE FROM tags")
    conn.executemany("INSERT OR REPLACE INTO tags (name, iri) VALUES (?, ?)", rows)
    record_verification(
        conn, kind="api_endpoint", key="GET /api/3/tags",
        method="live_api_get", status="tested_pass",
        notes=f"tags={len(rows)}",
    )


def write_teams(conn: sqlite3.Connection, rows: list[tuple[str, str]]) -> None:
    conn.execute("DELETE FROM teams")
    conn.executemany("INSERT OR REPLACE INTO teams (name, iri) VALUES (?, ?)", rows)
    record_verification(
        conn, kind="api_endpoint", key="GET /api/3/teams",
        method="live_api_get", status="tested_pass",
        notes=f"teams={len(rows)}",
    )


# ----------------------- modules -----------------------

def _picklist_list_name(attr: dict) -> str | None:
    """Return the listName the attribute binds to (e.g. 'AlertStatus'),
    or None if it isn't picklist-backed."""
    ds = attr.get("dataSource") or {}
    if not isinstance(ds, dict):
        return None
    query = ds.get("query") or {}
    for f in query.get("filters", []) or []:
        if isinstance(f, dict) and f.get("field") == "listName__name":
            v = f.get("value")
            if isinstance(v, str):
                return v
    return None


def _is_required(validation: Any) -> bool:
    return isinstance(validation, dict) and validation.get("required") is True


def _unique_columns(m: dict) -> list[str]:
    """The module's natural-key column(s), from its uniqueConstraint.

    Shape on the wire is a list of single-entry dicts::

        [{"c_v_es_unique": {"columns": ["cVEID"]}}]

    Most modules define one constraint; the columns of all of them are
    collected so a composite key is not silently halved.
    """
    out: list[str] = []
    for entry in (m.get("uniqueConstraint") or []):
        if not isinstance(entry, dict):
            continue
        for spec in entry.values():
            if isinstance(spec, dict):
                for col in (spec.get("columns") or []):
                    if isinstance(col, str) and col not in out:
                        out.append(col)
    return out


def insert_module(conn: sqlite3.Connection, m: dict) -> str | None:
    name = m.get("type") or m.get("module")
    if not name:
        return None
    unique = _unique_columns(m)
    conn.execute(
        """INSERT OR REPLACE INTO modules
             (name, label, plural, description, unique_constraint)
           VALUES (?, ?, ?, ?, ?)""",
        (
            name,
            _scalarize(m.get("displayName") or m.get("module") or name),
            _scalarize(m.get("module")),
            _scalarize(m.get("descriptions")),
            json.dumps(unique) if unique else None,
        ),
    )
    return name


def insert_field(
    conn: sqlite3.Connection,
    *,
    module: str,
    attr: dict,
    picklist_lists: dict[str, list[str]],
) -> None:
    name = attr.get("name")
    if not name:
        return
    list_name = _picklist_list_name(attr)
    options = picklist_lists.get(list_name) if list_name is not None else None
    conn.execute(
        """INSERT OR REPLACE INTO module_fields
           (module_name, field_name, title, type, required,
            picklist_options, tooltip, picklist_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            module,
            name,
            _scalarize(attr.get("title") or attr.get("displayName") or name),
            # Date fields are `type: integer` (epoch) with `formType: datetime`;
            # keep the datetime -- a query filter on one needs `type: datetime`.
            "datetime" if attr.get("formType") == "datetime"
            else _scalarize(attr.get("type") or attr.get("formType")),
            _bool(_is_required(attr.get("validation"))),
            json.dumps(options) if options else None,
            _scalarize(attr.get("tooltip")),
            list_name,
        ),
    )


def write_modules(
    conn: sqlite3.Connection,
    members: list,
    picklist_lists: dict[str, list[str]],
    *,
    method: str = "live_api_get",
    module_status: str = "tested_pass",
) -> tuple[int, int]:
    """Replace modules / module_fields and record their verifications.

    ``method``/``module_status`` let the local schema.json fallback reuse this
    writer as ``seen`` rows. Field verifications are ``seen`` on both paths.
    """
    conn.execute("DELETE FROM module_fields")
    conn.execute("DELETE FROM modules")
    conn.execute(
        "DELETE FROM verifications WHERE kind IN ('module','module_field') "
        "AND method IN ('live_api_get','schema_json')"
    )
    n_mod = n_fld = 0
    for m in members:
        if not isinstance(m, dict) or not m.get("type"):
            continue
        module = insert_module(conn, m)
        if not module:
            continue
        n_mod += 1
        record_verification(
            conn, kind="module", key=module,
            method=method, status=module_status,
        )
        for attr in m.get("attributes") or []:
            if not isinstance(attr, dict):
                continue
            insert_field(conn, module=module, attr=attr, picklist_lists=picklist_lists)
            n_fld += 1
            if attr.get("name"):
                record_verification(
                    conn, kind="module_field",
                    key=f"{module}:{attr['name']}",
                    method=method, status="seen",
                )
    return n_mod, n_fld


# ----------------------- installed connectors -----------------------

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

    # Param declaration was read live, so `seen` (we haven't executed it).
    record_verification(
        conn,
        kind="api_endpoint_param",
        key=f"{connector}:{op}:"
            + (f"{parent}={condition}/" if parent else "")
            + p.get("name", ""),
        method="live_api_get",
        status="seen",
    )


def upsert_connector_detail(conn: sqlite3.Connection, rec: dict, source: str) -> None:
    """Write one connector record with its operations and params.

    ``source`` is ``live_api_get`` for a box read, or an RPM / catalog tier name.
    """
    name = rec.get("name")
    if not name:
        return
    info_blob = json.dumps(_strip_icons(rec))
    # UPSERT (not INSERT OR REPLACE) so we preserve columns this tier doesn't
    # populate -- rpm_fingerprint (set by the RPM tier) and source_code (set
    # lazily by mcp_server.get_connector_source). OR REPLACE would null them.
    conn.execute(
        """INSERT INTO connectors
           (name, version, label, category, description, publisher, contributor,
            active, system, cs_approved, cs_compatible, ingestion_supported,
            tags_json, config_schema_json, source, source_path, info_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(name) DO UPDATE SET
             version = excluded.version,
             label = excluded.label,
             category = excluded.category,
             description = excluded.description,
             publisher = excluded.publisher,
             contributor = excluded.contributor,
             active = excluded.active,
             system = excluded.system,
             cs_approved = excluded.cs_approved,
             cs_compatible = excluded.cs_compatible,
             ingestion_supported = excluded.ingestion_supported,
             tags_json = excluded.tags_json,
             config_schema_json = excluded.config_schema_json,
             source = excluded.source,
             source_path = excluded.source_path,
             info_json = excluded.info_json""",
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


def _drop_connector_rows(conn: sqlite3.Connection) -> None:
    """Drop connector, operation and param rows so uninstalled ones disappear.

    Explicit deletes, not cascades: ``warm_catalog`` runs with foreign keys off,
    so ``op_safety`` (keyed by connector and op name) survives a re-warm.
    """
    conn.execute("DELETE FROM operation_params")
    conn.execute("DELETE FROM operations")
    conn.execute("DELETE FROM connectors")
    conn.execute(
        "DELETE FROM verifications WHERE method = 'live_api_get' "
        "AND kind IN ('connector','operation','api_endpoint_param')"
    )


def load_installed_connectors(
    conn: sqlite3.Connection, client, *, replace: bool = False,
) -> tuple[int, list[str]]:
    """Read the box's active connectors with their operations and params.

    ``replace=True`` drops the existing connector rows first, so a connector
    uninstalled since the last warm disappears. The drop runs only after the
    listing succeeds: a failed listing keeps the catalog. The probes leave
    ``replace`` off and upsert incrementally, because their RPM and catalog
    tiers own rows this path never reads.
    """
    try:
        listing = client.get(CONNECTORS_URL, params=INSTALLED_LIST_PARAMS)
    except Exception as e:  # noqa: BLE001
        return 0, [f"GET list failed: {e!r}"]

    summaries = listing.get("data", []) if isinstance(listing, dict) else []
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/integration/connectors/",
        method="live_api_get", status="tested_pass",
        notes=f"totalItems={listing.get('totalItems') if isinstance(listing, dict) else None}",
    )
    # Hydra advertises /api/3/connectors but it 404s on FSR 8.0. Record that so
    # a future probe does not try it again.
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/connectors", method="live_api_get",
        status="tested_fail",
        notes="404 'No route found' on this instance; use /api/integration/connectors/",
    )
    if replace:
        _drop_connector_rows(conn)

    errors: list[str] = []
    count = 0
    for s in summaries:
        cn, ver = s.get("name"), s.get("version")
        if not cn or not ver:
            continue
        try:
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
        upsert_connector_detail(conn, detail, source="live_api_get")
        count += 1

    record_verification(
        conn, kind="api_endpoint",
        key="POST /api/integration/connectors/{name}/{version}/",
        method="live_api_get", status="tested_pass",
        notes=f"hit on {count} connectors",
    )
    return count, errors


# ----------------------- connector configurations -----------------------

def fetch_connector_configs(client) -> tuple[list[dict], str | None]:
    """Return ``(connector_rows, etag)`` for the connector configurations.

    Raises on a non-200 response. A silent empty list would look like a box
    with no configurations.
    """
    resp = _get(client, CONNECTORS_URL, params=CONFIG_LIST_PARAMS)
    return resp.json().get("data") or [], resp.headers.get("ETag")


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


def write_connector_configs(conn: sqlite3.Connection, members: list[dict]) -> tuple[int, int]:
    """Replace connector_configs from the connector rows. Returns (connectors, rows)."""
    conn.execute("DELETE FROM connector_configs")
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
    return n_conn, len(all_rows)


# ----------------------- modules: the orchestrated read -----------------------

def warm_modules(
    conn: sqlite3.Connection, client, *, picklists_body: Any = None,
) -> tuple[int, int, list[str], dict[str, str]]:
    """Read picklists, tags, teams and module metadata, then write them.

    Every source is fetched before the first write. A failed picklists or
    metadata read raises :class:`WarmupFatal` with nothing written. A failed tags
    or teams read is reported and that table keeps its rows.

    ``picklists_body`` lets a caller that already fetched picklists (the
    conditional refetch) skip the second GET. Returns
    ``(n_modules, n_fields, errors, etags)``; ``etags`` covers only what this
    function fetched.
    """
    etags: dict[str, str] = {}
    errors: list[str] = []

    try:
        picklist_resp = None
        if picklists_body is None:
            picklist_resp = _get(client, PICKLISTS_URL)
            picklists_body = picklist_resp.json()
        picklist_items, picklist_lists, items_rows, n_lists = parse_picklists(picklists_body)
    except Exception as e:  # noqa: BLE001
        raise WarmupFatal(f"picklists: {e!r}") from e
    if picklist_resp is not None:
        _note_etag(etags, "picklists", picklist_resp)

    tag_rows: list[tuple[str, str]] | None = None
    try:
        tags_resp = _get(client, TAGS_URL)
        tag_rows = _tag_rows(tags_resp.json().get("hydra:member") or [])
        _note_etag(etags, "tags", tags_resp)
    except Exception as e:  # noqa: BLE001
        errors.append(f"tags: {e!r}")

    team_rows: list[tuple[str, str]] | None = None
    try:
        teams_resp = _get(client, TEAMS_URL)
        team_rows = _team_rows(teams_resp.json().get("hydra:member") or [])
    except Exception as e:  # noqa: BLE001
        errors.append(f"teams: {e!r}")

    try:
        metadata_resp = _get(client, METADATA_URL)
        metadata = metadata_resp.json()
    except Exception as e:  # noqa: BLE001
        raise WarmupFatal(f"metadata: {e!r}") from e
    _note_etag(etags, "model_metadatas", metadata_resp)

    write_picklists(conn, items_rows, n_lists)
    if tag_rows is not None:
        write_tags(conn, tag_rows)
    if team_rows is not None:
        write_teams(conn, team_rows)
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/staging_model_metadatas",
        method="live_api_get", status="tested_pass",
        notes="$relationships=true required for inline attributes",
    )
    members = metadata.get("hydra:member", []) if isinstance(metadata, dict) else []
    n_mod, n_fld = write_modules(conn, members, picklist_lists)
    return n_mod, n_fld, errors, etags


# ----------------------- provenance -----------------------

def live_license_serial(client) -> str | None:
    """The durable license serial of the box behind ``client``, or None.

    One advisory GET. A base_url says where we dialed; the serial says which
    appliance answered. One box answers on several listeners, and URL-only
    identity reads those as two boxes. Never fatal.
    """
    try:
        payload = client.get("/api/auth/license", params={"param": "license_details"})
    except Exception:  # noqa: BLE001 -- identity is advisory
        return None
    return _catalog_meta.license_serial_from_details(payload)


def stamp_provenance(
    conn: sqlite3.Connection,
    client,
    *,
    instance_label: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Stamp which box the catalog came from, and the row-count baseline.

    ``base_url`` defaults to ``client.base_url``. Best-effort: the extra GETs are
    cheap, and a failure here must not fail the warm. Returns the identity fields.
    """
    fsr_version = None
    last_publish = None
    try:  # public, no-auth, ~25 B -- Tier-0 upgrade gate
        v = client.get("/api/version")
        if isinstance(v, dict):
            fsr_version = v.get("version")
    except Exception:  # noqa: BLE001
        pass
    try:  # appliance-wide publish watermark -- Tier-1 gate
        p = client.get("/api/publish/error")
        if isinstance(p, dict):
            last_publish = p.get("last_publish_time")
    except Exception:  # noqa: BLE001
        pass
    serial = live_license_serial(client)
    _catalog_meta.stamp_instance(
        conn,
        instance_label=instance_label,
        base_url=base_url or client.base_url,
        fsr_version=fsr_version,
        last_publish_time=last_publish,
        instance_serial=serial,
    )
    # Baseline the cheap row counts so a later freshness check can detect
    # add/delete drift, including picklist value adds that publish nothing.
    for coll in COUNT_COLLECTIONS:
        try:
            r = client.get(f"/api/3/{coll}?$limit=0")
            total = r.get("hydra:totalItems") if isinstance(r, dict) else None
            if isinstance(total, int):
                _catalog_meta.record_count(conn, coll, total)
        except Exception:  # noqa: BLE001
            pass
    return {"fsr_version": fsr_version, "last_publish_time": last_publish,
            "instance_serial": serial}


def record_warm_markers(conn: sqlite3.Connection, etags: dict[str, str]) -> None:
    """Record the ETags this warm fetched, plus the Tier-2 warm time."""
    for collection, etag in etags.items():
        if etag:
            _catalog_meta.record_etag(conn, collection, etag)
    _catalog_meta.record_data_warmed_at(conn)


# ----------------------- warm_catalog -----------------------

def _refuse_shipped(target: Path) -> None:
    """Refuse the files a warm must never write: the packaged catalog, the dev
    corpus, and whatever ``default_db_path()`` resolves to right now.
    """
    protected = {PACKAGED_SLIM_DB.resolve(), REPO_PROBED_DB.resolve(),
                 default_db_path().resolve()}
    if target.resolve() in protected:
        raise WarmupError(
            f"refusing to warm {target}: it is a shipped or dev reference DB. "
            "Point db_path at a scratch copy."
        )


def _seed_if_absent(target: Path, seed: Path) -> None:
    """Make ``target`` a usable reference DB, copying ``seed`` only when absent.

    A zero-byte file counts as absent: ``sqlite3.connect`` creates one for any
    path it is pointed at. Any other non-sqlite file is refused, never overwritten.
    """
    if target.exists() and target.stat().st_size > 0:
        if not is_usable_sqlite(target):
            raise WarmupError(f"{target} exists and is not a sqlite database")
        return
    if not is_usable_sqlite(seed):
        raise WarmupError(f"seed catalog {seed} is missing or not a sqlite database")
    target.parent.mkdir(parents=True, exist_ok=True)
    # The sqlite backup API, not a file copy: a seed with an uncheckpointed WAL
    # would lose rows under a plain copy.
    src = sqlite3.connect(f"{seed.resolve().as_uri()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    # WAL, as the probes' open_db sets it. Foreign keys stay off on purpose; see
    # _drop_connector_rows.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in BOX_TABLES}


def _warm_in_transaction(
    conn: sqlite3.Connection,
    client,
    instance_label: str | None,
    errors: list[str],
) -> dict[str, Any]:
    """The warm itself. The caller owns the transaction: a :class:`WarmupFatal`
    or any other exception leaves the catalog as it was.
    """
    base_url = client.base_url
    etags: dict[str, str] = {}

    n_mod, n_fld, mod_errs, mod_etags = warm_modules(conn, client)
    etags.update(mod_etags)
    errors.extend(mod_errs)

    _, conn_errs = load_installed_connectors(conn, client, replace=True)
    errors.extend(conn_errs)

    try:
        members, cfg_etag = fetch_connector_configs(client)
    except Exception as e:  # noqa: BLE001
        errors.append(f"connector_configs: {e!r}")
    else:
        write_connector_configs(conn, members)
        if cfg_etag:
            etags["connector_configs"] = cfg_etag

    identity = stamp_provenance(conn, client, instance_label=instance_label)
    record_warm_markers(conn, etags)
    counts = _table_counts(conn)
    conn.execute(
        "INSERT INTO _probe_runs (probe_name, ts, source_paths, row_counts, version, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            PROBE_NAME, _utcnow(),
            json.dumps([_catalog_meta.normalize_base_url(base_url)]),
            json.dumps(counts), "1",
            json.dumps({"errors": errors[:30], "instance_label": instance_label or ""}),
        ),
    )
    conn.commit()
    return {
        "instance_label": instance_label or "",
        "base_url": _catalog_meta.normalize_base_url(base_url),
        "base_url_hash": _catalog_meta.base_url_hash(base_url),
        **identity,
    }


def warm_catalog(
    client,
    db_path: str | Path,
    *,
    instance_label: str | None = None,
    seed_from: str | Path | None = None,
) -> dict[str, Any]:
    """Warm ``db_path`` from the live box behind ``client``. Returns a report.

    - ``db_path`` absent: seeded from ``seed_from`` (default: the packaged
      catalog, via ``default_db_path()``) with the sqlite backup API. Present:
      used as is. The packaged file, the dev corpus and ``default_db_path()`` are
      always refused.
    - Replaces the box-owned tables (``BOX_TABLES``) and stamps
      ``_catalog_meta`` with the base URL, label, version, serial and counts.
    - One transaction. A failed picklists or module-metadata read rolls back
      everything and reports ``committed=False``. Other failed sources are
      reported in ``errors`` and their tables keep their previous rows.

    Endpoints read: ``/api/3/picklist_names``, ``/api/3/tags``, ``/api/3/teams``,
    ``/api/3/staging_model_metadatas``, ``/api/integration/connectors/`` (list,
    and per-connector ``POST .../{name}/{version}/?format=json``),
    ``/api/version``, ``/api/publish/error``, ``/api/auth/license``, and
    ``/api/3/<coll>?$limit=0`` for each count collection.

    Report keys: ``db``, ``committed``, ``counts`` (rows per box table),
    ``errors``, ``stamp`` (empty unless committed).

    Raises :class:`WarmupError` for a refused path or a non-catalog file.
    """
    target = Path(db_path)
    _refuse_shipped(target)
    _seed_if_absent(
        target,
        Path(seed_from) if seed_from is not None else default_db_path(),
    )

    errors: list[str] = []
    stamp: dict[str, Any] = {}
    committed = False
    conn = _open(target)
    try:
        ensure_schema(conn)
        try:
            stamp = _warm_in_transaction(conn, client, instance_label, errors)
            committed = True
        except WarmupFatal as e:
            conn.rollback()
            errors.append(str(e))
        counts = _table_counts(conn)
    finally:
        conn.close()
    return {
        "db": str(target),
        "committed": committed,
        "counts": counts,
        "errors": errors,
        "stamp": stamp,
    }


# Module/field totals move when a module or field is added or removed (live: one
# new module with two fields took 46/1003 to 47/1005). The publish watermark at
# /api/publish/error is not usable: some boxes answer it with 400.
_FRESHNESS_COLLECTIONS = ("model_metadatas", "attribute_metadatas")


def _live_counts(client) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for coll in _FRESHNESS_COLLECTIONS:
        try:
            r = client.get(f"/api/3/{coll}", params={"$limit": 0})
            total = r.get("hydra:totalItems") if isinstance(r, dict) else None
            out[coll] = total if isinstance(total, int) else None
        except Exception:  # noqa: BLE001 - unknown counts force a re-warm
            out[coll] = None
    return out


def box_catalog(client, cache_dir: str | Path | None = None, *, instance_label: str | None = None) -> Path:
    """The reference catalog for ``client``'s box, warming it when needed.

    One file per box under ``cache_dir`` (default ``$XDG_CACHE_HOME`` or
    ``~/.cache``, then ``fsr_playbooks/boxes``), named by the box's URL hash. It
    is (re)warmed when missing, stamped for another box, or when the box's
    module/field totals differ from the ones recorded at the last warm (the
    agent created a module since). Returns the path for ``compile_yaml``.
    """
    from . import _catalog_meta

    root = Path(cache_dir) if cache_dir else Path(
        os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "fsr_playbooks" / "boxes"
    root.mkdir(parents=True, exist_ok=True)
    base_url = client.base_url
    path = root / f"catalog-{_catalog_meta.base_url_hash(base_url)}.db"
    if path.exists() and path.stat().st_size:
        conn = sqlite3.connect(path)
        try:
            status, _, _ = _catalog_meta.check_instance(conn, base_url)
            recorded = {c: _catalog_meta.get(conn, f"count:{c}") for c in _FRESHNESS_COLLECTIONS}
        finally:
            conn.close()
        live = _live_counts(client)
        if status == "ok" and all(live[c] is not None and str(live[c]) == recorded[c]
                                  for c in _FRESHNESS_COLLECTIONS):
            return path
    fresh = not path.exists()
    try:
        report = warm_catalog(client, path, instance_label=instance_label)
        if not report.get("committed"):
            raise WarmupError(f"warming the catalog for {base_url} failed: {report.get('errors')}")
    except Exception:
        # A failed first warm leaves only the seed copy: another box's catalog
        # under this box's name. Remove it so the next call retries.
        if fresh:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{path}{suffix}").unlink(missing_ok=True)
        raise
    return path
