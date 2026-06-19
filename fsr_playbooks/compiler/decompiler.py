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

from .ir import PRIORITY_LIST_NAME, Annotation, Collection, Playbook, Step
from .resolver import SHORT_TYPE_TO_FSR

_FSR_TO_SHORT = {v: k for k, v in SHORT_TYPE_TO_FSR.items()}


def decompile_to_yaml(fsr_json: dict[str, Any], db_path: Path) -> str:
    """Decompile FSR WorkflowCollection JSON into authored-style YAML.

    Single-source-of-truth for the YAML serialization shape — the CLI
    pull/diff/decompile commands and the `generate_recipe` MCP tool
    both go through here so a recipe stored to the DB looks identical
    to a recipe pulled from a live FSR.
    """
    import yaml

    ir = decompile(fsr_json, db_path)
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
                "steps": [_decompile_step(s) for s in pb.steps],
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


def _decompile_step(s) -> dict:
    """Emit a step in the canonical authoring surface:
    `name:` only (no `id:`); `conditions:` / `options:` / `vars:` hoisted
    to step level; legacy `arguments.{conditions,options,arg_list}` and
    `branches:` collapsed away."""
    out: dict = {"type": s.type, "name": s.name or s.id}
    args = dict(s.arguments) if isinstance(s.arguments, dict) else None
    branches_remaining = dict(s.branches)

    if s.type == "decision" and isinstance(args, dict):
        conds = args.pop("conditions", None) or []
        new_conds = []
        for c in conds:
            if not isinstance(c, dict):
                continue
            entry = {}
            label = c.get("option")
            if label is not None:
                entry["display"] = label
            if c.get("default"):
                entry["default"] = True
            cond = c.get("condition")
            if cond is not None and not c.get("default"):
                entry["when"] = cond
            tgt = branches_remaining.pop(label, None) if label else None
            if tgt:
                entry["next"] = tgt
            new_conds.append(entry)
        if new_conds:
            out["conditions"] = new_conds
        if args:
            out["arguments"] = args
    elif s.type == "manual_input" and isinstance(args, dict):
        rmap = args.pop("response_mapping", None)
        opts = []
        if isinstance(rmap, dict):
            opts = rmap.get("options") or []
        new_opts = []
        for o in opts:
            if not isinstance(o, dict):
                continue
            entry = {}
            label = o.get("option")
            if label is not None:
                entry["display"] = label
            if o.get("primary"):
                entry["primary"] = True
            tgt = branches_remaining.pop(label, None) if label else None
            if tgt:
                entry["next"] = tgt
            new_opts.append(entry)
        if new_opts:
            out["options"] = new_opts
        if args:
            out["arguments"] = args
    elif s.type == "set_variable" and isinstance(args, dict):
        # Resolver flattens arg_list into the args dict; treat every key
        # as a variable assignment.
        if args:
            out["vars"] = args
    elif args:
        out["arguments"] = args

    if s.next:
        out["next"] = s.next
    # Any leftover branches (no matching condition/option) — surface as
    # an explicit `branches:` so info isn't lost; the parser rejects this
    # shape so a user must rewrite by hand. Rare in practice.
    if branches_remaining:
        out["branches"] = branches_remaining
    if s.unlabeled_next:
        out["unlabeled_next"] = list(s.unlabeled_next)
    if s.comment:
        out["comment"] = s.comment
    return out


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
        # IRI → name for workflow priority (reverse of the resolver's lookup).
        priority_by_iri = {
            r["item_iri"]: r["item_value"] for r in conn.execute(
                "SELECT item_iri, item_value FROM picklists WHERE list_name=?",
                (PRIORITY_LIST_NAME,),
            )
        }
    finally:
        conn.close()

    if "data" not in fsr_json or not fsr_json["data"]:
        raise ValueError("not an FSR WorkflowCollection JSON (missing data[])")
    coll = fsr_json["data"][0]

    playbooks: list[Playbook] = []
    for wf in coll.get("workflows", []):
        playbooks.append(_decompile_workflow(wf, type_by_uuid, priority_by_iri))

    return Collection(
        name=coll.get("name", "") or "",
        description=coll.get("description", "") or "",
        visible=bool(coll.get("visible", True)),
        playbooks=playbooks,
    )


def _decompile_workflow(wf: dict[str, Any], type_by_uuid: dict[str, str],
                        priority_by_iri: dict[str, str] | None = None) -> Playbook:
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

        # for_each lives inside arguments on the wire; lift it out into
        # its own IR field so authors see it as a step-level mapping.
        raw_args = dict(s.get("arguments") or {})
        fe_raw = raw_args.pop("for_each", None)
        for_each = dict(fe_raw) if isinstance(fe_raw, dict) and fe_raw else None
        steps_out.append(Step(
            id=sid,
            type=short_by_uuid.get(u, "") or "unknown",
            name=s.get("name", "") or sid,
            arguments=raw_args,
            next=nxt,
            branches=branches,
            unlabeled_next=unlabeled,
            step_type_uuid=(
                s["stepType"].get("uuid") if isinstance(s.get("stepType"), dict)
                else (s.get("stepType") or "").rsplit("/", 1)[-1] or None
            ),
            step_type_name=canonical_by_uuid.get(u),
            for_each=for_each,
        ))

    trigger_uuid = _to_uuid(wf.get("triggerStep"))
    trigger_id = id_by_uuid.get(trigger_uuid)

    # Decompile workflow_groups: blocks own steps via WorkflowStep.group,
    # notes are positional (no FK link) and may fold into step.comment.
    annotations: list[Annotation] = []
    ann_id_taken: set[str] = set()

    # Block-owned steps: index by group uuid → list of step ids.
    block_uuid_to_step_ids: dict[str, list[str]] = {}
    for s in raw_steps:
        gu = _to_uuid(s.get("group")) if s.get("group") else ""
        if gu:
            sid = id_by_uuid.get(s.get("uuid", ""), "")
            if sid:
                block_uuid_to_step_ids.setdefault(gu, []).append(sid)

    # Step canvas positions (id -> (top, left)) for the note→step heuristic.
    step_pos: dict[str, tuple[int, int]] = {}
    for s in raw_steps:
        sid = id_by_uuid.get(s.get("uuid", ""), "")
        if not sid:
            continue
        try:
            step_pos[sid] = (int(s.get("top") or 0), int(s.get("left") or 0))
        except (TypeError, ValueError):
            pass

    step_by_id = {st.id: st for st in steps_out}
    for g in wf.get("groups", []) or []:
        gtype = g.get("type") or "note"
        gtitle = g.get("name") or "Note"
        gbody = g.get("description") or ""
        guuid = g.get("uuid") or ""
        try:
            top_v = int(g.get("top") or 0)
            left_v = int(g.get("left") or 0)
            h_v = int(g.get("height") or 0)
            w_v = int(g.get("width") or 0)
        except (TypeError, ValueError):
            top_v = left_v = 0
            h_v = w_v = 0

        if gtype == "block":
            contains = block_uuid_to_step_ids.get(guuid, [])
        else:
            contains = []

        # Auto-comment fold for notes — title pattern is
        # "<PREFIX>: <step display name>" where PREFIX ∈
        # {Note, TODO, FIX, NOTE, WARN, HACK, XXX}. The prefix carries
        # the comment category and is preserved in the body via the
        # original first word, so we don't need to round-trip the
        # prefix separately. Legacy "Note" (no colon) → positional.
        _AUTO_PREFIXES = ("Note", "TODO", "FIX", "NOTE", "WARN", "HACK", "XXX")
        if gtype == "note":
            target_name = None
            for p in _AUTO_PREFIXES:
                if gtitle.startswith(p + ": "):
                    target_name = gtitle[len(p) + 2:]
                    break
            if target_name:
                matches = [sid for sid, st in step_by_id.items()
                           if (st.name or sid) == target_name
                           and st.comment is None]
                if len(matches) == 1:
                    step_by_id[matches[0]].comment = gbody
                    continue
                # Ambiguous or no match: keep as a regular note rather
                # than dropping the body.
        if gtype == "note" and gtitle == "Note":
            candidates = [
                sid for sid, (st_top, st_left) in step_pos.items()
                if abs(st_top - top_v) <= 50 and left_v > st_left + 100
                and step_by_id.get(sid) and step_by_id[sid].comment is None
            ]
            if len(candidates) == 1:
                step_by_id[candidates[0]].comment = gbody
                continue
            if len(candidates) > 1:
                candidates.sort(key=lambda sid: left_v - step_pos[sid][1])
                step_by_id[candidates[0]].comment = gbody
                continue

        aid = _slugify(gtitle if gtitle != "Note" else g.get("type", "note"),
                       ann_id_taken)
        annotations.append(Annotation(
            id=aid,
            kind=gtype,
            title=gtitle,
            body=gbody,
            top=top_v or None,
            left=left_v or None,
            height=h_v,
            width=w_v or 300,
            collapsed=bool(g.get("isCollapsed", False)),
            hide_in_logs=bool(g.get("hideInLogs", gtype == "note")),
            contains=contains,
        ))

    # FSR is inconsistent here: parameters is either `{}` (empty) or a
    # list of parameter names. Normalize to a list of strings.
    raw_params = wf.get("parameters") or []
    if isinstance(raw_params, list):
        params = [p for p in raw_params if isinstance(p, str)]
    else:
        params = []

    # priority IRI → name via the live-synced picklists map.
    raw_priority = wf.get("priority")
    priority = (priority_by_iri or {}).get(raw_priority) if isinstance(raw_priority, str) else None

    return Playbook(
        name=wf.get("name", "") or "",
        description=wf.get("description", "") or "",
        tag=wf.get("tag", "") or "",
        is_active=bool(wf.get("isActive", False)),
        priority=priority,
        priority_iri=raw_priority if isinstance(raw_priority, str) else None,
        trigger="start",
        trigger_step_id=trigger_id,
        parameters=params,
        steps=steps_out,
        annotations=annotations,
    )
