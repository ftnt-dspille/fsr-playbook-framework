"""Teach the reference store about a single connector.

`fsrpb refresh` rebuilds the whole catalog from every probe, which is far too
big a hammer when the only thing that changed is "I just wrote a new connector"
or "I just installed one on the box". Until the catalog knows it, the compiler
rejects every step that references it:

    [unknown_connector] playbooks[0].steps[1].arguments.connector:
        unknown connector: 'fortinet-fortisiemv2'
        -> did you mean 'fortinet-fortisiem'?

...and `fsrpb validate` / `push` refuse to run. This module warms exactly one
connector, from either of the two places a connector can exist:

  * **local** -- a connector source directory (or its ``info.json``). This is
    the case the compiler cannot recover from on its own: a connector being
    developed has never been installed anywhere, so no live probe can see it.

  * **instance** -- installed on the configured FortiSOAR. Pulls the same
    operation/parameter definitions the appliance reports.

The compiler reads SQLite directly (``resolver/catalog.py``), so an upsert here
takes effect on the very next compile -- there is no JSON snapshot to
regenerate.

Usage:
    fsrpb provision ~/src/fortinet-fortisiemv2      # from local source
    fsrpb provision --from-instance fortinet-fortisiemv2
    fsrpb provision --check fortinet-fortisiemv2    # what does the store know?
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sqlite3
import sys
from typing import Any, Optional

# Source tags written to `connectors.source`, matching the existing probe
# vocabulary ('live_api_get' | 'rpm_info_json' | ...).
SOURCE_LOCAL = "local_info_json"
SOURCE_LIVE = "live_api_get"


# --------------------------------------------------------------------------
# info.json -> store rows
# --------------------------------------------------------------------------

def _resolve_info_json(path: str) -> pathlib.Path:
    """Accept either a connector directory or a direct info.json path."""
    p = pathlib.Path(path).expanduser().resolve()
    if p.is_dir():
        p = p / "info.json"
    if not p.is_file():
        raise SystemExit(f"no info.json at {p}")
    return p


def _as_int(val: Any, default: int = 0) -> int:
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        return 1 if val.strip().lower() in {"1", "true", "yes"} else 0
    return default


def _connector_row(info: dict, source: str, source_path: Optional[str]) -> dict:
    category = info.get("category")
    if isinstance(category, list):
        category = ",".join(str(c) for c in category)
    return {
        "name": info["name"],
        "version": str(info.get("version") or ""),
        "label": info.get("label"),
        "category": category,
        "description": info.get("description"),
        "publisher": info.get("publisher"),
        "contributor": info.get("contributor"),
        "active": 1,
        "system": 0,
        "cs_approved": _as_int(info.get("cs_approved")),
        "cs_compatible": _as_int(info.get("cs_compatible")),
        "ingestion_supported": _as_int(info.get("ingestion_supported")),
        "tags_json": json.dumps(info.get("tags") or []),
        "config_schema_json": json.dumps(info.get("configuration") or {}),
        "source": source,
        "source_path": source_path,
        # Icons are large and useless here; the probes strip them too.
        "info_json": json.dumps({k: v for k, v in info.items()
                                 if not str(k).startswith("icon")}),
    }


def _param_rows(connector: str, op_name: str, params: Any,
                parent: Optional[str] = None,
                condition: Optional[str] = None) -> list[dict]:
    """Flatten an operation's parameter list, including `onchange` sub-params.

    FortiSOAR nests conditional parameters under
    ``param.onchange[<trigger value>] = [ ...more params... ]``; the store
    models that as rows carrying `parent_param_name` + `condition_value`.
    """
    rows: list[dict] = []
    if not isinstance(params, list):
        return rows
    for ordinal, p in enumerate(params):
        if not isinstance(p, dict) or not p.get("name"):
            continue
        rows.append({
            "connector_name": connector,
            "op_name": op_name,
            # The PK includes these two, and SQLite treats NULLs as distinct
            # in a UNIQUE index -- use '' so re-provisioning actually replaces
            # top-level rows instead of piling up duplicates.
            "parent_param_name": parent or "",
            "condition_value": condition or "",
            "param_name": p["name"],
            "title": p.get("title"),
            "type": p.get("type"),
            "required": _as_int(p.get("required")),
            "default_value": (json.dumps(p["value"])
                              if isinstance(p.get("value"), (list, dict))
                              else (None if p.get("value") is None
                                    else str(p.get("value")))),
            "options_json": json.dumps(p["options"]) if p.get("options") else None,
            "tooltip": p.get("tooltip"),
            "placeholder": p.get("placeholder"),
            "description": p.get("description"),
            "visible": _as_int(p.get("visible"), 1),
            "editable": _as_int(p.get("editable"), 1),
            "ord": ordinal,
        })
        onchange = p.get("onchange")
        if isinstance(onchange, dict):
            for trigger, sub in onchange.items():
                rows.extend(_param_rows(connector, op_name, sub,
                                        parent=p["name"], condition=str(trigger)))
    return rows


def _operation_rows(connector: str, operations: Any) -> tuple[list[dict], list[dict]]:
    ops: list[dict] = []
    params: list[dict] = []
    for op in operations or []:
        if not isinstance(op, dict):
            continue
        op_name = op.get("operation")
        if not op_name:
            continue
        output_schema = op.get("output_schema")
        conditional = op.get("conditional_output_schema")
        ops.append({
            "connector_name": connector,
            "op_name": op_name,
            "title": op.get("title"),
            "annotation": op.get("annotation"),
            "category": op.get("category"),
            "description": op.get("description"),
            "visible": _as_int(op.get("visible"), 1),
            "enabled": _as_int(op.get("enabled"), 1),
            "output_schema_json": json.dumps(output_schema) if output_schema else None,
            "conditional_output_schema_json": (json.dumps(conditional)
                                               if conditional else None),
        })
        params.extend(_param_rows(connector, op_name, op.get("parameters")))
    return ops, params


# --------------------------------------------------------------------------
# store writes
# --------------------------------------------------------------------------

def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    sql = (f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
           f"VALUES ({','.join('?' for _ in cols)})")
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])


def write_connector(conn: sqlite3.Connection, info: dict, source: str,
                    source_path: Optional[str]) -> dict:
    """Upsert one connector plus its operations and parameters. Idempotent."""
    name = info["name"]
    crow = _connector_row(info, source, source_path)
    ops, params = _operation_rows(name, info.get("operations"))

    # Replace rather than merge, so an operation removed upstream stops being
    # offered by the compiler's suggestions.
    conn.execute("DELETE FROM operation_params WHERE connector_name = ?", (name,))
    conn.execute("DELETE FROM operations WHERE connector_name = ?", (name,))
    _insert(conn, "connectors", [crow])
    _insert(conn, "operations", ops)
    _insert(conn, "operation_params", params)

    conn.execute(
        "INSERT OR REPLACE INTO _catalog_meta (key, value, updated_at) "
        "VALUES (?, ?, ?)",
        (f"provisioned:{name}", f"{source}:{crow['version']}",
         _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()
    return {"connector": name, "version": crow["version"], "source": source,
            "operations": len(ops), "parameters": len(params)}


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------

def load_local(path: str) -> tuple[dict, str]:
    info_path = _resolve_info_json(path)
    info = json.loads(info_path.read_text())
    if not info.get("name"):
        raise SystemExit(f"{info_path} has no 'name' -- not a connector info.json")
    return info, str(info_path)


def load_from_instance(name: str) -> dict:
    """Fetch one connector's definition from the configured FortiSOAR.

    Two calls, mirroring ``probe_connectors._live()``: the listing gives us the
    installed version, and the per-connector detail endpoint (which needs that
    version in the path) gives the operations and their parameters.
    """
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        raise SystemExit("FSR_BASE_URL / auth not configured (.env)")
    client = _env.get_client()

    listing = client.get("/api/integration/connectors/",
                         params={"page_size": 1000, "active": "true"})
    rows = listing.get("data") if isinstance(listing, dict) else listing
    match = next((r for r in (rows or [])
                  if isinstance(r, dict) and r.get("name") == name), None)
    if match is None:
        raise SystemExit(
            f"connector {name!r} is not installed on {client.base_url}. "
            f"Provision it from local source instead: fsrpb provision <path>",
        )

    version = match.get("version")
    detail = client.session.post(
        f"{client.base_url}/api/integration/connectors/{name}/{version}/?format=json",
        json={}, verify=client.verify_ssl,
    )
    if detail.ok:
        body = detail.json()
        body = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(body, dict) and body.get("operations"):
            return body
    # Detail endpoint unavailable -- the listing already carries operations on
    # 7.x, so fall back to it rather than failing the provision outright.
    return match


def _instance_mismatch_warning(conn: sqlite3.Connection) -> Optional[str]:
    """The catalog is warmed from one instance; warn when we're on another.

    Mixing two appliances' definitions into one store silently produces wrong
    config UUIDs and wrong operation sets. Delegates to the Phase 9 guard so
    this uses the same normalization as the rest of the catalog.
    """
    try:
        from fsr_playbooks import _catalog_meta
        from probes import _env  # type: ignore

        base_url = _env.get_config().base_url or ""
        if not base_url:
            return None
        # (status, stamped_label, stamped_hash) -- the label can be blank, so
        # fall back to the stamped base_url for a message a human can act on.
        status, stamped_label, _hash = _catalog_meta.check_instance(conn, base_url)
        if status == "mismatch":
            warmed = (stamped_label
                      or _catalog_meta.get(conn, "base_url")
                      or "an unnamed instance")
            return (f"catalog was warmed from {warmed} but FSR_BASE_URL points at "
                    f"{_catalog_meta.normalize_base_url(base_url)} -- provisioning "
                    f"from a different instance than the rest of the catalog")
    except Exception:  # noqa: BLE001 -- advisory only, never block the write
        return None
    return None


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def describe(conn: sqlite3.Connection, name: str) -> dict:
    crow = conn.execute(
        "SELECT name, version, source, source_path FROM connectors WHERE name = ?",
        (name,),
    ).fetchone()
    if crow is None:
        import difflib
        allnames = [r[0] for r in conn.execute("SELECT name FROM connectors")]
        near = difflib.get_close_matches(name, allnames, n=3, cutoff=0.6)
        return {"known": False, "connector": name, "near": near}
    nops = conn.execute(
        "SELECT count(*) FROM operations WHERE connector_name = ?", (name,),
    ).fetchone()[0]
    nparams = conn.execute(
        "SELECT count(*) FROM operation_params WHERE connector_name = ?", (name,),
    ).fetchone()[0]
    return {"known": True, "connector": crow[0], "version": crow[1],
            "source": crow[2], "source_path": crow[3],
            "operations": nops, "parameters": nparams}


def cmd_provision(args: argparse.Namespace) -> int:
    from fsr_playbooks._db import default_db_path

    db_path = args.db or str(default_db_path())
    conn = sqlite3.connect(db_path)

    if args.check:
        out = describe(conn, args.check)
        print(json.dumps(out, indent=2) if args.json else _fmt_check(out))
        return 0 if out["known"] else 1

    if args.from_instance:
        warn = _instance_mismatch_warning(conn)
        if warn:
            print(f"warning: {warn}", file=sys.stderr)
        info = load_from_instance(args.from_instance)
        source, source_path = SOURCE_LIVE, None
    else:
        if not args.path:
            raise SystemExit("give a connector path, --from-instance NAME, or --check NAME")
        info, source_path = load_local(args.path)
        source = SOURCE_LOCAL

    name = info["name"]
    existing = describe(conn, name)
    if existing["known"] and not args.force:
        if existing.get("version") == str(info.get("version") or ""):
            print(f"{name} v{existing['version']} already in the catalog "
                  f"(source={existing['source']}, {existing['operations']} ops). "
                  f"Use --force to re-provision.")
            return 0

    if args.dry_run:
        ops, params = _operation_rows(name, info.get("operations"))
        print(f"[dry-run] would provision {name} v{info.get('version')} "
              f"from {source}: {len(ops)} operations, {len(params)} parameters")
        return 0

    result = write_connector(conn, info, source, source_path)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"provisioned {result['connector']} v{result['version']} "
              f"({result['operations']} operations, {result['parameters']} parameters, "
              f"source={result['source']}) into {db_path}")
    return 0


def _fmt_check(out: dict) -> str:
    if not out["known"]:
        near = f" (near: {', '.join(out['near'])})" if out.get("near") else ""
        return (f"{out['connector']}: NOT in the catalog{near}\n"
                f"  provision it:  fsrpb provision <connector-source-dir>\n"
                f"             or:  fsrpb provision --from-instance {out['connector']}")
    return (f"{out['connector']} v{out['version']}: known "
            f"({out['operations']} operations, {out['parameters']} parameters, "
            f"source={out['source']})")


def add_parser(sub) -> None:
    sp = sub.add_parser(
        "provision",
        help="teach the catalog about one connector (new/dev connectors)",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("path", nargs="?",
                    help="connector source directory, or a path to its info.json")
    sp.add_argument("--from-instance", metavar="NAME",
                    help="pull NAME's definition from the configured FortiSOAR instead")
    sp.add_argument("--check", metavar="NAME",
                    help="report what the catalog knows about NAME and exit")
    sp.add_argument("--db", help="reference-store path (default: the configured store)")
    sp.add_argument("--force", action="store_true",
                    help="re-provision even when the same version is already present")
    sp.add_argument("--dry-run", action="store_true",
                    help="report what would be written without writing")
    sp.add_argument("--json", action="store_true", help="machine-readable output")
    sp.set_defaults(func=cmd_provision)
