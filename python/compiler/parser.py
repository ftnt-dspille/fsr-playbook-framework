"""YAML -> IR parser.

Strict-ish: missing required fields produce CompileErrors with paths.
We don't try to validate references here — that's the resolver's job.
"""
from __future__ import annotations

from typing import Any

import yaml

from .errors import CompileError, ErrorCode
from .ir import Collection, Playbook, Step


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

            steps.append(Step(
                id=sid,
                type=stype,
                name=s_raw.get("name") or sid,
                arguments=args,
                next=s_raw.get("next") if isinstance(s_raw.get("next"), str) else None,
                branches={str(k): str(v) for k, v in branches.items()},
            ))

        params_raw = pb_raw.get("parameters") or []
        if not isinstance(params_raw, list) or not all(isinstance(p, str) for p in params_raw):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="parameters must be a list of strings",
                path=f"{pb_path}.parameters",
            ))
            params_raw = []

        playbooks.append(Playbook(
            name=pb_name,
            description=pb_raw.get("description", "") or "",
            tag=pb_raw.get("tag", "") or "",
            is_active=bool(pb_raw.get("is_active", False)),
            trigger=str(pb_raw.get("trigger", "start") or "start"),
            parameters=list(params_raw),
            steps=steps,
        ))

    if errors:
        return None, errors

    return Collection(
        name=name or "",
        description=doc.get("description", "") or "",
        visible=bool(doc.get("visible", True)),
        playbooks=playbooks,
    ), errors
