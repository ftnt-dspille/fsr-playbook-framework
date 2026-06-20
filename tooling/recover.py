"""Recover deleted FortiSOAR playbooks from the activities audit log.

Background: FSR records every entity Delete in the `activities` feed with
the full pre-delete entity state preserved in `data.data[]`. That payload
includes the parent WorkflowCollection envelope and the deleted workflow
with all steps - enough to recreate the workflow byte-for-byte.

This module powers `fsrpb recover-deleted-playbooks`. Designed to be
idempotent: it skips any workflow whose UUID is already present (live or
soft-deleted) in the appliance.

Recovery shape:
  Each Delete entry has a single deleted workflow identified by
  `entityUuid`. We pull that workflow out of `data.data[0].workflows[]`,
  wrap it in a minimal WorkflowCollection envelope (reusing the parent
  collection's name + uuid), and POST/PUT via /api/3/workflow_collections
  - the same path `cmd_push` uses, so the cascade-persist semantics are
  identical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


CACHE_DIR = Path(os.environ.get(
    "XDG_CACHE_HOME", Path.home() / ".cache")) / "fsrpb" / "recover"
CACHE_TTL_S = 48 * 3600  # 48 hours; --refresh forces re-fetch

_HYDRATE_WORKERS = 30


# Source IP of the probe rig that caused the 2026-05-08 mass-delete.
# Activities authored by other sources are likely human deletes the user
# wants to keep. Filter is opt-out via --include-all-sources.
DEFAULT_SOURCE_BLOCKLIST = {"10.100.4.143"}


def _ms(d: dt.datetime) -> int:
    return int(d.timestamp() * 1000)


def _parse_date(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc) \
        if "T" in s or " " in s \
        else dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.json"


def _cache_get(key: str, *, max_age_s: int = CACHE_TTL_S) -> Any | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > max_age_s:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _cache_put(key: str, value: Any) -> None:
    p = _cache_path(key)
    p.write_text(json.dumps(value, default=str))


def _fetch_delete_activities(client, since_ms: int, until_ms: int,
                             limit: int) -> list[dict]:
    """POST /api/gateway/audit/activities with the same body shape the
    Angular Activities tab sends. Returns the raw audit entries
    (Spring Page envelope; `content` holds the rows)."""
    body = {
        "operation": "Delete",
        "entityType": "playbooks",
        "startDate": since_ms,
        "endDate": until_ms,
        "limit": limit,
    }
    r = client.session.post(
        client.base_url + "/api/gateway/audit/activities",
        json=body, verify=client.verify_ssl, timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"GET activities failed: {r.status_code} {r.text[:200]}")
    return r.json().get("content", []) or []


def _bulk_index_live_workflows(client) -> tuple[dict, dict]:
    """One-shot fetch of every live workflow as shallow records, then
    index by uuid and by name. We follow up with per-record GETs only
    for the ones we actually need to compare against.
    """
    print("  indexing live workflows (one bulk fetch)...", flush=True)
    by_uuid: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    page = 1
    while True:
        r = client.session.get(
            client.base_url + "/api/3/workflows",
            params={"$limit": 500, "$page": page},
            verify=client.verify_ssl, timeout=60,
        )
        if r.status_code != 200:
            break
        members = r.json().get("hydra:member") or []
        if not members:
            break
        for m in members:
            u = m.get("uuid")
            n = m.get("name")
            if u: by_uuid[u] = m
            if n: by_name[n] = m
        if len(members) < 500:
            break
        page += 1
    print(f"  live workflow index: {len(by_uuid)} by uuid, {len(by_name)} by name", flush=True)
    return by_uuid, by_name


def _hydrate(client, uuid: str) -> dict | None:
    r = client.session.get(
        client.base_url + f"/api/3/workflows/{uuid}?$relationships=true",
        verify=client.verify_ssl, timeout=20,
    )
    return r.json() if r.status_code == 200 else None


def _fetch_live_workflow(client, *, uuid: str | None = None,
                         name: str | None = None) -> dict | None:
    """Return the live workflow body (with steps[]) matching uuid or
    name, or None. Tries uuid first (fast 200/404), falls back to name."""
    if uuid:
        r = client.session.get(
            client.base_url + f"/api/3/workflows/{uuid}"
            f"?$relationships=true",
            verify=client.verify_ssl, timeout=20,
        )
        if r.status_code == 200:
            return r.json()
    if name:
        r = client.session.get(
            client.base_url + "/api/3/workflows",
            params={"name": name, "$limit": 5},
            verify=client.verify_ssl, timeout=20,
        )
        if r.status_code == 200:
            members = r.json().get("hydra:member") or []
            for m in members:
                if m.get("name") != name:
                    continue
                # Listing endpoint returns shallow steps[]; re-fetch the
                # single record so steps are fully hydrated for the
                # equivalence comparator.
                live_uuid = m.get("uuid")
                if live_uuid:
                    r2 = client.session.get(
                        client.base_url + f"/api/3/workflows/{live_uuid}"
                        f"?$relationships=true",
                        verify=client.verify_ssl, timeout=20,
                    )
                    if r2.status_code == 200:
                        return r2.json()
                return m
    return None


def _step_signature(step: dict) -> tuple[str, str]:
    """Loose fingerprint of one step: (name, stepType identifier).

    Deliberately ignores `arguments` because re-restoring a playbook
    generates fresh step UUIDs, and most arguments contain IRI
    references between steps (`next`, route targets, ...) - so two
    semantically-identical playbooks have different argument blobs.
    Step names are unique within a workflow (FSR enforces it), which
    makes (name, type) a reliable set-based identity.
    """
    # Audit stores stepType as an IRI string; live returns it as a
    # hydrated dict. Reduce both to the trailing UUID so they're
    # comparable.
    stype = step.get("stepType")
    if isinstance(stype, dict):
        stype = stype.get("@id") or stype.get("uuid") or ""
    stype = str(stype or "")
    if "/" in stype:
        stype = stype.rsplit("/", 1)[-1]
    return (step.get("name") or "", stype)


def _workflows_equivalent(audit_wf: dict, live_wf: dict) -> bool:
    """True iff live has the same name and the same set of
    (step-name, step-type) pairs as the audit snapshot.

    Tolerates: regenerated step UUIDs, argument drift, route shuffles,
    timestamp/owner differences.
    Catches: missing steps, renamed steps, type changes, added steps.
    """
    if (audit_wf.get("name") or "") != (live_wf.get("name") or ""):
        return False
    a = sorted(_step_signature(s) for s in (audit_wf.get("steps") or []))
    b = sorted(_step_signature(s) for s in (live_wf.get("steps") or []))
    return a == b


# Step-type IRIs -> friendly name. Filled lazily from any live step the
# comparator sees, so diff output reads "SetVariable" instead of a uuid.
_STEPTYPE_NAMES: dict[str, str] = {}


def _learn_steptype_name(step: dict) -> None:
    stype = step.get("stepType")
    if isinstance(stype, dict) and stype.get("@id") and stype.get("name"):
        uid = stype["@id"].rsplit("/", 1)[-1]
        _STEPTYPE_NAMES.setdefault(uid, stype["name"])


def _diff_workflows(audit_wf: dict, live_wf: dict) -> dict:
    """Set-based step diff between audit and live. Returns
    {only_in_live: [...], only_in_audit: [...]} keyed by (step name,
    friendly step-type)."""
    for s in (live_wf.get("steps") or []):
        _learn_steptype_name(s)
    a = {_step_signature(s) for s in (audit_wf.get("steps") or [])}
    b = {_step_signature(s) for s in (live_wf.get("steps") or [])}
    def pretty(sig: tuple) -> tuple[str, str]:
        return (sig[0], _STEPTYPE_NAMES.get(sig[1], sig[1]))
    return {
        "only_in_live":  sorted(pretty(s) for s in (b - a)),
        "only_in_audit": sorted(pretty(s) for s in (a - b)),
    }


def _bulk_index_step_types(client) -> dict[str, str]:
    """Map every workflow_step_types UUID -> friendly name in one GET.
    Lets the diff output read 'SetVariable' instead of a 36-char uuid."""
    out: dict[str, str] = {}
    try:
        r = client.session.get(
            client.base_url + "/api/3/workflow_step_types",
            params={"$limit": 500},
            verify=client.verify_ssl, timeout=30,
        )
        if r.status_code != 200:
            return out
        for m in r.json().get("hydra:member") or []:
            u = m.get("uuid")
            n = m.get("name")
            if u and n:
                out[u] = n
    except Exception:
        pass
    return out


def _bulk_index_live_collections(client) -> dict[str, str]:
    """Fetch every workflow_collection's name -> uuid in one shot.

    The returned dict also carries reverse lookups keyed as
    `__uuid__<uuid>` -> name so callers can resolve a workflow's parent
    `collection` IRI back to its live name without a second index dict.
    """
    print("  indexing live workflow_collections...", flush=True)
    by_name: dict[str, str] = {}
    page = 1
    while True:
        r = client.session.get(
            client.base_url + "/api/3/workflow_collections",
            params={"$limit": 500, "$page": page},
            verify=client.verify_ssl, timeout=60,
        )
        if r.status_code != 200:
            break
        members = r.json().get("hydra:member") or []
        if not members:
            break
        for m in members:
            if m.get("name") and m.get("uuid"):
                by_name[m["name"]] = m["uuid"]
                by_name[f"__uuid__{m['uuid']}"] = m["name"]
        if len(members) < 500:
            break
        page += 1
    # Count distinct collections (exclude reverse-index entries).
    distinct = sum(1 for k in by_name if not k.startswith("__uuid__"))
    print(f"  collection index: {distinct}", flush=True)
    return by_name


def _collection_uuid(client, name: str) -> str | None:
    """Legacy single-lookup. Prefer the bulk-indexed dict in cmd_recover_deleted."""
    r = client.session.get(
        client.base_url + "/api/3/workflow_collections",
        params={"name": name, "$limit": 5},
        verify=client.verify_ssl, timeout=15,
    )
    if r.status_code != 200:
        return None
    members = r.json().get("hydra:member") or []
    return members[0].get("uuid") if members else None


_WF_IRI_RX = __import__("re").compile(
    r"/api/3/workflows/([0-9a-fA-F-]{36})")


def _rewrite_workflow_refs(
    workflow: dict, *,
    audit_uuid_to_name: dict[str, str],
    live_by_uuid: dict[str, dict],
    live_by_name: dict[str, dict],
) -> tuple[dict, list[dict], list[dict]]:
    """Walk every step's arguments and rewrite any workflow IRI whose
    target UUID no longer exists live - look up the old UUID's name
    via the audit map and substitute the current live UUID for that
    name. Returns (workflow, rewrites, unresolved). Mutates in place.

    Catches cross-collection refs (`workflowReference: /api/3/workflows/<u>`)
    plus any other arg field that happens to embed a workflow IRI.
    Same-collection `target: <name>` refs are name-based and ignored
    here - they survive any UUID churn.
    """
    rewrites: list[dict] = []
    unresolved: list[dict] = []

    def _walk(node, step_name: str) -> object:
        if isinstance(node, dict):
            for k, v in list(node.items()):
                node[k] = _walk(v, step_name)
            return node
        if isinstance(node, list):
            for i, v in enumerate(node):
                node[i] = _walk(v, step_name)
            return node
        if isinstance(node, str) and "/api/3/workflows/" in node:
            def sub(m):
                old = m.group(1)
                if old in live_by_uuid:
                    return m.group(0)  # still valid - leave alone
                name = audit_uuid_to_name.get(old)
                target = live_by_name.get(name) if name else None
                if target and target.get("uuid"):
                    rewrites.append({
                        "step": step_name, "old": old,
                        "new": target["uuid"], "name": name,
                    })
                    return f"/api/3/workflows/{target['uuid']}"
                unresolved.append({
                    "step": step_name, "old": old, "name": name,
                })
                return m.group(0)
            return _WF_IRI_RX.sub(sub, node)
        return node

    for step in workflow.get("steps") or []:
        _walk(step.get("arguments"), step.get("name") or "")
    return workflow, rewrites, unresolved


def _restore_one(client, coll_envelope: dict, workflow: dict,
                 dry_run: bool,
                 collection_index: dict[str, str] | None = None,
                 live_workflow_exists: bool = False,
                 ) -> tuple[bool, str]:
    """Restore one workflow.

    Three cases:
      1. `live_workflow_exists` (overwrite): PUT /api/3/workflows/<uuid>
         directly. Updates the row in place; doesn't touch the
         collection or sibling workflows.
      2. Parent collection exists by name: PUT the collection with the
         workflow appended (cascade-persist handles nested upsert).
      3. Neither workflow nor collection exists: POST a fresh
         collection containing just this workflow.
    """
    wf_uuid = workflow.get("uuid")

    if live_workflow_exists and wf_uuid:
        # Hard-delete the live workflow first, then POST the audit
        # collection envelope so the original step/route UUIDs land
        # mutually consistent. PUT'ing in place fails because routes
        # reference step UUIDs and FSR's cascade-persist can't reconcile
        # the live step row UUIDs with the audit's.
        if dry_run:
            return True, (f"DELETE /api/3/workflows/{wf_uuid} then POST "
                          "/api/3/workflow_collections (overwrite)")
        dr = client.session.delete(
            client.base_url + "/api/3/delete/workflows?$hardDelete=true",
            json={"ids": [wf_uuid]},
            verify=client.verify_ssl, timeout=30,
        )
        if dr.status_code not in (200, 204):
            return False, (f"DELETE /api/3/workflows/{wf_uuid} -> "
                           f"{dr.status_code} {dr.text[:200]}")
        # Fall through to the regular POST path below.

    # Prefer the workflow's *real* parent collection (from its
    # `collection` IRI) over the audit's synthetic "<wfname>-Restored"
    # envelope. The audit wraps each deleted workflow in a 1-workflow
    # collection named after the workflow itself, which would scatter
    # siblings into per-workflow collections on restore.
    coll_name = None
    parent_iri = workflow.get("collection")
    if isinstance(parent_iri, str) and parent_iri.startswith(
        "/api/3/workflow_collections/"
    ):
        parent_uuid = parent_iri.rsplit("/", 1)[-1]
        if collection_index is not None:
            coll_name = collection_index.get(f"__uuid__{parent_uuid}")
    if not coll_name:
        coll_name = coll_envelope.get("name") or "Recovered"
    # Strip @id on embedded WorkflowGroups so FSR creates them inline
    # instead of treating @id as a reference lookup (which 400s with
    # EntityNotFoundException when the group uuid doesn't exist on the
    # target box). The "uuid" field is preserved so the group lands with
    # its original identifier and step `group` back-refs still match.
    for _g in workflow.get("groups") or []:
        if isinstance(_g, dict):
            _g.pop("@id", None)
            _g.pop("@context", None)
    # Strip the "-Restored" suffix FSR sometimes auto-appends.
    if coll_name.endswith("-Restored"):
        coll_name = coll_name[: -len("-Restored")]

    if collection_index is not None:
        existing_uuid = collection_index.get(coll_name)
    else:
        existing_uuid = _collection_uuid(client, coll_name)
    coll_to_send = {
        "@type": "WorkflowCollection",
        "name": coll_name,
        "visible": True,
        "workflows": [workflow],
    }
    if existing_uuid:
        coll_to_send["uuid"] = existing_uuid
        method, path = "PUT", f"/api/3/workflow_collections/{existing_uuid}"
    else:
        method, path = "POST", "/api/3/workflow_collections"

    if dry_run:
        return True, f"{method} {path} (would restore into collection '{coll_name}')"

    if method == "PUT":
        r = client.session.put(
            client.base_url + path, json=coll_to_send,
            verify=client.verify_ssl, timeout=60,
        )
    else:
        r = client.session.post(
            client.base_url + path, json=coll_to_send,
            verify=client.verify_ssl, timeout=60,
        )

    if r.status_code in (200, 201):
        if method == "POST" and collection_index is not None:
            try:
                new_uuid = (r.json() or {}).get("uuid")
            except Exception:
                new_uuid = None
            if new_uuid:
                collection_index[coll_name] = new_uuid
        return True, f"{method} {path} -> {r.status_code}"
    # POST collided with an existing collection created earlier in this
    # run (or out-of-band). Look it up live and retry as a PUT once.
    if method == "POST" and r.status_code == 409:
        existing_uuid = _collection_uuid(client, coll_name)
        if existing_uuid:
            if collection_index is not None:
                collection_index[coll_name] = existing_uuid
            coll_to_send["uuid"] = existing_uuid
            put_path = f"/api/3/workflow_collections/{existing_uuid}"
            r2 = client.session.put(
                client.base_url + put_path, json=coll_to_send,
                verify=client.verify_ssl, timeout=60,
            )
            if r2.status_code in (200, 201):
                return True, f"PUT {put_path} -> {r2.status_code} (after 409)"
            return False, (f"PUT {put_path} -> {r2.status_code} "
                           f"{r2.text[:200]} (after POST 409)")
    return False, f"{method} {path} -> {r.status_code} {r.text[:200]}"


def _fetch_collection_with_workflows(client, coll_uuid: str) -> dict | None:
    r = client.session.get(
        client.base_url + f"/api/3/workflow_collections/{coll_uuid}",
        verify=client.verify_ssl, timeout=30,
    )
    if r.status_code != 200:
        return None
    return r.json()


def cmd_reorganize(args, client, coll_index: dict[str, str],
                   audit_plan: list[dict]) -> int:
    """Post-pass cleanup for prior recover runs that scattered workflows
    into per-workflow collections.

    Strategy:
      1. From the audit plan, build workflow_uuid -> original_parent_uuid.
      2. For each workflow whose original parent uuid (or name) resolves
         to a live collection, PUT the workflow into that collection.
         FSR's cascade-persist moves the row, leaving the per-workflow
         junk collection empty.
      3. Delete any collection whose name matches one of the audit-known
         workflow names and which now has zero workflows.
    """
    dry = not args.apply

    # Step 1: audit map. Names are stored alongside uuids so we can fall
    # back to name lookup if the original parent uuid no longer exists.
    wf_to_parent_uuid: dict[str, str] = {}
    parent_uuids: set[str] = set()
    wf_names: set[str] = set()
    for it in audit_plan:
        wf = it.get("workflow") or {}
        wf_uuid = wf.get("uuid")
        if not wf_uuid:
            continue
        if wf.get("name"):
            wf_names.add(wf["name"])
        parent_iri = wf.get("collection")
        if isinstance(parent_iri, str) and "/workflow_collections/" in parent_iri:
            p_uuid = parent_iri.rsplit("/", 1)[-1]
            wf_to_parent_uuid[wf_uuid] = p_uuid
            parent_uuids.add(p_uuid)

    print(f"  audit workflows with parent IRI: {len(wf_to_parent_uuid)}")
    print(f"  distinct original parents:        {len(parent_uuids)}")

    # Step 2: fetch every live collection's full body once so we know
    # which workflows currently live where. Single pass, no per-workflow
    # GET storm.
    print("  fetching live collection bodies (with workflows)...", flush=True)
    coll_bodies: dict[str, dict] = {}
    page = 1
    while True:
        r = client.session.get(
            client.base_url + "/api/3/workflow_collections",
            params={"$limit": 200, "$page": page, "$relationships": "true"},
            verify=client.verify_ssl, timeout=120,
        )
        if r.status_code != 200:
            print(f"  list page {page} -> {r.status_code} {r.text[:200]}")
            return 2
        members = r.json().get("hydra:member") or []
        if not members:
            break
        for m in members:
            if m.get("uuid"):
                coll_bodies[m["uuid"]] = m
        if len(members) < 200:
            break
        page += 1
    print(f"  live collections fetched: {len(coll_bodies)}")

    # Locate each restored workflow live and figure out its target.
    moves: list[tuple[str, str, str, str]] = []  # (wf_uuid, wf_name, target_uuid, target_name)
    skipped_no_parent: list[str] = []
    for wf_uuid, parent_uuid in wf_to_parent_uuid.items():
        # Find current home of this workflow.
        current_home: dict | None = None
        wf_body: dict | None = None
        for c in coll_bodies.values():
            for w in c.get("workflows") or []:
                if w.get("uuid") == wf_uuid:
                    current_home = c
                    wf_body = w
                    break
            if current_home:
                break
        if not current_home or not wf_body:
            continue  # workflow not currently restored
        # Already in its real parent? skip.
        if current_home.get("uuid") == parent_uuid:
            continue
        # Resolve target by uuid (preferred) or by original name.
        target = coll_bodies.get(parent_uuid)
        if not target:
            skipped_no_parent.append(wf_body.get("name") or wf_uuid)
            continue
        moves.append((wf_uuid, wf_body.get("name") or wf_uuid,
                      target["uuid"], target.get("name") or ""))

    print(f"\n  workflows to move:        {len(moves)}")
    print(f"  workflows w/ no live parent: {len(skipped_no_parent)}")

    # --max caps both moves and the matching junk deletes so a smoke run
    # exercises the full pipeline without touching the whole box.
    if args.max and len(moves) > args.max:
        print(f"  capped to first {args.max} moves (was {len(moves)})")
        moves = moves[: args.max]

    # Step 3 (preview): which junk collections would empty out?
    moving_wf_uuids = {m[0] for m in moves}
    junk_to_delete: list[dict] = []
    for c in coll_bodies.values():
        wfs = c.get("workflows") or []
        if not wfs:
            # Already empty - delete only if name looks like a recover
            # artifact (matches an audited workflow name).
            if c.get("name") in wf_names:
                junk_to_delete.append(c)
            continue
        remaining = [w for w in wfs if w.get("uuid") not in moving_wf_uuids]
        if remaining:
            continue
        if c.get("name") in wf_names:
            junk_to_delete.append(c)

    print(f"  junk collections to delete: {len(junk_to_delete)}")

    mode = "DRY-RUN" if dry else "APPLY"
    print(f"\n=== REORGANIZE {mode} ===")
    if dry:
        for wf_uuid, wf_name, t_uuid, t_name in moves[:50]:
            print(f"  MOVE {wf_name!r:50s} -> '{t_name}'")
        if len(moves) > 50:
            print(f"  ...({len(moves) - 50} more)")
        for c in junk_to_delete[:50]:
            print(f"  DELETE collection '{c.get('name')}' ({c.get('uuid')})")
        if len(junk_to_delete) > 50:
            print(f"  ...({len(junk_to_delete) - 50} more)")
        return 0

    # Apply: per-target, PUT the collection body with the migrating
    # workflows appended. FSR's cascade-persist moves them.
    moves_by_target: dict[str, list[str]] = {}
    for wf_uuid, _, t_uuid, _ in moves:
        moves_by_target.setdefault(t_uuid, []).append(wf_uuid)

    ok_moves = fail_moves = 0
    for t_uuid, wf_uuids in moves_by_target.items():
        target = coll_bodies[t_uuid]
        # Find workflow bodies from their current homes.
        new_workflows = list(target.get("workflows") or [])
        existing_uuids = {w.get("uuid") for w in new_workflows}
        for wf_uuid in wf_uuids:
            if wf_uuid in existing_uuids:
                continue
            for c in coll_bodies.values():
                for w in c.get("workflows") or []:
                    if w.get("uuid") == wf_uuid:
                        new_workflows.append(w)
                        break
        body = {
            "@type": "WorkflowCollection",
            "uuid": t_uuid,
            "name": target.get("name"),
            "visible": target.get("visible", True),
            "workflows": new_workflows,
        }
        r = client.session.put(
            client.base_url + f"/api/3/workflow_collections/{t_uuid}",
            json=body, verify=client.verify_ssl, timeout=120,
        )
        if r.status_code in (200, 201):
            ok_moves += len(wf_uuids)
            print(f"  OK  moved {len(wf_uuids):3d} -> '{target.get('name')}'")
        else:
            fail_moves += len(wf_uuids)
            print(f"  ERR '{target.get('name')}' PUT -> {r.status_code} {r.text[:200]}")

    # Delete empties. Re-fetch each junk collection first to confirm it
    # is now empty (defense against partial PUT successes above).
    ok_del = fail_del = 0
    for c in junk_to_delete:
        cur = _fetch_collection_with_workflows(client, c["uuid"])
        if cur is None:
            fail_del += 1
            print(f"  ERR re-fetch {c.get('name')!r} -> gone or 4xx")
            continue
        if cur.get("workflows"):
            print(f"  SKIP '{c.get('name')}' still has "
                  f"{len(cur['workflows'])} workflow(s)")
            continue
        r = client.session.delete(
            client.base_url + f"/api/3/workflow_collections/{c['uuid']}",
            verify=client.verify_ssl, timeout=30,
        )
        if r.status_code in (200, 204):
            ok_del += 1
        else:
            fail_del += 1
            print(f"  ERR DELETE '{c.get('name')}' -> "
                  f"{r.status_code} {r.text[:200]}")

    print(f"\nREORGANIZE summary: moved {ok_moves} ok / {fail_moves} failed, "
          f"deleted {ok_del} ok / {fail_del} failed")
    return 0 if (fail_moves == 0 and fail_del == 0) else 1


def cmd_recover_deleted(args: argparse.Namespace) -> int:
    from probes import _env  # type: ignore

    cfg = _env.get_config()
    if not cfg.is_live():
        print("FSR_BASE_URL / auth not configured (.env)", file=sys.stderr)
        return 2
    client = _env.get_client()

    since = _parse_date(args.since)
    until = _parse_date(args.until) if args.until else dt.datetime.now(dt.timezone.utc)
    print(f"Scanning Delete activities for entityType=playbooks "
          f"between {since.isoformat()} and {until.isoformat()}")

    audit_key = (f"audit::{cfg.base_url}::{_ms(since)}::{_ms(until)}"
                 f"::{args.limit}")
    cached_audit = None if args.refresh else _cache_get(audit_key)
    if cached_audit is not None:
        entries = cached_audit
        print(f"  audit entries: {len(entries)} (from cache)")
    else:
        entries = _fetch_delete_activities(
            client, _ms(since), _ms(until), args.limit)
        _cache_put(audit_key, entries)
        print(f"  audit entries: {len(entries)}")

    block = set() if args.include_all_sources else set(DEFAULT_SOURCE_BLOCKLIST)
    if args.only_source:
        block = set()  # explicit --only-source overrides the blocklist

    plan: list[dict[str, Any]] = []
    seen_uuids: set[str] = set()
    for e in entries:
        src = e.get("source") or ""
        if args.only_source and src != args.only_source:
            continue
        if src in block:
            continue
        wf_uuid = e.get("entityUuid")
        if not wf_uuid or wf_uuid in seen_uuids:
            continue
        seen_uuids.add(wf_uuid)
        data = ((e.get("data") or {}).get("data") or [])
        if not data:
            continue
        coll_env = data[0] if isinstance(data[0], dict) else {}
        wfs = coll_env.get("workflows") or []
        target = next(
            (w for w in wfs if isinstance(w, dict) and w.get("uuid") == wf_uuid),
            None,
        )
        if not target:
            continue
        plan.append({
            "wf_uuid": wf_uuid,
            "wf_name": target.get("name") or e.get("displayName") or wf_uuid,
            "coll_envelope": coll_env,
            "workflow": target,
            "source": src,
            "ts": e.get("transactionDate"),
        })

    if not plan:
        print("Nothing to recover.")
        return 0

    print(f"  unique deleted workflows: {len(plan)}")
    print(f"  source blocklist:         {sorted(block) or '(none)'}")

    if args.reorganize:
        coll_index = _bulk_index_live_collections(client)
        return cmd_reorganize(args, client, coll_index, plan)

    # Pre-load step-type uuid -> name map so diff output is readable.
    sts_key = f"step_types::{cfg.base_url}"
    sts_cached = None if args.refresh else _cache_get(sts_key)
    if sts_cached:
        _STEPTYPE_NAMES.update(sts_cached)
    else:
        sts = _bulk_index_step_types(client)
        _STEPTYPE_NAMES.update(sts)
        _cache_put(sts_key, sts)

    # Pre-load workflow_collections so per-restore lookup is local. Was
    # at the bottom of the function which polluted diff output; doing
    # it up front keeps the diff section clean.
    coll_index_key = f"colls::{cfg.base_url}"
    coll_index = None if args.refresh else _cache_get(coll_index_key)
    if not coll_index:
        coll_index = _bulk_index_live_collections(client)
        _cache_put(coll_index_key, coll_index)

    # Bulk-index every live workflow once. Cached on disk for fast
    # iteration; --refresh forces re-fetch.
    index_key = f"index::{cfg.base_url}"
    cached = None if args.refresh else _cache_get(index_key)
    if cached:
        print(f"  live workflow index: loaded from cache "
              f"({len(cached['by_uuid'])} by uuid)")
        by_uuid = cached["by_uuid"]
        by_name = cached["by_name"]
    else:
        by_uuid, by_name = _bulk_index_live_workflows(client)
        _cache_put(index_key, {"by_uuid": by_uuid, "by_name": by_name})

    # Decide which records need full hydration (only those that matched
    # a live record - missing ones go straight to to_restore).
    to_hydrate: list[tuple[dict, dict]] = []  # (plan_item, shallow_live)
    to_restore: list[dict[str, Any]] = []
    for item in plan:
        shallow = by_uuid.get(item["wf_uuid"]) or by_name.get(item["wf_name"])
        if shallow is None:
            to_restore.append(item)
        else:
            to_hydrate.append((item, shallow))

    # Hydrate in parallel - this used to be the bottleneck.
    live_full: dict[str, dict] = {}
    hyd_key = f"hydrated::{cfg.base_url}::" + ",".join(
        sorted(s.get("uuid") for _, s in to_hydrate if s.get("uuid")))
    cached_h = None if args.refresh else _cache_get(hyd_key)
    if cached_h:
        live_full = cached_h
        print(f"  hydrated live records: loaded from cache "
              f"({len(live_full)})")
    elif to_hydrate:
        print(f"  hydrating {len(to_hydrate)} live records "
              f"({_HYDRATE_WORKERS} workers)...", flush=True)
        uuids = [s.get("uuid") for _, s in to_hydrate if s.get("uuid")]
        with ThreadPoolExecutor(max_workers=_HYDRATE_WORKERS) as pool:
            futures = {pool.submit(_hydrate, client, u): u for u in uuids}
            for i, fut in enumerate(as_completed(futures), 1):
                u = futures[fut]
                doc = fut.result()
                if doc:
                    live_full[u] = doc
                if i % 100 == 0:
                    print(f"    {i}/{len(uuids)}", flush=True)
        _cache_put(hyd_key, live_full)

    skipped_equiv: list[str] = []
    skipped_diff: list[dict] = []
    for item, shallow in to_hydrate:
        live = live_full.get(shallow.get("uuid"), shallow)
        if _workflows_equivalent(item["workflow"], live):
            skipped_equiv.append(item["wf_name"])
            if args.verbose:
                print(f"  skip (already present, same content): "
                      f"{item['wf_name']}")
            continue
        # Live exists but content differs - don't auto-overwrite.
        diff = _diff_workflows(item["workflow"], live)
        skipped_diff.append({
            "name": item["wf_name"],
            "live_uuid": live.get("uuid") or "?",
            "audit_uuid": item["wf_uuid"],
            "diff": diff,
        })
        if args.overwrite:
            # Tag this item as an overwrite so the restore path uses
            # the direct PUT /api/3/workflows/<uuid> instead of trying
            # to POST a collection (which would 409 on UUID uniqueness).
            item["_overwrite_target_uuid"] = live.get("uuid") or item["wf_uuid"]
            to_restore.append(item)

    print(f"  already present (same):   {len(skipped_equiv)}")
    print(f"  live differs:             {len(skipped_diff)}"
          f"{' (will overwrite)' if args.overwrite else ' (skipped; use --overwrite to force)'}")
    print(f"  to restore:               {len(to_restore)}")

    if skipped_diff and (args.show_diffs or args.verbose):
        # Classify each diff so the user can triage quickly.
        verdicts: dict[str, list[dict]] = {
            "additions only (live evolved since deletion - keep live)": [],
            "removals only (overwrite to restore lost steps)": [],
            "mixed (manual review)": [],
        }
        for d in skipped_diff:
            only_l = d["diff"]["only_in_live"]
            only_a = d["diff"]["only_in_audit"]
            if only_l and not only_a:
                verdicts["additions only (live evolved since deletion - keep live)"].append(d)
            elif only_a and not only_l:
                verdicts["removals only (overwrite to restore lost steps)"].append(d)
            else:
                verdicts["mixed (manual review)"].append(d)

        print(f"\n  ===== {len(skipped_diff)} workflows DIFFER from audit =====")
        for verdict, items in verdicts.items():
            if not items:
                continue
            print(f"\n  [{len(items)}]  {verdict}")
            for d in items:
                name = d["name"]
                aud = d["audit_uuid"]
                liv = d["live_uuid"]
                uuid_line = (f"uuid {aud}" if aud == liv
                             else f"audit {aud} -> live {liv}")
                print(f"    * {name}   ({uuid_line})")
                for nm, ty in d["diff"]["only_in_live"]:
                    print(f"        + {nm}  [{ty}]")
                for nm, ty in d["diff"]["only_in_audit"]:
                    print(f"        - {nm}  [{ty}]")
    elif skipped_diff:
        print("    (run with --show-diffs to see what's different)")

    # Optional name filter (substring, case-insensitive) and cap.
    if args.only_name:
        needles = [n.lower() for n in args.only_name]
        before = len(to_restore)
        to_restore = [
            it for it in to_restore
            if any(n in (it["wf_name"] or "").lower() for n in needles)
        ]
        print(f"  after --only-name filter: {len(to_restore)} (was {before})")
    if args.max and len(to_restore) > args.max:
        print(f"  capped to first {args.max} (was {len(to_restore)})")
        to_restore = to_restore[: args.max]

    if not to_restore:
        return 0

    # Build audit-uuid -> name map so we can rewrite cross-collection
    # workflowReference IRIs whose target UUID changed during a prior
    # manual restore.
    audit_uuid_to_name: dict[str, str] = {}
    for it in plan:
        wf = it.get("workflow") or {}
        if wf.get("uuid") and wf.get("name"):
            audit_uuid_to_name[wf["uuid"]] = wf["name"]

    mode = "DRY-RUN" if not args.apply else "APPLY"
    print(f"\n=== {mode} ===")
    ok = fail = 0
    total_rewrites = 0
    unresolved_all: list[dict] = []
    for item in to_restore:
        # Rewrite step-arg workflow IRIs before sending.
        wf, rewrites, unresolved = _rewrite_workflow_refs(
            item["workflow"],
            audit_uuid_to_name=audit_uuid_to_name,
            live_by_uuid=by_uuid, live_by_name=by_name,
        )
        total_rewrites += len(rewrites)
        for u in unresolved:
            u["from"] = item["wf_name"]
            unresolved_all.append(u)
        # If we're overwriting a live workflow, rewrite the workflow's
        # uuid in the audit payload to match the live row (in case the
        # user re-created it with a new uuid). _restore_one will then
        # hard-delete the live row and POST the audit payload fresh.
        overwrite_uuid = item.get("_overwrite_target_uuid")
        if overwrite_uuid:
            wf["uuid"] = overwrite_uuid
        success, msg = _restore_one(
            client, item["coll_envelope"], wf,
            dry_run=not args.apply,
            collection_index=coll_index,
            live_workflow_exists=bool(overwrite_uuid),
        )
        marker = "OK " if success else "ERR"
        rw_tag = f"  [rewrote {len(rewrites)} ref]" if rewrites else ""
        print(f"  {marker} {item['wf_name']:50s} {msg}{rw_tag}")
        ok += int(success); fail += int(not success)

    if total_rewrites:
        print(f"\nReference rewrites:        {total_rewrites}")
    if unresolved_all:
        print(f"Unresolved IRIs:           {len(unresolved_all)}"
              " (target not in live or audit)")
        if args.verbose:
            for u in unresolved_all:
                print(f"  - {u['from']} / step '{u['step']}' "
                      f"-> /api/3/workflows/{u['old']}"
                      f"{' (name: '+u['name']+')' if u['name'] else ''}")
        else:
            print("    (run with -v to list them)")

    print(f"\n{mode} summary: {ok} ok, {fail} failed")
    if args.json_out:
        from pathlib import Path
        Path(args.json_out).write_text(json.dumps(
            [{k: v for k, v in i.items() if k != "coll_envelope"} for i in to_restore],
            indent=2, default=str))
        print(f"plan written to {args.json_out}")

    return 0 if fail == 0 else 1


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "recover-deleted-playbooks",
        help="Rehydrate playbooks deleted from FSR using the activities audit log",
    )
    p.add_argument("--since", required=True,
                   help="Start date (YYYY-MM-DD or ISO-8601)")
    p.add_argument("--until",
                   help="End date (default: now)")
    p.add_argument("--limit", type=int, default=500,
                   help="Max audit entries to scan (default 500)")
    p.add_argument("--apply", action="store_true",
                   help="Actually restore. Without this flag, dry-run only.")
    p.add_argument("--overwrite", action="store_true",
                   help="Restore even if a live workflow with the same "
                        "name exists with different content. Default: skip "
                        "diffs to avoid clobbering edits you've made since "
                        "the deletion.")
    p.add_argument("--show-diffs", action="store_true",
                   help="Print step-level diff for every workflow flagged "
                        "as 'live differs' (additions / removals vs. the "
                        "audit snapshot). Helps decide whether to "
                        "--overwrite.")
    p.add_argument("--max", type=int, default=0,
                   help="Cap the number of restores actually performed "
                        "(0 = no cap). Useful for smoke-testing: --max 3.")
    p.add_argument("--only-name", action="append", default=[],
                   help="Only restore workflows whose name matches this "
                        "string (repeatable). Substring match, case-"
                        "insensitive. E.g. --only-name 'Get Users'.")
    p.add_argument("--include-all-sources", action="store_true",
                   help="Do not filter by source IP; consider every Delete event")
    p.add_argument("--only-source",
                   help="Restrict to deletes from this source IP "
                        "(e.g. 10.100.4.143 for the 2026-05-08 probe rig)")
    p.add_argument("--json-out",
                   help="Write the restore plan to this JSON file")
    p.add_argument("--refresh", action="store_true",
                   help="Bypass the 48-hour disk cache and re-fetch live "
                        "workflows + per-record hydration from FSR.")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--reorganize", action="store_true",
                   help="Post-pass: move workflows from per-workflow "
                        "'<wfname>-Restored' (or '<wfname>') collections "
                        "into their original parent collection (read from "
                        "the workflow's audited `collection` IRI), then "
                        "delete the empty junk collections. Dry-run unless "
                        "combined with --apply.")
    p.set_defaults(func=cmd_recover_deleted)
