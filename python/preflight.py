"""Recycle-bin-aware preflight for playbook pushes.

The compiler emits deterministic uuid5 IDs for every entity table the push
will touch (collection / workflow / step / route). FSR keeps soft-deleted
rows reserved at the DB level — a plain GET 404s but a POST/PUT to the
same uuid hits a UniqueConstraintViolation. Without preflight we never
know we're about to step on something until FSR rejects the push.

This module's job, given a compiled collection dict, is:

  1. Walk it and produce an `Inventory` of the uuids per entity table.
  2. Query each entity table once (POST /api/query/<entity>?$showDeleted=true)
     filtered by `uuid in [...]` to classify every uuid as one of:

       - "fresh"    — not present server-side
       - "live"     — exists, deletedAt is null
       - "recycled" — exists in the recycle bin (deletedAt is a timestamp)

  3. Restore recycled rows by re-PUTting them with `deletedAt: null`.
     (Empirically confirmed against the dev FSR 7.6.x build: a single PUT
      to `/api/3/<entity>/<uuid>?$showDeleted=true` with `deletedAt: null`
      in the body un-soft-deletes the row; a subsequent plain GET returns
      200.)

The classification step does NOT mutate anything; restore is a separate
explicit call. Callers can preflight to surface intent (e.g., the web UI
showing "this push will restore 3 workflows from the recycle bin") before
committing.

Hard-delete is intentionally NOT part of this module. The previous
``_purge_soft_deleted`` path in cli.py was the source of a past
mass-deletion incident; the recycle-bin-restore design here makes
hard-delete unnecessary for the common re-push case.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# Entity tables the compiler writes into, ordered parent-first. The
# restore order matters: FK references resolve cleanly when the parent
# row is restored before its children.
ENTITY_TABLES = (
    "workflow_collections",
    "workflows",
    "workflow_steps",
    "workflow_routes",
)


@dataclass
class _Row:
    """One server-side fact about a uuid."""
    uuid: str
    status: str           # "fresh" | "live" | "recycled"
    name: str | None = None
    deleted_at: float | None = None


@dataclass
class Inventory:
    """All deterministic uuids a push would write, grouped by entity.

    Names are stored alongside so preflight reports can identify rows by
    human-readable label (e.g., "Hello World" rather than the raw uuid).
    """
    by_entity: dict[str, list[str]] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)

    def total(self) -> int:
        return sum(len(v) for v in self.by_entity.values())


def inventory_from_collection(coll_entity: dict[str, Any]) -> Inventory:
    """Walk a compiled collection dict and collect uuids per entity table.

    Shape mirrors what the emitter produces:
      collection
        └── workflows[]
              ├── steps[]
              └── routes[]
    """
    inv = Inventory()
    inv.by_entity = {t: [] for t in ENTITY_TABLES}

    coll_uuid = coll_entity.get("uuid")
    if coll_uuid:
        inv.by_entity["workflow_collections"].append(coll_uuid)
        if coll_entity.get("name"):
            inv.names[coll_uuid] = coll_entity["name"]

    for wf in coll_entity.get("workflows", []) or []:
        wf_uuid = wf.get("uuid")
        if wf_uuid:
            inv.by_entity["workflows"].append(wf_uuid)
            if wf.get("name"):
                inv.names[wf_uuid] = wf["name"]
        for s in wf.get("steps", []) or []:
            if s.get("uuid"):
                inv.by_entity["workflow_steps"].append(s["uuid"])
                if s.get("name"):
                    inv.names[s["uuid"]] = s["name"]
        for rt in wf.get("routes", []) or []:
            if rt.get("uuid"):
                inv.by_entity["workflow_routes"].append(rt["uuid"])
    return inv


def _query_entity(client, entity: str, uuids: list[str]) -> list[dict]:
    """Single batched query: which of these uuids exist on the server,
    soft-deleted or live? Empty list short-circuits to a no-op."""
    if not uuids:
        return []
    # API Platform's /api/query endpoint accepts `operator: in` with a
    # list value. Confirmed against 7.6.x: returns rows whose uuid is
    # in the list, including soft-deleted ones when $showDeleted=true.
    r = client.session.post(
        f"{client.base_url}/api/query/{entity}?$showDeleted=true",
        json={
            "showDeleted": True,
            "logic": "AND",
            "limit": len(uuids),
            "filters": [{
                "field": "uuid", "operator": "in",
                "value": uuids, "type": "primitive",
            }],
        },
        verify=client.verify_ssl, timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"preflight query {entity!r} failed: HTTP {r.status_code} "
            f"{r.text[:200]}"
        )
    return (r.json() or {}).get("hydra:member", []) or []


def classify(client, inv: Inventory) -> dict[str, dict[str, _Row]]:
    """Classify every uuid in the inventory against the live server.

    Returns ``{entity: {uuid: _Row}}``. Missing uuids are marked
    "fresh"; matched rows are "live" or "recycled" based on deletedAt.
    """
    out: dict[str, dict[str, _Row]] = {t: {} for t in ENTITY_TABLES}
    for entity in ENTITY_TABLES:
        uuids = inv.by_entity.get(entity) or []
        if not uuids:
            continue
        rows = _query_entity(client, entity, uuids)
        seen: dict[str, _Row] = {}
        for m in rows:
            u = m.get("uuid")
            if not u:
                continue
            da = m.get("deletedAt")
            seen[u] = _Row(
                uuid=u,
                status="recycled" if da else "live",
                name=m.get("name"),
                deleted_at=da if isinstance(da, (int, float)) else None,
            )
        for u in uuids:
            out[entity][u] = seen.get(u) or _Row(uuid=u, status="fresh")
    return out


def summarize(inv: Inventory, cls: dict[str, dict[str, _Row]]) -> str:
    """Human-readable preflight summary. Three columns per entity:
    fresh / live / recycled. Recycled rows are listed individually so
    the operator sees exactly what will be resurrected."""
    lines: list[str] = []
    coll_uuid = (inv.by_entity.get("workflow_collections") or [None])[0]
    coll_name = inv.names.get(coll_uuid or "", "<unknown>")
    lines.append(f"Preflight for collection {coll_name!r} ({coll_uuid}):")
    for entity in ENTITY_TABLES:
        rows = cls.get(entity, {})
        if not rows:
            continue
        fresh = sum(1 for r in rows.values() if r.status == "fresh")
        live = sum(1 for r in rows.values() if r.status == "live")
        recycled = [r for r in rows.values() if r.status == "recycled"]
        lines.append(
            f"  {entity:22s} fresh={fresh:<3d} live={live:<3d} "
            f"recycled={len(recycled):<3d}"
        )
        for r in recycled:
            label = r.name or inv.names.get(r.uuid, "")
            lines.append(f"    RECYCLED  {r.uuid}  {label!r}")
    return "\n".join(lines)


def find_foreign_workflows(
    client, coll_uuid: str, known_workflow_uuids: Iterable[str],
) -> list[dict]:
    """List workflows that live under ``coll_uuid`` but aren't in our YAML.

    These are usually playbooks a user added via the FSR web UI after our
    original push. A naive cascade-delete on the collection would wipe
    them — surfacing them in preflight lets the caller refuse to proceed
    until the user moves them elsewhere (or explicitly opts into loss).

    Returns ``[{"uuid": …, "name": …, "deletedAt": …}, …]``. Empty list
    means the collection contents match the YAML 1:1.

    FK-bound: queries by ``collection`` IRI, so the result cannot leak
    workflows from other collections.
    """
    known = set(known_workflow_uuids)
    coll_iri = f"/api/3/workflow_collections/{coll_uuid}"
    r = client.session.post(
        f"{client.base_url}/api/query/workflows?$showDeleted=true",
        json={
            "showDeleted": True,
            "logic": "AND",
            "limit": 1000,
            "filters": [{
                "field": "collection", "operator": "eq",
                "value": coll_iri, "type": "primitive",
            }],
        },
        verify=client.verify_ssl, timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"foreign-child query failed: HTTP {r.status_code} {r.text[:200]}"
        )
    members = (r.json() or {}).get("hydra:member", []) or []
    foreign: list[dict] = []
    for w in members:
        u = w.get("uuid")
        if not u or u in known:
            continue
        # Verify the parent FK actually matches before flagging — belt
        # and suspenders in case the server filter ever misbehaves.
        parent = w.get("collection") or w.get("workflowCollection") or ""
        if isinstance(parent, dict):
            parent = parent.get("@id") or ""
        if not str(parent).endswith(coll_iri):
            continue
        foreign.append({
            "uuid": u,
            "name": w.get("name"),
            "deletedAt": w.get("deletedAt"),
        })
    return foreign


def find_children_of_workflows(
    client, workflow_uuids: list[str],
) -> dict[str, list[str]]:
    """For each workflow uuid, find every step + route uuid that lives
    server-side under it. Returns ``{"workflow_steps": […], "workflow_routes": […]}``.

    Used by the purge path to clean up orphan child rows that don't
    appear in the new YAML (e.g. when the playbook's step structure
    changed between pushes). FK-bound discovery — we only follow uuids
    that belong to workflows we already own, so the scope cannot leak
    across collections.
    """
    out: dict[str, list[str]] = {"workflow_steps": [], "workflow_routes": []}
    if not workflow_uuids:
        return out
    for wf_uuid in workflow_uuids:
        try:
            r = client.session.get(
                f"{client.base_url}/api/3/workflows/{wf_uuid}"
                f"?$relationships=true&$showDeleted=true",
                verify=client.verify_ssl, timeout=20,
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"child discovery: GET workflow {wf_uuid} raised {e!r}"
            )
        if r.status_code == 404:
            continue
        if r.status_code != 200:
            raise RuntimeError(
                f"child discovery: GET workflow {wf_uuid} HTTP {r.status_code}"
            )
        body = r.json() or {}
        # Belt-and-suspenders: verify the returned uuid matches what we
        # asked for. If FSR ever misroutes, fail closed.
        if body.get("uuid") and body["uuid"] != wf_uuid:
            raise RuntimeError(
                f"child discovery: response uuid {body.get('uuid')!r} != "
                f"requested {wf_uuid!r}"
            )
        for s in body.get("steps") or []:
            if isinstance(s, dict) and s.get("uuid"):
                if s["uuid"] not in out["workflow_steps"]:
                    out["workflow_steps"].append(s["uuid"])
        for rt in body.get("routes") or []:
            if isinstance(rt, dict) and rt.get("uuid"):
                if rt["uuid"] not in out["workflow_routes"]:
                    out["workflow_routes"].append(rt["uuid"])
    return out


def recycled_uuids(cls: dict[str, dict[str, _Row]]) -> dict[str, list[str]]:
    """Return ``{entity: [uuid, …]}`` for everything classified recycled."""
    return {
        entity: [u for u, r in rows.items() if r.status == "recycled"]
        for entity, rows in cls.items()
    }


def restore_recycled(
    client,
    recycled: dict[str, list[str]],
) -> tuple[int, list[str]]:
    """Restore each recycled uuid by re-PUTting its body with
    ``deletedAt: null``. Returns (restored_count, errors).

    Restore order is parent-first (collection → workflow → step → route)
    so FK validation succeeds at each step. Each row is fetched fresh
    via ``GET …?$showDeleted=true`` so we PUT a complete body — partial
    bodies risk wiping unmodelled fields.
    """
    restored = 0
    errors: list[str] = []
    for entity in ENTITY_TABLES:
        for uuid in recycled.get(entity) or []:
            try:
                gr = client.session.get(
                    f"{client.base_url}/api/3/{entity}/{uuid}?$showDeleted=true",
                    verify=client.verify_ssl, timeout=20,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"{entity}/{uuid}: GET raised {e!r}")
                continue
            if gr.status_code != 200:
                errors.append(
                    f"{entity}/{uuid}: GET HTTP {gr.status_code}"
                )
                continue
            try:
                body = gr.json() or {}
            except Exception as e:  # noqa: BLE001
                errors.append(f"{entity}/{uuid}: JSON parse {e!r}")
                continue
            # Strip Hydra/JSON-LD scaffolding API Platform rejects on PUT.
            clean = {k: v for k, v in body.items() if not k.startswith("@")}
            clean["deletedAt"] = None
            try:
                pr = client.session.put(
                    f"{client.base_url}/api/3/{entity}/{uuid}?$showDeleted=true",
                    json=clean, verify=client.verify_ssl, timeout=30,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"{entity}/{uuid}: PUT raised {e!r}")
                continue
            if pr.status_code >= 400:
                errors.append(
                    f"{entity}/{uuid}: PUT HTTP {pr.status_code} "
                    f"{pr.text[:200]}"
                )
                continue
            restored += 1
    return restored, errors
