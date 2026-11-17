"""Pull one live playbook off the box as a collection envelope, for decompile.

``why_did_playbook_fail``'s no-YAML fallback used to reach the repo's
``tooling/cli.py`` for the fetch + decompile. On an installed wheel
``tooling/`` does not exist, so the tool died with
``decompile_import_failed`` ("No module named 'cli'") on exactly the call
an analyst makes first: "diagnose my failed run" by playbook name. The
fetch is plain REST over the same live client every MCP tool uses
(``_shared._live_client()``), and the decompiler already ships in the
package (``compiler.decompiler``), so the pull belongs here.

Adapted from ``tooling/cli.py``'s ``_fetch_workflow_with_refs`` -- quiet:
no interactive stderr UX, and a name shared by several workflows resolves
to the most recently modified (the box accumulates same-named imports
across collections).
"""
from __future__ import annotations

import re
from typing import Any

from ..compiler.wire import as_record_list

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def _is_uuid(ident: str) -> bool:
    return bool(_UUID_RE.match((ident or "").strip()))


def resolve_workflow_uuid(client: Any, ident: str) -> str | None:
    """Resolve a playbook display name or UUID to the workflow UUID.

    None when the name matches nothing. A UUID passes through untouched.
    """
    ident = (ident or "").strip()
    if not ident:
        return None
    if _is_uuid(ident):
        return ident
    listing = _get_json(client, "/api/3/workflows",
                        params={"name": ident, "$limit": 50})
    members = listing.get("hydra:member") if isinstance(listing, dict) else []
    if not members:
        return None
    exact = [m for m in members if m.get("name") == ident] or members
    exact.sort(key=lambda m: m.get("modified") or "", reverse=True)
    return exact[0].get("uuid")


def _get_json(client: Any, path: str, params: dict[str, Any] | None = None) -> Any:
    """GET via the client and return the parsed JSON body.

    Two client shapes reach here: pyfsr (an HTTP Response carrying
    ``.raise_for_status()`` / ``.json()``) and the connector's crudhub
    bridge client (``CrudhubLiveClient`` — the parsed body straight back,
    transport errors raised inside make_request). Normalize both so the
    pull works identically on a box and off one.
    """
    r = client.get(path, params=params)
    if hasattr(r, "json"):
        r.raise_for_status()
        return r.json()
    return r


def fetch_workflow_export(client: Any, uuids: list[str]) -> list[dict[str, Any]]:
    """Bulk-fetch full Workflow records via /api/3/workflows?$export=true.

    Each member carries steps/routes/groups expanded inline -- the same
    shape a collection export produces, just per workflow.
    """
    if not uuids:
        return []
    listing = _get_json(client, "/api/3/workflows", params={
        "$export": "true", "$relationships": "true",
        "uuid$in": ",".join(uuids), "$limit": 500,
    })
    return listing.get("hydra:member", []) if isinstance(listing, dict) else []


def pull_collection_with_refs(client: Any, ident: str) -> dict[str, Any] | None:
    """Fetch one Workflow + transitive workflow_reference dependencies.

    Bundles them into a synthetic collection envelope keyed off the root
    playbook's parent collection -- so decompile produces a YAML where
    in-collection refs round-trip via local ``target:`` and
    cross-collection refs stay as IRIs. Cycles are broken by uuid de-dup.

    Returns None when ``ident`` resolves to nothing on the box.
    """
    root_uuid = resolve_workflow_uuid(client, ident)
    if not root_uuid:
        return None

    fetched: dict[str, dict] = {}
    pending = [root_uuid]
    while pending:
        new = [u for u in pending if u not in fetched]
        pending = []
        if not new:
            break
        for wf in fetch_workflow_export(client, new):
            u = wf.get("uuid") or (wf.get("@id") or "").rsplit("/", 1)[-1]
            if not u:
                continue
            fetched[u] = wf
            # `as_record_list`, not a bare iteration: on the id-keyed wire
            # shape this loop would walk STRINGS, the isinstance guard
            # would skip every one, and dependency discovery would come
            # back empty -- a pull that silently drops referenced
            # sub-playbooks rather than failing.
            for s in as_record_list(wf.get("steps"), path="workflow.steps"):
                args = s.get("arguments")
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
            cdata = _get_json(client, coll_iri)
            coll_name = cdata.get("name") or coll_name
            coll_desc = cdata.get("description") or ""
            coll_uuid = cdata.get("uuid") or ""
        except Exception:  # noqa: BLE001 -- the envelope still decompiles
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
