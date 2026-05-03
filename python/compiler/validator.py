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

        # Step names must be unique within a playbook. FSR's Jinja runtime
        # exposes step output at `vars.steps.<Name_with_underscores>`, so
        # two steps sharing a name (or sharing an underscored form, e.g.
        # "Step One" and "Step_One") silently overwrite each other in the
        # context. The compiler catches this since FSR's importer doesn't.
        step_seen_names: dict[str, int] = {}
        step_seen_keys: dict[str, int] = {}
        for si, s in enumerate(pb.steps):
            sname = s.name or s.id
            sp = f"{path}.steps[{si}].name"
            if sname in step_seen_names:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"duplicate step name {sname!r} in playbook "
                             f"{pb.name!r} (already used by step #"
                             f"{step_seen_names[sname]}); names must be "
                             f"unique — vars.steps.<name> would collide "
                             f"silently at runtime"),
                    path=sp,
                ))
            else:
                step_seen_names[sname] = si
            jinja_key = sname.replace(" ", "_")
            if jinja_key in step_seen_keys and step_seen_keys[jinja_key] != si:
                # Skip if it's already flagged as a literal duplicate above.
                if sname not in step_seen_names or step_seen_names[sname] != step_seen_keys[jinja_key]:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(f"step name {sname!r} normalises to Jinja key "
                                 f"{jinja_key!r}, which collides with step #"
                                 f"{step_seen_keys[jinja_key]}'s name; rename one"),
                        path=sp,
                    ))
            else:
                step_seen_keys[jinja_key] = si

        # A playbook's trigger can be `start` (manual / abstract_trigger),
        # `record_action`, `start_on_create`, or `start_on_update`. Exactly
        # one trigger step required, of any of those flavours.
        TRIGGER_TYPES = {"start", "start_on_create", "start_on_update"}
        starts = [s for s in pb.steps if s.type in TRIGGER_TYPES]
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
