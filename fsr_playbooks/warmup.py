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

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
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
#: Every connector configuration on the box, hub AND remote agents. The
#: connectors listing above omits agent-bound configs (an agent's connector is a
#: separate record that only appears with ``?agent=<agentId>``), so a config that
#: lives only on an agent was never warmed.
CONFIGURATION_URL = "/api/integration/configuration/"
AGENTS_URL = "/api/3/agents"
#: Name the hub's own (local) agent is stored under in the ``agents`` table.
SELF_AGENT = "self"

#: Tables that belong to the box. ``warm_catalog`` replaces their contents.
BOX_TABLES = (
    "modules", "module_fields", "picklists", "tags", "teams",
    "connectors", "operations", "operation_params", "connector_configs", "agents",
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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS agents ("
        "  name TEXT PRIMARY KEY,"
        "  agent_id TEXT NOT NULL,"
        "  is_self INTEGER DEFAULT 0)"
    )
    _migrate_connector_configs_agent(conn)
    _catalog_meta.ensure_table(conn)


def _migrate_connector_configs_agent(conn: sqlite3.Connection) -> None:
    """Give ``connector_configs`` an ``agent_id`` column, keyed into the PK.

    ``''`` is the hub (self); a remote agent's config carries its ``agentId``.
    The same config name may exist on the hub and on an agent, so the primary
    key must include the agent. SQLite cannot alter a PK, so the table is
    rebuilt, keeping every existing column (e.g. ``allow_imports``).
    """
    info = list(conn.execute("PRAGMA table_info(connector_configs)"))
    if not info:
        conn.execute(
            "CREATE TABLE connector_configs ("
            "  connector TEXT NOT NULL,"
            "  config_name TEXT NOT NULL,"
            "  config_id TEXT,"
            "  is_default INTEGER DEFAULT 0,"
            "  agent_id TEXT NOT NULL DEFAULT '',"
            "  PRIMARY KEY (connector, config_name, agent_id))"
        )
        return
    cols = [r[1] for r in info]
    if "agent_id" in cols:
        return
    extra = [f"{r[1]} {r[2] or ''}".strip() for r in info
             if r[1] not in ("connector", "config_name", "config_id", "is_default")]
    keep = ", ".join(cols)
    # legacy_alter_table: a rename otherwise re-validates every view in the
    # schema, and one stale view (unrelated to this table) aborts the rebuild.
    conn.execute("PRAGMA legacy_alter_table=ON")
    conn.execute("ALTER TABLE connector_configs RENAME TO _connector_configs_old")
    conn.execute(
        "CREATE TABLE connector_configs ("
        "  connector TEXT NOT NULL,"
        "  config_name TEXT NOT NULL,"
        "  config_id TEXT,"
        "  is_default INTEGER DEFAULT 0,"
        + "".join(f"  {c}," for c in extra)
        + "  agent_id TEXT NOT NULL DEFAULT '',"
        "  PRIMARY KEY (connector, config_name, agent_id))"
    )
    conn.execute(f"INSERT INTO connector_configs ({keep}) SELECT {keep} FROM _connector_configs_old")
    conn.execute("DROP TABLE _connector_configs_old")
    conn.execute("PRAGMA legacy_alter_table=OFF")


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

def _http_timeout() -> float:
    """Seconds before a stalled read gives up (``$FSRPB_HTTP_TIMEOUT``, default 120).

    Without one, a connection the box stops answering hangs the warm forever.
    """
    try:
        return float(os.environ.get("FSRPB_HTTP_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def _get(client, url: str, params: dict | None = None):
    """GET through the client's session. The raw response keeps the ETag header."""
    resp = client.session.get(
        client.base_url + url, params=params, verify=client.verify_ssl, timeout=_http_timeout(),
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


def write_picklists(conn: sqlite3.Connection, items_rows: list, n_lists: int,
                    *, only: Iterable[str] | None = None) -> None:
    """Replace the picklists table. ``items_rows`` is (list_name, value, iri).

    ``only`` replaces just those lists and keeps the rest (a targeted warm).
    """
    if only is None:
        conn.execute("DELETE FROM picklists")
    else:
        conn.executemany("DELETE FROM picklists WHERE list_name = ?", [(n,) for n in only])
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
    replace_all: bool = True,
) -> tuple[int, int]:
    """Replace modules / module_fields and record their verifications.

    ``method``/``module_status`` let the local schema.json fallback reuse this
    writer as ``seen`` rows. Field verifications are ``seen`` on both paths.
    ``replace_all=False`` replaces only the modules in ``members`` (a targeted warm).
    """
    if replace_all:
        conn.execute("DELETE FROM module_fields")
        conn.execute("DELETE FROM modules")
        conn.execute(
            "DELETE FROM verifications WHERE kind IN ('module','module_field') "
            "AND method IN ('live_api_get','schema_json')"
        )
    else:
        names = [(m["type"],) for m in members if isinstance(m, dict) and m.get("type")]
        conn.executemany("DELETE FROM module_fields WHERE module_name = ?", names)
        conn.executemany("DELETE FROM modules WHERE name = ?", names)
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
    only: Iterable[str] | None = None,
    listing: Any = None,
) -> tuple[int, list[str]]:
    """Read the box's active connectors with their operations and params.

    ``replace=True`` drops the existing connector rows first, so a connector
    uninstalled since the last warm disappears. The drop runs only after the
    listing succeeds: a failed listing keeps the catalog. The probes leave
    ``replace`` off and upsert incrementally, because their RPM and catalog
    tiers own rows this path never reads.
    """
    if isinstance(listing, Exception):
        return 0, [f"GET list failed: {listing!r}"]
    if listing is None:
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
    if replace and only is None:
        _drop_connector_rows(conn)

    wanted = set(only) if only is not None else None
    summaries = [x for x in summaries if x.get("name") and x.get("version")
                 and (wanted is None or x.get("name") in wanted)]
    details, errors, _ = fetch_connector_details(client, summaries)
    count = 0
    for detail in details:
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


def _allow_imports(c: dict) -> int | None:
    v = (c.get("config") or {}).get("allow_imports") if isinstance(c.get("config"), dict) else None
    return None if not isinstance(v, bool) else int(v)


def _health(c: dict) -> str | None:
    h = c.get("health_status")
    if isinstance(h, dict):
        h = h.get("status")
    return str(h) if h not in (None, "") else None


def _rows_for(connector: str, configs: list[dict], agent_id: str = "") -> list[tuple]:
    rows: list[tuple] = []
    default: dict | None = None
    for c in configs:
        cid = c.get("config_id")
        name = c.get("name")
        is_def = bool(c.get("default"))
        if name is None:
            continue
        rows.append((connector, name, cid, 1 if is_def else 0, agent_id, _allow_imports(c), _health(c)))
        if is_def and default is None:
            default = c
    if default is None and configs:
        default = configs[0]
    if default is not None:
        rows.append((connector, "__default__", default.get("config_id"), 1, agent_id,
                     _allow_imports(default), _health(default)))
    return rows


def _ensure_config_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(connector_configs)")}
    for col, typ in (("allow_imports", "INTEGER"), ("health_status", "TEXT")):
        if col not in cols:
            conn.execute(f"ALTER TABLE connector_configs ADD COLUMN {col} {typ}")


def write_connector_configs(conn: sqlite3.Connection, members: list[dict]) -> tuple[int, int]:
    """Replace connector_configs from the connector rows. Returns (connectors, rows).

    ``members`` are connector-listing rows (each with a ``configuration`` list).
    A row may carry ``_agent_id``: the remote agent its configs live on (``''``
    or absent = the hub). See :func:`fetch_all_connector_configs`.
    """
    _migrate_connector_configs_agent(conn)  # older catalogs: add agent_id first
    _ensure_config_columns(conn)
    conn.execute("DELETE FROM connector_configs")
    n_conn = 0
    all_rows: list[tuple] = []
    for m in members:
        name = m.get("name")
        configs = m.get("configuration") or []
        if not name or not configs:
            continue
        rows = _rows_for(name, configs, m.get("_agent_id") or "")
        if rows:
            n_conn += 1
            all_rows.extend(rows)
    conn.executemany(
        "INSERT OR REPLACE INTO connector_configs "
        "(connector, config_name, config_id, is_default, agent_id, allow_imports, health_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        all_rows,
    )
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/integration/connectors/",
        method="live_api_get", status="tested_pass",
        notes=f"connectors_with_config={n_conn}, rows={len(all_rows)}",
    )
    return n_conn, len(all_rows)


def _paged(client, url: str, params: dict) -> list[dict]:
    """All ``data`` rows of an integration-API listing (follows ``nextPage``)."""
    out: list[dict] = []
    page = 1
    while True:
        body = client.get(url, params={**params, "page": page})
        rows = body.get("data", []) if isinstance(body, dict) else (body or [])
        out.extend(r for r in rows if isinstance(r, dict))
        if not (isinstance(body, dict) and body.get("nextPage")) or not rows:
            return out
        page += 1


def fetch_agents(client) -> tuple[dict[str, str], str | None]:
    """``({agent name: agentId}, self_agent_id)``.

    Remote agents come from ``/api/3/agents``. The hub's own agent is not listed
    there; its id is the ``agent`` stamped on the hub's connector records.
    """
    body = client.get(AGENTS_URL, params={"$limit": 2147483647})
    members = body.get("hydra:member", []) if isinstance(body, dict) else []
    agents = {a["name"]: a["agentId"] for a in members
              if isinstance(a, dict) and a.get("name") and a.get("agentId")}
    hub = _paged(client, CONNECTORS_URL, dict(CONFIG_LIST_PARAMS))
    ids = [r.get("agent") for r in hub if r.get("agent")]
    self_id = max(set(ids), key=ids.count) if ids else None
    return agents, self_id


def fetch_all_connector_configs(client) -> tuple[list[dict], dict[str, str], str | None]:
    """Every config on the box as connector rows for :func:`write_connector_configs`.

    Returns ``(members, agents, self_id)``. Each member is ``{name, _agent_id,
    configuration: [...]}``: one per (connector, agent). Hub configs get
    ``_agent_id=''``; a remote agent's configs get its ``agentId``. Connector ids
    on agent configs point at the agent's own connector record, which only the
    ``?agent=<agentId>`` listing returns, so each such agent is listed once.
    """
    agents, self_id = fetch_agents(client)
    configs = _paged(client, CONFIGURATION_URL, {"page_size": 1000, "format": "json"})
    by_agent: dict[str, list[dict]] = {}
    for c in configs:
        by_agent.setdefault(c.get("agent") or "", []).append(c)
    conn_name: dict[tuple[str, int], str] = {}
    for agent in by_agent:
        params = dict(CONFIG_LIST_PARAMS)
        if agent and agent != self_id:
            params["agent"] = agent
        for r in _paged(client, CONNECTORS_URL, params):
            if r.get("id") is not None and r.get("name"):
                conn_name[(agent, r["id"])] = r["name"]
    grouped: dict[tuple[str, str], list[dict]] = {}
    for agent, rows in by_agent.items():
        aid = "" if (not agent or agent == self_id) else agent
        for c in rows:
            name = conn_name.get((agent, c.get("connector")))
            if name:
                grouped.setdefault((name, aid), []).append(c)
    members = [{"name": n, "_agent_id": a, "configuration": cfgs}
               for (n, a), cfgs in sorted(grouped.items())]
    return members, agents, self_id


def write_agents(conn: sqlite3.Connection, agents: dict[str, str], self_id: str | None) -> int:
    conn.execute("DELETE FROM agents")
    rows = [(n, a, 0) for n, a in agents.items()]
    if self_id:
        rows.append((SELF_AGENT, self_id, 1))
    conn.executemany("INSERT OR REPLACE INTO agents (name, agent_id, is_self) VALUES (?, ?, ?)", rows)
    return len(rows)


def configs_fingerprint(members: list[dict]) -> str:
    """A stable hash of (connector, agent, config name, config id) -- the freshness key."""
    import hashlib
    items = sorted(
        (m.get("name") or "", m.get("_agent_id") or "", c.get("name") or "", c.get("config_id") or "")
        for m in members for c in (m.get("configuration") or [])
    )
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:16]


# ----------------------- concurrency and the connector definition cache -----------------------

#: Box-specific keys on a connector detail. The rest is the definition, identical on
#: every box for one (name, version) of a Fortinet RPM install.
_BOX_KEYS = frozenset({
    "configuration", "id", "agent", "created", "modified", "status", "config_count",
    "install_result", "remote_status", "installed", "requirements_installed", "active",
})
_SAFE_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}$")


def _warm_workers() -> int:
    try:
        return max(1, int(os.environ.get("FSRPB_WARM_WORKERS", "8")))
    except ValueError:
        return 8


def _parallel(tasks: dict[str, Callable[[], Any]]) -> dict[str, Any]:
    """Run independent reads at once. Each value is the result or the exception raised."""
    if not tasks:
        return {}
    out: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=min(_warm_workers(), len(tasks))) as ex:
        futures = {key: ex.submit(fn) for key, fn in tasks.items()}
        for key, fut in futures.items():
            try:
                out[key] = fut.result()
            except Exception as e:  # noqa: BLE001 - the caller decides per section
                out[key] = e
    return out


def defs_cache_root() -> Path:
    env = os.environ.get("FSRPB_DEFS_CACHE")
    if env:
        return Path(env)
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "fsr_playbooks" / "connector_defs"


def _def_cache_path(summary: dict, base_url: str) -> Path | None:
    """Where a connector definition is cached, or None when its name is unsafe as a path.

    A Fortinet RPM install is the same on every box, so it is shared across boxes.
    Anything else (an uploaded or locally built connector) is cached for its box only,
    keyed by its install time, because one name and version can differ between boxes.
    """
    name, ver = str(summary.get("name") or ""), str(summary.get("version") or "")
    if not (_SAFE_PART.match(name) and _SAFE_PART.match(ver)) or ".." in name or ".." in ver:
        return None
    root = defs_cache_root()
    if summary.get("rpm_installed") is True and str(summary.get("publisher") or "").startswith("Fortinet"):
        return root / "shared" / f"{name}@{ver}.json"
    stamp = hashlib.sha256(str(summary.get("modified") or "").encode()).hexdigest()[:12]
    return root / _catalog_meta.base_url_hash(base_url) / f"{name}@{ver}@{stamp}.json"


def _read_def(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _write_def(path: Path, definition: dict) -> None:
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        with os.fdopen(fd, "w") as fh:
            json.dump(definition, fh)
        os.replace(tmp, path)


def fetch_connector_details(client, summaries: list[dict]) -> tuple[list[dict], list[str], dict[str, int]]:
    """Each listed connector's detail: from the definition cache, else fetched in parallel.

    Returns ``(details, errors, {"cached": n, "fetched": n})``. A cached definition is
    merged with the box's own listing row, so per-box fields (configurations, ids,
    status) always come from this box.
    """
    base_url = client.base_url
    out: list[dict | None] = [None] * len(summaries)
    todo: list[tuple[int, dict, Path | None]] = []
    stats = {"cached": 0, "fetched": 0}
    for i, summ in enumerate(summaries):
        path = _def_cache_path(summ, base_url)
        cached = _read_def(path) if path else None
        if cached is not None:
            out[i] = {**cached, **{k: summ[k] for k in _BOX_KEYS if k in summ}}
            stats["cached"] += 1
        else:
            todo.append((i, summ, path))

    def one(item: tuple[int, dict, Path | None]) -> tuple[int, dict]:
        i, summ, path = item
        detail = client.post(f"/api/integration/connectors/{summ['name']}/{summ['version']}/?format=json", data={})
        if not isinstance(detail, dict):
            raise ValueError(f"detail not dict ({type(detail).__name__})")
        if path is not None:
            _write_def(path, {k: v for k, v in _strip_icons(detail).items() if k not in _BOX_KEYS})
        return i, detail

    errors: list[str] = []
    results = _parallel({str(i): partial(one, item) for i, item in enumerate(todo)})
    for key, res in results.items():
        _, summ, _ = todo[int(key)]
        if isinstance(res, Exception):
            errors.append(f"{summ.get('name')} {summ.get('version')}: {res!r}")
        else:
            out[res[0]] = res[1]
            stats["fetched"] += 1
    return [d for d in out if d is not None], errors, stats


def _in_filter(names: Iterable[str]) -> str | None:
    vals = sorted({n for n in names if n and "|" not in n})
    return "|".join(vals) if vals else None


def fetch_module_metadata(client, modules: Iterable[str]) -> list[dict]:
    """Staging metadata for just these modules, in one call."""
    flt = _in_filter(modules)
    if flt is None:
        return []
    body = _get(client, "/api/3/staging_model_metadatas",
                {"type$in": flt, "$relationships": "true", "$limit": 500}).json()
    return body.get("hydra:member", []) if isinstance(body, dict) else []


def fetch_picklists_body(client, names: Iterable[str]) -> dict:
    """A picklist_names body holding just these lists, in one call."""
    flt = _in_filter(names)
    if flt is None:
        return {"hydra:member": []}
    resp = _get(client, "/api/3/picklist_names",
                {"name$in": flt, "$relationships": "true", "$limit": 1000})
    body = resp.json()
    return body if isinstance(body, dict) else {"hydra:member": []}


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

    tasks: dict[str, Callable[[], Any]] = {
        "tags": lambda: _get(client, TAGS_URL),
        "teams": lambda: _get(client, TEAMS_URL),
        "metadata": lambda: _get(client, METADATA_URL),
    }
    if picklists_body is None:
        tasks["picklists"] = lambda: _get(client, PICKLISTS_URL)
    got = _parallel(tasks)

    try:
        picklist_resp = None
        if picklists_body is None:
            if isinstance(got["picklists"], Exception):
                raise got["picklists"]
            picklist_resp = got["picklists"]
            picklists_body = picklist_resp.json()
        picklist_items, picklist_lists, items_rows, n_lists = parse_picklists(picklists_body)
    except Exception as e:  # noqa: BLE001
        raise WarmupFatal(f"picklists: {e!r}") from e
    if picklist_resp is not None:
        _note_etag(etags, "picklists", picklist_resp)

    tag_rows: list[tuple[str, str]] | None = None
    try:
        if isinstance(got["tags"], Exception):
            raise got["tags"]
        tag_rows = _tag_rows(got["tags"].json().get("hydra:member") or [])
        _note_etag(etags, "tags", got["tags"])
    except Exception as e:  # noqa: BLE001
        errors.append(f"tags: {e!r}")

    team_rows: list[tuple[str, str]] | None = None
    try:
        if isinstance(got["teams"], Exception):
            raise got["teams"]
        team_rows = _team_rows(got["teams"].json().get("hydra:member") or [])
    except Exception as e:  # noqa: BLE001
        errors.append(f"teams: {e!r}")

    try:
        if isinstance(got["metadata"], Exception):
            raise got["metadata"]
        metadata_resp = got["metadata"]
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
    tasks: dict[str, Callable[[], Any]] = {
        "version": lambda: client.get("/api/version"),  # public, ~25 B -- Tier-0 upgrade gate
        "publish": lambda: client.get("/api/publish/error"),  # appliance-wide publish watermark
        "serial": lambda: live_license_serial(client),
    }
    for coll in COUNT_COLLECTIONS:
        tasks[f"count:{coll}"] = partial(client.get, f"/api/3/{coll}?$limit=0")
    got = _parallel(tasks)
    v, p = got["version"], got["publish"]
    fsr_version = v.get("version") if isinstance(v, dict) else None
    last_publish = p.get("last_publish_time") if isinstance(p, dict) else None
    serial = got["serial"] if isinstance(got["serial"], str) else None
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
        r = got[f"count:{coll}"]
        total = r.get("hydra:totalItems") if isinstance(r, dict) else None
        if isinstance(total, int):
            _catalog_meta.record_count(conn, coll, total)
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

    with ThreadPoolExecutor(max_workers=2) as ex:
        listing_f = ex.submit(client.get, CONNECTORS_URL, params=INSTALLED_LIST_PARAMS)
        configs_f = ex.submit(fetch_all_connector_configs, client)
        n_mod, n_fld, mod_errs, mod_etags = warm_modules(conn, client)
        try:
            listing: Any = listing_f.result()
        except Exception as e:  # noqa: BLE001
            listing = e
        try:
            configs_res: Any = configs_f.result()
        except Exception as e:  # noqa: BLE001
            configs_res = e
    etags.update(mod_etags)
    errors.extend(mod_errs)

    _, conn_errs = load_installed_connectors(conn, client, replace=True, listing=listing)
    errors.extend(conn_errs)

    if isinstance(configs_res, Exception):
        errors.append(f"connector_configs: {configs_res!r}")
    else:
        members, agents, self_id = configs_res
        write_connector_configs(conn, members)
        write_agents(conn, agents, self_id)
        _catalog_meta.set_(conn, "configs_fingerprint", configs_fingerprint(members))

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


def box_catalog_path(base_url: str, cache_dir: str | Path | None = None) -> Path:
    """The one catalog file for a box, shared by every tool that compiles for it."""
    root = Path(cache_dir) if cache_dir else Path(
        os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "fsr_playbooks" / "boxes"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"catalog-{_catalog_meta.base_url_hash(base_url)}.db"


def _remove_catalog(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _full_warm(client, path: Path, instance_label: str | None) -> None:
    fresh = not path.exists()
    try:
        report = warm_catalog(client, path, instance_label=instance_label, seed_from=PACKAGED_SLIM_DB)
        if not report.get("committed"):
            raise WarmupError(f"warming the catalog for {client.base_url} failed: {report.get('errors')}")
        conn = sqlite3.connect(path)
        try:
            for key in [k for k in _catalog_meta.get_all(conn) if k.startswith("scope:")]:
                _catalog_meta.set_(conn, key, None)
            _catalog_meta.set_(conn, "scope:full", _utcnow())
            _catalog_meta.set_(conn, "probed_at", str(time.time()))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # A failed first warm leaves only the seed copy: another box's catalog
        # under this box's name. Remove it so the next call retries.
        if fresh:
            _remove_catalog(path)
        raise


def _stamp_probed(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        _catalog_meta.set_(conn, "probed_at", str(time.time()))
        conn.commit()
    finally:
        conn.close()


def _recheck_seconds() -> float:
    try:
        return float(os.environ.get("FSRPB_WARM_RECHECK", "30"))
    except ValueError:
        return 30.0


def _total(r: Any) -> int | None:
    t = r.get("hydra:totalItems") if isinstance(r, dict) else None
    return t if isinstance(t, int) else None


def warm_for_playbook(client, path: Path, playbook: str, *,
                      instance_label: str | None = None) -> dict[str, Any]:
    """Warm only what ``playbook`` uses into the box's catalog at ``path``.

    Fetches the definitions, configurations and health of the connectors its steps
    call, the metadata of the modules its record steps touch, and the picklists those
    fields bind to (plus any named in Jinja). What is already warmed and still
    current is not fetched again. Freshness is judged from cheap reads made in
    parallel (row counts, the connector listing, the configurations), and skipped
    entirely within ``$FSRPB_WARM_RECHECK`` seconds (default 30) of the last check.
    Returns a report of what was fetched.
    """
    from .playbook_needs import playbook_needs

    needs = playbook_needs(playbook)
    started = time.perf_counter()
    report: dict[str, Any] = {"level": "targeted", "db": str(path), "fetched": {}, "errors": []}
    first = not (path.exists() and path.stat().st_size)
    _seed_if_absent(path, PACKAGED_SLIM_DB)
    conn = _open(path)
    try:
        ensure_schema(conn)
        meta = _catalog_meta.get_all(conn)
        status, _, _ = _catalog_meta.check_instance(conn, client.base_url)
        if status == "mismatch":
            report["level"] = "mismatch"
            return report
        full = "scope:full" in meta

        def have(kind: str, name: str) -> bool:
            return full or f"scope:{kind}:{name}" in meta

        installed = {r[0]: r[1] for r in conn.execute("SELECT name, version FROM connectors")}
        missing = ([c for c in needs.connectors if not have("connector", c) or c not in installed]
                   + [m for m in needs.modules if not have("module", m)]
                   + [p for p in needs.picklists if not have("picklist", p)])
        probed_at = float(meta.get("probed_at") or 0)
        if not first and not missing and time.time() - probed_at < _recheck_seconds():
            report["seconds"] = round(time.perf_counter() - started, 3)
            return report

        probes: dict[str, Callable[[], Any]] = {
            f"count:{c}": partial(client.get, f"/api/3/{c}?$limit=0") for c in COUNT_COLLECTIONS}
        probes["listing"] = lambda: client.get(CONNECTORS_URL, params=INSTALLED_LIST_PARAMS)
        probes["configs"] = lambda: fetch_all_connector_configs(client)
        got = _parallel(probes)

        changed = {c for c in COUNT_COLLECTIONS
                   if _total(got[f"count:{c}"]) is not None
                   and str(_total(got[f"count:{c}"])) != meta.get(f"count:{c}")}
        modules_stale = bool(changed & {"model_metadatas", "attribute_metadatas"}) and not first
        picklists_stale = bool(changed & {"picklists", "picklist_names"}) and not first
        if modules_stale or picklists_stale:
            for key in [k for k in meta if k == "scope:full"
                        or (modules_stale and k.startswith("scope:module:"))
                        or (picklists_stale and k.startswith("scope:picklist:"))]:
                _catalog_meta.set_(conn, key, None)
                meta.pop(key, None)
            full = False

        listing = got["listing"]
        summaries = {x["name"]: x for x in (listing.get("data", []) if isinstance(listing, dict) else [])
                     if x.get("name") and x.get("version")}
        conn_todo = [summaries[c] for c in sorted(needs.connectors)
                     if c in summaries and installed.get(c) != summaries[c]["version"]]
        mod_todo = sorted(m for m in needs.modules if modules_stale or not have("module", m))
        tags_todo = first or "tags" in changed or not have("box", "tags")

        stage1: dict[str, Callable[[], Any]] = {}
        if mod_todo:
            stage1["modules"] = lambda: fetch_module_metadata(client, mod_todo)
        if conn_todo:
            stage1["connectors"] = lambda: fetch_connector_details(client, conn_todo)
        if tags_todo:
            stage1["tags"] = lambda: _get(client, TAGS_URL).json()
            stage1["teams"] = lambda: _get(client, TEAMS_URL).json()
        s1 = _parallel(stage1)

        mods_res = s1.get("modules")
        members: list[dict] = mods_res if isinstance(mods_res, list) else []
        if isinstance(s1.get("modules"), Exception):
            report["errors"].append(f"modules: {s1['modules']!r}")
        bound: set[str] = set(needs.picklists)
        for m in members:
            for attr in m.get("attributes") or []:
                name = _picklist_list_name(attr) if isinstance(attr, dict) else None
                if name:
                    bound.add(name)
        for mod in needs.modules:
            bound.update(r[0] for r in conn.execute(
                "SELECT DISTINCT picklist_name FROM module_fields WHERE module_name = ? "
                "AND picklist_name IS NOT NULL", (mod,)))
        pl_todo = sorted(n for n in bound if picklists_stale or not have("picklist", n)
                         or any(m.get("type") for m in members))
        picklist_lists: dict[str, list[str]] = {}
        if pl_todo:
            try:
                _, picklist_lists, items_rows, n_lists = parse_picklists(fetch_picklists_body(client, pl_todo))
                write_picklists(conn, items_rows, n_lists, only=pl_todo)
                for n in pl_todo:
                    _catalog_meta.set_(conn, f"scope:picklist:{n}", _utcnow())
                report["fetched"]["picklists"] = pl_todo
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"picklists: {e!r}")
        if members:
            write_modules(conn, members, picklist_lists, replace_all=False)
            for m in members:
                _catalog_meta.set_(conn, f"scope:module:{m['type']}", _utcnow())
            report["fetched"]["modules"] = [m["type"] for m in members]

        res = s1.get("connectors")
        if isinstance(res, Exception):
            report["errors"].append(f"connectors: {res!r}")
        elif res is not None:
            details, errs, stats = res
            for d in details:
                upsert_connector_detail(conn, d, source="live_api_get")
                _catalog_meta.set_(conn, f"scope:connector:{d.get('name')}", str(d.get("version")))
            report["errors"].extend(errs)
            report["fetched"]["connectors"] = [d.get("name") for d in details]
            report["fetched"]["connector_defs_from_cache"] = stats["cached"]

        cfg = got["configs"]
        if isinstance(cfg, Exception):
            report["errors"].append(f"connector_configs: {cfg!r}")
        else:
            cmembers, agents, self_id = cfg
            fp = configs_fingerprint(cmembers)
            if first or fp != meta.get("configs_fingerprint") or not have("box", "configs"):
                write_connector_configs(conn, cmembers)
                write_agents(conn, agents, self_id)
                _catalog_meta.set_(conn, "configs_fingerprint", fp)
                _catalog_meta.set_(conn, "scope:box:configs", _utcnow())
                report["fetched"]["configs"] = True

        if tags_todo:
            if not isinstance(s1.get("tags"), Exception):
                write_tags(conn, _tag_rows(s1["tags"].get("hydra:member") or []))
            if not isinstance(s1.get("teams"), Exception):
                write_teams(conn, _team_rows(s1["teams"].get("hydra:member") or []))
            _catalog_meta.set_(conn, "scope:box:tags", _utcnow())
            report["fetched"]["tags_teams"] = True

        if status != "ok":
            stamp_provenance(conn, client, instance_label=instance_label)
        else:
            for c in COUNT_COLLECTIONS:
                total = _total(got[f"count:{c}"])
                if total is not None:
                    _catalog_meta.record_count(conn, c, total)
        _catalog_meta.set_(conn, "probed_at", str(time.time()))
        conn.commit()
    except Exception:
        conn.rollback()
        if first:
            conn.close()
            _remove_catalog(path)
            raise
        raise
    finally:
        with contextlib.suppress(Exception):
            conn.close()
    report["seconds"] = round(time.perf_counter() - started, 3)
    return report


def box_catalog(
    client,
    cache_dir: str | Path | None = None,
    *,
    instance_label: str | None = None,
    playbook: str | None = None,
    full: bool = False,
) -> Path:
    """The reference catalog for ``client``'s box, warmed to the level asked for.

    One file per box under ``cache_dir`` (default ``$XDG_CACHE_HOME`` or
    ``~/.cache``, then ``fsr_playbooks/boxes``), named by the box's normalized URL
    hash, so every tool compiling for that box shares it and switching boxes is a
    file switch, never a re-warm. New files are seeded from the packaged catalog.

    - ``playbook=<yaml>``: targeted. Only the connectors, modules and picklists that
      playbook uses are fetched, and only when missing or stale (see
      :func:`warm_for_playbook`).
    - ``full=True``: everything is re-read now, sections in parallel.
    - neither: everything, when the file is missing, stamped for another box, or the
      box's module/field totals or connector configurations changed since the last warm.

    Returns the path for ``compile_yaml``.
    """
    path = box_catalog_path(client.base_url, cache_dir)
    if full:
        _full_warm(client, path, instance_label)
        return path
    if playbook is not None:
        rep = warm_for_playbook(client, path, playbook, instance_label=instance_label)
        if rep.get("level") == "mismatch":
            _remove_catalog(path)
            _full_warm(client, path, instance_label)
        return path
    if path.exists() and path.stat().st_size:
        conn = sqlite3.connect(path)
        try:
            status, _, _ = _catalog_meta.check_instance(conn, client.base_url)
            recorded = {c: _catalog_meta.get(conn, f"count:{c}") for c in _FRESHNESS_COLLECTIONS}
            recorded_fp = _catalog_meta.get(conn, "configs_fingerprint")
            is_full = _catalog_meta.get(conn, "scope:full") is not None or recorded_fp is not None
            probed = _catalog_meta.get(conn, "probed_at")
        finally:
            conn.close()
        try:
            recent = probed is not None and time.time() - float(probed) < _recheck_seconds()
        except ValueError:
            recent = False
        if status == "ok" and is_full and recent:
            return path
        got = _parallel({"counts": lambda: _live_counts(client),
                         "configs": lambda: fetch_all_connector_configs(client)[0]})
        live = got["counts"] if isinstance(got["counts"], dict) else {c: None for c in _FRESHNESS_COLLECTIONS}
        live_fp = configs_fingerprint(got["configs"]) if isinstance(got["configs"], list) else None
        if status == "ok" and is_full and all(
                live[c] is not None and str(live[c]) == recorded[c] for c in _FRESHNESS_COLLECTIONS) \
                and (live_fp is None or live_fp == recorded_fp):
            _stamp_probed(path)
            return path
    _full_warm(client, path, instance_label)
    return path
