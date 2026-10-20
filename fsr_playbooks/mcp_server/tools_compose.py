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

from typing import Any

from ._shared import mcp

# plan `kind` -> the compiler skill id it maps to.
_KIND_TO_SKILL = {
    "connector": "run_connector_action",
    "decision": "decision",
    "manual_input": "manual_input",
    "set_variable": "set_variable",
}
# The connector envelope defaults to `.data` (get_op_schema's binding rule); the
# other skills publish their outputs at the step root.
_DEFAULT_REF_PREFIX = {"connector": "data"}


def _jkey(step_name: str) -> str:
    return (step_name or "").replace(" ", "_")


# The trigger record is referenced through the playbook input, not a step.
_INPUT_STEP = "__input__"


def _wire_ref(from_step: str, output: str, ref_prefix: str) -> str:
    """A cross-step reference the author declared structurally, rendered to the
    one correct jinja path -- the error-prone part the model no longer types.

    `from_step == "__input__"` means a field of the triggering record, which
    lives at `vars.input.records[0].<field>`, not under a step."""
    path = (output or "").strip()
    if from_step == _INPUT_STEP:
        base = "vars.input.records[0]"
    else:
        base = f"vars.steps.{_jkey(from_step)}"
        if ref_prefix:
            base += f".{ref_prefix}"
    if path and not path.startswith(("[", ".")):
        path = "." + path
    return "{{ " + base + path + " }}"


def _resolve_inputs(raw: dict[str, Any],
                    ref_prefix_by_step: dict[str, str]) -> dict[str, Any]:
    """Pass literals through; translate a `{from_step, output}` ref to jinja."""
    out: dict[str, Any] = {}
    for key, val in (raw or {}).items():
        if isinstance(val, dict) and "from_step" in val:
            src = str(val.get("from_step") or "")
            out[key] = _wire_ref(src, str(val.get("output") or ""),
                                 ref_prefix_by_step.get(src, "data"))
        else:
            out[key] = val
    return out


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
        skill_id = _KIND_TO_SKILL.get(kind)
        if not skill_id:
            errors.append(f"step {i} ({name!r}): unknown kind {kind!r}; "
                          f"use one of {sorted(_KIND_TO_SKILL)}")
            continue
        ref_prefix = _DEFAULT_REF_PREFIX.get(kind, "")
        ref_prefix_by_step[name] = ref_prefix

        if kind == "connector":
            inputs = dict(step.get("inputs") or {})
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
            resolved = _resolve_inputs(dict(step.get("values") or {}),
                                       ref_prefix_by_step)

        for_each = None
        raw_fe = step.get("for_each")
        if isinstance(raw_fe, dict) and raw_fe:
            if kind not in ("connector", "set_variable"):
                errors.append(f"step {i} ({name!r}): for_each loops a connector "
                              "or set_variable step, not a "
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


@mcp.tool()
def compose_playbook(steps: list[dict[str, Any]],
                     name: str = "New Playbook",
                     module: str = "",
                     guard_containment: bool = True) -> dict[str, Any]:
    """Build a playbook from a typed plan -- you declare the steps, this writes
    and verifies the YAML. Do NOT hand-author YAML when you can use this.

    `steps` is the ordered plan, each a small object with a `kind` and a `name`:
      - `connector`: `{kind, name, connector, operation, inputs?}` -- `inputs`
        maps each parameter to a literal, or to `{from_step, output}` to read an
        earlier step's output (this writes the correct `vars.steps...` path for
        you; never type jinja yourself).
      - `decision`: `{kind, name, conditions, default?}` -- route on conditions
        over earlier outputs.
      - `manual_input`: `{kind, name, message?, options?, fields?}` -- a human
        confirmation or extra input a following decision consumes.
      - `set_variable`: `{kind, name, values}` -- stage/normalize values.
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
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "code": "no_steps",
                "message": "pass a non-empty ordered list of plan steps"}

    from fsr_playbooks.compiler import skill_compiler as sc
    from fsr_playbooks.compiler import skill_verify as sv

    trace, errors = _plan_to_trace(steps, module)
    if errors:
        return {"ok": False, "code": "bad_plan", "errors": errors}
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

    return {
        "ok": True,
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
