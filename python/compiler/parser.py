"""YAML -> IR parser.

Strict-ish: missing required fields produce CompileErrors with paths.
We don't try to validate references here — that's the resolver's job.
"""
from __future__ import annotations

import re
from typing import Any

import yaml

from .errors import CompileError, ErrorCode
from .ir import Annotation, Collection, Playbook, Step


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _coerce_label(v: Any) -> tuple[Any, bool]:
    """YAML 1.1 'Norway problem': bare `yes`/`no`/`on`/`off` are parsed as
    booleans. When such a value lands in a label position (decision
    `display:`, manual_input option `display:`), FSR's branch lookup
    keys off the literal string and silently fails. Coerce True→"yes",
    False→"no" so the playbook compiles, and signal a warning to the
    caller (return tuple second element).
    """
    if v is True:
        return "yes", True
    if v is False:
        return "no", True
    return v, False


_norway_warnings: list[str] = []  # populated transiently by callers below


def _rewrite_condition_keys(c: Any) -> Any:
    """Decision conditions: surface keys are `display` / `when` / `next` /
    `default`. Rewrite to wire keys `option` / `condition` for the resolver."""
    if not isinstance(c, dict):
        return c
    out: dict[str, Any] = {}
    for k, v in c.items():
        if k == "display":
            v2, fixed = _coerce_label(v)
            if fixed:
                _norway_warnings.append(str(v2))
            out["option"] = v2
        elif k == "when":
            out["condition"] = v
        else:
            out[k] = v
    return out


def _rewrite_option_keys(o: Any) -> Any:
    """Manual_input options: surface key is `display`. Rewrite to wire key `option`."""
    if not isinstance(o, dict):
        return o
    out: dict[str, Any] = {}
    for k, v in o.items():
        if k == "display":
            v2, fixed = _coerce_label(v)
            if fixed:
                _norway_warnings.append(str(v2))
            out["option"] = v2
        else:
            out[k] = v
    return out


def _slugify(s: str) -> str:
    """Lowercase, replace runs of non-alphanumerics with `_`, strip edges.

    Used to derive a step `id:` from `name:` when the author omitted the
    explicit id. Collisions surface as duplicate-id errors with a hint to
    set `id:` explicitly.
    """
    out = _SLUG_RE.sub("_", s.lower()).strip("_")
    return out or "step"


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
        if "uid" in pb_raw:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="playbook.uid is not allowed — identify playbooks by `name:` only",
                path=f"{pb_path}.uid",
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
            if "id" in s_raw:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        "step.id is not allowed — identify steps by `name:` "
                        "only; references in `next:` use the name verbatim"
                    ),
                    path=f"{sp}.id",
                ))
                continue
            sname = s_raw.get("name")
            stype = s_raw.get("type")
            sid = _slugify(sname) if isinstance(sname, str) and sname else None
            if not sid:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="step.name is required",
                    path=f"{sp}.name",
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
                    message=(
                        f"two steps slugify to the same id ({sid!r}); "
                        f"rename one of the colliding `name:` values"
                    ),
                    path=f"{sp}.name",
                ))
                continue
            seen_ids.add(sid)

            if stype == "stop":
                # Auto-rewrite: `stop` and `end` map to the same FSR
                # canonical (Connectors → cyops_utilities.no_op). Rather
                # than hard-erroring on a near-synonym the author had
                # every reason to expect to work, rewrite it to `end`
                # and emit a warning. Mechanical translation > prompt
                # rule.
                stype = "end"
                s_raw["type"] = "end"
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    severity="warning",
                    message="step type 'stop' auto-rewritten to 'end'",
                    path=f"{sp}.type",
                ))

            args = s_raw.get("arguments") or {}
            if not isinstance(args, dict):
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message="arguments must be a mapping",
                    path=f"{sp}.arguments",
                ))
                args = {}

            # Reject legacy nested shapes that have step-level shortcuts.
            if stype == "decision" and "conditions" in args:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        "decision: write `conditions:` at the step level "
                        "(not under `arguments:`)"
                    ),
                    path=f"{sp}.arguments.conditions",
                ))
                continue
            if stype == "manual_input" and "options" in args:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        "manual_input: write `options:` at the step level "
                        "(not under `arguments:`)"
                    ),
                    path=f"{sp}.arguments.options",
                ))
                continue
            if stype == "set_variable" and "arguments" in s_raw:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        "set_variable: write a top-level `vars:` mapping; "
                        "`arguments:` is not used"
                    ),
                    path=f"{sp}.arguments",
                ))
                continue

            # Step-level cross-cutting fields hoisted into `arguments:` so
            # downstream resolver/emitter code (and the wire shape) sees
            # them where it expects. Authors get to write them next to the
            # step instead of buried under `arguments:`. Both forms are
            # accepted transitionally; supplying both is an error so the
            # author doesn't accidentally end up with two values.
            #
            #   step.mock_result    → arguments.mock_result
            #   step.when           → arguments.when (start_on_* only — the
            #                         resolver pops it back out)
            #   step.step_variables → arguments.step_variables
            #   step.set            → arguments.step_variables (sugar — same
            #                         spelling whether you're on set_variable
            #                         (`vars:`) or a connector/create step)
            for hoist_key in ("mock_result", "when", "step_variables", "message"):
                if hoist_key in s_raw:
                    if hoist_key in args:
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"{hoist_key!r} set both at step level and "
                                f"under arguments — pick one"
                            ),
                            path=f"{sp}.{hoist_key}",
                        ))
                    else:
                        args[hoist_key] = s_raw[hoist_key]
            if "set" in s_raw:
                if "step_variables" in args:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(
                            "step.set: conflicts with step_variables "
                            "(both compile to arguments.step_variables) — pick one"
                        ),
                        path=f"{sp}.set",
                    ))
                elif not isinstance(s_raw["set"], dict):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="step.set must be a mapping of name → value",
                        path=f"{sp}.set",
                    ))
                else:
                    args["step_variables"] = dict(s_raw["set"])

            # Step-level shortcuts that hoist common nested shapes to the
            # surface so authors don't have to nest under `arguments:`. The
            # parser translates each shortcut into the canonical wire
            # arguments the resolver/emitter already understand.
            #
            # decision:    step.conditions[] → arguments.conditions[]
            #              with key renames display→option, when→condition
            # manual_input: step.options[]   → arguments.options[]
            #              with key rename   display→option
            # set_variable: step.vars (dict) → arguments.arg_list[{name,value}]
            if stype == "decision":
                top_conds = s_raw.get("conditions")
                if isinstance(top_conds, list):
                    _norway_warnings.clear()
                    args["conditions"] = [
                        _rewrite_condition_keys(c) for c in top_conds
                    ]
                    for label in _norway_warnings:
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            severity="warning",
                            message=(
                                f"decision branch label parsed as YAML "
                                f"boolean (Norway problem) — coerced to "
                                f"{label!r}; quote bare yes/no/on/off in "
                                f"`display:` to avoid this"
                            ),
                            path=f"{sp}.conditions",
                        ))
                    _norway_warnings.clear()
            if stype == "manual_input":
                top_opts = s_raw.get("options")
                if isinstance(top_opts, list):
                    _norway_warnings.clear()
                    args["options"] = [
                        _rewrite_option_keys(o) for o in top_opts
                    ]
                    for label in _norway_warnings:
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            severity="warning",
                            message=(
                                f"manual_input option label parsed as YAML "
                                f"boolean (Norway problem) — coerced to "
                                f"{label!r}; quote bare yes/no/on/off in "
                                f"`display:` to avoid this"
                            ),
                            path=f"{sp}.options",
                        ))
                    _norway_warnings.clear()
            if stype == "set_variable":
                top_vars = s_raw.get("vars")
                if isinstance(top_vars, dict):
                    args["arg_list"] = [
                        {"name": k, "value": v} for k, v in top_vars.items()
                    ]
                elif top_vars is not None:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="set_variable.vars must be a mapping of name → value",
                        path=f"{sp}.vars",
                    ))

            if stype == "connector":
                # Step-level `connector:` / `operation:` siblings of
                # `arguments:` are a recurring agent typo (session
                # 0eb8c6a6 burned a validate round on this). FSR's wire
                # format keeps them under arguments; auto-hoist with a
                # warning so the agent learns instead of cycling.
                for hk in ("connector", "operation"):
                    if hk in s_raw and hk not in args:
                        args[hk] = s_raw[hk]
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            severity="warning",
                            message=(
                                f"connector step has step-level `{hk}:` — "
                                f"hoisted into `arguments.{hk}`. Put it "
                                f"under `arguments:` next time."
                            ),
                            path=f"{sp}.{hk}",
                        ))

            if "branches" in s_raw:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(
                        "step-level `branches:` is not allowed — write "
                        "`next:` on each entry of `conditions:` (decision) "
                        "or `options:` (manual_input)"
                    ),
                    path=f"{sp}.branches",
                ))
                continue
            if stype == "decision" and s_raw.get("next"):
                # Warn-and-fix: a bare step-level `next:` on a Decision is
                # ambiguous (FSR's designer needs an explicit `default: true`
                # row to render the else edge with a label). Rather than
                # hard-fail the compile, let the value through — the emitter
                # auto-synthesizes an "Else" default condition pointing at
                # the same target. Match the user's standing preference for
                # mechanical translation over prompt rules.
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    severity="warning",
                    message=(
                        "decision step has a step-level `next:` — auto-"
                        "synthesizing an `Else` default condition pointing "
                        "at that target"
                    ),
                    path=f"{sp}.next",
                ))
            branches: dict[str, str] = {}

            cmt = s_raw.get("comment")

            for_each = None
            fe_raw = s_raw.get("for_each")
            if fe_raw is not None:
                if not isinstance(fe_raw, dict):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="for_each must be a mapping",
                        path=f"{sp}.for_each",
                    ))
                else:
                    accepted = {"item", "parallel", "condition", "__bulk",
                                "batch_size", "break_loop"}
                    unknown = set(fe_raw.keys()) - accepted
                    if unknown:
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                f"for_each has unknown keys: {sorted(unknown)}. "
                                f"Accepted: {sorted(accepted)}"
                            ),
                            path=f"{sp}.for_each",
                        ))
                    item = fe_raw.get("item")
                    if not isinstance(item, str) or not item.strip():
                        errors.append(CompileError(
                            code=ErrorCode.MISSING_FIELD,
                            message="for_each.item is required (Jinja list expression, e.g. '{{ vars.records }}')",
                            path=f"{sp}.for_each.item",
                        ))
                    else:
                        for_each = {
                            "item": item,
                            "parallel": bool(fe_raw.get("parallel", False)),
                            "condition": str(fe_raw.get("condition", "") or ""),
                        }
                        if "__bulk" in fe_raw:
                            for_each["__bulk"] = bool(fe_raw["__bulk"])
                        if "batch_size" in fe_raw:
                            try:
                                for_each["batch_size"] = int(fe_raw["batch_size"])
                            except (TypeError, ValueError):
                                errors.append(CompileError(
                                    code=ErrorCode.BAD_VALUE,
                                    message="for_each.batch_size must be an integer",
                                    path=f"{sp}.for_each.batch_size",
                                ))
                        if "break_loop" in fe_raw:
                            for_each["break_loop"] = str(fe_raw["break_loop"] or "")

            steps.append(Step(
                id=sid,
                type=stype,
                name=sname or sid,
                arguments=args,
                next=s_raw.get("next") if isinstance(s_raw.get("next"), str) else None,
                branches={str(k): str(v) for k, v in branches.items()},
                comment=cmt if isinstance(cmt, str) and cmt.strip() else None,
                for_each=for_each,
            ))

        # Resolve reference values against the playbook's step roster.
        # Authors write references as the step's `name:` (canonical) or
        # the slugified id; both work. After this pass, every reference
        # holds the literal step.id so downstream resolver/emitter code
        # never has to think about the duality.
        name_to_id: dict[str, str] = {}
        # Mirror the linter's charset substitution so `next:` references
        # written with disallowed chars (em-dash, hyphen, etc) still
        # resolve after the linter auto-renames the target step.
        _bad_char_runs = re.compile(r"[^A-Za-z0-9 _]+")
        for s in steps:
            name_to_id.setdefault(s.name, s.id)
            name_to_id.setdefault(s.id, s.id)
            name_to_id.setdefault(_slugify(s.name), s.id)
            charset_fixed = _bad_char_runs.sub("_", s.name).strip("_")
            if charset_fixed:
                name_to_id.setdefault(charset_fixed, s.id)

        def _resolve_ref(v: Any) -> Any:
            if isinstance(v, str) and v in name_to_id:
                return name_to_id[v]
            return v

        for s in steps:
            if s.next:
                s.next = _resolve_ref(s.next)
            s.branches = {k: _resolve_ref(v) for k, v in s.branches.items()}
            # Inline `next:` on decision conditions and manual_input options
            # is promoted into step.branches by the resolver — pre-resolve
            # the string here so the resolver doesn't have to know names.
            if isinstance(s.arguments, dict):
                conds = s.arguments.get("conditions")
                if isinstance(conds, list):
                    for c in conds:
                        if isinstance(c, dict) and isinstance(c.get("next"), str):
                            c["next"] = _resolve_ref(c["next"])
                opts = s.arguments.get("options")
                if isinstance(opts, list):
                    for o in opts:
                        if isinstance(o, dict) and isinstance(o.get("next"), str):
                            o["next"] = _resolve_ref(o["next"])

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

    if any(e.severity != "warning" for e in errors):
        return None, errors

    return Collection(
        name=name or "",
        description=doc.get("description", "") or "",
        visible=bool(doc.get("visible", True)),
        playbooks=playbooks,
    ), errors
