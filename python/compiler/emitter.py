"""IR -> FSR WorkflowCollection JSON.

What the emitter does:
  - Synthesize UUIDs for collection / playbook / step / route entities
  - Build /api/3/workflow_steps/<uuid> IRIs for cross-references
  - Build /api/3/workflow_step_types/<uuid> IRIs from resolver-stamped UUIDs
  - Construct routes from step.next and step.branches
  - Lay out steps top-to-bottom (FSR's UI needs `top` / `left` strings;
    the executor doesn't care, but the importer rejects empties)

What it does NOT do:
  - Reference resolution (resolver's job)
  - Argument validation (resolver's job)

UUID strategy: deterministic UUIDv5 derived from collection name + playbook
name + step id. This keeps re-compiles diff-stable, which is the property
the bambenek round-trip test depends on.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .ir import Annotation, Collection, Playbook, Step

_NS = uuid.UUID("00000000-0000-0000-0000-000000000fc1")  # FSR-compiler namespace


def _u(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "|".join(parts)))


def _step_iri(u: str) -> str:
    return f"/api/3/workflow_steps/{u}"


def _step_type_iri(u: str) -> str:
    return f"/api/3/workflow_step_types/{u}"


def _group_iri(u: str) -> str:
    return f"/api/3/workflow_groups/{u}"


# Layout constants used both for steps and for auto-positioning notes.
_STEP_LEFT = 200
_STEP_TOP_BASE = 120
_STEP_VSTRIDE = 100
_STEP_HSTRIDE = 280          # Horizontal spacing between sibling branches.
_STEP_WIDTH = 200            # FSR canvas step boxes are ~200px wide.
_NOTE_GAP = 40               # Horizontal gap between step and its auto-note.


def _compute_layout(steps: list, start_id: str | None) -> dict[str, tuple[int, int]]:
    """Tree-aware (top, left) assignment.

    Linear `next:` keeps the same column. Decision `branches:` (and any
    other multi-target step type that uses the same field) fan out: the
    first branch stays in the parent column, each subsequent branch gets
    a column to the right. `unlabeled_next` siblings get the same
    treatment. BFS so a step reachable via two paths wins on the shorter
    one. Steps unreachable from start fall through to a stable
    column=last+1 to avoid stacking on the trunk.
    """
    if not steps:
        return {}
    by_id = {s.id: s for s in steps}
    layout: dict[str, tuple[int, int]] = {}
    if start_id and start_id in by_id:
        first = start_id
    else:
        first = steps[0].id

    # BFS: (id, depth, col)
    queue: list[tuple[str, int, int]] = [(first, 0, 0)]
    max_col = 0
    while queue:
        sid, depth, col = queue.pop(0)
        if sid in layout or sid not in by_id:
            continue
        top = _STEP_TOP_BASE + depth * _STEP_VSTRIDE
        left = _STEP_LEFT + col * _STEP_HSTRIDE
        layout[sid] = (top, left)
        if col > max_col:
            max_col = col
        s = by_id[sid]
        # Collect children. Linear `next` stays in column; each branch
        # target gets an offset column.
        children: list[tuple[str, int]] = []
        if s.next and s.next in by_id:
            children.append((s.next, col))
        # branches: dict[label, target_id] — labels iterated in declaration order
        offset = 0
        for label, target in s.branches.items():
            if target in by_id:
                # If linear `next` already used this column, branches start at +1
                branch_col = col + offset + (1 if s.next and offset == 0 else 0)
                # Actually simpler: branches always offset from the parent's column,
                # incrementing per branch. If there's no linear `next`, the first
                # branch stays in the parent column (looks centered).
                branch_col = col + offset
                children.append((target, branch_col))
                offset += 1
        for target in getattr(s, "unlabeled_next", []) or []:
            if target in by_id:
                children.append((target, col + offset))
                offset += 1
        for tgt, tcol in children:
            if tgt not in layout:
                queue.append((tgt, depth + 1, tcol))

    # Steps not reachable from start: park them in their declaration order
    # at the bottom of the trunk, in a fresh column to the right.
    for s in steps:
        if s.id in layout:
            continue
        max_col += 1
        layout[s.id] = (_STEP_TOP_BASE + (len(layout)) * _STEP_VSTRIDE,
                        _STEP_LEFT + max_col * _STEP_HSTRIDE)
    return layout


def emit(collection: Collection) -> dict[str, Any]:
    coll_uuid = _u("collection", collection.name)
    workflows_out: list[dict[str, Any]] = []

    # All playbook UUIDs upfront so workflow_reference steps can resolve
    # local `target: <name>` references to /api/3/workflows/<uuid> IRIs.
    wf_uuid_by_name = {
        pb.name: _u("workflow", collection.name, pb.name) for pb in collection.playbooks
    }

    for pb in collection.playbooks:
        wf_uuid = wf_uuid_by_name[pb.name]
        steps_out: list[dict[str, Any]] = []
        routes_out: list[dict[str, Any]] = []

        # Pass 1: assign UUIDs, compute step layout
        step_uuids: dict[str, str] = {
            s.id: _u("step", collection.name, pb.name, s.id) for s in pb.steps
        }
        step_layout: dict[str, tuple[int, int]] = {}  # id -> (top, left)

        # Build the merged annotation list: explicit annotations + one
        # auto-generated note per step that carries a comment. Auto-notes
        # are tagged so the decompiler can fold them back into step.comment.
        annotations: list[Annotation] = list(pb.annotations)
        for s in pb.steps:
            if s.comment:
                annotations.append(Annotation(
                    id=f"__comment_{s.id}",
                    kind="note",
                    title="Note",
                    body=s.comment,
                    contains=[s.id],
                    auto_for_step=s.id,
                ))

        # block annotations need step.group set on contained steps.
        # Pre-compute a step_id -> group_uuid map for blocks only.
        step_group: dict[str, str] = {}
        for ann in annotations:
            if ann.kind != "block":
                continue
            ann_uuid = _u("group", collection.name, pb.name, ann.id)
            ann.uuid = ann_uuid
            for sid in ann.contains:
                step_group[sid] = ann_uuid

        # Tree-aware layout: linear flow goes top-to-bottom in one column;
        # each decision branch (and unlabeled multi-`next`) fans out into
        # its own column. BFS from start so reachability + first-visit
        # row dominates.
        start_id = pb.trigger_step_id
        if not start_id:
            for s in pb.steps:
                if s.type == "start":
                    start_id = s.id
                    break
        step_layout = _compute_layout(pb.steps, start_id)

        trigger_step_iri = None
        for idx, s in enumerate(pb.steps):
            su = step_uuids[s.id]
            top, left = step_layout[s.id]
            # workflow_reference: rewrite local `target: <name>` to IRI;
            # drop the friendly key from emitted JSON.
            if s.type == "workflow_reference" and isinstance(s.arguments, dict):
                target = s.arguments.pop("target", None)
                if target and target in wf_uuid_by_name:
                    s.arguments["workflowReference"] = (
                        f"/api/3/workflows/{wf_uuid_by_name[target]}"
                    )
            # manual_input: each response option needs a `step_iri` that
            # points at the next step. Map by branch label (DecisionBased
            # multi-option) or fall back to the step's `next:` (the only
            # option for InputBased single-button prompts). Without this
            # FSR's manual_input handler emits a malformed-URL error and
            # the run fails.
            # decision: each condition entry needs `step_iri` (and optionally
            # `step_name`) pointing at the branch target. Without it FSR's
            # `cond` handler raises CS-WF-10 ("Step IRI or Condition not set").
            # Mirrors manual_input's option→step_iri injection. Implicit-else
            # branches in `branches:` whose option has no matching `conditions`
            # entry get a synthesized `{option, step_iri, default: true}` row.
            if s.type == "decision" and isinstance(s.arguments, dict):
                conds = s.arguments.get("conditions")
                if not isinstance(conds, list):
                    conds = []
                    s.arguments["conditions"] = conds
                step_name_by_id = {st.id: (st.name or st.id) for st in pb.steps}
                seen_options = set()
                for cond in conds:
                    if not isinstance(cond, dict):
                        continue
                    label = cond.get("option")
                    if label is not None:
                        seen_options.add(label)
                    if cond.get("step_iri"):
                        continue
                    target_id = s.branches.get(label) if label else None
                    if target_id and target_id in step_uuids:
                        cond["step_iri"] = _step_iri(step_uuids[target_id])
                        cond.setdefault("step_name", step_name_by_id.get(target_id))
                # implicit-else branches: in `branches:` but not in `conditions:`
                for label, target_id in s.branches.items():
                    if label in seen_options:
                        continue
                    if target_id not in step_uuids:
                        continue
                    conds.append({
                        "option": label,
                        "default": True,
                        "step_iri": _step_iri(step_uuids[target_id]),
                        "step_name": step_name_by_id.get(target_id),
                    })
            if s.type == "manual_input" and isinstance(s.arguments, dict):
                rmap = s.arguments.get("response_mapping") or {}
                opts = rmap.get("options") or []
                for opt in opts:
                    if not isinstance(opt, dict) or opt.get("step_iri"):
                        continue
                    label = opt.get("option")
                    target_id = s.branches.get(label) if label else None
                    if not target_id:
                        target_id = s.next
                    if target_id and target_id in step_uuids:
                        opt["step_iri"] = _step_iri(step_uuids[target_id])
            steps_out.append(_emit_step(
                s, su, top, left,
                group_iri=_group_iri(step_group[s.id]) if s.id in step_group else None,
            ))
            if pb.trigger_step_id is None and s.type in (
                    "start", "start_on_create", "start_on_update"):
                trigger_step_iri = _step_iri(su)
        if pb.trigger_step_id and pb.trigger_step_id in step_uuids:
            trigger_step_iri = _step_iri(step_uuids[pb.trigger_step_id])

        groups_out: list[dict[str, Any]] = []
        for ann in annotations:
            if not ann.uuid:
                ann.uuid = _u("group", collection.name, pb.name, ann.id)
            groups_out.append(_emit_group(ann, step_layout))

        # Pass 2: emit routes from .next + .branches
        for s in pb.steps:
            src_iri = _step_iri(step_uuids[s.id])
            if s.next:
                tgt = step_uuids.get(s.next)
                if tgt:
                    routes_out.append(_emit_route(
                        collection.name, pb.name, s.id, s.next,
                        src_iri, _step_iri(tgt),
                    ))
            for option, target in s.branches.items():
                tgt = step_uuids.get(target)
                if tgt:
                    routes_out.append(_emit_route(
                        collection.name, pb.name, f"{s.id}:{option}", target,
                        src_iri, _step_iri(tgt), label=option,
                    ))
            for target in s.unlabeled_next:
                tgt = step_uuids.get(target)
                if tgt:
                    routes_out.append(_emit_route(
                        collection.name, pb.name, f"{s.id}:_{target}", target,
                        src_iri, _step_iri(tgt),
                    ))

        workflows_out.append({
            "@type": "Workflow",
            "name": pb.name,
            "aliasName": None,
            "tag": pb.tag or "",
            "description": pb.description or "",
            "isActive": pb.is_active,
            "debug": False,
            "singleRecordExecution": False,
            "remoteExecutableFlag": 0,
            "parameters": list(pb.parameters),
            "synchronous": False,
            "lastModifyDate": None,
            "collection": None,  # populated by FSR import
            "versions": [],
            "triggerStep": trigger_step_iri,
            "steps": steps_out,
            "routes": routes_out,
            "groups": groups_out,
            "priority": None,
            "playbookOrigin": None,
            "isEditable": True,
            "uuid": wf_uuid,
            "owners": [],
            "isPrivate": False,
        })

    return {
        "type": "workflow_collections",
        "macros": [],
        "exported_tags": [],
        "data": [{
            "@type": "WorkflowCollection",
            "name": collection.name,
            "description": collection.description or "",
            "visible": collection.visible,
            "image": None,
            "uuid": coll_uuid,
            "recordTags": [],
            "workflows": workflows_out,
        }],
    }


def _emit_step(s: Step, step_uuid: str, top: int, left: int,
               group_iri: str | None = None) -> dict[str, Any]:
    return {
        "@type": "WorkflowStep",
        "name": s.name or s.id,
        "description": None,
        "arguments": s.arguments or {},
        "status": None,
        "top": str(top),
        "left": str(left),
        "stepType": _step_type_iri(s.step_type_uuid) if s.step_type_uuid else None,
        "group": group_iri,
        "uuid": step_uuid,
    }


def _emit_group(ann: Annotation, step_layout: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """Emit a WorkflowGroup. Auto-fills position when missing.

    For notes: place to the right of the first contained step. For blocks
    with explicit step set: bounding box around them. Otherwise: pin near
    the playbook origin so the user can drag in the UI.
    """
    top = ann.top
    left = ann.left
    height = ann.height
    width = ann.width

    if (top is None or left is None) and ann.contains:
        layouts = [step_layout[sid] for sid in ann.contains if sid in step_layout]
        if layouts:
            tops = [t for t, _ in layouts]
            lefts = [l for _, l in layouts]
            if ann.kind == "note":
                top = top if top is not None else min(tops)
                left = left if left is not None else max(lefts) + _STEP_WIDTH + _NOTE_GAP
            else:  # block: bounding box
                top = top if top is not None else max(0, min(tops) - 30)
                left = left if left is not None else max(0, min(lefts) - 30)
                height = height or (max(tops) - min(tops) + _STEP_VSTRIDE + 60)
                width = width or (_STEP_WIDTH + 60)
    if top is None:
        top = _STEP_TOP_BASE
    if left is None:
        left = _STEP_LEFT + _STEP_WIDTH + _NOTE_GAP

    return {
        "@type": "WorkflowGroup",
        "name": ann.title or "Note",
        "description": ann.body or "",
        "type": ann.kind,
        "isCollapsed": ann.collapsed,
        "hasTriggerStep": False,
        "hideInLogs": ann.hide_in_logs,
        "metadata": [],
        "reusable": False,
        "top": str(top),
        "left": str(left),
        "height": str(height),
        "width": str(width),
        "uuid": ann.uuid,
        "recordTags": [],
    }


def _emit_route(
    coll: str, pb: str, src_id: str, tgt_id: str,
    src_iri: str, tgt_iri: str, label: str | None = None,
) -> dict[str, Any]:
    return {
        "@type": "WorkflowRoute",
        "name": f"{src_id}->{tgt_id}",
        "targetStep": tgt_iri,
        "sourceStep": src_iri,
        "label": label,
        "isExecuted": False,
        "group": None,
        "uuid": _u("route", coll, pb, src_id, tgt_id),
    }


def emit_to_json(collection: Collection, indent: int = 2) -> str:
    return json.dumps(emit(collection), indent=indent)
