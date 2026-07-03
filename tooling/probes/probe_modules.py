"""probe_modules — populate modules / module_fields from a live FSR.

Live source:
  GET /api/3/staging_model_metadatas?$limit=...&$orderby=type&$relationships=true
      → every module + its `attributes[]` inline (the `$relationships=true`
        flag is the magic param; without it `attributes` is null).
  GET /api/3/picklist_names?$limit=...&$relationships=true
      → picklists with their items inlined, used to resolve picklist @id refs
        on attribute defaults.

Trust ladder:
  module existence:    tested_pass via live_api_get
  field declaration:   seen via live_api_get (declared on the box, not exercised)
  picklist values:     tested_pass via live_api_get (we read them directly)

Local fallback:
  fortisoar/schema.json (snapshot) — written as `seen` only.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path
from typing import Any

from . import _env
from .common import (
    SCHEMA_JSON_PATH,
    conditional_refetch,
    probe_session,
    record_verification,
    wipe_probe_tables,
)

PROBE_NAME = "probe_modules"

METADATA_URL = (
    "/api/3/staging_model_metadatas"
    "?$limit=2147483647&$orderby=type&$relationships=true"
)
PICKLISTS_URL = (
    "/api/3/picklist_names"
    "?$export=false&$limit=2147483647&$orderby=name&$relationships=true"
)
TAGS_URL = "/api/3/tags?$limit=2147483647&$orderby=name"
TEAMS_URL = "/api/3/teams?$limit=2147483647&$orderby=name"


def _scalarize(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bytes)):
        return v
    return json.dumps(v)


def _bool(v: Any) -> int:
    return 1 if v else 0


def _is_required(validation: Any) -> bool:
    return isinstance(validation, dict) and validation.get("required") is True


def _resolve_default(raw: Any, picklist_items: dict[str, str]) -> Any:
    """If defaultValue is a `/api/3/picklists/{uuid}` ref, swap in itemValue."""
    if isinstance(raw, str) and raw.startswith("/api/3/picklists/"):
        return picklist_items.get(raw, raw)
    return raw


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


def _picklist_options_for(attr: dict, picklist_lists: dict[str, list[str]]) -> list[str] | None:
    """Extract picklist option strings if the attribute references one."""
    list_name = _picklist_list_name(attr)
    if list_name is None:
        return None
    return picklist_lists.get(list_name)


def _insert_module(conn: sqlite3.Connection, m: dict) -> str | None:
    name = m.get("type") or m.get("module")
    if not name:
        return None
    conn.execute(
        """INSERT OR REPLACE INTO modules (name, label, plural, description)
           VALUES (?, ?, ?, ?)""",
        (
            name,
            _scalarize(m.get("displayName") or m.get("module") or name),
            _scalarize(m.get("module")),
            _scalarize(m.get("descriptions")),
        ),
    )
    return name


def _insert_field(
    conn: sqlite3.Connection,
    *,
    module: str,
    attr: dict,
    picklist_items: dict[str, str],
    picklist_lists: dict[str, list[str]],
) -> None:
    name = attr.get("name")
    if not name:
        return
    options = _picklist_options_for(attr, picklist_lists)
    list_name = _picklist_list_name(attr)
    conn.execute(
        """INSERT OR REPLACE INTO module_fields
           (module_name, field_name, title, type, required,
            picklist_options, tooltip, picklist_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            module,
            name,
            _scalarize(attr.get("title") or attr.get("displayName") or name),
            _scalarize(attr.get("type") or attr.get("formType")),
            _bool(_is_required(attr.get("validation"))),
            json.dumps(options) if options else None,
            _scalarize(attr.get("tooltip")),
            list_name,
        ),
    )


# ----------------------- live -----------------------

def _parse_picklists(body: Any) -> tuple[dict[str, str], dict[str, list[str]],
                                          list[tuple[str, str, str]], int]:
    """Parse a picklist_names JSON body into (item_id_to_value,
    list_name_to_options, items_rows, totalItems). Fetch-agnostic so the
    conditional-refetch path can reuse it without a double-GET.
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


def _load_picklists(client) -> tuple[dict[str, str], dict[str, list[str]],
                                      list[tuple[str, str, str]], int, str | None]:
    """Returns (item_id_to_value, list_name_to_options, items_rows, totalItems, etag).

    `items_rows` is a list of (list_name, item_value, item_iri) tuples,
    ready for bulk-insertion into the `picklists` table. `etag` is the
    ETag response header (if present), for use in Tier-2 freshness checks.
    """
    resp = client.session.get(
        client.base_url + PICKLISTS_URL,
        verify=client.verify_ssl,
    )
    resp.raise_for_status()
    return (*_parse_picklists(resp.json()), resp.headers.get("ETag"))


def _live(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, 0, ["env not configured"]
    errors: list[str] = []

    # Tier-2 conditional refetch (opt-in via FSR_CONDITIONAL_REFETCH), keyed on
    # the picklists collection. Coarse-grained: a fresh/unchanged picklists
    # response skips the whole re-derive (all collections current); a refreshed
    # 200 wipes + re-derives everything (tags/teams/metadata are re-fetched on
    # the refreshed path — the rare case). Per-collection ETags (tags /
    # model_metadatas) are still recorded on the refreshed path; conditional_refetch
    # owns the picklists ETag + data_warmed_at, so the legacy recording below is
    # skipped for picklists on this path. The non-conditional path leaves the wipe
    # to main() (current behavior).
    conditional = _env.is_conditional_enabled()
    picklists_etag: str | None = None
    if conditional:
        outcome, payload = conditional_refetch(
            client, url=PICKLISTS_URL, conn=conn, collection="picklists",
        )
        if outcome in ("fresh", "unchanged"):
            print(f"[{PROBE_NAME}] conditional_refetch: {outcome} "
                  f"(catalog current; skipped rewrite)")
            return 0, 0, []
        if outcome == "error":
            return 0, 0, [str(payload)]
        # refreshed: wipe + clear module verifications before re-deriving.
        wipe_probe_tables(conn, PROBE_NAME)
        conn.execute(
            "DELETE FROM verifications WHERE kind IN ('module','module_field') "
            "AND method IN ('live_api_get','schema_json')"
        )
        picklist_items, picklist_lists, items_rows, n_pl = _parse_picklists(payload)
        # picklists_etag stays None — conditional_refetch recorded it.
    else:
        try:
            picklist_items, picklist_lists, items_rows, n_pl, picklists_etag = _load_picklists(client)
        except Exception as e:  # noqa: BLE001
            return 0, 0, [f"picklists: {e!r}"]
    # Persist (list_name, item_value, item_iri) so the resolver can map
    # friendly picklist tokens in record-write payloads to IRIs without
    # an online lookup.
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
        notes=f"picklists={n_pl}, items={len(items_rows)}",
    )

    # Tags catalog — drives compile-time validation of
    # set_variable.message.tags so the agent can't ship a playbook that
    # silently creates a typo tag at runtime.
    tags_etag = None
    try:
        tags_resp = client.session.get(
            client.base_url + TAGS_URL,
            verify=client.verify_ssl,
        )
        tags_resp.raise_for_status()
        rt = tags_resp.json()
        tags_etag = tags_resp.headers.get("ETag")
        tag_rows: list[tuple[str, str]] = []
        for m in rt.get("hydra:member") or []:
            if not isinstance(m, dict):
                continue
            name = m.get("itemValue") or m.get("name")
            iri = m.get("@id")
            if name and iri:
                tag_rows.append((str(name), str(iri)))
        conn.execute("DELETE FROM tags")
        conn.executemany(
            "INSERT OR REPLACE INTO tags (name, iri) VALUES (?, ?)",
            tag_rows,
        )
        record_verification(
            conn, kind="api_endpoint",
            key="GET /api/3/tags",
            method="live_api_get", status="tested_pass",
            notes=f"tags={len(tag_rows)}",
        )
    except Exception as e:  # noqa: BLE001
        errors.append(f"tags: {e!r}")

    # Owner teams — populate the `teams` table so the resolver can map
    # playbook `owners:` friendly names to /api/3/teams/<uuid> IRIs.
    try:
        teams_resp = client.session.get(
            client.base_url + TEAMS_URL,
            verify=client.verify_ssl,
        )
        teams_resp.raise_for_status()
        tr = teams_resp.json()
        team_rows: list[tuple[str, str]] = []
        for m in tr.get("hydra:member") or []:
            if not isinstance(m, dict):
                continue
            name = m.get("name")
            iri = m.get("@id")
            if name and iri:
                team_rows.append((str(name), str(iri)))
        conn.execute("DELETE FROM teams")
        conn.executemany(
            "INSERT OR REPLACE INTO teams (name, iri) VALUES (?, ?)",
            team_rows,
        )
        record_verification(
            conn, kind="api_endpoint",
            key="GET /api/3/teams",
            method="live_api_get", status="tested_pass",
            notes=f"teams={len(team_rows)}",
        )
    except Exception as e:  # noqa: BLE001
        errors.append(f"teams: {e!r}")

    metadata_etag = None
    try:
        metadata_resp = client.session.get(
            client.base_url + METADATA_URL,
            verify=client.verify_ssl,
        )
        metadata_resp.raise_for_status()
        r = metadata_resp.json()
        metadata_etag = metadata_resp.headers.get("ETag")
    except Exception as e:  # noqa: BLE001
        return 0, 0, [f"metadata: {e!r}"]
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/staging_model_metadatas",
        method="live_api_get", status="tested_pass",
        notes="$relationships=true required for inline attributes",
    )

    members = r.get("hydra:member", [])
    n_modules = 0
    n_fields = 0
    for m in members:
        if not isinstance(m, dict) or not m.get("type"):
            continue
        module = _insert_module(conn, m)
        if not module:
            continue
        n_modules += 1
        record_verification(
            conn, kind="module", key=module,
            method="live_api_get", status="tested_pass",
        )
        for attr in m.get("attributes") or []:
            if not isinstance(attr, dict):
                continue
            _insert_field(
                conn, module=module, attr=attr,
                picklist_items=picklist_items,
                picklist_lists=picklist_lists,
            )
            n_fields += 1
            if attr.get("name"):
                record_verification(
                    conn, kind="module_field",
                    key=f"{module}:{attr['name']}",
                    method="live_api_get", status="seen",
                )

    _stamp_provenance(conn, client)

    # Record ETags for Tier-2 freshness checks (conditional re-pull on TTL expiry).
    # Best-effort: these are supplementary to the core warmup.
    from fsr_playbooks import _catalog_meta
    if picklists_etag:
        _catalog_meta.record_etag(conn, "picklists", picklists_etag)
    if tags_etag:
        _catalog_meta.record_etag(conn, "tags", tags_etag)
    if metadata_etag:
        _catalog_meta.record_etag(conn, "model_metadatas", metadata_etag)
    # Also record data_warmed_at timestamp for TTL tracking.
    _catalog_meta.record_data_warmed_at(conn)
    conn.commit()  # _stamp_provenance already committed, but re-record these for atomicity

    return n_modules, n_fields, errors


def _stamp_provenance(conn: sqlite3.Connection, client) -> None:
    """Record which instance (+ version / publish watermark) this catalog was
    warmed from, into ``_catalog_meta`` — drives the compile-time multi-instance
    guard and the Tier-0/Tier-1 freshness check. Best-effort: the two extra
    GETs are cheap and failure here must not fail the warmup."""
    from fsr_playbooks import _catalog_meta

    cfg = _env.get_config()
    fsr_version = None
    last_publish = None
    try:  # public, no-auth, ~25 B — Tier-0 upgrade gate
        v = client.get("/api/version")
        if isinstance(v, dict):
            fsr_version = v.get("version")
    except Exception:  # noqa: BLE001
        pass
    try:  # appliance-wide publish watermark — Tier-1 gate
        p = client.get("/api/publish/error")
        if isinstance(p, dict):
            last_publish = p.get("last_publish_time")
    except Exception:  # noqa: BLE001
        pass
    _catalog_meta.stamp_instance(
        conn,
        instance_label=cfg.instance_label,
        base_url=cfg.base_url,
        fsr_version=fsr_version,
        last_publish_time=last_publish,
    )
    # Baseline the cheap row counts so a later `check-fresh` can detect
    # add/delete drift (incl. picklist value adds that publish nothing).
    for coll in ("model_metadatas", "attribute_metadatas",
                 "picklists", "picklist_names", "tags"):
        try:
            r = client.get(f"/api/3/{coll}?$limit=0")
            total = r.get("hydra:totalItems") if isinstance(r, dict) else None
            if isinstance(total, int):
                _catalog_meta.record_count(conn, coll, total)
        except Exception:  # noqa: BLE001
            pass
    conn.commit()


# ----------------------- local fallback -----------------------

def _local(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    if not SCHEMA_JSON_PATH.exists():
        return 0, 0, [f"missing {SCHEMA_JSON_PATH}"]
    try:
        d = json.loads(SCHEMA_JSON_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        return 0, 0, [f"{SCHEMA_JSON_PATH}: {e!r}"]
    members = d.get("hydra:member") or []
    n_modules = 0
    n_fields = 0
    for m in members:
        if not isinstance(m, dict) or not m.get("type"):
            continue
        module = _insert_module(conn, m)
        if not module:
            continue
        n_modules += 1
        record_verification(
            conn, kind="module", key=module,
            method="schema_json", status="seen",
        )
        for attr in m.get("attributes") or []:
            if not isinstance(attr, dict):
                continue
            _insert_field(
                conn, module=module, attr=attr,
                picklist_items={}, picklist_lists={},
            )
            n_fields += 1
            if attr.get("name"):
                record_verification(
                    conn, kind="module_field",
                    key=f"{module}:{attr['name']}",
                    method="schema_json", status="seen",
                )
    return n_modules, n_fields, []


# ----------------------- entry -----------------------

def main() -> int:
    warnings.filterwarnings("ignore")
    cfg = _env.get_config()
    sources: list[Path] = []
    if cfg.is_live():
        sources.append(Path(cfg.base_url + METADATA_URL))

    with probe_session(PROBE_NAME, sources) as conn:
        # Idempotent migration for already-built DBs that predate the
        # picklists table / module_fields.picklist_name column.
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
        # Owner teams — drives compile-time resolution of playbook `owners:`
        # team names to /api/3/teams/<uuid> IRIs (so a private playbook can
        # be authored by team name, not raw UUID).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS teams ("
            "  name TEXT PRIMARY KEY,"
            "  iri  TEXT NOT NULL)"
        )
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(module_fields)").fetchall()}
        if "picklist_name" not in cols:
            conn.execute(
                "ALTER TABLE module_fields ADD COLUMN picklist_name TEXT"
            )
        # Default (always-re-pull) path wipes before _live rewrites. When
        # FSR_CONDITIONAL_REFETCH is on, _live owns the wipe (only on a refreshed
        # 200) so a fresh/unchanged outcome leaves existing rows intact.
        if not _env.is_conditional_enabled():
            wipe_probe_tables(conn, PROBE_NAME)
            conn.execute(
                "DELETE FROM verifications WHERE kind IN ('module','module_field') "
                "AND method IN ('live_api_get','schema_json')"
            )

        n_mod = n_fld = 0
        live_errs: list[str] = []
        if cfg.is_live():
            n_mod, n_fld, live_errs = _live(conn)

        local_errs: list[str] = []
        if (not cfg.is_live()) or n_mod == 0:
            n_mod, n_fld, local_errs = _local(conn)
            sources.append(SCHEMA_JSON_PATH)

        notes = json.dumps({
            "modules": n_mod, "fields": n_fld,
            "errors": (live_errs + local_errs)[:30],
            "instance_label": cfg.instance_label,
        })
        conn.execute(
            "UPDATE _probe_runs SET notes = ? "
            "WHERE id = (SELECT MAX(id) FROM _probe_runs WHERE probe_name = ?)",
            (notes, PROBE_NAME),
        )
        print(f"[{PROBE_NAME}] modules={n_mod}  fields={n_fld}  "
              f"errors={len(live_errs)+len(local_errs)}")
        for e in (live_errs + local_errs)[:10]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
