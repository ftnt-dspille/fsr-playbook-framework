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


def _picklist_options_for(attr: dict, picklist_lists: dict[str, list[str]]) -> list[str] | None:
    """Extract picklist option strings if the attribute references one."""
    ds = attr.get("dataSource") or {}
    if not isinstance(ds, dict):
        return None
    # The data source filter contains: filters: [{field:'listName__name', value:'AlertStatus'}]
    query = ds.get("query") or {}
    for f in query.get("filters", []) or []:
        if isinstance(f, dict) and f.get("field") == "listName__name":
            list_name = f.get("value")
            if isinstance(list_name, str):
                return picklist_lists.get(list_name)
    return None


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
    default = _resolve_default(attr.get("defaultValue"), picklist_items)
    conn.execute(
        """INSERT OR REPLACE INTO module_fields
           (module_name, field_name, title, type, required, picklist_options, tooltip)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            module,
            name,
            _scalarize(attr.get("title") or attr.get("displayName") or name),
            _scalarize(attr.get("type") or attr.get("formType")),
            _bool(_is_required(attr.get("validation"))),
            json.dumps(options) if options else None,
            _scalarize(attr.get("tooltip")),
        ),
    )


# ----------------------- live -----------------------

def _load_picklists(client) -> tuple[dict[str, str], dict[str, list[str]], int]:
    """Returns (item_id_to_value, list_name_to_options, totalItems)."""
    r = client.get(PICKLISTS_URL)
    members = r.get("hydra:member", [])
    item_id_to_value: dict[str, str] = {}
    list_name_to_options: dict[str, list[str]] = {}
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
        if name:
            list_name_to_options[name] = opts
    return item_id_to_value, list_name_to_options, len(members)


def _live(conn: sqlite3.Connection) -> tuple[int, int, list[str]]:
    client = _env.get_client()
    if client is None:
        return 0, 0, ["env not configured"]
    errors: list[str] = []

    try:
        picklist_items, picklist_lists, n_pl = _load_picklists(client)
    except Exception as e:  # noqa: BLE001
        return 0, 0, [f"picklists: {e!r}"]
    record_verification(
        conn, kind="api_endpoint",
        key="GET /api/3/picklist_names",
        method="live_api_get", status="tested_pass",
        notes=f"picklists={n_pl}",
    )

    try:
        r = client.get(METADATA_URL)
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
    return n_modules, n_fields, errors


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
