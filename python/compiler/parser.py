"""YAML -> IR parser.

Strict-ish: missing required fields produce CompileErrors with paths.
We don't try to validate references here — that's the resolver's job.
"""
from __future__ import annotations

from typing import Any

import yaml

from .errors import CompileError, ErrorCode
from .ir import Annotation, Collection, Playbook, Step


def parse_yaml(text: str) -> tuple[Collection | None, list[CompileError]]:
    errors: list[CompileError] = []
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        errors.append(CompileError(
            code=ErrorCode.PARSE_ERROR,
            message=f"YAML parse error: {e}",
            path="",
        ))
        return None, errors

    if not isinstance(doc, dict):
        errors.append(CompileError(
            code=ErrorCode.PARSE_ERROR,
            message="top level must be a mapping (collection: ..., playbooks: [...])",
        ))
        return None, errors

    name = doc.get("collection")
    if not isinstance(name, str) or not name:
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message="collection name is required",
            path="collection",
        ))

    pbs_raw = doc.get("playbooks")
    if not isinstance(pbs_raw, list) or not pbs_raw:
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message="at least one playbook is required",
            path="playbooks",
        ))
        if errors:
            return None, errors

    playbooks: list[Playbook] = []
    for i, pb_raw in enumerate(pbs_raw or []):
        pb_path = f"playbooks[{i}]"
        if not isinstance(pb_raw, dict):
            errors.append(CompileError(
                code=ErrorCode.PARSE_ERROR,
                message="playbook entry must be a mapping",
                path=pb_path,
            ))
            continue
        pb_name = pb_raw.get("name")
        if not isinstance(pb_name, str) or not pb_name:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message="playbook name is required",
                path=f"{pb_path}.name",
            ))
            continue

        steps_raw = pb_raw.get("steps") or []
        if not isinstance(steps_raw, list):
            errors.append(CompileError(
                code=ErrorCode.PARSE_ERROR,
                message="steps must be a list",
                path=f"{pb_path}.steps",
            ))
            continue

        steps: list[Step] = []
        seen_ids: set[str] = set()
        for j, s_raw in enumerate(steps_raw):
            sp = f"{pb_path}.steps[{j}]"
            if not isinstance(s_raw, dict):
                errors.append(CompileError(
                    code=ErrorCode.PARSE_ERROR,
                    message="step entry must be a mapping",
                    path=sp,
                ))
                continue
            sid = s_raw.get("id")
            stype = s_raw.get("type")
            if not isinstance(sid, str) or not sid:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="step.id is required",
                    path=f"{sp}.id",
                ))
                continue
            if not isinstance(stype, str) or not stype:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="step.type is required",
                    path=f"{sp}.type",
                ))
                continue
            if sid in seen_ids:
                errors.append(CompileError(
                    code=ErrorCode.DUPLICATE_STEP_ID,
                    message=f"duplicate step id: {sid}",
                    path=f"{sp}.id",
                ))
                continue
            seen_ids.add(sid)

            args = s_raw.get("arguments") or {}
            if not isinstance(args, dict):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message="arguments must be a mapping",
                    path=f"{sp}.arguments",
                ))
                args = {}

            branches = s_raw.get("branches") or {}
            if not isinstance(branches, dict):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message="branches must be a mapping (option -> step id)",
                    path=f"{sp}.branches",
                ))
                branches = {}

            cmt = s_raw.get("comment")
            steps.append(Step(
                id=sid,
                type=stype,
                name=s_raw.get("name") or sid,
                arguments=args,
                next=s_raw.get("next") if isinstance(s_raw.get("next"), str) else None,
                branches={str(k): str(v) for k, v in branches.items()},
                comment=cmt if isinstance(cmt, str) and cmt.strip() else None,
            ))

        params_raw = pb_raw.get("parameters") or []
        if not isinstance(params_raw, list) or not all(isinstance(p, str) for p in params_raw):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="parameters must be a list of strings",
                path=f"{pb_path}.parameters",
            ))
            params_raw = []

        annotations: list[Annotation] = []
        ann_raw = pb_raw.get("annotations") or []
        if not isinstance(ann_raw, list):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="annotations must be a list",
                path=f"{pb_path}.annotations",
            ))
            ann_raw = []
        seen_ann_ids: set[str] = set()
        for k, a_raw in enumerate(ann_raw):
            ap = f"{pb_path}.annotations[{k}]"
            if not isinstance(a_raw, dict):
                errors.append(CompileError(
                    code=ErrorCode.PARSE_ERROR,
                    message="annotation entry must be a mapping",
                    path=ap,
                ))
                continue
            aid = a_raw.get("id")
            if not isinstance(aid, str) or not aid:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="annotation.id is required",
                    path=f"{ap}.id",
                ))
                continue
            if aid in seen_ann_ids:
                errors.append(CompileError(
                    code=ErrorCode.DUPLICATE_STEP_ID,
                    message=f"duplicate annotation id: {aid}",
                    path=f"{ap}.id",
                ))
                continue
            seen_ann_ids.add(aid)
            kind = a_raw.get("kind", "note")
            if kind not in ("note", "block", "custom"):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=f"annotation.kind must be note|block|custom (got {kind!r})",
                    path=f"{ap}.kind",
                ))
                continue
            position = a_raw.get("position") or {}
            if not isinstance(position, dict):
                position = {}
            contains = a_raw.get("contains") or []
            if not isinstance(contains, list):
                contains = []
            annotations.append(Annotation(
                id=aid,
                kind=kind,
                title=str(a_raw.get("title") or "Note"),
                body=str(a_raw.get("body") or ""),
                top=position.get("top"),
                left=position.get("left"),
                height=int(position.get("height") or 0),
                width=int(position.get("width") or 300),
                collapsed=bool(a_raw.get("collapsed", False)),
                hide_in_logs=bool(a_raw.get("hide_in_logs", kind == "note")),
                contains=[str(c) for c in contains],
            ))

        playbooks.append(Playbook(
            name=pb_name,
            description=pb_raw.get("description", "") or "",
            tag=pb_raw.get("tag", "") or "",
            is_active=bool(pb_raw.get("is_active", False)),
            trigger=str(pb_raw.get("trigger", "start") or "start"),
            parameters=list(params_raw),
            steps=steps,
            annotations=annotations,
        ))

    if errors:
        return None, errors

    return Collection(
        name=name or "",
        description=doc.get("description", "") or "",
        visible=bool(doc.get("visible", True)),
        playbooks=playbooks,
    ), errors
