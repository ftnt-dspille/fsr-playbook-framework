"""Compose a playbook from a typed plan -- the model declares, code compiles.

E6 (playbook-loop-redesign.md). The build census showed the agent's failures
are at the CLOSE: it does the discovery, then authors free-form YAML and spends
~35 checkpoints catching the ways free text goes wrong (a `stepType:` typo, a
bad fence, an orphan step, a guessed jinja path). This tool removes the failure
surface by removing the free text: the model declares an ordered, typed plan and
this compiles it -- the model never writes YAML.

It reuses the trace compiler wholesale: a plan step becomes a `SkillCall`, the
list becomes a `SkillTrace`, and the exact `compile_and_verify` + containment
guards + assemble pipeline that `build_playbook_from_trace` runs produces the
YAML, verifies every wire, and surfaces the unresolved ones as gaps. The only
new code is the plan -> SkillCall translation. The four skills the compiler
registers (connector, decision, manual_input, set_variable) plus the injected
trigger are the plan's vocabulary.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ._shared import mcp

# plan `kind` -> the compiler skill id it maps to.
_KIND_TO_SKILL = {
    "connector": "run_connector_action",
    "decision": "decision",
    "manual_input": "manual_input",
    "set_variable": "set_variable",
}
# A `record` plan step selects its skill by `action` (the FSR record step type).
_RECORD_ACTION_TO_SKILL = {
    "create": "create_record",
    "update": "update_record",
    "find": "find_record",
}
# The ONE description of each record action's accepted keys and a worked
# example. The validator, the error text and the tool description are all
# derived from this table, so they cannot drift apart. `required` keys must be
# present; `optional` may be.
_RECORD_SHAPES: dict[str, dict[str, Any]] = {
    "create": {
        "required": ("module",),
        "optional": ("fields", "operation"),
        "example": {
            "kind": "record", "name": "Open Incident", "action": "create",
            "module": "incidents",
            "fields": {"name": "Phishing follow-up",
                       "description": {"from_step": "__input__",
                                       "output": "name"}}},
    },
    "update": {
        # `record` is the IRI of the record to write to (the compiler's
        # update_record has nothing to write to without it).
        "required": ("module", "record"),
        "optional": ("fields", "operation"),
        "example": {
            "kind": "record", "name": "Stamp Alert", "action": "update",
            "module": "alerts",
            "record": {"from_step": "__input__", "output": "@id"},
            "fields": {"description": {"from_step": "Lookup",
                                       "output": "summary"}}},
    },
    "find": {
        "required": ("module",),
        "optional": ("filters", "limit", "sort"),
        "example": {
            "kind": "record", "name": "Find Open Alerts", "action": "find",
            "module": "alerts",
            "filters": [{"field": "status", "operator": "eq",
                         "value": "Open"}]},
    },
}


def _record_example(action: str) -> str:
    return json.dumps(_RECORD_SHAPES[action]["example"])


def _record_shape_doc() -> str:
    """The `record` bullet of the tool description, built from the table."""
    lines = []
    for action, spec in _RECORD_SHAPES.items():
        keys = ", ".join(list(spec["required"]) +
                         [k + "?" for k in spec["optional"]])
        lines.append(f"        action `{action}`: `{{kind, name, action, "
                     f"{keys}}}` e.g. {_record_example(action)}")
    return "\n".join(lines)


# The connector envelope defaults to `.data` (get_op_schema's binding rule); the
# other skills publish their outputs at the step root.
_DEFAULT_REF_PREFIX = {"connector": "data"}


def _jkey(step_name: str) -> str:
    return (step_name or "").replace(" ", "_")


# The trigger record is referenced through the playbook input, not a step.
_INPUT_STEP = "__input__"


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])*$")


def _path_suffix(path: str) -> str:
    """Render an output path to jinja. A plain name is `.name`; a name that is
    not an identifier (`@id`, `a-b`) is bracketed, `['@id']`, because
    `vars.x.@id` is not valid jinja."""
    path = (path or "").strip()
    if not path:
        return ""
    if path.startswith(("[", ".")):
        return path
    out = ""
    for tok in path.split("."):
        out += f".{tok}" if _IDENT.match(tok) else f"['{tok}']"
    return out


def _wire_ref(from_step: str, output: str, ref_prefix: str) -> str:
    """A cross-step reference the author declared structurally, rendered to the
    one correct jinja path -- the error-prone part the model no longer types.

    `from_step == "__input__"` means a field of the triggering record, which
    lives at `vars.input.records[0].<field>`, not under a step. A `find` record
    step's output is a LIST, so its prefix is `[0]` (the first match)."""
    if from_step == _INPUT_STEP:
        base = "vars.input.records[0]"
    else:
        base = f"vars.steps.{_jkey(from_step)}"
        if ref_prefix:
            base += ref_prefix if ref_prefix.startswith("[") \
                else f".{ref_prefix}"
    return "{{ " + base + _path_suffix(output) + " }}"


def _resolve_value(val: Any, ref_prefix_by_step: dict[str, str]) -> Any:
    """Translate every `{from_step, output}` ref inside a value (nested in a
    list or object too, e.g. a `filters` entry's `value`) to jinja."""
    if isinstance(val, dict):
        if "from_step" in val:
            src = str(val.get("from_step") or "")
            return _wire_ref(src, str(val.get("output") or ""),
                             ref_prefix_by_step.get(src, "data"))
        return {k: _resolve_value(v, ref_prefix_by_step)
                for k, v in val.items()}
    if isinstance(val, list):
        return [_resolve_value(v, ref_prefix_by_step) for v in val]
    return val


def _resolve_inputs(raw: dict[str, Any],
                    ref_prefix_by_step: dict[str, str]) -> dict[str, Any]:
    """Pass literals through; translate a `{from_step, output}` ref to jinja."""
    return {key: _resolve_value(val, ref_prefix_by_step)
            for key, val in (raw or {}).items()}


def _resolve_for_each(raw: dict[str, Any],
                      ref_prefix_by_step: dict[str, str]) -> dict[str, Any]:
    """Translate a plan `for_each` into the step-level loop modifier. `item` is
    the list to iterate: a literal jinja string, or a `{from_step, output}` ref
    that we render to the one correct `vars.steps...` path -- the author never
    types jinja. `parallel` / `condition` / `__bulk` pass through."""
    out: dict[str, Any] = {}
    item = raw.get("item")
    if isinstance(item, dict) and "from_step" in item:
        src = str(item.get("from_step") or "")
        out["item"] = _wire_ref(src, str(item.get("output") or ""),
                                ref_prefix_by_step.get(src, "data"))
    elif item is not None:
        out["item"] = item
    for k in ("parallel", "condition", "__bulk", "batch_size"):
        if raw.get(k) is not None:
            out[k] = raw[k]
    return out


_COMMON_STEP_KEYS = frozenset({"kind", "name", "for_each"})
_STEP_KEYS: dict[str, frozenset[str]] = {
    "connector": frozenset({"connector", "operation", "inputs", "params",
                            "config"}),
    "record": frozenset({"action"}).union(
        *(set(v["required"]) | set(v["optional"])
          for v in _RECORD_SHAPES.values())),
    "decision": frozenset({"conditions", "default"}),
    "manual_input": frozenset({"message", "options", "fields"}),
    "set_variable": frozenset({"values", "vars"}),
}


def _merged_alias(step: dict[str, Any], canonical: str, alias: str,
                  where: str, errors: list[str]) -> dict[str, Any]:
    """Read `canonical` or its YAML-shaped `alias`; both at once is ambiguous."""
    a, b = step.get(canonical), step.get(alias)
    if a is not None and b is not None:
        errors.append(f"{where}: pass `{alias}` or `{canonical}`, not both")
        return {}
    val = a if a is not None else b
    if val is None:
        return {}
    if not isinstance(val, dict):
        errors.append(f"{where}: `{alias if b is not None else canonical}` "
                      "must be an object mapping names to values")
        return {}
    return dict(val)


def _plan_to_trace(steps: list[dict[str, Any]], module: str):
    from fsr_playbooks.agent.skill_trace import SkillCall, SkillTrace

    calls: list[SkillCall] = []
    ref_prefix_by_step: dict[str, str] = {}
    errors: list[str] = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"step {i}: must be an object")
            continue
        kind = str(step.get("kind") or "").strip()
        name = str(step.get("name") or "").strip() or f"Step {i + 1}"
        if kind == "record":
            action = str(step.get("action") or "").strip().lower()
            skill_id = _RECORD_ACTION_TO_SKILL.get(action)
            if not skill_id:
                errors.append(f"step {i} ({name!r}): a record step needs "
                              f"`action` one of {sorted(_RECORD_ACTION_TO_SKILL)}")
                continue
        else:
            skill_id = _KIND_TO_SKILL.get(kind)
            if not skill_id:
                errors.append(
                    f"step {i} ({name!r}): unknown kind {kind!r}; use one of "
                    f"{sorted(list(_KIND_TO_SKILL) + ['record'])}")
                continue
        accepted = _STEP_KEYS.get(kind, frozenset())
        if kind == "record":
            spec = _RECORD_SHAPES[action]
            accepted = frozenset({"action"} | set(spec["required"])
                                 | set(spec["optional"]))
            # `query` as a list of {field, operator, value} IS `filters`; one
            # obvious spelling, not an ambiguity.
            if (action == "find" and "filters" not in step
                    and isinstance(step.get("query"), list)):
                step = {**{k: v for k, v in step.items() if k != "query"},
                        "filters": step["query"]}
        unknown = sorted(k for k in step
                         if k not in accepted and k not in _COMMON_STEP_KEYS)
        if unknown:
            hint = (f"; example: {_record_example(action)}"
                    if kind == "record" else "")
            errors.append(
                f"step {i} ({name!r}): unknown key(s) {unknown} for a "
                f"{(kind + ' ' + action) if kind == 'record' else repr(kind)} "
                f"step; accepted keys: "
                f"{sorted((accepted - {'kind'}) | _COMMON_STEP_KEYS)}{hint}")
            continue
        ref_prefix = _DEFAULT_REF_PREFIX.get(kind, "")
        if kind == "record" and action == "find":
            ref_prefix = "[0]"   # find_record output is a list of records
        ref_prefix_by_step[name] = ref_prefix

        if kind == "record":
            missing = [k for k in spec["required"]
                       if not step.get(k) and not (k == "module" and module)]
            if missing:
                errors.append(
                    f"step {i} ({name!r}): a record {action} step needs "
                    f"{['`' + k + '`' for k in missing]}; example: "
                    f"{_record_example(action)}")
                continue
            resolved = {"module": step.get("module") or module}
            if action == "create":
                resolved["operation"] = step.get("operation") or "Create"
            elif step.get("operation"):
                resolved["operation"] = step["operation"]
            raw_fields = step.get("fields") or {}
            if not isinstance(raw_fields, dict):
                errors.append(f"step {i} ({name!r}): `fields` must be an "
                              "object mapping field names to values; "
                              f"example: {_record_example(action)}")
                continue
            if action == "update" and "record" in raw_fields:
                errors.append(
                    f"step {i} ({name!r}): `record` is the target of the "
                    "update, a step key beside `fields`, not a field in it; "
                    f"example: {_record_example('update')}")
                continue
            if raw_fields:
                resolved["fields"] = _resolve_inputs(dict(raw_fields),
                                                     ref_prefix_by_step)
            for key in ("record", "filters", "limit", "sort"):
                if step.get(key) is not None:
                    resolved[key] = _resolve_value(step[key],
                                                   ref_prefix_by_step)
        elif kind == "connector":
            inputs = _merged_alias(step, "inputs", "params",
                                   f"step {i} ({name!r})", errors)
            if step.get("config") is not None:
                inputs["config"] = step["config"]
            inputs["connector"] = step.get("connector") or ""
            inputs["operation"] = step.get("operation") or ""
            if not inputs["connector"] or not inputs["operation"]:
                errors.append(f"step {i} ({name!r}): a connector step needs "
                              "both `connector` and `operation`")
            resolved = _resolve_inputs(inputs, ref_prefix_by_step)
        elif kind == "decision":
            resolved = {"conditions": step.get("conditions") or [],
                        "default": step.get("default") or ""}
        elif kind == "manual_input":
            resolved = {k: step[k] for k in ("message", "options", "fields")
                        if step.get(k) is not None}
        else:  # set_variable
            resolved = _resolve_inputs(
                _merged_alias(step, "values", "vars",
                              f"step {i} ({name!r})", errors),
                ref_prefix_by_step)

        for_each = None
        raw_fe = step.get("for_each")
        if isinstance(raw_fe, dict) and raw_fe:
            if kind not in ("connector", "set_variable", "record"):
                errors.append(f"step {i} ({name!r}): for_each loops a connector, "
                              "record or set_variable step, not a "
                              f"{kind!r} step")
            elif not raw_fe.get("item"):
                errors.append(f"step {i} ({name!r}): for_each needs an `item` "
                              "list to iterate")
            else:
                for_each = _resolve_for_each(raw_fe, ref_prefix_by_step)

        calls.append(SkillCall(skill_id=skill_id, step_name=name,
                               resolved_inputs=resolved, ref_prefix=ref_prefix,
                               for_each=for_each))

    return SkillTrace(calls=calls, module=module or None), errors


_COMPOSE_DOC = """Build a playbook from a typed plan -- you declare the steps, this writes
    and verifies the YAML. Do NOT hand-author YAML when you can use this.

    `steps` is the ordered plan, each a small object with a `kind` and a `name`:
      - `connector`: `{kind, name, connector, operation, inputs?, config?}` -- `inputs`
        (alias `params`)
        maps each parameter to a literal, or to `{from_step, output}` to read an
        earlier step's output (this writes the correct `vars.steps...` path for
        you; never type jinja yourself).
      - `record`: a record action on an FSR module, `action` is `create` /
        `update` / `find`. The accepted keys differ per action (`?` = optional);
        `fields` / `record` / filter values may be `{from_step, output}` refs
        (`from_step: "__input__"` is the triggering record, `output: "@id"` its
        IRI; a `find` step's output is its first match). `update` MUST name its
        target with `record`:
{RECORD_SHAPES}
      - `decision`: `{kind, name, conditions, default?}` -- route on conditions
        over earlier outputs.
      - `manual_input`: `{kind, name, message?, options?, fields?}` -- a human
        confirmation or extra input a following decision consumes.
      - `set_variable`: `{kind, name, values}` (alias `vars`) -- stage/normalize values.
      Unknown step keys are rejected with the accepted list, never dropped.
      - loop any `connector` / `record` / `set_variable` step by adding
        `for_each: {item, parallel?}`, where `item` is the list to iterate
        (a `{from_step, output}` ref, or a jinja string); the element is bound as
        `{{ vars.item }}` in that step's inputs. `for_each` is a step MODIFIER --
        there is no standalone loop step type.
    `module` is the trigger module (alerts, incidents, ...). Resolve each
    connector/operation with `plan_playbook` or `find` first.

    It compiles the plan, verifies every wire resolves, repairs the ones that do
    not (back to a literal plus a `gap`, never a dangling reference), gates any
    containment op behind a confirm + malicious-verdict decision, and confirms
    the result imports clean. Returns `{ok, yaml, compile_summary, verified,
    gaps, repaired, static_errors}`. A `gap` is the honest signal that a value
    could not be wired -- fix the plan and compose again; do not paper over it in
    prose. Deliver the returned YAML with `emit_playbook_offer`.
    """


def compose_playbook(steps: list[dict[str, Any]],
                     name: str = "New Playbook",
                     module: str = "",
                     guard_containment: bool = True) -> dict[str, Any]:
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "code": "no_steps",
                "message": "pass a non-empty ordered list of plan steps"}

    from fsr_playbooks.compiler import skill_compiler as sc
    from fsr_playbooks.compiler import skill_verify as sv

    trace, errors = _plan_to_trace(steps, module)
    if errors:
        return {"ok": False, "code": "bad_plan", "errors": errors,
                "message": "; ".join(errors)}
    if len(trace) == 0:
        return {"ok": False, "code": "no_steps",
                "message": "the plan produced no compilable steps"}

    compiled = sv.compile_and_verify(trace)
    if guard_containment:
        compiled = sc.insert_containment_guard(compiled, trace)
        compiled = sc.insert_containment_target_check(compiled)
        compiled = sc.insert_containment_confirm(compiled)
    compiled = sc.attach_containment_mock_result(compiled, trace)

    trigger_module = module or getattr(trace, "module", None) or None
    doc = sc.assemble_playbook(compiled, name=name, module=trigger_module)
    yaml_text = sc.to_yaml(doc)
    trace.last_build_yaml = yaml_text

    compile_summary: dict[str, Any]
    try:
        from fsr_playbooks.compiler import compile_yaml as _compile

        from . import _shared
        result = _compile(yaml_text, _shared.DB_PATH)
        if result.ok:
            coll = (result.compiled_json().get("data") or [{}])[0]
            workflows = coll.get("workflows") or []
            compile_summary = {"ok": True, "workflows": len(workflows),
                               "steps": sum(len(w.get("steps") or [])
                                            for w in workflows)}
        else:
            from .tools_compile import _serialize_compiler_error
            compile_summary = {"ok": False,
                               "errors": [_serialize_compiler_error(e)
                                          for e in result.errors]}
    except ImportError as exc:  # noqa: BLE001
        compile_summary = {"ok": False, "errors": [str(exc)]}

    # A plan that compiles to YAML the compiler then rejects is not a success:
    # report it as one failure with the error text, yaml attached, instead of
    # `ok: true` with the real verdict buried in compile_summary.
    hard = [e for e in compile_summary.get("errors") or []
            if not isinstance(e, dict) or e.get("severity", "error") == "error"]
    ok = bool(compile_summary.get("ok")) or not hard
    extra: dict[str, Any] = {}
    if not ok:
        extra = {"code": "compile_failed",
                 "errors": [(f"{e.get('path', '')}: {e.get('message', '')}"
                             if isinstance(e, dict) else str(e))
                            for e in hard]}
        extra["message"] = "; ".join(extra["errors"])

    return {
        "ok": ok,
        **extra,
        "yaml": yaml_text,
        "compile_summary": compile_summary,
        "verified": compiled.get("verified", {}),
        "gaps": compiled.get("gaps", {}),
        "repaired": compiled.get("repaired", {}),
        # Params dropped because they are hidden until a gating selector is set
        # (e.g. fortigate block_ip_new hides `ip_addresses` until `method` is
        # chosen). Surfaced, never silent: add the selector to the plan and
        # compose again. get_op_schema shows the "when X = ..." groups.
        "pruned": compiled.get("pruned", {}),
        "static_errors": compiled.get("static_errors", []),
    }


compose_playbook.__doc__ = _COMPOSE_DOC.replace("{RECORD_SHAPES}",
                                                _record_shape_doc())
compose_playbook = mcp.tool()(compose_playbook)
