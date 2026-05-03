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
import difflib
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
      replace (default) — try PUT first; on 404 POST; on 409 (UUID owned
                          by a soft-deleted record) hard-purge and POST.
                          Idempotent across recycle-bin state.
      create            — POST only. Fails with 409 if UUID/name collides
                          (live or soft-deleted).
      update            — PUT only. Fails with 404 if no record.
      upsert            — POST to `/api/3/bulkupsert/workflow_collections`.
                          NOTE: confirmed broken on FSR side (PHP 8 bugs
                          in UpsertController.php at lines 89 and 258 —
                          `array_key_exists` and array-index access used
                          on stdClass). Works only for fresh creates with
                          no existing match. Kept as opt-in for testing.
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

    def _upsert() -> tuple[bool, object]:
        # Body is a single workflow_collection object (NOT a list, despite
        # the "bulkupsert" name). Verified live 2026-05-03.
        # Limitation: UpsertController.php:89 uses array_key_exists on a
        # stdClass which crashes when an existing soft-deleted record
        # matches by uuid/name. Caller should hard-purge first if that's
        # the case — see _purge_soft_deleted().
        try:
            return True, client.post(
                "/api/3/bulkupsert/workflow_collections", coll_entity,
            )
        except Exception as e:  # noqa: BLE001
            return False, e

    def _purge_soft_deleted() -> bool:
        """Hard-purge by UUID via the canonical UI endpoint.
        `DELETE /api/3/delete/workflow_collections?$hardDelete=true` body
        `{ids:[<uuid>]}` — what the FSR web UI uses for "permanently delete".
        Returns True on success. Idempotent.

        Also purges every child workflow UUID in the payload — collection
        hard-delete does NOT cascade to workflows that ended up orphaned by
        a previous failed import (verified live 2026-05-03).
        """
        try:
            client.session.delete(
                client.base_url
                + "/api/3/delete/workflow_collections?$hardDelete=true",
                json={"ids": [coll_uuid]},
                verify=client.verify_ssl,
            )
        except Exception:  # noqa: BLE001
            pass
        wf_uuids = [w.get("uuid") for w in coll_entity.get("workflows", []) if w.get("uuid")]
        if wf_uuids:
            try:
                client.session.delete(
                    client.base_url
                    + "/api/3/delete/workflows?$hardDelete=true",
                    json={"ids": wf_uuids},
                    verify=client.verify_ssl,
                )
            except Exception:  # noqa: BLE001
                pass
        return True

    if args.mode == "create":
        ok, payload_or_err = _post()
        action = "POST"
    elif args.mode == "update":
        ok, payload_or_err = _put()
        action = "PUT"
    elif args.mode == "upsert":
        ok, payload_or_err = _upsert()
        action = "BULKUPSERT"
    else:  # replace — PUT, then POST, then (purge+POST) for soft-delete collision
        ok, payload_or_err = _put()
        action = "PUT"
        if not ok:
            r = getattr(payload_or_err, "response", None)
            status = getattr(r, "status_code", None)
            if status == 404:
                ok, payload_or_err = _post()
                action = "POST"
                if not ok:
                    r2 = getattr(payload_or_err, "response", None)
                    status2 = getattr(r2, "status_code", None)
                    if status2 == 409 and _purge_soft_deleted():
                        ok, payload_or_err = _post()
                        action = "PURGE+POST"
            elif status == 409:
                # PUT 409 also indicates soft-deleted UUID lock — same recovery
                if _purge_soft_deleted():
                    ok, payload_or_err = _post()
                    action = "PURGE+POST"
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


def _fetch_workflow_export(client, uuids: list[str]) -> list[dict]:
    """Bulk-fetch full Workflow records via /api/3/workflows?$export=true.

    Each member in the result has steps/routes/groups expanded inline —
    the same shape collection-export produces, just per-workflow.
    """
    if not uuids:
        return []
    qs = "&".join([
        "$export=true", "$relationships=true",
        "uuid$in=" + ",".join(uuids), "$limit=500",
    ])
    r = client.session.get(
        client.base_url + "/api/3/workflows?" + qs,
        verify=client.verify_ssl,
    )
    r.raise_for_status()
    return r.json().get("hydra:member", [])


def _resolve_workflow_ident(client, ident: str, collection: str | None = None) -> str | None:
    """Resolve a name (or "Collection:Name") or UUID to a workflow UUID.

    When multiple workflows share the same name (common after FSR
    instances accumulate test imports across collections) we'd rather
    print a list and ask than silently grab a stale one. Pass an
    explicit collection or `Collection:Name` shorthand to disambiguate.
    """
    if _is_uuid(ident):
        return ident
    if collection is None and ":" in ident:
        collection, ident = ident.split(":", 1)
    listing = client.get("/api/3/workflows", params={"name": ident, "$limit": 50})
    members = listing.get("hydra:member") if isinstance(listing, dict) else []
    if not members:
        return None
    exact = [m for m in members if m.get("name") == ident] or members
    if collection:
        coll_listing = client.get("/api/3/workflow_collections",
                                  params={"name": collection, "$limit": 5})
        coll_members = coll_listing.get("hydra:member") if isinstance(coll_listing, dict) else []
        coll_iris = {f"/api/3/workflow_collections/{c.get('uuid')}" for c in coll_members
                     if c.get("name") == collection}
        narrowed = [m for m in exact if m.get("collection") in coll_iris]
        if narrowed:
            exact = narrowed
    if len(exact) > 1:
        print(f"warning: {len(exact)} workflows named {ident!r}; picking the "
              f"most recently modified. Use --collection to disambiguate or "
              f"pass a UUID directly:", file=sys.stderr)
        for m in exact[:10]:
            print(f"  {m.get('uuid')}  collection={m.get('collection')}  "
                  f"modified={m.get('modified')}", file=sys.stderr)
        exact.sort(key=lambda m: m.get("modified") or "", reverse=True)
    return exact[0].get("uuid")


def _fetch_workflow_with_refs(client, ident: str) -> dict | None:
    """Fetch one Workflow + transitive workflow_reference dependencies.

    Bundles them into a synthetic collection envelope keyed off the root
    playbook's parent collection — so decompile produces a YAML where
    in-collection refs round-trip via local `target:` and cross-collection
    refs stay as IRIs. Cycles are broken by uuid de-dup.
    """
    root_uuid = _resolve_workflow_ident(client, ident)
    if not root_uuid:
        return None

    fetched: dict[str, dict] = {}
    pending = [root_uuid]
    while pending:
        new = [u for u in pending if u not in fetched]
        pending = []
        if not new:
            break
        for wf in _fetch_workflow_export(client, new):
            u = wf.get("uuid") or (wf.get("@id") or "").rsplit("/", 1)[-1]
            if not u:
                continue
            fetched[u] = wf
            for s in wf.get("steps") or []:
                args = s.get("arguments") if isinstance(s, dict) else None
                if not isinstance(args, dict):
                    continue
                ref = args.get("workflowReference")
                if isinstance(ref, str) and ref.startswith("/api/3/workflows/"):
                    dep = ref.rsplit("/", 1)[-1]
                    if dep not in fetched:
                        pending.append(dep)

    root = fetched.get(root_uuid)
    if not root:
        return None

    coll_iri = root.get("collection")
    coll_name = root.get("name") or ident
    coll_desc = ""
    coll_uuid = ""
    if isinstance(coll_iri, str) and coll_iri:
        try:
            cdata = client.get(coll_iri)
            coll_name = cdata.get("name") or coll_name
            coll_desc = cdata.get("description") or ""
            coll_uuid = cdata.get("uuid") or ""
        except Exception:  # noqa: BLE001
            pass

    return {
        "type": "workflow_collections", "macros": [], "exported_tags": [],
        "data": [{
            "@type": "WorkflowCollection",
            "name": coll_name,
            "description": coll_desc,
            "visible": True,
            "uuid": coll_uuid,
            "workflows": list(fetched.values()),
        }],
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
                        "comment": s.comment,
                    }
                    for s in pb.steps
                ],
                "annotations": [
                    {
                        "id": a.id,
                        "kind": a.kind if a.kind != "note" else None,
                        "title": a.title if a.title != "Note" else None,
                        "body": a.body or None,
                        "contains": list(a.contains) or None,
                        "position": (
                            {"top": a.top, "left": a.left,
                             "height": a.height or None, "width": a.width}
                            if a.top is not None or a.left is not None
                            else None
                        ),
                        "collapsed": a.collapsed or None,
                    }
                    for a in pb.annotations
                ] or None,
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
    """Fetch a single playbook (and its workflow_reference deps) as YAML.

    Walks workflow_reference IRIs transitively so the resulting YAML is
    self-contained: in-collection callees come along, cross-collection
    refs stay as IRIs (the decompiler emits them as-is).
    """
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    coll = _fetch_workflow_with_refs(client, args.playbook)
    if coll is None:
        print(f"no playbook matching {args.playbook!r}", file=sys.stderr)
        return 1
    pulled = len(coll["data"][0]["workflows"])
    if pulled > 1:
        print(f"pulled {pulled} playbook(s) (root + refs)", file=sys.stderr)
    yaml_text = _decompile_to_yaml(coll, Path(args.db))
    if args.output:
        Path(args.output).write_text(yaml_text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(yaml_text)
    return 0


def cmd_pull_collection(args: argparse.Namespace) -> int:
    """Fetch every playbook in a collection (folder) and decompile to YAML."""
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


def _fetch_run_env(client, pb_execution: str) -> tuple[dict | None, str | None]:
    """Fetch a workflow run's `{vars: {...env, steps: {<Name_us>: result}}}`
    Jinja context. Returns (env_dict, error_str). Resolves either a workflow
    PK (digits) or a task_id UUID. Mirrors view.controller.js:534-538.
    """
    if "-" in pb_execution and not pb_execution.isdigit():
        pr = client.session.get(
            client.base_url + "/api/wf/api/workflows/"
            f"?task_id={pb_execution}&parent_wf__isnull=True&format=json&limit=1",
            verify=client.verify_ssl,
        )
        if pr.status_code != 200:
            return None, f"task_id lookup failed: HTTP {pr.status_code}"
        members = pr.json().get("hydra:member") or []
        if not members:
            return None, f"no workflow run found for task_id {pb_execution!r}"
        pk_url = members[0].get("@id") or ""
        url = client.base_url + "/api" + pk_url + "?step_detail=true"
    else:
        url = client.base_url + f"/api/wf/api/workflows/{pb_execution}/?step_detail=true"
    r = client.session.get(url, verify=client.verify_ssl)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    data = r.json()
    env_obj = data.get("env") or {}
    steps_arr = data.get("steps") or []
    steps_map: dict = {}
    for s in steps_arr:
        name = s.get("name")
        if isinstance(name, str):
            steps_map[name.replace(" ", "_")] = s.get("result") or {}
    return ({"vars": dict(env_obj, steps=steps_map),
             "_run_status": data.get("status"),
             "_run_name": data.get("name")}, None)


def cmd_jinja(args: argparse.Namespace) -> int:
    """Render a Jinja template against a context, using FSR's live engine.

    Three context-source flavors (combinable):
      --from-pb-execution PK           Use the {vars: ...} context from a past run
      --input FILE_OR_JSON    Load context from a JSON file or inline string
      --bind KEY=VALUE        Add/override a single value (repeatable)

    POST /api/wf/api/jinja-editor/ runs the template through the same engine
    as FSR's playbook runtime — FSR-custom filters (`| tojson`, `| b64encode`,
    `| yaql`, …) all work. Use this to test that
    `{{ vars.steps.Get_organization.records[0].name }}` actually resolves
    against a real run before wiring it into the next step.
    """
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    context: dict = {}
    if args.from_pb_execution:
        env, err = _fetch_run_env(client, args.from_pb_execution)
        if err:
            print(f"--from-pb-execution {args.from_pb_execution!r}: {err}", file=sys.stderr)
            return 1
        # Strip the meta keys before sending to the engine.
        context = {k: v for k, v in (env or {}).items() if not k.startswith("_run_")}

    if args.input:
        raw = (Path(args.input).read_text() if Path(args.input).is_file() else args.input)
        try:
            inp = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            print(f"--input parse failed: {e!r}", file=sys.stderr)
            return 1
        # Deep-merge: --input replaces top-level keys but doesn't blow away
        # vars.steps from --from-pb-execution unless it explicitly sets it.
        for k, v in (inp or {}).items():
            if k == "vars" and isinstance(v, dict) and isinstance(context.get("vars"), dict):
                context["vars"] = {**context["vars"], **v}
            else:
                context[k] = v

    for kv in (args.bind or []):
        if "=" not in kv:
            print(f"--bind expects KEY=VALUE, got {kv!r}", file=sys.stderr)
            return 1
        k, v = kv.split("=", 1)
        try:
            v_parsed = json.loads(v)
        except Exception:  # noqa: BLE001
            v_parsed = v  # plain string fallback
        # Dotted keys land inside vars: --bind vars.foo=1
        cur: dict = context
        parts = k.split(".")
        for p in parts[:-1]:
            cur.setdefault(p, {})
            cur = cur[p]
        cur[parts[-1]] = v_parsed

    try:
        r = client.post("/api/wf/api/jinja-editor/",
                        data={"template": args.template, "values": context})
    except Exception as e:  # noqa: BLE001
        print(f"render failed: {e!r}", file=sys.stderr)
        return 1
    if isinstance(r, dict):
        out = r.get("result") or r.get("output") or r.get("rendered") or r.get("value")
        if out is None:
            out = json.dumps(r, indent=2, default=str)
    else:
        out = str(r)
    print(out)
    return 0


def cmd_env(args: argparse.Namespace) -> int:
    """Dump the live Jinja context from a previous playbook run.

    Hits GET /api/wf/api/workflows/<pk>/?step_detail=true and rebuilds the
    `{vars: {...env, steps: {<name_underscored>: <result>}}}` shape that
    FSR's runtime exposes to templates. Mirrors the transform used by the
    Jinja editor widget (view.controller.js: step.name.split(" ").join("_")).

    Why this is useful: while building a playbook, the LLM (or the human)
    needs to know what fields are actually available at `vars.steps.<X>.Y`
    for the NEXT step. Running the playbook once and dumping its env tells
    you exactly what data shape the next step will see.

    Identifier: workflow PK (integer, e.g. 676747) or task_id (UUID).
    Pass --task-id explicitly for unambiguous UUID resolution.
    """
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    ident = args.pb_execution
    if args.task_id or (not ident.isdigit() and "-" in ident):
        # Resolve task_id → workflow PK via /api/wf/api/workflows/?task_id=…
        pr = client.session.get(
            client.base_url + "/api/wf/api/workflows/"
            f"?task_id={ident}&parent_wf__isnull=True&format=json&limit=1",
            verify=client.verify_ssl,
        )
        if pr.status_code != 200:
            print(f"task_id lookup failed: HTTP {pr.status_code}", file=sys.stderr)
            return 1
        members = pr.json().get("hydra:member") or []
        if not members:
            print(f"no workflow run found for task_id {ident!r}", file=sys.stderr)
            return 1
        pk_url = members[0].get("@id") or ""
        # @id is `/wf/api/workflows/<pk>/` — needs `/api` prefix
        url = client.base_url + "/api" + pk_url + "?step_detail=true"
    else:
        url = client.base_url + f"/api/wf/api/workflows/{ident}/?step_detail=true"

    r = client.session.get(url, verify=client.verify_ssl)
    if r.status_code != 200:
        print(f"failed: HTTP {r.status_code}\n{r.text[:300]}", file=sys.stderr)
        return 1
    data = r.json()
    env_obj = data.get("env") or {}
    steps_arr = data.get("steps") or []
    steps_map: dict = {}
    for s in steps_arr:
        name = s.get("name")
        if isinstance(name, str):
            # Match the widget's transform exactly: spaces → underscores,
            # case preserved (so a step named "Get Org" becomes Get_Org).
            steps_map[name.replace(" ", "_")] = s.get("result") or {}
    values = {"vars": dict(env_obj, steps=steps_map)}
    if args.summary:
        print(_ansi(f"\nrun {data.get('name')!r} status={data.get('status')}", "1"),
              file=sys.stderr)
        print(_ansi("  vars (top-level):", "2"), file=sys.stderr)
        for k in sorted(values["vars"]):
            if k == "steps": continue
            print(f"    {k}", file=sys.stderr)
        print(_ansi("  vars.steps:", "2"), file=sys.stderr)
        for k in sorted(steps_map):
            kind = type(steps_map[k]).__name__
            preview = json.dumps(steps_map[k], default=str)[:80]
            print(f"    {k:<32} ({kind})  {preview}", file=sys.stderr)
    else:
        print(json.dumps(values, indent=2, default=str))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """List configured-and-active connectors, with optional live healthcheck.

    Two endpoints:
      - POST /api/integration/connector_details/?configured=true&active=true
        Returns the set of connectors that have at least one configuration
        AND are active. One round-trip; the right starting point when
        deciding which connectors a playbook can actually call.
      - GET /api/integration/connectors/healthcheck/{name}/{version}/
        Per-connector live status — {status, message, name, version,
        config_id}. status="Available" = configured + reachable;
        "Disconnected" = configured but upstream is down; 404 = no config.

    Default: list configured + active. Use --probe to also healthcheck
    each one (slower; one HTTP call per connector). For a single
    connector, pass its name as the positional arg — that always probes.
    """
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    if args.connector:
        # Specific connector — pick version from --version, or from the
        # configured-and-active listing (multiple installed versions are
        # common, e.g. hello-world ships at 1.0.4 / 1.1.0 / 1.0.5 / 1.1.1).
        version = args.version
        candidates: list[dict] = []
        if not version:
            r = client.session.post(
                client.base_url
                + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
                json={}, verify=client.verify_ssl,
            )
            rows = (r.json().get("data") or []) if r.status_code == 200 else []
            candidates = [x for x in rows if x.get("name") == args.connector]
            if not candidates:
                print(f"no configured connector named {args.connector!r}; "
                      f"pass --version to probe an unconfigured one",
                      file=sys.stderr)
                return 1
            if len(candidates) > 1 and not version:
                print(f"warning: {len(candidates)} versions of {args.connector!r} "
                      f"are configured — pass --version to pick one. "
                      f"Probing the first.", file=sys.stderr)
            version = candidates[0].get("version")
        targets = [{"name": args.connector, "version": version}]
        do_probe = True
    else:
        r = client.session.post(
            client.base_url
            + "/api/integration/connector_details/?format=json&configured=true&exclude=operation&active=true",
            json={}, verify=client.verify_ssl,
        )
        rows = (r.json().get("data") or []) if r.status_code == 200 else []
        targets = [{"name": x.get("name"), "version": x.get("version"),
                    "label": x.get("label"), "config_count": x.get("config_count"),
                    "status_listed": x.get("status")}
                   for x in rows if x.get("name") and x.get("version")]
        do_probe = bool(args.probe)

    available, disconnected, other = [], [], []
    for t in targets:
        if do_probe:
            url = (client.base_url
                   + f"/api/integration/connectors/healthcheck/{t['name']}/{t['version']}/")
            if args.config:
                url += f"?config={args.config}"
            try:
                r = client.session.get(url, verify=client.verify_ssl)
                if r.status_code == 404:
                    status = "no-config"; bucket = other
                else:
                    j = r.json(); status = j.get("status", "?")
                    bucket = (available if status == "Available"
                              else disconnected if status == "Disconnected"
                              else other)
            except Exception as e:  # noqa: BLE001
                status = f"error:{e!r}"; bucket = other
            t["status"] = status
            bucket.append(t)
        else:
            t["status"] = t.get("status_listed") or "configured"
            available.append(t)

    if args.json:
        out = ({"available": available, "disconnected": disconnected, "other": other}
               if do_probe else {"configured": available})
        print(json.dumps(out, indent=2))
        return 0

    def _print(label: str, color: str, rows: list) -> None:
        if not rows: return
        print(_ansi(f"\n{label} ({len(rows)})", color))
        for r in rows:
            extra = f"  cfg={r.get('config_count')}" if r.get('config_count') is not None else ""
            print(f"  {r['name']:<35} {r['version']:<10} {r['status']}{extra}")

    if do_probe:
        _print("Available", "32", available)
        _print("Disconnected", "33", disconnected)
        _print("Other / no-config", "2", other)
        print(_ansi(f"\n{len(available)} available · {len(disconnected)} disconnected "
                    f"· {len(other)} other", "1"), file=sys.stderr)
        return 0 if available else 1
    _print("Configured + active", "32", available)
    print(_ansi(f"\n{len(available)} configured · run with --probe to live-check each",
                "1"), file=sys.stderr)
    return 0


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
    """Manually trigger a deployed playbook via /api/triggers/1/.

    Two modes (live-verified 2026-05-03):
      - default ("designer-run"): POST /api/triggers/1/notrigger/<route_uuid>
        body {input, request:{data:{}}, useMockOutput, globalMock}.
        Returns {task_id}. Used by the playbook designer Run button.
      - --record <module>:<uuid>: POST /api/triggers/1/action/<route_uuid>
        body {singleRecordExecution, __resource, __uuid, records:[<iri>]}.
        Used by record-context "Execute" menu (cybersponse.action triggers).

    Resolves <route_uuid> from the workflow's trigger step
    (arguments.route). Pass the playbook by name or workflow uuid.
    """
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    wf_uuid = _resolve_workflow_ident(client, args.playbook, getattr(args, "collection", None))
    if not wf_uuid:
        print(f"no playbook matching {args.playbook!r}", file=sys.stderr)
        return 1

    input_data = {}
    if args.input:
        input_data = json.loads(
            Path(args.input).read_text() if Path(args.input).is_file()
            else args.input
        )

    # Both /action and /notrigger take the workflow uuid in the URL
    # (verified live 2026-05-03). Earlier guess that they took the
    # trigger-route uuid was wrong — the route uuid lives only inside
    # the trigger step's arguments, not in the URL.
    if args.record:
        if ":" not in args.record:
            print("--record must be <module>:<uuid>", file=sys.stderr)
            return 2
        module, rec_uuid = args.record.split(":", 1)
        path = f"/api/triggers/1/action/{wf_uuid}"
        body = {
            "singleRecordExecution": True,
            "__resource": module,
            "__uuid": rec_uuid,
            "records": [f"/api/3/{module}/{rec_uuid}"],
        }
    else:
        path = f"/api/triggers/1/notrigger/{wf_uuid}"
        body = {
            "input": input_data,
            "request": {"data": {}},
            "useMockOutput": False,
            "globalMock": False,
        }

    r = client.session.post(client.base_url + path, json=body, verify=client.verify_ssl)
    if r.status_code >= 400:
        print(f"run-playbook failed: HTTP {r.status_code}\n{r.text[:500]}",
              file=sys.stderr)
        return 1
    mode = "action" if args.record else "notrigger"
    print(f"triggered: wf={wf_uuid[:8]} mode={mode}", file=sys.stderr)
    try:
        resp = r.json()
    except Exception:  # noqa: BLE001
        resp = None
    if not args.follow:
        if resp is not None:
            print(json.dumps(resp, indent=2))
        return 0
    task_id = (resp or {}).get("task_id") if isinstance(resp, dict) else None
    if not task_id:
        print("(no task_id returned — cannot follow; --record async fires "
              "have no task_id)", file=sys.stderr)
        return 0
    return _follow_task(client, task_id, args.follow_timeout, args.follow_interval)


def _follow_task(client, task_id: str, timeout_s: int, interval_s: int) -> int:
    """Poll /api/wf/api/workflows/?task_id=<id>&parent_wf__isnull=True
    until terminal status, then print final record. See store entry for
    /api/wf/api/workflows GET — Django-side polling endpoint, the
    canonical run-status surface (sister historical-workflows/<id>/
    currently 500s)."""
    import time
    # Terminal statuses per workflow/0052_historical_workflow.py migration
    # (HistoricalWorkflow choices). 'rejected' is workflow-level only;
    # 'finished_with_error' is technically terminal too — it means the run
    # completed but at least one step errored. We treat it as terminal+failed.
    terminal = {"finished", "failed", "terminated", "skipped",
                "finished_with_error", "rejected"}
    start = time.time()
    last_status = ""
    url = (client.base_url + "/api/wf/api/workflows/"
           "?format=json&limit=1&offset=0&ordering=-modified"
           f"&task_id={task_id}&parent_wf__isnull=True")
    while time.time() - start < timeout_s:
        r = client.session.get(url, verify=client.verify_ssl)
        if r.status_code != 200:
            print(f"poll failed: HTTP {r.status_code}", file=sys.stderr)
            return 1
        members = r.json().get("hydra:member") or []
        if members:
            rec = members[0]
            status = rec.get("status", "unknown")
            if status != last_status:
                print(f"  status: {status}  ({int(time.time()-start)}s)",
                      file=sys.stderr)
                last_status = status
            if status in terminal:
                if status == "finished":
                    print(json.dumps(rec, indent=2, default=str))
                    return 0
                # On non-clean terminal: surface step-level diagnostics so
                # the demo loop doesn't require manually re-running `fsrpb
                # steps <task_id>` to find the failure.
                print(_ansi(f"\nrun {status} — step diagnostics:", "31"),
                      file=sys.stderr)
                try:
                    sr = client.session.get(
                        client.base_url
                        + f"/api/wf/api/historical-steps/?task_id={task_id}"
                          "&format=json&limit=200&ordering=created",
                        verify=client.verify_ssl,
                    )
                    items = sr.json().get("hydra:member", []) if sr.status_code == 200 else []
                except Exception:  # noqa: BLE001
                    items = []
                # The polling URL `/api/wf/api/workflows/?task_id=` trims
                # fields. Fetch the full record by PK to get `result`
                # (top-level "Error message") and embedded `steps[]` with
                # per-step status (verified via UI request 2026-05-03).
                # Note: @id is `/wf/api/workflows/<pk>/` — needs `/api`
                # prefix to hit the actual route.
                full = rec
                pk_url = rec.get("@id") or ""
                if pk_url:
                    try:
                        fr = client.session.get(
                            client.base_url + "/api" + pk_url,
                            verify=client.verify_ssl,
                        )
                        if fr.status_code == 200:
                            full = fr.json()
                    except Exception:  # noqa: BLE001
                        pass
                top_err = full.get("result") or {}
                err_msg = (top_err.get("Error message") if isinstance(top_err, dict) else None) \
                          or full.get("errorMessage") or full.get("error")
                if err_msg:
                    print(_ansi(f"  Error message: {err_msg}", "31"), file=sys.stderr)
                wf_steps = full.get("steps") or []
                if not wf_steps and not items:
                    print(_ansi("  no per-step history; full workflow record:", "2"),
                          file=sys.stderr)
                    print(json.dumps(full, indent=2, default=str), file=sys.stderr)
                for s in wf_steps or items:
                    st = s.get("status") or "?"
                    name = (s.get("name") or "?")[:36]
                    color = "31" if st in ("failed", "finished_with_error", "terminated") \
                            else ("32" if st == "finished" else "2")
                    print(_ansi(f"  {st:<22} {name}", color), file=sys.stderr)
                    if st in ("failed", "finished_with_error"):
                        res = s.get("result") or {}
                        err = (res.get("Error message") or res.get("error")
                               or res.get("message") or json.dumps(res)[:300])
                        print(_ansi(f"    → {err}", "31"), file=sys.stderr)
                print(file=sys.stderr)
                print(json.dumps({"task_id": task_id, "status": status,
                                  "uuid": rec.get("uuid")}, indent=2))
                return 2
        time.sleep(interval_s)
    print(f"timeout after {timeout_s}s; last status={last_status!r}",
          file=sys.stderr)
    return 1


def cmd_find(args: argparse.Namespace) -> int:
    """Find playbooks by step type, connector, operation, called-playbook, or text.

    Uses FSR's native API Platform filters:
      - steps.stepType.name=<Type>      (relational join)
      - steps.arguments$like=%<text>%   (JSON LIKE on serialized arguments)

    Filters AND together. With no filter: lists every playbook on the
    appliance — useful for piping into grep but rarely the goal.
    """
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    qs = ["$limit=500"]
    if args.step_type:
        qs.append(f"steps.stepType.name={args.step_type}")
    likes: list[str] = []
    # FSR's LIKE filter rejects double-quote chars in the needle, so we
    # match on the bare value. Connector + operation slugs are unique
    # enough that false positives are rare; use --text for exact JSON.
    if args.connector:
        likes.append(args.connector)
    if args.operation:
        likes.append(args.operation)
    if args.calls:
        # calls is a workflow uuid or name → resolve to uuid for IRI match
        ref_uuid = _resolve_workflow_ident(client, args.calls)
        if not ref_uuid:
            print(f"no workflow matching {args.calls!r}", file=sys.stderr)
            return 1
        likes.append(f"/api/3/workflows/{ref_uuid}")
    if args.text:
        likes.append(args.text)
    # Record-trigger graph: playbooks listening to module CREATE/UPDATE/DELETE
    # events. Combines a stepType filter with a module substring on the
    # trigger step's arguments. Side-effect map: any update_record against
    # the same module *can* fire these playbooks (filters evaluated live).
    trigger_step_types = {
        "on-create": "cybersponse.post_create",
        "on-update": "cybersponse.post_update",
        "on-delete": "cybersponse.post_delete",
        "pre-create": "cybersponse.pre_create",
        "pre-update": "cybersponse.pre_update",
        "pre-delete": "cybersponse.pre_delete",
    }
    if args.triggered_by:
        if not args.module:
            print("--triggered-by requires --module", file=sys.stderr)
            return 2
        st = trigger_step_types.get(args.triggered_by)
        if not st:
            print(f"unknown trigger kind {args.triggered_by!r}; one of "
                  f"{', '.join(trigger_step_types)}", file=sys.stderr)
            return 2
        # AND with any existing step_type filter would over-constrain; replace
        qs = [q for q in qs if not q.startswith("steps.stepType.name=")]
        qs.append(f"steps.stepType.name={st}")
        likes.append(args.module)
    for needle in likes:
        # URL-encode % as %25 and wrap with %25...%25
        from urllib.parse import quote
        qs.append(f"steps.arguments$like=%25{quote(needle, safe='')}%25")
    if args.active:
        qs.append("isActive=true")
    if args.collection:
        # Filter by parent collection name
        qs.append(f"collection.name={args.collection}")

    # --writes-to: union over the three FSR write step types in a single
    # POST /api/query/workflows call (payload-level OR, verified 2026-05-03
    # against ExpressionBuilder::logicOr in /opt/cyops-api/src/Query).
    write_step_types = ["UpdateRecord", "InsertData", "ApprovalManualInput"]
    if args.writes_to:
        body = {
            "logic": "AND",
            "filters": [
                {"logic": "OR", "filters": [
                    {"field": "steps.stepType.name", "operator": "eq", "value": st}
                    for st in write_step_types
                ]},
                {"field": "steps.arguments", "operator": "like",
                 "value": f"%{args.writes_to}%"},
            ] + [
                {"field": "steps.arguments", "operator": "like",
                 "value": f"%{n}%"} for n in likes
            ],
        }
        if args.active:
            body["filters"].append(
                {"field": "isActive", "operator": "eq", "value": True}
            )
        if args.collection:
            body["filters"].append(
                {"field": "collection.name", "operator": "eq", "value": args.collection}
            )
        r = client.session.post(
            client.base_url + "/api/query/workflows?$limit=500",
            json=body, verify=client.verify_ssl,
        )
        if r.status_code != 200:
            print(f"failed: HTTP {r.status_code}\n{r.text[:300]}", file=sys.stderr)
            return 1
        data = r.json()
        members = data.get("hydra:member", [])
        total = data.get("hydra:totalItems", len(members))
    else:
        url = client.base_url + "/api/3/workflows?" + "&".join(qs)
        r = client.session.get(url, verify=client.verify_ssl)
        if r.status_code != 200:
            print(f"failed: HTTP {r.status_code}\n{r.text[:300]}", file=sys.stderr)
            return 1
        data = r.json()
        members = data.get("hydra:member", [])
        total = data.get("hydra:totalItems", len(members))

    # Resolve collection IRI -> name for grouping (one extra GET per
    # distinct collection; cheap because there are usually few).
    coll_name_by_iri: dict[str, str] = {}
    for m in members:
        ci = m.get("collection")
        ci = ci if isinstance(ci, str) else ""
        if ci and ci not in coll_name_by_iri:
            try:
                coll_name_by_iri[ci] = client.get(ci).get("name", ci)
            except Exception:  # noqa: BLE001
                coll_name_by_iri[ci] = ci

    if args.json:
        out = [{
            "name": m.get("name"),
            "uuid": m.get("uuid"),
            "isActive": m.get("isActive"),
            "collection": coll_name_by_iri.get(m.get("collection") or "", ""),
            "tag": m.get("tag"),
        } for m in members]
        print(json.dumps({"total": total, "results": out}, indent=2))
        return 0

    # Group by collection for the "what products are impacted" view.
    by_coll: dict[str, list[dict]] = {}
    for m in members:
        cn = coll_name_by_iri.get(m.get("collection") or "", "(no collection)")
        by_coll.setdefault(cn, []).append(m)
    print(f"{total} playbook(s) matched across {len(by_coll)} collection(s)\n")
    for cn in sorted(by_coll):
        wfs = by_coll[cn]
        print(f"{cn}  ({len(wfs)})")
        for m in sorted(wfs, key=lambda x: x.get("name", "")):
            flag = "" if m.get("isActive") else "  [inactive]"
            print(f"  - {m.get('name','?')}{flag}  {m.get('uuid','')}")
        print()
    return 0


def cmd_triggers(args: argparse.Namespace) -> int:
    """List manual-trigger playbooks via /api/workflows/actions.

    This is the same API the FSR UI uses to populate a record's
    right-click "Execute" menu — manual-trigger playbooks (cybersponse.action
    start step) optionally scoped to a module.
    """
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    qs = ["$limit=250", "$relationships=true", "$triggerOnly=true"]
    if not args.inactive:
        qs.append("isActive=true")
    if args.module:
        qs.append(f"type={args.module}")
    r = client.session.get(
        client.base_url + "/api/workflows/actions?" + "&".join(qs),
        verify=client.verify_ssl,
    )
    if r.status_code != 200:
        print(f"failed: HTTP {r.status_code}\n{r.text[:400]}", file=sys.stderr)
        return 1
    data = r.json()
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    members = data.get("hydra:member", [])
    total = data.get("hydra:totalItems", len(members))
    label = args.module or "all modules"
    print(f"{total} manual-trigger playbook(s) for {label}\n")
    for m in members:
        ts_iri = m.get("triggerStep") or ""
        ts_uuid = ts_iri.rsplit("/", 1)[-1] if isinstance(ts_iri, str) else ""
        ts_args = {}
        for st in (m.get("steps") or []):
            if isinstance(st, dict) and st.get("uuid") == ts_uuid:
                ts_args = st.get("arguments") or {}
                break
        title = ts_args.get("title") or m.get("name", "?")
        resources = ts_args.get("resources") or []
        params_list = m.get("parameters") or []
        route = ts_args.get("route") or ""
        wf_uuid = (m.get("@id") or "").rsplit("/", 1)[-1]
        flag_active = "" if m.get("isActive") else " [inactive]"
        flag_single = " [single-record]" if ts_args.get("singleRecordExecution") else ""
        flag_norec = " [no-record]" if ts_args.get("noRecordExecution") else ""
        print(f"  {title}{flag_active}{flag_single}{flag_norec}")
        print(f"    workflow: {wf_uuid}  name: {m.get('name','')!r}")
        if resources:
            print(f"    resources: {', '.join(resources)}")
        if params_list:
            print(f"    parameters: {', '.join(params_list)}")
        if wf_uuid:
            print(f"    trigger: POST /api/triggers/1/notrigger/{wf_uuid}")
        if route:
            print(f"    route: {route}  (in trigger step args; not used in URL)")
        print()
    return 0


def _ansi(s: str, code: str) -> str:
    if not sys.stdout.isatty():
        return s
    return f"\033[{code}m{s}\033[0m"


def _human_age(iso_ts: str) -> str:
    """Convert an ISO-8601 timestamp into a short relative age (e.g. '12s', '4m', '3h')."""
    if not iso_ts:
        return "?"
    from datetime import datetime, timezone
    try:
        # Strip microsecond fractions beyond 6 digits + 'Z' → +00:00
        ts = iso_ts.rstrip("Z").split(".")
        head = ts[0]
        frac = (ts[1][:6] if len(ts) > 1 else "0").ljust(6, "0")
        dt = datetime.fromisoformat(head + "." + frac).replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return "?"
    delta = (datetime.now(timezone.utc) - dt).total_seconds()
    for unit, secs in [("d", 86400), ("h", 3600), ("m", 60)]:
        if delta >= secs:
            return f"{int(delta // secs)}{unit}"
    return f"{int(delta)}s"


def _resolve_workflow_pk(client, *, task_id: str | None = None,
                         input_pk: int | None = None) -> int | None:
    """Resolve the integer workflow pk needed for manual-input PUT.

    Try task_id first; otherwise look up by manual-wf-input id (which
    requires fetching the run that owns it — we use the encrypted token
    field on the input record as a hint to find the awaiting run).
    """
    if task_id:
        r = client.session.get(
            client.base_url + "/api/wf/api/workflows/"
            f"?task_id={task_id}&parent_wf__isnull=True&format=json&limit=1",
            verify=client.verify_ssl,
        )
        members = r.json().get("hydra:member") or []
        if members:
            return int(members[0]["@id"].rstrip("/").split("/")[-1])
    if input_pk is not None:
        # Find the most-recently-modified awaiting run; in practice the
        # input was just queued so it's the latest.
        r = client.session.get(
            client.base_url + "/api/wf/api/workflows/"
            "?status=awaiting&parent_wf__isnull=True&ordering=-modified"
            "&format=json&limit=10",
            verify=client.verify_ssl,
        )
        members = r.json().get("hydra:member") or []
        if members:
            return int(members[0]["@id"].rstrip("/").split("/")[-1])
    return None


def _list_pending_inputs(client) -> list[dict]:
    # `limit` is required; without it the endpoint 500s. Use a large
    # value to fetch all pendings in one call.
    r = client.session.post(
        client.base_url + "/api/wf/api/manual-wf-input/list_wfinput/"
        "?format=json&limit=200",
        json={}, verify=client.verify_ssl,
    )
    if r.status_code != 200:
        raise RuntimeError(f"list_wfinput failed: {r.status_code} {r.text[:200]}")
    return r.json().get("hydra:member") or []


def cmd_inputs_list(args: argparse.Namespace) -> int:
    """Show pending manual_input prompts (paused playbook runs awaiting response)."""
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    items = _list_pending_inputs(client)
    if args.json:
        print(json.dumps(items, indent=2, default=str))
        return 0
    if not items:
        print("no pending manual inputs", file=sys.stderr)
        return 0

    rows = []
    for inp in items:
        rows.append({
            "id": inp.get("id"),
            "age": _human_age(inp.get("created", "")),
            "type": "approval" if inp.get("is_approval") else (inp.get("type") or "?"),
            "title": (inp.get("title") or "(untitled)")[:55],
            "owner": "self" if (inp.get("assignment_type") == "none") else (inp.get("assignment_type") or "?"),
        })

    widths = {k: max(len(k.upper()), max(len(str(r[k])) for r in rows)) for k in rows[0]}
    header = "  ".join(_ansi(k.upper().ljust(widths[k]), "1;36") for k in rows[0])
    print(header)
    print(_ansi("  ".join("─" * widths[k] for k in rows[0]), "2"))
    for r in rows:
        line = "  ".join(str(r[k]).ljust(widths[k]) for k in r)
        print(line)
    print(_ansi(f"\n{len(items)} pending  ·  fsrpb inputs respond <id>", "2"),
          file=sys.stderr)
    return 0


def cmd_inputs_show(args: argparse.Namespace) -> int:
    """Show the full schema + button options for a pending input."""
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    r = client.session.post(
        client.base_url + f"/api/wf/api/manual-wf-input/{args.id}/retrieve_wfinput/?format=json",
        json={}, verify=client.verify_ssl,
    )
    if r.status_code != 200:
        print(f"failed: HTTP {r.status_code}\n{r.text[:300]}", file=sys.stderr)
        return 1
    rec = r.json()
    if args.json:
        print(json.dumps(rec, indent=2, default=str))
        return 0

    schema = (rec.get("input") or {}).get("schema") or {}
    title = schema.get("title") or rec.get("title") or "(untitled)"
    desc = schema.get("description") or ""
    rmap = rec.get("response_mapping") or {}
    options = rmap.get("options") or []
    ivars = schema.get("inputVariables") or []

    print(_ansi(title, "1") + _ansi(f"   #{rec.get('id')}", "2"))
    if desc:
        # strip simple HTML tags for readability
        import re
        clean = re.sub(r"<[^>]+>", " ", desc).strip()
        clean = re.sub(r"\s+", " ", clean)
        print(_ansi(clean[:200] + ("…" if len(clean) > 200 else ""), "2"))
    print()

    if ivars:
        print(_ansi("INPUT VARIABLES", "1;36"))
        for v in ivars:
            req = " (required)" if v.get("required") else ""
            default = f"  default={v.get('default')!r}" if v.get("default") not in (None, "") else ""
            print(f"  {v.get('name','?'):20s} {v.get('type','?'):10s} {v.get('label','')!r}{req}{default}")
        print()
    if options:
        print(_ansi("OPTIONS", "1;36"))
        for o in options:
            star = " ★" if o.get("primary") else ""
            print(f"  - {o.get('option','?')}{star}")
        print()
    print(_ansi(f"Respond:  fsrpb inputs respond {rec.get('id')} "
                f"--option '{(options[0].get('option') if options else 'OK')}'"
                + (" --vars '{...}'" if ivars else ""), "2"))
    return 0


def cmd_inputs_respond(args: argparse.Namespace) -> int:
    """Submit a response to a pending manual_input and resume the run.

    Canonical mechanism (per fsr_src/app.unmin.js:52478 + 37731):
      POST /api/wf/api/workflows/<wf_pk>/wfinput_resume/
      Body: {
        input:            {<var_name>: <value>, ...},   # inputVariables
        step_iri:         "<chosen option's step_iri>", # routing
        step_id:          <int>,                         # from list_wfinput
        manual_input_id:  <int>,                         # the pending input pk
        approved:         true|false,                    # only when is_approval
        user:             "/api/3/people/<uuid>"         # auth context (optional)
      }

    Earlier we used PUT /manual-wf-input/<pk>/ which returns 200 but
    does NOT actually resume the run — it only updates the record.
    """
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    # Fetch the input + schema so we can validate the user's response
    rr = client.session.post(
        client.base_url + f"/api/wf/api/manual-wf-input/{args.id}/retrieve_wfinput/?format=json",
        json={}, verify=client.verify_ssl,
    )
    if rr.status_code != 200:
        print(f"input #{args.id} not pending: HTTP {rr.status_code}", file=sys.stderr)
        return 1
    rec = rr.json()
    step_id = rec.get("step_id")
    rmap = rec.get("response_mapping") or {}
    options = rmap.get("options") or []
    schema = (rec.get("input") or {}).get("schema") or {}
    ivars = schema.get("inputVariables") or []
    type_ = "Approval" if rec.get("is_approval") else (rec.get("type") or "InputBased")

    # Resolve the chosen option (must match one of response_mapping.options).
    chosen_option = None
    if args.option:
        valid = [o.get("option") for o in options]
        if valid and args.option not in valid:
            print(f"unknown option {args.option!r}; valid: "
                  f"{', '.join(repr(v) for v in valid)}", file=sys.stderr)
            return 2
        chosen_option = next((o for o in options if o.get("option") == args.option), None)
    if chosen_option is None and options:
        chosen_option = next((o for o in options if o.get("primary")), options[0])
    if not chosen_option and options:
        print("no --option given and no default; "
              "use --option <label>", file=sys.stderr)
        return 2

    # inputVariable values
    iv_values = {}
    if args.vars:
        iv_values = json.loads(args.vars)
    missing = [v["name"] for v in ivars if v.get("required")
               and v["name"] not in iv_values]
    if missing:
        print(f"required inputVariables missing: {', '.join(missing)}; "
              f"pass --vars '{{...}}'", file=sys.stderr)
        return 2

    wf_pk = _resolve_workflow_pk(client, task_id=args.task_id, input_pk=int(args.id))
    if not wf_pk:
        print("could not resolve workflow pk; pass --task-id from the trigger response",
              file=sys.stderr)
        return 1

    body: dict = {
        "input": iv_values,
        "step_iri": (chosen_option or {}).get("step_iri"),
        "step_id": step_id,
        "manual_input_id": int(args.id),
    }
    if rec.get("is_approval"):
        body["approved"] = bool((chosen_option or {}).get("primary"))

    pr = client.session.post(
        client.base_url + f"/api/wf/api/workflows/{wf_pk}/wfinput_resume/?format=json",
        json=body, verify=client.verify_ssl,
    )
    if pr.status_code != 200:
        print(f"resume failed: HTTP {pr.status_code}\n{pr.text[:300]}", file=sys.stderr)
        return 1
    label = (chosen_option or {}).get("option", "?")
    print(_ansi(f"✓ resumed input #{args.id} → workflow {wf_pk} "
                f"(picked {label!r})", "32"), file=sys.stderr)
    if args.json:
        print(json.dumps(pr.json(), indent=2, default=str))
    return 0


def cmd_steps(args: argparse.Namespace) -> int:
    """Inspect every step of a playbook run by task_id.

    Reads /api/wf/api/historical-steps/?task_id=<id> (the only filter
    field actually wired on this endpoint per workflow.filtersets.
    HistoricalStepFilterSet.base_filters: id, name, func, status,
    task_id, initial, template_iri). Prints each step's name + status,
    plus its `result`/`input` JSONFields when --verbose.
    """
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    r = client.session.get(
        client.base_url + f"/api/wf/api/historical-steps/?task_id={args.task_id}"
        f"&format=json&limit=200&ordering=created",
        verify=client.verify_ssl,
    )
    if r.status_code != 200:
        print(f"failed: HTTP {r.status_code}", file=sys.stderr)
        return 1
    items = r.json().get("hydra:member", [])
    if args.json:
        print(json.dumps(items, indent=2, default=str))
        return 0
    if not items:
        print(f"no steps for task {args.task_id}", file=sys.stderr)
        return 1
    failed = 0
    rows = []
    for s in items:
        rows.append({
            "step": (s.get("name") or "?")[:38],
            "status": s.get("status") or "?",
            "func": s.get("func") or "",
            "ms": _step_duration_ms(s),
        })
        if s.get("status") in ("failed", "finished_with_error", "terminated"):
            failed += 1
    widths = {k: max(len(k.upper()), max(len(str(r[k])) for r in rows)) for k in rows[0]}
    print("  ".join(_ansi(k.upper().ljust(widths[k]), "1;36") for k in rows[0]))
    print(_ansi("  ".join("─" * widths[k] for k in rows[0]), "2"))
    for r in rows:
        line = "  ".join(str(r[k]).ljust(widths[k]) for k in r)
        if r["status"] in ("failed", "finished_with_error", "terminated"):
            line = _ansi(line, "31")
        elif r["status"] == "skipped":
            line = _ansi(line, "2")
        print(line)
    if args.verbose:
        print()
        for s in items:
            inp = s.get("input") or {}
            res = s.get("result") or {}
            args_ = s.get("args") or {}
            if not (inp or res or args_):
                continue
            print(_ansi(f"\n— {s.get('name')} ({s.get('status')})", "1"))
            if args_: print(f"  args:   {json.dumps(args_, default=str)[:400]}")
            if inp:   print(f"  input:  {json.dumps(inp, default=str)[:400]}")
            if res:   print(f"  result: {json.dumps(res, default=str)[:400]}")
    print(_ansi(f"\n{len(items)} steps  ·  {failed} failed", "2"), file=sys.stderr)
    return 0 if failed == 0 else 2


def _step_duration_ms(s: dict) -> str:
    """Compute duration from started/completed; return '?' if not yet finished."""
    if not (s.get("started") and s.get("completed")):
        return "?"
    from datetime import datetime
    try:
        a = datetime.fromisoformat(s["started"].rstrip("Z").split(".")[0])
        b = datetime.fromisoformat(s["completed"].rstrip("Z").split(".")[0])
        return f"{int((b - a).total_seconds() * 1000)}"
    except Exception:  # noqa: BLE001
        return "?"


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


def cmd_hub(args: argparse.Namespace) -> int:
    """Search or browse the FortiSOAR Content Hub (solutionpacks catalog).

    Examples:
      fsrpb hub search virustotal          # find connectors matching a query
      fsrpb hub search "threat intel"      # multi-word search
      fsrpb hub show abuseipdb             # show full ops + params for a connector
      fsrpb hub list --category "Threat Intelligence"  # list by category
    """
    from probes import _env  # type: ignore

    client = _env.get_client()
    if client is None:
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2

    sub = args.hub_cmd

    if sub == "search":
        query = args.query.lower()
        # Fetch a broad page and filter client-side (catalog is small enough)
        results = []
        page = 1
        while True:
            r = client.post(
                f"/api/query/solutionpacks?$limit=100&$page={page}",
                {
                    "logic": "AND",
                    "sort": [{"field": "label", "direction": "ASC"}],
                    "filters": [{"field": "type", "operator": "in", "value": ["connector"]}],
                },
            )
            members = r.get("hydra:member", [])
            if not members:
                break
            for sp in members:
                info = sp.get("infoContent") or {}
                name = info.get("name") or sp.get("name", "")
                label = info.get("label") or sp.get("label", "")
                desc = info.get("description") or sp.get("description", "")
                cat = info.get("category") or sp.get("category", "")
                if isinstance(cat, list):
                    cat = ", ".join(c if isinstance(c, str) else str(c) for c in cat)
                haystack = f"{name} {label} {desc} {cat}".lower()
                if query in haystack:
                    ops = info.get("operations", [])
                    installed = sp.get("installed", False)
                    results.append({
                        "name": name, "label": label, "category": cat,
                        "version": sp.get("version", ""), "installed": installed,
                        "ops": len(ops),
                        "description": desc[:80],
                    })
            if len(members) < 100:
                break
            page += 1

        if not results:
            print(f"no connectors matching {args.query!r}")
            return 0
        print(f"{'NAME':<35} {'VERSION':<10} {'OPS':>4}  {'INST':>4}  CATEGORY")
        print("-" * 90)
        for r in sorted(results, key=lambda x: x["name"]):
            inst = "yes" if r["installed"] else ""
            print(f"{r['name']:<35} {r['version']:<10} {r['ops']:>4}  {inst:>4}  {r['category']}")
        print(f"\n{len(results)} results")

    elif sub == "show":
        name = args.name
        r = client.post(
            "/api/query/solutionpacks?$limit=10",
            {
                "logic": "AND",
                "filters": [
                    {"field": "name", "operator": "eq", "value": name},
                    {"field": "type", "operator": "in", "value": ["connector"]},
                ],
            },
        )
        members = r.get("hydra:member", [])
        if not members:
            print(f"connector {name!r} not found in content hub", file=sys.stderr)
            return 1
        sp = members[0]
        info = sp.get("infoContent") or {}
        print(f"Name:        {info.get('name') or sp.get('name')}")
        print(f"Version:     {sp.get('version')}")
        print(f"Label:       {info.get('label') or sp.get('label')}")
        cat = info.get("category") or sp.get("category") or ""
        print(f"Category:    {', '.join(cat) if isinstance(cat, list) else cat}")
        print(f"Publisher:   {info.get('publisher') or sp.get('publisher')}")
        print(f"Installed:   {sp.get('installed', False)}")
        print(f"InfoPath:    {sp.get('infoPath') or 'N/A'}")
        desc = info.get("description") or sp.get("description") or ""
        print(f"Description: {desc[:120]}")
        ops = info.get("operations", [])
        print(f"\n{len(ops)} operations:")
        for op in ops:
            params = op.get("parameters", [])
            req = [p["name"] for p in params if p.get("required")]
            opt = [p["name"] for p in params if not p.get("required")]
            print(f"  {op.get('operation'):<35} {len(params):>3} params"
                  + (f"  required: {', '.join(req)}" if req else "")
                  + (f"  optional: {', '.join(opt[:3])}{'…' if len(opt)>3 else ''}" if opt else ""))

    elif sub == "list":
        cat_filter = (args.category or "").lower()
        r = client.post(
            "/api/query/solutionpacks?$limit=200",
            {
                "logic": "AND",
                "sort": [{"field": "label", "direction": "ASC"}],
                "filters": [{"field": "type", "operator": "in", "value": ["connector"]}],
            },
        )
        members = r.get("hydra:member", [])
        total = r.get("hydra:totalItems", len(members))
        print(f"{'NAME':<40} {'VERSION':<10} {'INSTALLED':>9}  CATEGORY")
        print("-" * 90)
        shown = 0
        for sp in members:
            info = sp.get("infoContent") or {}
            cat = info.get("category") or sp.get("category") or ""
            if isinstance(cat, list):
                cat = ", ".join(cat)
            if cat_filter and cat_filter not in cat.lower():
                continue
            inst = "yes" if sp.get("installed") else ""
            name = info.get("name") or sp.get("name", "")
            print(f"{name:<40} {sp.get('version',''):<10} {inst:>9}  {cat}")
            shown += 1
        print(f"\n{shown} shown (total in catalog: {total})")

    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    """List recent workflow runs, optionally filtered to failures.

    Hits /api/wf/api/workflows/?status__in=...&parent_wf__isnull=True. Returns
    playbook name, task_id, status, modified timestamp, and the top-level
    error message when the run failed — exactly what's needed to triage
    "my playbook is broken" without knowing which one.
    """
    from probes import _env  # type: ignore
    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()
    # Django filter quirk: only single-value `status=<v>` works on this
    # endpoint; `status__in=` and `status__exact=` are silently ignored
    # and return all runs (verified live 2026-05-03). For multi-status
    # filtering we fetch wider and filter client-side.
    want_statuses: set[str] | None = None
    if args.status:
        want_statuses = {s.strip() for s in args.status.split(",") if s.strip()}
    elif not args.all:
        want_statuses = {"failed", "finished_with_error", "terminated"}
    if want_statuses and len(want_statuses) == 1:
        only = next(iter(want_statuses))
        qs = ["format=json", f"limit={args.limit}", "ordering=-modified",
              "parent_wf__isnull=True", f"status={only}"]
    else:
        # Fetch a wider window and client-side filter; FSR's index is
        # plenty fast for limit≤200.
        fetch_n = max(args.limit * 4, 50) if want_statuses else args.limit
        qs = ["format=json", f"limit={fetch_n}", "ordering=-modified",
              "parent_wf__isnull=True"]
    url = client.base_url + "/api/wf/api/workflows/?" + "&".join(qs)
    r = client.session.get(url, verify=client.verify_ssl)
    if r.status_code != 200:
        print(f"poll failed: HTTP {r.status_code}", file=sys.stderr)
        return 1
    members = r.json().get("hydra:member") or []
    if want_statuses and len(want_statuses) > 1:
        members = [m for m in members if m.get("status") in want_statuses]
        members = members[:args.limit]
    if args.json:
        print(json.dumps(members, indent=2, default=str))
        return 0
    if not members:
        print("(no runs)", file=sys.stderr)
        return 0
    for m in members:
        status = m.get("status", "?")
        name = (m.get("name") or "?")[:48]
        task_id = m.get("task_id") or ""
        modified = m.get("modified") or ""
        age = _human_age(modified) if modified else ""
        color = ("31" if status in ("failed", "finished_with_error", "terminated")
                 else "32" if status == "finished" else "33")
        print(_ansi(f"{status:<22}", color), end="")
        print(f" {name:<48} {task_id} {age}")
        # Surface error message inline when present.
        res = m.get("result")
        if isinstance(res, dict):
            err = res.get("Error message") or res.get("error")
            if err and status in ("failed", "finished_with_error"):
                err_str = str(err)[:160]
                print(_ansi(f"    → {err_str}", "31"))
    return 0


def cmd_e2e(args: argparse.Namespace) -> int:
    """Run a .test.yaml end-to-end: compile → push → trigger → poll → assert → cleanup.

    Subcommands:
      run <test.yaml>    Run a single test sidecar against the live instance.
      cleanup [PATTERN]  Hard-purge collections whose name matches glob(s).
                         Default patterns: 'FSRPB Demo*', 'Compiler Demo*',
                         '*__fsrpb_probe__*'. Override with one or more args.
    """
    from probes import _env  # type: ignore
    from e2e.runner import run_test, cleanup_all

    sub = getattr(args, "e2e_cmd", None)
    if sub == "run":
        if not getattr(args, "test", None):
            print("usage: fsrpb e2e run <test.yaml>", file=sys.stderr)
            return 2
        test_path = Path(args.test)
        if not test_path.exists():
            print(f"test spec not found: {test_path}", file=sys.stderr)
            return 2
        res = run_test(test_path, keep=getattr(args, "keep", False))
        print(json.dumps({
            "run_id": res.run_id, "ok": res.ok, "status": res.status,
            "task_id": res.task_id, "wf_pk": res.wf_pk,
            "coll_uuid": res.coll_uuid,
            "failures": res.failures,
            "log_dir": str(res.log_dir) if res.log_dir else None,
        }, indent=2))
        return 0 if res.ok else 1

    if sub == "cleanup":
        cfg = _env.get_config()
        if not cfg.is_live():
            print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
            return 2
        client = _env.get_client()
        patterns = args.patterns or [
            "FSRPB Demo*", "Compiler Demo*", "*__fsrpb_probe__*",
        ]
        n = cleanup_all(client, patterns)
        print(f"purged {n} collection(s) matching {patterns}", file=sys.stderr)
        return 0

    print("usage: fsrpb e2e {run,cleanup} ...", file=sys.stderr)
    return 2


def cmd_mcp(_args: argparse.Namespace) -> int:
    from mcp_server import main as mcp_main
    mcp_main()
    return 0


# Registry of all runnable probes.  Each entry: (module_path, description).
_PROBES: dict[str, tuple[str, str]] = {
    "connectors":    ("probes.probe_connectors",       "connectors / operations / operation_params"),
    "modules":       ("probes.probe_modules",           "FSR modules, fields, and picklists"),
    "playbooks":     ("probes.probe_playbooks",         "step types, playbook corpus, trigger recipes"),
    "jinja":         ("probes.probe_jinja",             "Jinja filter catalog (live render)"),
    "jinja-backend": ("probes.probe_jinja_backend",     "Jinja filter signatures (backend introspect)"),
    "api-endpoints": ("probes.probe_api_endpoints",     "API endpoint inventory from Hydra root"),
    "step-handlers": ("probes.probe_step_handlers",     "FUNCTION_MAP step handler signatures"),
    "constraints":   ("probes.probe_playbook_constraints", "playbook constraint rules"),
    "cleanup":       ("probes.probe_cleanup",           "remove fsrpb test artifacts from FSR"),
    "jinja-corpus":  ("probes.probe_jinja_corpus",       "mine all Jinja blocks (expr/set/for/if/macro) + filter usage from live workflows"),
}


def cmd_probe(args: argparse.Namespace) -> int:
    """Run one or more reference-store probes against the live FSR instance.

    Each probe fetches a slice of FSR's metadata and writes it into
    store/fsr_reference.db.  All probes are idempotent — re-running them
    updates the store in place without destroying existing data.

    Examples:
      fsrpb probe connectors            # refresh connector / op / param data
      fsrpb probe jinja jinja-backend   # refresh both Jinja probes
      fsrpb probe --all                 # run every probe in sequence
      fsrpb probe --list                # show available probes
    """
    if args.list:
        print("Available probes:")
        for name, (_, desc) in sorted(_PROBES.items()):
            print(f"  {name:<20} {desc}")
        return 0

    targets: list[str] = args.probes
    if args.all:
        # Deterministic order: connectors first (others may depend on it),
        # then modules, playbooks, jinja, jinja-backend, api-endpoints, rest.
        ordered = ["connectors", "modules", "playbooks", "jinja", "jinja-backend",
                   "api-endpoints", "step-handlers", "constraints"]
        targets = ordered + [k for k in _PROBES if k not in ordered]

    if not targets:
        print("specify probe names or --all  (use --list to see options)", file=sys.stderr)
        return 1

    failed: list[str] = []
    for name in targets:
        if name not in _PROBES:
            close = difflib.get_close_matches(name, list(_PROBES), n=1, cutoff=0.5)
            hint = f"  did you mean {close[0]!r}?" if close else ""
            print(f"unknown probe {name!r}{hint}", file=sys.stderr)
            failed.append(name)
            continue

        module_path, desc = _PROBES[name]
        print(f"\n{'='*60}")
        print(f"probe: {name}  ({desc})")
        print('='*60)
        try:
            import importlib
            mod = importlib.import_module(module_path)
            rc = mod.main()
            if rc:
                print(f"[{name}] exited with code {rc}", file=sys.stderr)
                failed.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] ERROR: {exc}", file=sys.stderr)
            import traceback; traceback.print_exc()
            failed.append(name)

    if failed:
        print(f"\nFailed probes: {', '.join(failed)}", file=sys.stderr)
        return 1
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

    sp = sub.add_parser("pull", help="fetch a single playbook (+ ref deps) as YAML")
    sp.add_argument("playbook", help="workflow name or UUID")
    sp.add_argument("-o", "--output", default=None)
    sp.set_defaults(func=cmd_pull)

    sp = sub.add_parser("pull-collection",
                        help="fetch every playbook in a collection as YAML")
    sp.add_argument("collection", help="collection name or UUID")
    sp.add_argument("-o", "--output", default=None)
    sp.set_defaults(func=cmd_pull_collection)

    sp = sub.add_parser("diff", help="semantic diff: local YAML vs live collection")
    sp.add_argument("input", help="local YAML")
    sp.add_argument("-c", "--collection", default=None,
                    help="live collection name (defaults to YAML's collection name)")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("jinja", help="render a Jinja template against a run env / inline context")
    sp.add_argument("template", help="Jinja template string, e.g. '{{ vars.steps.Get_org.records[0].id }}'")
    sp.add_argument("--from-pb-execution", default=None,
                    help="seed context from a past run (workflow PK or task_id)")
    sp.add_argument("--input", default=None,
                    help="JSON file path or inline JSON to merge into context")
    sp.add_argument("--bind", action="append", default=[],
                    help="KEY=VALUE override (repeatable; dotted keys nest under vars). "
                         "Value is JSON-parsed if possible, else plain string")
    sp.set_defaults(func=cmd_jinja)

    sp = sub.add_parser("env", help="dump a past run's vars/steps Jinja context")
    sp.add_argument("pb_execution", help="workflow PK (integer) or task_id (UUID)")
    sp.add_argument("--task-id", action="store_true",
                    help="force UUID-as-task_id resolution (rarely needed; auto-detected)")
    sp.add_argument("--summary", action="store_true",
                    help="print a one-line-per-key index instead of full JSON")
    sp.set_defaults(func=cmd_env)

    sp = sub.add_parser("health", help="list configured connectors; --probe to live-check")
    sp.add_argument("connector", nargs="?",
                    help="connector name (omit to list all configured); single-name always probes")
    sp.add_argument("--version", default=None, help="connector version (default: looked up live)")
    sp.add_argument("--config", default=None,
                    help="config UUID to test (when a connector has multiple configurations)")
    sp.add_argument("--probe", action="store_true",
                    help="when listing all, also healthcheck each one (one extra round-trip per connector)")
    sp.add_argument("--json", action="store_true", help="emit JSON instead of grouped tables")
    sp.set_defaults(func=cmd_health)

    sp = sub.add_parser("run-op", help="fire a single connector operation in isolation")
    sp.add_argument("connector")
    sp.add_argument("operation")
    sp.add_argument("--params", default=None, help="JSON string or path to a JSON file")
    sp.add_argument("--version", default=None, help="override connector version (default: store)")
    sp.add_argument("--config", default=None, help="connector config name")
    sp.set_defaults(func=cmd_run_op)

    sp = sub.add_parser("run-playbook", help="manually trigger a deployed playbook")
    sp.add_argument("playbook", help="workflow name, UUID, or 'Collection:Name'")
    sp.add_argument("--collection", default=None,
                    help="restrict name lookup to this collection (disambiguates duplicates)")
    sp.add_argument("--input", default=None, help="JSON string or path to a JSON file (designer-run mode)")
    sp.add_argument("--record", default=None, metavar="MODULE:UUID",
                    help="fire as record-context Execute (cybersponse.action triggers); e.g. alerts:db7afbf7-...")
    sp.add_argument("--follow", action="store_true",
                    help="poll task status until terminal (finished/failed/terminated/skipped)")
    sp.add_argument("--follow-interval", type=int, default=3, help="seconds between polls (default 3)")
    sp.add_argument("--follow-timeout", type=int, default=300, help="give up after N seconds (default 300)")
    sp.set_defaults(func=cmd_run_playbook)

    sp = sub.add_parser("steps", help="inspect a playbook run's per-step audit log by task_id")
    sp.add_argument("task_id", help="task_id from `run-playbook` output")
    sp.add_argument("-v", "--verbose", action="store_true", help="dump each step's args/input/result JSON")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_steps)

    sp = sub.add_parser("status", help="list recent import_jobs and their state")
    sp.add_argument("-n", "--limit", type=int, default=10)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("push", help="compile + POST to /api/3/import_jobs (upsert)")
    sp.add_argument("input")
    sp.add_argument("--mode", choices=["replace", "create", "update", "upsert"], default="replace",
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

    sp = sub.add_parser("find", help="find playbooks by step-type / connector / op / caller / text")
    sp.add_argument("--step-type", help="WorkflowStepType name (Connectors, ManualInput, Decision, …)")
    sp.add_argument("--connector", help="connector name in any step's arguments.connector")
    sp.add_argument("--operation", help="operation name in any step's arguments.operation")
    sp.add_argument("--calls", help="playbooks that workflow_reference this name/uuid")
    sp.add_argument("--text", help="any substring in any step's serialized arguments")
    sp.add_argument("--collection", help="restrict to one collection (name)")
    sp.add_argument("--active", action="store_true", help="only isActive=true")
    sp.add_argument("--triggered-by",
                    choices=["on-create", "on-update", "on-delete",
                             "pre-create", "pre-update", "pre-delete"],
                    help="playbooks listening to this record-event (requires --module)")
    sp.add_argument("--module", help="module name (alerts, incidents, …) — used with --triggered-by")
    sp.add_argument("--writes-to", metavar="MODULE",
                    help="playbooks with insert_record / update_record / approval against this module")
    sp.add_argument("--json", action="store_true", help="emit JSON")
    sp.set_defaults(func=cmd_find)

    sp = sub.add_parser("inputs", help="list/respond to pending manual_input prompts")
    isub = sp.add_subparsers(dest="inputs_cmd", required=True)

    sp_list = isub.add_parser("list", help="show all pending manual_input prompts")
    sp_list.add_argument("--json", action="store_true")
    sp_list.set_defaults(func=cmd_inputs_list)

    sp_show = isub.add_parser("show", help="show form schema + button options for one prompt")
    sp_show.add_argument("id", type=int, help="manual-wf-input pk")
    sp_show.add_argument("--json", action="store_true")
    sp_show.set_defaults(func=cmd_inputs_show)

    sp_resp = isub.add_parser("respond", help="submit a response and resume the run")
    sp_resp.add_argument("id", type=int, help="manual-wf-input pk (from `inputs list`)")
    sp_resp.add_argument("--option", help="button label to pick (default: primary option)")
    sp_resp.add_argument("--vars", help="JSON dict of inputVariable values")
    sp_resp.add_argument("--task-id", help="task_id from the original trigger (helps resolve wf pk)")
    sp_resp.add_argument("--json", action="store_true")
    sp_resp.set_defaults(func=cmd_inputs_respond)

    sp = sub.add_parser("triggers", help="list manual-trigger playbooks for a module")
    sp.add_argument("module", nargs="?", default=None,
                    help="module name (alerts, incidents, indicators, …); omit for all")
    sp.add_argument("--inactive", action="store_true",
                    help="include unpublished playbooks (isActive=false)")
    sp.add_argument("--json", action="store_true", help="emit raw JSON")
    sp.set_defaults(func=cmd_triggers)

    sp = sub.add_parser("explain", help="describe a store entity")
    sp.add_argument("kind", choices=["connector", "step", "handler",
                                      "filter", "module", "recipe"])
    sp.add_argument("name")
    sp.set_defaults(func=cmd_explain)

    sp = sub.add_parser(
        "hub",
        help="search / browse the FortiSOAR Content Hub connector catalog",
        description=cmd_hub.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    hub_sub = sp.add_subparsers(dest="hub_cmd", required=True)

    h = hub_sub.add_parser("search", help="search connectors by name/category/description")
    h.add_argument("query", help="search term")

    h = hub_sub.add_parser("show", help="show ops and params for a specific connector")
    h.add_argument("name", help="connector name (e.g. abuseipdb)")

    h = hub_sub.add_parser("list", help="list all catalog connectors")
    h.add_argument("--category", help="filter by category (partial match)")

    sp.set_defaults(func=cmd_hub)

    sp = sub.add_parser("runs", help="list recent workflow runs (default: failed only)")
    sp.add_argument("--all", action="store_true",
                    help="include successful runs (default: failed/errored only)")
    sp.add_argument("--status", help="explicit status filter "
                    "(comma-separated, e.g. 'failed,finished_with_error,terminated')")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_runs)

    sp = sub.add_parser(
        "e2e",
        help="end-to-end test runner: compile→push→trigger→poll→assert→cleanup",
        description=cmd_e2e.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    e2e_sub = sp.add_subparsers(dest="e2e_cmd", required=True)
    e_run = e2e_sub.add_parser("run", help="run a single .test.yaml")
    e_run.add_argument("test", help="path to <fixture>.test.yaml")
    e_run.add_argument("--keep", action="store_true",
                       help="leave the deployed collection in place after the run")
    e_cln = e2e_sub.add_parser("cleanup",
                               help="hard-purge demo/test collections by glob")
    e_cln.add_argument("patterns", nargs="*",
                       help="name glob(s); defaults to FSRPB Demo* / Compiler Demo* / *__fsrpb_probe__*")
    sp.set_defaults(func=cmd_e2e)

    sp = sub.add_parser("mcp", help="start the MCP server (stdio transport)")
    sp.set_defaults(func=cmd_mcp)

    sp = sub.add_parser(
        "probe",
        help="run reference-store probes against the live FSR instance",
        description=cmd_probe.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("probes", nargs="*", metavar="PROBE",
                    help="probe name(s) to run (omit with --all)")
    sp.add_argument("--all", action="store_true", help="run all probes in order")
    sp.add_argument("--list", action="store_true", help="list available probes and exit")
    sp.set_defaults(func=cmd_probe)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
