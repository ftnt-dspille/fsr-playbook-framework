"""fsrpb CLI — thin dispatcher over the compiler library.

Subcommands:
  refresh      — re-run probes and rebuild the reference store JSON
  compile      — YAML playbook -> FSR WorkflowCollection JSON
  validate     — YAML playbook -> structured errors (no JSON output)
  decompile    — FSR JSON -> simplified YAML
  roundtrip    — FSR JSON -> IR -> FSR JSON, semantic diff
  explain      — describe a connector / step / module from the store
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "store" / "fsr_reference.db"


def _print_errors(errors) -> None:
    for e in errors:
        line = f"[{e.code.value}] {e.path}: {e.message}"
        if e.suggestion:
            line += f"\n    -> {e.suggestion}"
        print(line, file=sys.stderr)


def cmd_refresh(_args: argparse.Namespace) -> int:
    from store.export import build_reference_json
    out = build_reference_json()
    print(f"reference json: {out}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    from compiler import compile_yaml
    text = Path(args.input).read_text()
    result = compile_yaml(text, Path(args.db))
    if not result.ok:
        _print_errors(result.errors)
        return 1
    out = Path(args.output)
    out.write_text(json.dumps(result.fsr_json, indent=2))
    print(f"wrote {out}", file=sys.stderr)
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    """Compile YAML and POST/PUT the unwrapped collection to /api/3/workflow_collections.

    `/api/3/workflow_collections` is plain API Platform CRUD on the
    `WorkflowCollection` entity — distinct from `/api/3/import_jobs`,
    which is for full configuration-bundle (Solution Pack) imports.
    Cascade-persist on the entity automatically writes nested
    `workflows[]` and their steps/routes.

    Mode semantics:
      replace (default) — try PUT first (in-place update); fall back to
                          POST if no record exists yet at that UUID.
                          Avoids the soft-delete uniqueness trap (FSR
                          marks records `deletedat=NOW()` rather than
                          purging, so DELETE+POST collides on the
                          soft-deleted UUID).
      create            — POST only; fail with 409 if UUID/name collides.
      update            — PUT to /api/3/workflow_collections/{uuid}; fail
                          with 404 if no record exists at that UUID.
    """
    from compiler import compile_yaml
    from probes import _env  # type: ignore

    text = Path(args.input).read_text()
    result = compile_yaml(text, Path(args.db))
    if not result.ok:
        _print_errors(result.errors)
        return 1

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2

    coll_entity = result.fsr_json["data"][0]
    coll_uuid = coll_entity["uuid"]
    coll_name = coll_entity["name"]

    client = _env.get_client()

    def _put() -> tuple[bool, object]:
        try:
            return True, client.put(
                f"/api/3/workflow_collections/{coll_uuid}", coll_entity,
            )
        except Exception as e:  # noqa: BLE001
            return False, e

    def _post() -> tuple[bool, object]:
        try:
            return True, client.post("/api/3/workflow_collections", coll_entity)
        except Exception as e:  # noqa: BLE001
            return False, e

    if args.mode == "create":
        ok, payload_or_err = _post()
        action = "POST"
    elif args.mode == "update":
        ok, payload_or_err = _put()
        action = "PUT"
    else:  # replace — try PUT first, fall back to POST on 404
        ok, payload_or_err = _put()
        action = "PUT"
        if not ok:
            r = getattr(payload_or_err, "response", None)
            if r is not None and r.status_code == 404:
                ok, payload_or_err = _post()
                action = "POST"
    if not ok:
        e = payload_or_err
        r = getattr(e, "response", None)
        status = getattr(r, "status_code", "?")
        body = (r.text if r is not None else str(e))[:500]
        print(f"push failed: HTTP {status}\n{body}", file=sys.stderr)
        return 1
    resp = payload_or_err

    print(
        f"{action} {coll_name} ({len(coll_entity['workflows'])} playbook(s)) "
        f"uuid={coll_uuid[:8]} mode={args.mode}",
        file=sys.stderr,
    )
    if args.json and resp is not None:
        print(json.dumps(resp, indent=2))
    return 0


def _is_uuid(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s or ""))


def _fetch_live_collection(client, ident: str) -> dict | None:
    """Return a single FSR collection envelope shape `{type, data:[{...}]}`,
    matching the corpus / decompiler input shape. `ident` is a name or UUID.

    Strategy: workflow_collections records don't auto-expand workflows[] in
    the standard CRUD response. We fetch the collection, then list its
    workflows separately with $relationships=true so steps + routes come
    inline (matches the export envelope shape).
    """
    if _is_uuid(ident):
        try:
            coll = client.get(f"/api/3/workflow_collections/{ident}")
        except Exception:
            return None
    else:
        # Filter by exact name. API Platform supports ?name=<value>.
        listing = client.get("/api/3/workflow_collections", params={"name": ident})
        members = listing.get("hydra:member") if isinstance(listing, dict) else None
        if not members:
            return None
        # If multiple, prefer exact-name match.
        coll = next((m for m in members if m.get("name") == ident), members[0])

    coll_uuid = coll.get("uuid")
    coll_iri = f"/api/3/workflow_collections/{coll_uuid}"
    wfs_resp = client.get(
        "/api/3/workflows",
        params={"collection": coll_iri, "$relationships": "true", "$limit": 500},
    )
    workflows = wfs_resp.get("hydra:member", []) if isinstance(wfs_resp, dict) else []
    coll = dict(coll)
    coll["workflows"] = workflows
    return {
        "type": "workflow_collections", "macros": [], "exported_tags": [],
        "data": [coll],
    }


def _decompile_to_yaml(coll, db_path: Path) -> str:
    """Same shape as cmd_decompile output, factored for reuse by pull/diff."""
    import yaml
    from compiler.decompiler import decompile

    ir = decompile(coll, db_path)
    out = {
        "collection": ir.name,
        "description": ir.description,
        "visible": ir.visible,
        "playbooks": [
            {
                "name": pb.name,
                "description": pb.description or None,
                "tag": pb.tag or None,
                "is_active": pb.is_active,
                "trigger_step_id": pb.trigger_step_id,
                "parameters": list(pb.parameters) or None,
                "steps": [
                    {
                        "id": s.id,
                        "type": s.type,
                        "name": s.name if s.name != s.id else None,
                        "arguments": s.arguments or None,
                        "next": s.next,
                        "branches": dict(s.branches) or None,
                        "unlabeled_next": list(s.unlabeled_next) or None,
                    }
                    for s in pb.steps
                ],
            }
            for pb in ir.playbooks
        ],
    }

    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o

    return yaml.safe_dump(_clean(out), sort_keys=False, allow_unicode=True)


def cmd_pull(args: argparse.Namespace) -> int:
    """Fetch a collection from live FSR and decompile to YAML."""
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    coll = _fetch_live_collection(client, args.collection)
    if coll is None:
        print(f"no collection matching {args.collection!r}", file=sys.stderr)
        return 1
    yaml_text = _decompile_to_yaml(coll, Path(args.db))
    if args.output:
        Path(args.output).write_text(yaml_text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(yaml_text)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare local YAML against the live state of a collection."""
    from compiler import compile_yaml
    from compiler.roundtrip import normalize_collection, diff
    from probes import _env  # type: ignore

    text = Path(args.input).read_text()
    result = compile_yaml(text, Path(args.db))
    if not result.ok:
        _print_errors(result.errors)
        return 1

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    target_name = args.collection or result.fsr_json["data"][0]["name"]
    live = _fetch_live_collection(client, target_name)
    if live is None:
        print(f"no live collection matching {target_name!r}", file=sys.stderr)
        return 1

    a = normalize_collection(live)
    b = normalize_collection(result.fsr_json)
    diffs = diff(a, b, "collection")
    if not diffs:
        print(f"in sync: local YAML matches live collection {target_name!r}", file=sys.stderr)
        return 0
    for d in diffs:
        print(d)
    return 1


def cmd_run_op(args: argparse.Namespace) -> int:
    """Fire a single connector operation via /api/integration/execute/.

    Verified 2026-05-02: the workflow service dispatcher
    `wf/workflow/tasks/connector/` returns 403 for direct API-key calls
    (likely needs the workflow-internal HMAC headers). The PHP
    integration service has `/api/integration/execute/` which proxies to
    the same dispatcher with the right auth, accepts the same body
    shape, and returns `{operation, status, message, data}`.

    `--params` accepts a JSON string OR a path to a JSON file.
    """
    import sqlite3
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2

    # Resolve canonical version from the store unless --version is given.
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    crow = conn.execute(
        "SELECT version FROM connectors WHERE name = ?", (args.connector,),
    ).fetchone()
    conn.close()
    if crow is None and not args.version:
        print(f"unknown connector {args.connector!r} (and no --version given)",
              file=sys.stderr)
        return 1
    version = args.version or crow["version"]

    params: dict = {}
    if args.params:
        if Path(args.params).is_file():
            params = json.loads(Path(args.params).read_text())
        else:
            params = json.loads(args.params)

    body = {
        "connector": args.connector,
        "operation": args.operation,
        "version": version,
        "config": args.config or "",
        "params": params,
    }
    client = _env.get_client()
    try:
        resp = client.post("/api/integration/execute/", body)
    except Exception as e:  # noqa: BLE001
        r = getattr(e, "response", None)
        status = getattr(r, "status_code", "?")
        text = (r.text if r is not None else str(e))[:500]
        print(f"run-op failed: HTTP {status}\n{text}", file=sys.stderr)
        return 1
    print(json.dumps(resp, indent=2) if resp is not None else "(empty response)")
    return 0


def cmd_run_playbook(args: argparse.Namespace) -> int:
    """Manually trigger a deployed playbook.

    ⚠ Endpoint pending discovery (2026-05-02). `WorkflowTriggerController`
    in PHP has `postManualAction` and `noTriggerExecuteAction` but route
    bindings live in `config/routing.yaml` which we don't yet have.
    Probed paths that all returned 400/404:
      - /api/wf/api/workflows/<wf_uuid>/start/   (Django dispatcher; 400 with empty body)
      - /api/triggers/1/<trigger_step_uuid>      (404)
      - /api/triggers/manual/<trigger_step_uuid> (404)
    To unblock: grep `WorkflowTriggerController` in /opt/cyops-api/config/
    or tail nginx access log while clicking "Run Manually" in the UI.
    """
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    if _is_uuid(args.playbook):
        wf_uuid = args.playbook
    else:
        # Look up by name. /api/3/workflows accepts ?name= filter.
        listing = client.get("/api/3/workflows", params={"name": args.playbook, "$limit": 5})
        members = listing.get("hydra:member", []) if isinstance(listing, dict) else []
        if not members:
            print(f"no playbook matching {args.playbook!r}", file=sys.stderr)
            return 1
        wf_uuid = next((m for m in members if m.get("name") == args.playbook), members[0])["uuid"]

    body: dict = {}
    if args.input:
        body = json.loads(Path(args.input).read_text() if Path(args.input).is_file() else args.input)

    try:
        resp = client.post(f"/api/wf/api/workflows/{wf_uuid}/start/", body)
    except Exception as e:  # noqa: BLE001
        r = getattr(e, "response", None)
        status = getattr(r, "status_code", "?")
        text = (r.text if r is not None else str(e))[:500]
        print(f"run-playbook failed: HTTP {status}\n{text}", file=sys.stderr)
        return 1
    print(f"triggered: {wf_uuid}", file=sys.stderr)
    if resp is not None:
        print(json.dumps(resp, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """List recent import_jobs with their state — sanity check after a push."""
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    resp = client.get("/api/3/import_jobs", params={"$limit": args.limit})
    rows = resp.get("hydra:member", []) if isinstance(resp, dict) else []
    if not rows:
        print("no import_jobs found", file=sys.stderr)
        return 0
    for j in rows:
        status = j.get("status") or "?"
        progress = j.get("progressPercent")
        progress_s = f"{progress}%" if progress is not None else ""
        print(
            f"{j.get('uuid','')[:8]}  {(j.get('type') or '?'):<20}  "
            f"{status:<22}  {progress_s:<6}  "
            f"{j.get('currentlyImporting') or ''}"
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from compiler import compile_yaml
    text = Path(args.input).read_text()
    result = compile_yaml(text, Path(args.db))
    if not result.ok:
        _print_errors(result.errors)
        if args.json:
            print(json.dumps([e.to_dict() for e in result.errors], indent=2))
        return 1
    print("ok", file=sys.stderr)
    return 0


def cmd_decompile(args: argparse.Namespace) -> int:
    """FSR JSON -> simplified YAML (one playbook, optionally filtered by name)."""
    import yaml
    from compiler.decompiler import decompile

    src = json.loads(Path(args.input).read_text())
    coll = decompile(src, Path(args.db))

    if args.workflow:
        coll.playbooks = [p for p in coll.playbooks if p.name == args.workflow]
        if not coll.playbooks:
            print(f"no playbook named {args.workflow!r}", file=sys.stderr)
            return 1

    out = {
        "collection": coll.name,
        "description": coll.description,
        "visible": coll.visible,
        "playbooks": [
            {
                "name": pb.name,
                "description": pb.description or None,
                "tag": pb.tag or None,
                "is_active": pb.is_active,
                "trigger_step_id": pb.trigger_step_id,
                "steps": [
                    {
                        "id": s.id,
                        "type": s.type,
                        "name": s.name if s.name != s.id else None,
                        "arguments": s.arguments or None,
                        "next": s.next,
                        "branches": dict(s.branches) or None,
                        "unlabeled_next": list(s.unlabeled_next) or None,
                    }
                    for s in pb.steps
                ],
            }
            for pb in coll.playbooks
        ],
    }
    # Drop None-valued keys for readability
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        return o
    yaml_text = yaml.safe_dump(_clean(out), sort_keys=False, allow_unicode=True)
    if args.output:
        Path(args.output).write_text(yaml_text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(yaml_text)
    return 0


def cmd_roundtrip(args: argparse.Namespace) -> int:
    from compiler.roundtrip import roundtrip
    src = json.loads(Path(args.input).read_text())
    ok, diffs = roundtrip(src, Path(args.db))
    if ok:
        print("ok", file=sys.stderr)
        return 0
    for d in diffs:
        print(d, file=sys.stderr)
    return 1


def cmd_explain(args: argparse.Namespace) -> int:
    import sqlite3
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    if args.kind == "connector":
        row = conn.execute("SELECT * FROM connectors WHERE name = ?", (args.name,)).fetchone()
        if not row:
            print(f"no connector named {args.name!r}", file=sys.stderr)
            return 1
        print(f"{row['name']} v{row['version']}  ({row['category']})")
        print(row['description'] or "")
        ops = conn.execute(
            "SELECT op_name, title FROM operations WHERE connector_name = ? ORDER BY op_name",
            (args.name,),
        ).fetchall()
        print(f"\n{len(ops)} operations:")
        for o in ops:
            print(f"  {o['op_name']}  -- {o['title'] or ''}")
    elif args.kind == "step":
        row = conn.execute("SELECT * FROM step_types WHERE name = ?", (args.name,)).fetchone()
        if not row:
            print(f"no step type named {args.name!r}", file=sys.stderr)
            return 1
        print(f"{row['name']}  ({row['category']})")
        print(f"uuid: {row['uuid']}")
        print(f"occurrences: {row['occurrences']}")
        if row['args_schema_json']:
            schema = json.loads(row['args_schema_json'])
            handler = (schema.get('script') or '').rsplit('/', 1)[-1]
            print(f"handler: {handler}")
            h = conn.execute(
                "SELECT signature FROM step_handlers WHERE name = ?", (handler,)
            ).fetchone()
            if h:
                print(f"signature: {handler}{h['signature']}")
    elif args.kind == "handler":
        row = conn.execute("SELECT * FROM step_handlers WHERE name = ?", (args.name,)).fetchone()
        if not row:
            print(f"no handler named {args.name!r}", file=sys.stderr)
            return 1
        print(f"{row['name']}{row['signature']}")
        print(f"qualname: {row['qualname']}")
        print(f"module: {row['module']}")
        if row['doc']:
            print(f"\n{row['doc']}")
    elif args.kind == "filter":
        row = conn.execute(
            "SELECT * FROM jinja_macros WHERE name = ?", (args.name,)
        ).fetchone()
        if not row:
            print(f"no jinja filter named {args.name!r}", file=sys.stderr)
            return 1
        sig = row["signature"] or ""
        print(f"{row['name']}{sig}")
        if row["module"]:
            print(f"module: {row['module']}")
        if row["output_type_observed"]:
            print(f"observed return type: {row['output_type_observed']}")
        if row["output_type_declared"]:
            print(f"declared return type: {row['output_type_declared']}")
        if row["description"]:
            print(f"\n{row['description'].strip()}")
        if row["example"]:
            print(f"\nexample:\n  {row['example']}")
    elif args.kind == "module":
        row = conn.execute("SELECT * FROM modules WHERE name = ?", (args.name,)).fetchone()
        if not row:
            print(f"no module named {args.name!r}", file=sys.stderr)
            return 1
        print(f"{row['name']}  ({row['plural']})")
        if row["label"]:
            print(f"label: {row['label']}")
        if row["description"]:
            print(row["description"])
        fields = conn.execute(
            "SELECT field_name, type, required, picklist_options "
            "FROM module_fields WHERE module_name = ? ORDER BY field_name",
            (args.name,),
        ).fetchall()
        print(f"\n{len(fields)} fields:")
        for f in fields:
            req = " (required)" if f["required"] else ""
            print(f"  {f['field_name']:<30} {f['type']}{req}")
    elif args.kind == "recipe":
        row = conn.execute("SELECT * FROM recipes WHERE name = ?", (args.name,)).fetchone()
        if not row:
            # Best-effort: list available recipe names if exact match fails.
            print(f"no recipe named {args.name!r}", file=sys.stderr)
            available = conn.execute(
                "SELECT name FROM recipes ORDER BY name LIMIT 20"
            ).fetchall()
            if available:
                print("available:", file=sys.stderr)
                for r in available:
                    print(f"  {r['name']}", file=sys.stderr)
            return 1
        print(f"{row['name']}  ({row['kind']})")
        if row["when_to_use"]:
            print(row["when_to_use"])
        if row["yaml_template"]:
            print(f"\nYAML template:\n{row['yaml_template']}")
    else:
        print(f"unsupported kind: {args.kind}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fsrpb")
    p.add_argument("--db", default=str(DEFAULT_DB), help="path to fsr_reference.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("refresh", help="rebuild reference store JSON")
    sp.set_defaults(func=cmd_refresh)

    sp = sub.add_parser("compile", help="YAML -> FSR JSON")
    sp.add_argument("input")
    sp.add_argument("-o", "--output", required=True)
    sp.set_defaults(func=cmd_compile)

    sp = sub.add_parser("pull", help="fetch a collection from live FSR as YAML")
    sp.add_argument("collection", help="collection name or UUID")
    sp.add_argument("-o", "--output", default=None)
    sp.set_defaults(func=cmd_pull)

    sp = sub.add_parser("diff", help="semantic diff: local YAML vs live collection")
    sp.add_argument("input", help="local YAML")
    sp.add_argument("-c", "--collection", default=None,
                    help="live collection name (defaults to YAML's collection name)")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("run-op", help="fire a single connector operation in isolation")
    sp.add_argument("connector")
    sp.add_argument("operation")
    sp.add_argument("--params", default=None, help="JSON string or path to a JSON file")
    sp.add_argument("--version", default=None, help="override connector version (default: store)")
    sp.add_argument("--config", default=None, help="connector config name")
    sp.set_defaults(func=cmd_run_op)

    sp = sub.add_parser("run-playbook", help="manually trigger a deployed playbook")
    sp.add_argument("playbook", help="workflow name or UUID")
    sp.add_argument("--input", default=None, help="JSON string or path to a JSON file")
    sp.set_defaults(func=cmd_run_playbook)

    sp = sub.add_parser("status", help="list recent import_jobs and their state")
    sp.add_argument("-n", "--limit", type=int, default=10)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("push", help="compile + POST to /api/3/import_jobs (upsert)")
    sp.add_argument("input")
    sp.add_argument("--mode", choices=["replace", "create", "update"], default="replace",
                    help="replace (default): DELETE+POST clean-slate update. "
                         "create: POST only (409 on UUID/name collision). "
                         "update: PUT in-place (preserves unmodeled fields).")
    sp.add_argument("--json", action="store_true", help="print response JSON to stdout")
    sp.set_defaults(func=cmd_push)

    sp = sub.add_parser("validate", help="validate YAML against the store")
    sp.add_argument("input")
    sp.add_argument("--json", action="store_true", help="emit errors as JSON on stdout")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("decompile", help="FSR JSON -> YAML")
    sp.add_argument("input")
    sp.add_argument("-o", "--output", default=None)
    sp.add_argument("-w", "--workflow", default=None,
                    help="filter to a single workflow by exact name")
    sp.set_defaults(func=cmd_decompile)

    sp = sub.add_parser("roundtrip", help="FSR JSON round-trip semantic diff")
    sp.add_argument("input")
    sp.set_defaults(func=cmd_roundtrip)

    sp = sub.add_parser("explain", help="describe a store entity")
    sp.add_argument("kind", choices=["connector", "step", "handler",
                                      "filter", "module", "recipe"])
    sp.add_argument("name")
    sp.set_defaults(func=cmd_explain)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
