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

from .ir import Collection, Playbook, Step

_NS = uuid.UUID("00000000-0000-0000-0000-000000000fc1")  # FSR-compiler namespace


def _u(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "|".join(parts)))


def _step_iri(u: str) -> str:
    return f"/api/3/workflow_steps/{u}"


def _step_type_iri(u: str) -> str:
    return f"/api/3/workflow_step_types/{u}"


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

        # Pass 1: assign UUIDs and emit step JSON
        step_uuids: dict[str, str] = {
            s.id: _u("step", collection.name, pb.name, s.id) for s in pb.steps
        }

        trigger_step_iri = None
        for idx, s in enumerate(pb.steps):
            su = step_uuids[s.id]
            # workflow_reference: rewrite local `target: <name>` to IRI;
            # drop the friendly key from emitted JSON.
            if s.type == "workflow_reference" and isinstance(s.arguments, dict):
                target = s.arguments.pop("target", None)
                if target and target in wf_uuid_by_name:
                    s.arguments["workflowReference"] = (
                        f"/api/3/workflows/{wf_uuid_by_name[target]}"
                    )
            steps_out.append(_emit_step(s, su, idx))
            if pb.trigger_step_id is None and s.type == "start":
                trigger_step_iri = _step_iri(su)
        if pb.trigger_step_id and pb.trigger_step_id in step_uuids:
            trigger_step_iri = _step_iri(step_uuids[pb.trigger_step_id])

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
            "groups": [],
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


def _emit_step(s: Step, step_uuid: str, idx: int) -> dict[str, Any]:
    return {
        "@type": "WorkflowStep",
        "name": s.name or s.id,
        "description": None,
        "arguments": s.arguments or {},
        "status": None,
        "top": str(120 + idx * 100),
        "left": str(200),
        "stepType": _step_type_iri(s.step_type_uuid) if s.step_type_uuid else None,
        "group": None,
        "uuid": step_uuid,
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
