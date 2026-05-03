"""FSR WorkflowCollection JSON -> IR.

The inverse of `emitter.emit`. Used for the round-trip acceptance test
and (later) for "import an existing playbook into the YAML world."

Lossiness: FSR JSON carries fields the IR doesn't model (lastModifyDate,
deletedAt, layout coords, recordTags, ownership). Those are dropped
on the way in; the IR is the human-meaningful subset.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .ir import Collection, Playbook, Step
from .resolver import SHORT_TYPE_TO_FSR

_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}


def _slugify(name: str, taken: set[str]) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (name or "step").lower()).strip("_") or "step"
    base = s
    i = 2
    while s in taken:
        s = f"{base}_{i}"
        i += 1
    taken.add(s)
    return s


def decompile(fsr_json: dict[str, Any], db_path: Path) -> Collection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        type_by_uuid = {
            r["uuid"]: r["name"] for r in conn.execute(
                "SELECT uuid, name FROM step_types"
            )
        }
    finally:
        conn.close()

    if "data" not in fsr_json or not fsr_json["data"]:
        raise ValueError("not an FSR WorkflowCollection JSON (missing data[])")
    coll = fsr_json["data"][0]

    playbooks: list[Playbook] = []
    for wf in coll.get("workflows", []):
        playbooks.append(_decompile_workflow(wf, type_by_uuid))

    return Collection(
        name=coll.get("name", "") or "",
        description=coll.get("description", "") or "",
        visible=bool(coll.get("visible", True)),
        playbooks=playbooks,
    )


def _decompile_workflow(wf: dict[str, Any], type_by_uuid: dict[str, str]) -> Playbook:
    raw_steps = wf.get("steps", []) or []
    raw_routes = wf.get("routes", []) or []

    # Assign a stable id per step (slug of name)
    taken: set[str] = set()
    id_by_uuid: dict[str, str] = {}
    canonical_by_uuid: dict[str, str] = {}
    short_by_uuid: dict[str, str] = {}
    for s in raw_steps:
        u = s.get("uuid") or ""
        sid = _slugify(s.get("name", ""), taken)
        id_by_uuid[u] = sid
        # `stepType` is an IRI string in export JSON, but a nested dict
        # when fetched via /api/3/workflows?$relationships=true. Handle both.
        st_field = s.get("stepType")
        if isinstance(st_field, dict):
            st_uuid = st_field.get("uuid", "")
            canonical = st_field.get("name") or type_by_uuid.get(st_uuid, "")
        elif isinstance(st_field, str):
            st_uuid = st_field.rsplit("/", 1)[-1]
            canonical = type_by_uuid.get(st_uuid, "")
        else:
            st_uuid = ""
            canonical = ""
        canonical_by_uuid[u] = canonical
        short_by_uuid[u] = _FSR_TO_SHORT.get(canonical, canonical)

    def _to_uuid(field):
        """Normalize an IRI string or expanded dict to a uuid."""
        if isinstance(field, dict):
            return field.get("uuid") or ""
        if isinstance(field, str):
            return field.rsplit("/", 1)[-1]
        return ""

    # Build adjacency (source uuid -> [(target uuid, label)])
    adj: dict[str, list[tuple[str, str | None]]] = {}
    for r in raw_routes:
        s_uuid = _to_uuid(r.get("sourceStep"))
        t_uuid = _to_uuid(r.get("targetStep"))
        if not s_uuid or not t_uuid:
            continue
        adj.setdefault(s_uuid, []).append((t_uuid, r.get("label")))

    steps_out: list[Step] = []
    for s in raw_steps:
        u = s.get("uuid") or ""
        sid = id_by_uuid[u]
        outs = adj.get(u, [])
        nxt: str | None = None
        branches: dict[str, str] = {}
        unlabeled: list[str] = []
        if len(outs) == 1 and not outs[0][1]:
            t_uuid, _ = outs[0]
            nxt = id_by_uuid.get(t_uuid)
        else:
            for t_uuid, label in outs:
                tgt_id = id_by_uuid.get(t_uuid)
                if not tgt_id:
                    continue
                if label:
                    branches[label] = tgt_id
                else:
                    unlabeled.append(tgt_id)

        steps_out.append(Step(
            id=sid,
            type=short_by_uuid.get(u, "") or "unknown",
            name=s.get("name", "") or sid,
            arguments=s.get("arguments") or {},
            next=nxt,
            branches=branches,
            unlabeled_next=unlabeled,
            step_type_uuid=(
                s["stepType"].get("uuid") if isinstance(s.get("stepType"), dict)
                else (s.get("stepType") or "").rsplit("/", 1)[-1] or None
            ),
            step_type_name=canonical_by_uuid.get(u),
        ))

    trigger_uuid = _to_uuid(wf.get("triggerStep"))
    trigger_id = id_by_uuid.get(trigger_uuid)

    # FSR is inconsistent here: parameters is either `{}` (empty) or a
    # list of parameter names. Normalize to a list of strings.
    raw_params = wf.get("parameters") or []
    if isinstance(raw_params, list):
        params = [p for p in raw_params if isinstance(p, str)]
    else:
        params = []

    return Playbook(
        name=wf.get("name", "") or "",
        description=wf.get("description", "") or "",
        tag=wf.get("tag", "") or "",
        is_active=bool(wf.get("isActive", False)),
        trigger="start",
        trigger_step_id=trigger_id,
        parameters=params,
        steps=steps_out,
    )
