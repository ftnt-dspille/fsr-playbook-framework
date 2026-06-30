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

# Declared playbook-parameter types (STATIC_TYPE_FLOW Phase 3). Author-facing
# vocabulary; the typed walker maps these to source Shapes. `any` is allowed
# but stored as "untyped" (omitted from parameter_types).
_PARAM_TYPE_VOCAB = {
    "string", "integer", "boolean", "float", "number", "object", "json",
    "list", "array", "datetime", "ipv4", "url", "email", "any",
}


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

    # Push-mode detection: `collection:` = wrap (replace whole collection,
    # default for backward compat), `into_collection:` = per_playbook
    # (only touches listed playbooks within a shared target). Default
    # collection for empty per-playbook YAMLs: the studio's own bucket.
    DEFAULT_TARGET = "00 - FSR Studio"
    has_collection = "collection" in doc
    has_into = "into_collection" in doc
    if has_collection and has_into:
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message="set EITHER `collection:` (wrap mode) OR "
                    "`into_collection:` (per-playbook mode), not both",
            path="collection",
        ))
        return None, errors
    if has_into:
        name = doc.get("into_collection")
        target_mode = "per_playbook"
        name_path = "into_collection"
    elif has_collection:
        name = doc.get("collection")
        target_mode = "wrap"
        name_path = "collection"
    else:
        name = DEFAULT_TARGET
        target_mode = "per_playbook"
        name_path = "into_collection"
    if not isinstance(name, str) or not name:
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message=f"{name_path} must be a non-empty string",
            path=name_path,
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
            #   step.module(s)      → arguments.module(s) (start: binds the
            #                         trigger to a module so it resolves to a
            #                         cybersponse.action manual Execute-menu
            #                         trigger; the normalizer reads it off
            #                         arguments). Without this hoist a
            #                         top-level `module:` is silently dropped
            #                         and the start stays a Referenced trigger.
            #   step.set            → arguments.step_variables (sugar — same
            #                         spelling whether you're on set_variable
            #                         (`vars:`) or a connector/create step)
            #   step.ignore_errors  → arguments.ignore_errors (universal: keep
            #                         running the playbook even if this step
            #                         raises)
            #   step.do_until       → arguments.do_until (retry loop; `retry:`
            #                         below is the friendly sugar for it)
            #   step.apply_async    → arguments.apply_async (fire-and-forget
            #                         connector / workflow_reference execution)
            #   step.agent/agentId/pickFromTenant → the remote-agent envelope
            #                         (`on_remote:` below is the friendly sugar)
            for hoist_key in ("mock_result", "when", "step_variables", "message",
                              "module", "modules", "ignore_errors", "do_until",
                              "apply_async", "agent", "agentId", "pickFromTenant"):
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

            # Universal-envelope sugar — friendly spellings of the wire keys
            # hoisted above, translated here so the resolver/emitter only ever
            # see the canonical shape. Each guards against colliding with the
            # canonical key it expands to.
            #
            #   retry: {times, delay, until} → do_until: {retries, delay, condition}
            #     A retry loop re-runs the step until `until` is truthy (or the
            #     retry budget is spent). `times`→`retries`, `until`→`condition`;
            #     `delay` passes through (seconds between attempts).
            if "retry" in s_raw:
                if "do_until" in args:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=("step.retry and do_until both set — they "
                                 "compile to the same `do_until` block; pick one"),
                        path=f"{sp}.retry",
                    ))
                elif not isinstance(s_raw["retry"], dict):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="step.retry must be a mapping (times/delay/until)",
                        path=f"{sp}.retry",
                    ))
                else:
                    rt = s_raw["retry"]
                    unknown = set(rt) - {"times", "delay", "until", "condition",
                                         "retries"}
                    if unknown:
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(f"step.retry has unknown keys: "
                                     f"{sorted(unknown)}. Accepted: times, "
                                     f"delay, until"),
                            path=f"{sp}.retry",
                        ))
                    du: dict[str, Any] = {}
                    if "until" in rt or "condition" in rt:
                        du["condition"] = rt.get("until", rt.get("condition"))
                    if "times" in rt or "retries" in rt:
                        du["retries"] = rt.get("times", rt.get("retries"))
                    if "delay" in rt:
                        du["delay"] = rt["delay"]
                    args["do_until"] = du

            #   on_remote: <agent>            → agent: <agent>, pickFromTenant: false
            #   on_remote: pick_from_record   → agent: "Pick From Record
            #                                   Ownership", pickFromTenant: true
            #     Routes step execution to a remote/tenant agent. The literal
            #     "Pick From Record Ownership" is FSR's magic value for
            #     record-ownership-based selection.
            if "on_remote" in s_raw:
                if "agent" in args:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=("step.on_remote and agent both set — they "
                                 "compile to the same `agent`; pick one"),
                        path=f"{sp}.on_remote",
                    ))
                else:
                    rem = s_raw["on_remote"]
                    if not isinstance(rem, str) or not rem.strip():
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=("step.on_remote must be an agent name or "
                                     "'pick_from_record'"),
                            path=f"{sp}.on_remote",
                        ))
                    elif rem.strip().lower() in ("pick_from_record",
                                                 "pick_from_record_ownership",
                                                 "pick from record ownership"):
                        args["agent"] = "Pick From Record Ownership"
                        args["pickFromTenant"] = True
                    else:
                        args["agent"] = rem.strip()
                        args.setdefault("pickFromTenant", False)

            #   post_comment: "text"  → message: {content: "text"}
            #     Friendly sugar for posting a collaboration comment on the
            #     triggering record. `message:` (the canonical block) still works.
            if "post_comment" in s_raw:
                if "message" in args:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=("step.post_comment and message both set — "
                                 "they compile to the same `message` block; "
                                 "pick one"),
                        path=f"{sp}.post_comment",
                    ))
                elif not isinstance(s_raw["post_comment"], str):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="step.post_comment must be a string",
                        path=f"{sp}.post_comment",
                    ))
                else:
                    args["message"] = {"content": s_raw["post_comment"]}

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
                # Step-level `default: <step_id>` sugar — synthesizes an
                # Else default-condition row that targets that step. Pairs
                # with the non-default conditions[] entries; surfaces in
                # `step.branches` via the resolver's normalizer.
                top_default = s_raw.get("default")
                if isinstance(top_default, str) and top_default.strip():
                    existing = args.setdefault("conditions", [])
                    has_default = any(
                        isinstance(c, dict) and c.get("default") is True
                        for c in existing
                    )
                    if has_default:
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(
                                "decision step has both a step-level "
                                "`default:` and a default-flagged entry in "
                                "`conditions:` — keep only one"
                            ),
                            path=f"{sp}.default",
                        ))
                    else:
                        existing.append({
                            "option": "Else",
                            "default": True,
                            "next": top_default.strip(),
                        })
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
                # The prompt's form fields + heading are documented as
                # step-level keys (guides/playbook-yaml-reference.md), same as
                # `options:`. Hoist them into `arguments:` so the resolver's
                # `_normalize_manual_input_args` (which reads `a.pop("inputs")`
                # etc.) actually sees them — otherwise step-level `inputs:` is
                # silently dropped and the prompt ships with an empty form
                # (`inputVariables: []`), `title`/`description` falling back to
                # the step name. Conflict-guard mirrors the global hoist.
                for hk in ("inputs", "title", "description"):
                    if hk in s_raw:
                        if hk in args:
                            errors.append(CompileError(
                                code=ErrorCode.BAD_VALUE,
                                message=(f"manual_input: {hk!r} set both at "
                                         f"step level and under arguments — "
                                         f"keep one"),
                                path=f"{sp}.{hk}",
                            ))
                        else:
                            args[hk] = s_raw[hk]
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

            if stype == "delete_record":
                # Hoist the friendly delete targeting keys from step level into
                # arguments (the resolver's _normalize_delete_record_args reads
                # them there). `module` is already hoisted globally.
                for hk in ("record", "record_id", "query", "show_deleted"):
                    if hk in s_raw:
                        if hk in args:
                            errors.append(CompileError(
                                code=ErrorCode.BAD_VALUE,
                                message=(f"{hk!r} set both at step level and "
                                         f"under arguments — keep one"),
                                path=f"{sp}.{hk}",
                            ))
                        else:
                            args[hk] = s_raw[hk]

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
            # Host step types that never legitimately carry `for_each` in
            # the live corpus (369 hits across 11 step types — these
            # never appear). Looping a control-flow step would be a
            # nonsense or unsafe construct.
            _FOR_EACH_DISALLOWED_HOSTS = {
                "start", "start_on_create", "start_on_update", "start_on_delete",
                "decision", "end", "manual_input",
            }
            if fe_raw is not None:
                if stype in _FOR_EACH_DISALLOWED_HOSTS:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(
                            f"for_each is not supported on step type "
                            f"{stype!r}. Attach for_each to a data /"
                            f" action step instead (create_record, "
                            f"update_record, find_record, connector, "
                            f"workflow_reference, set_variable, delay, "
                            f"code_snippet, send_mail). Control-flow "
                            f"steps (start*, decision, end, manual_input)"
                            f" cannot be iterated."
                        ),
                        path=f"{sp}.for_each",
                    ))
                    fe_raw = None
            if fe_raw is not None:
                if not isinstance(fe_raw, dict):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="for_each must be a mapping",
                        path=f"{sp}.for_each",
                    ))
                else:
                    accepted = {"item", "parallel", "condition", "__bulk",
                                "batch_size", "break_loop",
                                "max_parallel", "concurrency_count"}
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
                        # Loop max-parallel cap (FSR 8.0). Author-friendly
                        # `max_parallel: N` (alias `concurrency_count`) compiles
                        # to the wire pair the designer emits: the
                        # `concurrency: true` toggle + the `concurrencyCount: N`
                        # limit. Only meaningful on a parallel loop, and the
                        # engine's minimum is 2 (CONCURRENCY_CONFIG_MIN_INPUT).
                        cap_key = ("max_parallel" if "max_parallel" in fe_raw
                                   else "concurrency_count" if "concurrency_count" in fe_raw
                                   else None)
                        if cap_key is not None:
                            try:
                                cap = int(fe_raw[cap_key])
                            except (TypeError, ValueError):
                                errors.append(CompileError(
                                    code=ErrorCode.BAD_VALUE,
                                    message=f"for_each.{cap_key} must be an integer",
                                    path=f"{sp}.for_each.{cap_key}",
                                ))
                            else:
                                if not for_each["parallel"]:
                                    errors.append(CompileError(
                                        code=ErrorCode.BAD_VALUE,
                                        severity="warning",
                                        message=(
                                            f"for_each.{cap_key} caps a *parallel* "
                                            "loop; this loop is sequential "
                                            "(parallel: false), so the cap is "
                                            "ignored. Set parallel: true."
                                        ),
                                        path=f"{sp}.for_each.{cap_key}",
                                    ))
                                if cap < 2:
                                    errors.append(CompileError(
                                        code=ErrorCode.BAD_VALUE,
                                        severity="warning",
                                        message=(
                                            f"for_each.{cap_key}={cap} is below the "
                                            "FSR minimum of 2; the engine will "
                                            "treat it as 2."
                                        ),
                                        path=f"{sp}.for_each.{cap_key}",
                                    ))
                                for_each["concurrency"] = True
                                for_each["concurrencyCount"] = cap

            # Loop-mode defaulting (authoring path only). The editor injects
            # these when you build a loop in the UI, so the friendly authoring
            # surface must produce the same wire shape. The shared emitter is a
            # faithful serializer and no longer normalizes for_each, so that a
            # decompiled (already-canonical) for_each round-trips byte-for-byte
            # — the corpus carries inconsistent bulk shapes (some bulk loops
            # have no batch_size, some keep parallel) that no emit-time rule
            # could reproduce. See `_clean_step_arguments` + the round-trip gate.
            if isinstance(for_each, dict):
                if for_each.get("__bulk"):
                    for_each.pop("parallel", None)        # bulk implies sequential batches
                    for_each.setdefault("batch_size", 100)  # editor default when bulk
                else:
                    for_each.pop("batch_size", None)      # batch_size is a bulk-only key

            steps.append(Step(
                id=sid,
                type=stype,
                name=sname or sid,
                arguments=args,
                next=s_raw.get("next") if isinstance(s_raw.get("next"), str) else None,
                branches={str(k): str(v) for k, v in branches.items()},
                comment=cmt if isinstance(cmt, str) and cmt.strip() else None,
                description=(s_raw["description"]
                            if isinstance(s_raw.get("description"), str) else ""),
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

        # `parameters:` accepts two shapes (STATIC_TYPE_FLOW Phase 3):
        #   - bare list of names (untyped → each param is `any`), or
        #   - mapping {name: type} declaring a static type per param, which
        #     seeds `vars.input.params.<name>` in the typed walker.
        params_in = pb_raw.get("parameters") or []
        params_raw: list[str] = []
        param_types: dict[str, str] = {}
        if isinstance(params_in, dict):
            for pname, ptype in params_in.items():
                if not isinstance(pname, str):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message="parameter names must be strings",
                        path=f"{pb_path}.parameters",
                    ))
                    continue
                params_raw.append(pname)
                tnorm = str(ptype).strip().lower() if ptype is not None else ""
                if tnorm and tnorm not in _PARAM_TYPE_VOCAB:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(f"parameter {pname!r} has unknown type "
                                 f"{ptype!r}; allowed: "
                                 f"{', '.join(sorted(_PARAM_TYPE_VOCAB))}"),
                        path=f"{pb_path}.parameters.{pname}",
                        severity="warning",
                    ))
                elif tnorm and tnorm != "any":
                    param_types[pname] = tnorm
        elif isinstance(params_in, list) and all(
                isinstance(p, str) for p in params_in):
            params_raw = list(params_in)
        else:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=("parameters must be a list of strings or a mapping "
                         "{name: type}"),
                path=f"{pb_path}.parameters",
            ))

        # Capture the priority NAME as-authored (normalized to Title case).
        # Optional — defaults to "High" so authored playbooks run at high
        # priority unless they opt down. Validation + IRI resolution happens in
        # the resolver against the live-synced `picklists` table (no DB here).
        priority_raw = pb_raw.get("priority")
        priority: str = (
            str(priority_raw).strip().title() if priority_raw not in (None, "") else "High"
        )

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

        # Owner teams + private visibility. `owners` accepts team NAMES (the
        # author-friendly form — "TeamA") or IRIs (`/api/3/teams/<uuid>`); the
        # resolver converts names to IRIs via the warmed `teams` table. Coerce
        # to a list of strings.
        owners_raw = pb_raw.get("owners", []) or []
        if not isinstance(owners_raw, list):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="`owners` must be a list of team names or IRIs",
                path=f"{pb_path}.owners",
            ))
            owners_raw = []
        owners = [str(o) for o in owners_raw]

        # Private visibility is DERIVED from owners, matching FSR's model: a
        # playbook with owner teams is private to those teams; a playbook with
        # no owners is public (any team can run it — the SOAR default).
        # `is_private:` is an optional explicit override; when omitted it
        # follows `bool(owners)`. The SOAR invariant is enforced: no owners
        # => never private, even if `is_private: true` was written (warned).
        explicit_private = "is_private" in pb_raw
        is_private = bool(pb_raw.get("is_private", False)) if explicit_private else bool(owners)
        if not owners:
            if explicit_private and is_private:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=("`is_private: true` with no owners — a private "
                             "playbook requires owner teams; emitting PUBLIC "
                             "(any team can run it, the SOAR default)"),
                    path=f"{pb_path}.is_private",
                    severity="warning",
                ))
            is_private = False

        playbooks.append(Playbook(
            name=pb_name,
            description=pb_raw.get("description", "") or "",
            tag=pb_raw.get("tag", "") or "",
            # Defaults to active — authors almost never want to deploy an
            # inactive playbook, and FSR's UI creates them active by default.
            # Set `is_active: false` explicitly to ship a disabled draft.
            is_active=bool(pb_raw.get("is_active", True)),
            debug=bool(pb_raw.get("debug", False)),
            is_private=is_private,
            owners=owners,
            priority=priority,
            trigger=str(pb_raw.get("trigger", "start") or "start"),
            parameters=list(params_raw),
            parameter_types=param_types,
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
        target_mode=target_mode,
    ), errors
