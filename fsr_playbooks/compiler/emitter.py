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
from datetime import datetime, timezone
from typing import Any

from .ir import Annotation, Collection, Step

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
        # branches: dict[label, target_id] — labels iterated in declaration order.
        # If the step has a linear `next:`, that target stays in the parent
        # column and each branch target offsets one column to the right per
        # branch. With no linear `next:`, the first branch stays in the parent
        # column and subsequent branches offset right from there. Without this,
        # `next` and `branches[0]` collide on the same (top, left).
        offset = 0
        base_branch_offset = 1 if s.next else 0
        for label, target in s.branches.items():
            if target in by_id:
                children.append((target, col + base_branch_offset + offset))
                offset += 1
        for target in getattr(s, "unlabeled_next", []) or []:
            if target in by_id:
                children.append((target, col + base_branch_offset + offset))
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
        # Recognized prefixes — first word of the comment body categorizes
        # the note. Lets authors flag actionable items vs. background
        # explanation in the canvas without a separate field.
        _PREFIXES = ("TODO", "FIX", "NOTE", "WARN", "HACK", "XXX")
        for s in pb.steps:
            if s.comment:
                # Title with the step's display name so the canvas makes
                # the note→step linkage obvious. Prefix carries the
                # comment category (TODO/FIX/Note/...) so authors can
                # scan the canvas for actionable items.
                body = s.comment
                first_word = body.lstrip().split(None, 1)[0].rstrip(":").upper() if body.strip() else ""
                prefix = first_word if first_word in _PREFIXES else "Note"
                title = f"{prefix}: {s.name or s.id}"
                # ~58 visible chars per line at width=440; 22px per
                # line; 50px chrome (title bar + padding). Cap so
                # really long notes don't dominate the canvas.
                est_lines = sum(max(1, (len(line) // 58) + 1)
                                for line in body.splitlines() or [""])
                height = min(360, 50 + est_lines * 22)
                annotations.append(Annotation(
                    id=f"__comment_{s.id}",
                    kind="note",
                    title=title,
                    body=body,
                    width=440,
                    height=height,
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
                    seen_options.add(label)
                # `next:` fall-through: FSR's Decision designer requires an
                # explicit `default: true` row in conditions for the else
                # branch — an unlabeled route from a Decision step renders
                # as a broken edge with no else label. If the author wrote
                # `next: <id>` on a Decision and didn't already supply a
                # default condition row, synthesize one labeled "Else" and
                # promote the target into `branches:` so the route emitted
                # below carries the label too. Clearing `s.next` prevents
                # a duplicate unlabeled route to the same target.
                has_default = any(
                    isinstance(c, dict) and c.get("default")
                    for c in conds
                )
                if (not has_default) and s.next and s.next in step_uuids:
                    else_label = "Else"
                    suffix = 2
                    while else_label in seen_options:
                        else_label = f"Else {suffix}"
                        suffix += 1
                    target_id = s.next
                    conds.append({
                        "option": else_label,
                        "default": True,
                        "step_iri": _step_iri(step_uuids[target_id]),
                        "step_name": step_name_by_id.get(target_id),
                    })
                    s.branches[else_label] = target_id
                    s.next = None
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
                    "start", "start_on_create", "start_on_update",
                    "start_on_delete", "api_endpoint"):
                trigger_step_iri = _step_iri(su)
        if pb.trigger_step_id and pb.trigger_step_id in step_uuids:
            trigger_step_iri = _step_iri(step_uuids[pb.trigger_step_id])

        # Pre-pass: stack auto-comment notes vertically so a tall note
        # doesn't overlap the next note that wants its step's row.
        # Sort by the contained step's `top`, then push each note down
        # to clear the previous one (with a small gap). Notes inherit
        # their preferred top from the step they annotate; this pass
        # only nudges them downward when needed.
        _NOTE_VGAP = 20
        cursor = -1
        auto_notes = sorted(
            (a for a in annotations
             if a.kind == "note" and a.auto_for_step
             and a.top is None and a.contains
             and a.contains[0] in step_layout),
            key=lambda a: step_layout[a.contains[0]][0],
        )
        for ann in auto_notes:
            step_top = step_layout[ann.contains[0]][0]
            note_top = max(step_top, cursor + _NOTE_VGAP) if cursor >= 0 else step_top
            ann.top = note_top
            cursor = note_top + (ann.height or 60)

        groups_out: list[dict[str, Any]] = []
        for ann in annotations:
            if not ann.uuid:
                ann.uuid = _u("group", collection.name, pb.name, ann.id)
            groups_out.append(_emit_group(ann, step_layout))

        # Pass 2: emit routes from .next + .branches
        # Route `name` follows FSR's UI convention "<src display> -> <tgt display>"
        # (spaces around the arrow, display names not snake_case ids). The JS
        # canvas seems to derive lookup ids from this string and silently
        # fails — `addRoute` throws and the whole jsPlumb batch aborts so no
        # edges render — when it deviates (e.g. "src->tgt" or "src:label->tgt").
        # Verified empirically: every playbook we'd pushed with the old
        # `f"{s.id}->{tgt_id}"` format failed to render; FSR-UI-built
        # playbooks with the spaced display-name format work.
        name_by_id = {s.id: s.name or s.id for s in pb.steps}
        for s in pb.steps:
            src_iri = _step_iri(step_uuids[s.id])
            src_disp = name_by_id[s.id]
            if s.next:
                tgt = step_uuids.get(s.next)
                if tgt:
                    tgt_disp = name_by_id.get(s.next, s.next)
                    routes_out.append(_emit_route(
                        collection.name, pb.name, s.id, s.next,
                        src_iri, _step_iri(tgt),
                        display_name=f"{src_disp} -> {tgt_disp}",
                    ))
            for option, target in s.branches.items():
                tgt = step_uuids.get(target)
                if tgt:
                    tgt_disp = name_by_id.get(target, target)
                    routes_out.append(_emit_route(
                        collection.name, pb.name, f"{s.id}:{option}", target,
                        src_iri, _step_iri(tgt), label=option,
                        display_name=f"{src_disp} -> {tgt_disp}",
                    ))
            for target in s.unlabeled_next:
                tgt = step_uuids.get(target)
                if tgt:
                    tgt_disp = name_by_id.get(target, target)
                    routes_out.append(_emit_route(
                        collection.name, pb.name, f"{s.id}:_{target}", target,
                        src_iri, _step_iri(tgt),
                        display_name=f"{src_disp} -> {tgt_disp}",
                    ))

        workflows_out.append({
            "@type": "Workflow",
            "name": pb.name,
            "aliasName": None,
            "tag": pb.tag or "",
            "description": pb.description or "",
            "isActive": pb.is_active,
            "debug": pb.debug,
            "singleRecordExecution": False,
            "remoteExecutableFlag": 0,
            "parameters": list(pb.parameters),
            "synchronous": False,
            # wf-engine reads this when materializing workflow_wfmetadata.wf_modified;
            # leaving it null makes it stamp the 1990-01-19 sentinel which makes
            # "is this row stale?" diagnostics impossible.
            # Format: integer Unix epoch seconds (NOT ISO-8601 — Doctrine rejects
            # string formats with NotNormalizableValueException, verified live
            # 2026-05-06 against /api/3/workflow_collections).
            "lastModifyDate": int(datetime.now(timezone.utc).timestamp()),
            # Stamp the parent-collection IRI explicitly. Fresh POST to
            # `/api/3/workflow_collections` populates this from the parent
            # row, but bulkupsert on a row whose `deletedAt` we just
            # cleared via the recycle-bin restore does NOT — the workflow
            # comes back with `collection: null`, which makes the FSR UI's
            # breadcrumb resolver (and `?collection=<uuid>` filters) treat
            # the playbook as orphaned. Stamping it here keeps the parent
            # link intact through restore + upsert.
            "collection": f"/api/3/workflow_collections/{coll_uuid}",
            "versions": [],
            "triggerStep": trigger_step_iri,
            "steps": steps_out,
            "routes": routes_out,
            "groups": groups_out,
            # Bare IRI string (hydra accepts IRI on POST, same as collection/
            # triggerStep). Resolver-stamped from the live-synced picklists
            # table; None when unset or the name didn't resolve.
            "priority": pb.priority_iri,
            "playbookOrigin": None,
            "isEditable": True,
            "uuid": wf_uuid,
            # Owner teams — IRI strings (`/api/3/teams/<uuid>`). The resolver
            # converts authored team names to IRIs (owners_iris); IRIs authored
            # directly pass through. Private playbooks require owners (enforced
            # in the parser); a public playbook emits owners: [].
            "owners": list(pb.owners_iris),
            "isPrivate": pb.is_private,
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


def _is_blank(v: Any) -> bool:
    """Editor's notion of an empty argument value (bundle line 34487)."""
    return v is None or v == "" or v == {} or v == []


def _clean_step_arguments(args: dict[str, Any]) -> None:
    """Mirror the FortiSOAR editor's save-time argument cleanup so emitted JSON
    matches what the editor actually POSTs.

    Two editor rules, reverse-engineered from the 8.0 bundle (see
    docs/STEP_WIRE_SHAPES.md):

    1. Empty-field deletion (line 34487): drop `when`, `mock_result`, `do_until`
       (empty condition), `message` (empty content), `for_each` (empty item).
    2. for_each `break_loop` is incompatible with async/agent execution and is
       dropped. NOTE: loop-mode *defaulting* (bulk `batch_size`, `parallel`/
       `batch_size` pruning) is NOT done here — it lives in the authoring parser
       so the emitter stays a faithful serializer and decompiled for_each shapes
       round-trip byte-for-byte (the corpus carries inconsistent bulk shapes).

    Mutates `args` in place.
    """
    # 1. Empty-field deletion.
    if _is_blank(args.get("when")):
        args.pop("when", None)
    if _is_blank(args.get("mock_result")):
        args.pop("mock_result", None)
    du = args.get("do_until")
    if isinstance(du, dict) and _is_blank(du.get("condition")):
        args.pop("do_until", None)
    msg = args.get("message")
    if (isinstance(msg, dict) and _is_blank(msg.get("content"))
            and _is_blank(msg.get("records"))):
        # The editor drops a message only when it carries no user payload.
        # A blank `content` with a non-blank `records` (related-record links)
        # is kept on the wire (corpus-grounded), so guard on records too.
        args.pop("message", None)
    fe = args.get("for_each")
    if isinstance(fe, dict) and _is_blank(fe.get("item")):
        args.pop("for_each", None)
        fe = None

    # 2. for_each: only the cross-argument compatibility guard lives here.
    # Loop-mode defaulting (bulk batch_size, parallel/batch_size pruning) is
    # applied in the authoring parser, NOT here — the emitter stays a faithful
    # serializer so a decompiled for_each round-trips byte-for-byte. The corpus
    # carries inconsistent bulk shapes that no emit-time normalization could
    # reproduce (some bulk loops omit batch_size, some keep parallel).
    if isinstance(fe, dict):
        # break_loop requires sync loop-state tracking, incompatible with
        # fire-and-forget async or agent-routed execution.
        if args.get("apply_async") is True or args.get("agent"):
            fe.pop("break_loop", None)


def _emit_step(s: Step, step_uuid: str, top: int, left: int,
               group_iri: str | None = None) -> dict[str, Any]:
    args = dict(s.arguments or {})
    if s.for_each:
        # for_each lives inside arguments on the wire (alongside resource,
        # operation, etc). The IR keeps it as a sibling of `arguments` for
        # ergonomic YAML; we merge it in here.
        args["for_each"] = dict(s.for_each)
    _clean_step_arguments(args)
    return {
        "@type": "WorkflowStep",
        "name": s.name or s.id,
        "description": s.description or None,
        "arguments": args,
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
                # Park notes in a single column to the RIGHT of every step
                # in the workflow, not just the right of the contained
                # step. Otherwise notes for steps in column 0 land
                # mid-canvas and visually collide with steps in column 1+
                # (Decision branch targets). All notes in the same column
                # → no overlap with the topology, and notes for different
                # steps differ vertically so they don't overlap each other.
                if left is None:
                    canvas_max_left = max(l for _, l in step_layout.values()) if step_layout else max(lefts)
                    left = canvas_max_left + _STEP_WIDTH + _NOTE_GAP
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
    display_name: str | None = None,
) -> dict[str, Any]:
    return {
        "@type": "WorkflowRoute",
        "name": display_name or f"{src_id} -> {tgt_id}",
        "targetStep": tgt_iri,
        "sourceStep": src_iri,
        "label": label,
        "isExecuted": False,
        "group": None,
        "uuid": _u("route", coll, pb, src_id, tgt_id),
    }


def emit_to_json(collection: Collection, indent: int = 2) -> str:
    return json.dumps(emit(collection), indent=indent)
