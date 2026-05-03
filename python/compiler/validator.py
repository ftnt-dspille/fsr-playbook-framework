"""Cross-cutting validation that runs after resolve.

The resolver already checks per-step references; this module covers
graph-level invariants: every playbook has a Start, exactly one Start,
linear paths terminate, etc.
"""
from __future__ import annotations

from .errors import CompileError, ErrorCode
from .ir import Collection


def validate(collection: Collection) -> list[CompileError]:
    errors: list[CompileError] = []

    # Workflow names must be unique within a collection (FSR Doctrine
    # constraint: UniqueConstraint on (name, collection) — see
    # Entity/Workflow/Workflow.php). Catch this at compile time rather
    # than letting FSR's import_jobs return an opaque error.
    seen_names: dict[str, int] = {}
    for pi, pb in enumerate(collection.playbooks):
        if pb.name in seen_names:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=f"duplicate playbook name {pb.name!r} (FSR enforces unique workflow names per collection)",
                path=f"playbooks[{pi}].name",
            ))
        seen_names[pb.name] = pi

    for pi, pb in enumerate(collection.playbooks):
        path = f"playbooks[{pi}]"
        starts = [s for s in pb.steps if s.type == "start"]
        if not starts:
            errors.append(CompileError(
                code=ErrorCode.NO_TRIGGER,
                message=f"playbook {pb.name!r} has no 'start' step",
                path=path,
                suggestion="add `- id: start\\n  type: start` as the first step",
            ))
        elif len(starts) > 1:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=f"playbook {pb.name!r} has {len(starts)} 'start' steps; exactly one is required",
                path=path,
            ))
    return errors
