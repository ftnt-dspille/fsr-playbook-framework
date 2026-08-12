"""Verify/repair the value-match wiring (SKILL_BASED_PLAYBOOK_PLAN §4).

The compiler (§3) produces *candidate* wiring. This pass proves each wire
before push, reusing the tools we already have rather than inventing a new
validator:

1. **Resolve check** -- render every wired ref against the captured outputs
   (`skill_compiler.render_context`, keyed exactly like FSR runtime). A ref
   that doesn't evaluate to a defined value is a bad wire. Offline this
   uses a local StrictUndefined Jinja2 env; a caller with a live FSR engine
   can inject `render_fn=render_jinja` for stronger, runtime-identical
   evidence.
2. **Static check** -- assemble the playbook and run the existing
   `parser.parse_yaml` + `validator.validate` (which calls
   `_check_jinja_paths`): undefined-reference / DAG-ordering detection
   across the step graph, no new code.

**Repair:** a ref that fails the resolve check is demoted back to its
original literal (from the SkillCall) and the param is recorded as a gap,
so the step keeps a value and the analyst sees an amber field instead of a
dangling reference shipping silently.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..agent.skill_trace import SkillTrace
from . import skill_compiler as sc
from .skills import get_skill

# A render function: (template, context) -> {"output": value} | {"error": str}.
# Defaults to the local engine; the live `tools_jinja.render_jinja` is
# signature-compatible (its extra args are optional).
RenderFn = Callable[..., dict[str, Any]]


def _local_render(template: str, context: dict[str, Any] | None = None,
                  **_ignore: Any) -> dict[str, Any]:
    """Offline Jinja render with StrictUndefined so a missing path raises
    rather than silently rendering empty -- that strictness is the point:
    a wire that doesn't resolve must surface, not pass."""
    try:
        from jinja2 import Environment, StrictUndefined
        from jinja2.exceptions import TemplateError, UndefinedError
    except ImportError:  # pragma: no cover - jinja2 is a runtime dep
        return {"error": "jinja2 not available"}
    env = Environment(undefined=StrictUndefined,
                      extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])
    try:
        out = env.from_string(template).render(**(context or {}))
        return {"output": out}
    except (UndefinedError, TemplateError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - any eval failure = bad wire
        return {"error": str(exc)}


def verify_wire(ref: str, context: dict[str, Any],
                render_fn: RenderFn | None = None) -> bool:
    """True iff `ref` renders to a defined, non-empty value against
    `context`."""
    fn = render_fn or _local_render
    res = fn(ref, context)
    if not isinstance(res, dict) or "error" in res:
        return False
    out = res.get("output")
    # StrictUndefined would have raised; an empty string still means the
    # path produced nothing useful for a wire.
    return out is not None and out != ""


def _static_path_errors(steps: list[dict[str, Any]], first_step: str | None,
                        start_step: str) -> list[str]:
    """Reuse parser + validator to surface undefined/unreachable jinja refs
    across the assembled step graph. Returns human-readable messages for
    the jinja-path diagnostics only."""
    import yaml

    from .parser import parse_yaml
    from .validator import validate

    doc = {
        "collection": "00 - FSR Studio",
        "playbooks": [{
            "name": "Skill Verify",
            "trigger": "start",
            "steps": [{"type": "start", "name": start_step,
                       "next": first_step}] + steps if first_step else steps,
        }],
    }
    coll, perrs = parse_yaml(yaml.safe_dump(doc, sort_keys=False))
    msgs: list[str] = [
        e.message for e in perrs
        if getattr(e, "severity", "error") != "warning"
    ]
    if coll is not None:
        for e in validate(coll):
            if getattr(e, "severity", "error") == "warning":
                continue
            # Keep only references diagnostics (vars.steps undefined / DAG).
            if "vars.steps" in e.message or "step" in e.message.lower():
                msgs.append(e.message)
    return msgs


def compile_and_verify(
    trace: SkillTrace, *, render_fn: RenderFn | None = None,
    start_step: str = "Start",
) -> dict[str, Any]:
    """Compile the trace, verify each wire, repair the failures, and run the
    static path check on the repaired graph.

    Returns the §3 compile dict enriched with:
      - `verified`: {step_name: {param: bool}} -- resolve-check result.
      - `repaired`: {step_name: [param,...]} -- wires demoted to literals.
      - `static_errors`: [str] -- undefined/unreachable refs after repair.
      - `gaps` now also includes any repaired (un-wirable) params.
    """
    compiled = sc.compile_trace(trace, start_step=start_step)
    # Position of each call so a step only renders against EARLIER outputs.
    pos = {c.step_name: i for i, c in enumerate(trace.calls)}

    verified: dict[str, dict[str, bool]] = {}
    repaired: dict[str, list[str]] = {}

    for name, wired in list(compiled["wiring"].items()):
        ctx = sc.render_context(trace, upto=pos.get(name, len(trace.calls)))
        good: dict[str, str] = {}
        for param, ref in wired.items():
            ok = verify_wire(ref, ctx, render_fn)
            verified.setdefault(name, {})[param] = ok
            if ok:
                good[param] = ref
            else:
                repaired.setdefault(name, []).append(param)
        if good:
            compiled["wiring"][name] = good
        else:
            del compiled["wiring"][name]

    # Re-emit steps with only the surviving wires; repaired params fall back
    # to the literal and join the gap list.
    #
    # This rebuilds each step from `call.resolved_inputs`, which means it
    # DISCARDS everything compile_trace did to the step dicts it produced --
    # including the hidden-param prune. That silently un-did the prune on the
    # only path that matters: compile_trace pruned, and then these fresh steps
    # overwrote the result, so the live block_ip_new trace kept both branches
    # of its conditional and P4 produced no playbook. Two releases were cut
    # against the wrong suspect (the step SHAPE) because the unit tests drove
    # compile_trace directly and never came through here. So re-prune the
    # re-emitted steps, and keep `pruned` reporting what actually survived.
    rules_for = compiled.pop("_rules_for", None) or sc._rules_lookup()
    new_steps: list[dict[str, Any]] = []
    calls = trace.calls
    for i, call in enumerate(calls):
        skill = get_skill(call.skill_id)
        if skill is None:
            continue
        wired = compiled["wiring"].get(call.step_name, {})
        step = skill.compile(call.resolved_inputs, wired, call.step_name)
        dropped = sc.prune_hidden_params(step, rules_for)
        if dropped:
            compiled.setdefault("pruned", {})[call.step_name] = dropped
        nxt = calls[i + 1].step_name if i + 1 < len(calls) else None
        if nxt:
            step["next"] = nxt
        new_steps.append(step)
    compiled["steps"] = new_steps

    for name, params in repaired.items():
        gap = compiled["gaps"].setdefault(name, [])
        for p in params:
            if p not in gap:
                gap.append(p)

    # Parameterize one-off triage IOCs to the trigger record. Only when the
    # playbook is module-bound (a per-record manual trigger) does
    # vars.input.records[0] resolve at runtime, so gate on trace.module.
    # Runs after repair so it can rescue values that fell back to literals too.
    record_vars: dict[str, str] = {}
    if getattr(trace, "module", None) and getattr(trace, "record_fields", None):
        record_vars, compiled["steps"], compiled["first_step"] = \
            sc.wire_record_inputs(compiled["steps"], compiled["gaps"],
                                  trace.record_fields, compiled.get("first_step"))
    compiled["record_vars"] = record_vars

    compiled["verified"] = verified
    compiled["repaired"] = repaired
    compiled["static_errors"] = _static_path_errors(
        compiled["steps"], compiled.get("first_step"), start_step
    )
    return compiled
