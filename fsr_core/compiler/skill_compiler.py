"""Trace → YAML compiler — wire a playbook from the typed action trace.

Consumes a `SkillTrace` (the SkillCalls the agent executed during triage,
SKILL_BASED_PLAYBOOK_PLAN §2) and emits FSRPB YAML by **value-match over
captured outputs** (§3) instead of the model guessing jinja paths:

1. Emit one candidate step per SkillCall via the Phase-1 skill `compile()`
   hooks, chained in trace (dependency) order.
2. For each step's input args, scan *earlier* SkillCalls' `observed_output`
   for the same value and back-derive a jinja path, replacing the literal
   with `{{ vars.steps.<source>[.data].<path> }}`.
3. The first occurrence of a one-off triage value (no earlier producer) is
   left as a literal here; parameterizing it into a playbook input is a
   later refinement. Branch preservation (decision steps from recorded
   choice/manual-input values) is wired by the caller, not value-match.

Value-match yields *candidate* wiring with possible false positives (a
literal that happens to equal a prior output). That is fine — §4 verifies
each wire with `render_jinja`/`step_through_playbook` against the same
captured outputs before push. This module does the deterministic part;
verification is its own pass.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .skills import get_skill
from ..agent.skill_trace import SkillCall, SkillTrace


# A param value is only trusted for value-match if it is non-trivial — short
# ints, booleans, and tiny strings coincide across unrelated steps too often
# (port 443, True, "yes"). IOC-shaped / structured / long values are safe.
_MIN_STR_LEN = 4

# Params that are never wired (they identify the step, not its data).
_SKIP_PARAMS = frozenset({"connector", "operation"})


def _jkey(step_name: str) -> str:
    """FSR keys vars.steps.* off the step name with spaces→underscores."""
    return step_name.replace(" ", "_")


def _is_wirable_value(v: Any) -> bool:
    """Reject trivial values that would produce false-positive matches."""
    if isinstance(v, bool) or v is None:
        return False
    if isinstance(v, (int, float)):
        return False                       # numbers coincide too readily
    if isinstance(v, str):
        return len(v.strip()) >= _MIN_STR_LEN
    if isinstance(v, (dict, list)):
        return bool(v)                     # structured values are distinctive
    return False


def _find_value_path(output: Any, target: Any) -> Optional[str]:
    """Return a jinja access suffix (e.g. `.attributes.ip` or
    `['hydra:member'][0].ip`) into `output` whose leaf equals `target`, or
    None. Depth-first; returns the first (shallowest-leftmost) match."""
    # Bracket-quote keys that aren't bare-identifier safe (`hydra:member`).
    def _key_access(k: str) -> str:
        if k.isidentifier():
            return f".{k}"
        return f"[{k!r}]"

    def _walk(node: Any, path: str) -> Optional[str]:
        if node == target and type(node) == type(target):
            return path
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(k, str):
                    continue
                r = _walk(v, path + _key_access(k))
                if r is not None:
                    return r
        elif isinstance(node, list):
            for i, v in enumerate(node):
                r = _walk(v, f"{path}[{i}]")
                if r is not None:
                    return r
        return None

    return _walk(output, "")


def _ref_for(call: SkillCall, suffix: str) -> str:
    """Build the full jinja reference into a prior step's output."""
    base = f"vars.steps.{_jkey(call.step_name)}"
    if call.ref_prefix:
        base += f".{call.ref_prefix}"
    return "{{ " + base + suffix + " }}"


def wire_inputs(
    inputs: Dict[str, Any], prior: List[SkillCall]
) -> Tuple[Dict[str, str], List[str]]:
    """Value-match each wirable input against earlier observed outputs.

    Returns `(wired_refs, unwired)` where `wired_refs` maps a param to a
    `{{ vars.steps... }}` reference and `unwired` lists wirable params that
    found no producer (candidates for parameterize / set_variable / gap).
    """
    wired: Dict[str, str] = {}
    unwired: List[str] = []
    for param, value in inputs.items():
        if param in _SKIP_PARAMS or not _is_wirable_value(value):
            continue
        matched = False
        # Most-recent producer first — closest dependency wins.
        for src in reversed(prior):
            suffix = _find_value_path(src.observed_output, value)
            if suffix is not None:
                wired[param] = _ref_for(src, suffix)
                matched = True
                break
        if not matched:
            unwired.append(param)
    return wired, unwired


def compile_trace(
    trace: SkillTrace, *, start_step: str = "Start"
) -> Dict[str, Any]:
    """Compile a SkillTrace into a list of candidate YAML source-form steps
    chained in trace order, with value-match wiring applied.

    Returns `{"steps": [...], "wiring": {step_name: {param: ref}}, "gaps":
    {step_name: [param,...]}}`. The caller assembles these into a playbook
    doc, then runs the §4 verify loop before push.
    """
    steps: List[Dict[str, Any]] = []
    wiring: Dict[str, Dict[str, str]] = {}
    gaps: Dict[str, List[str]] = {}

    calls = trace.calls
    for i, call in enumerate(calls):
        skill = get_skill(call.skill_id)
        if skill is None:
            continue
        wired, unwired = wire_inputs(call.resolved_inputs, calls[:i])
        step = skill.compile(call.resolved_inputs, wired, call.step_name)
        # Chain linearly in trace order (decision/branch rewires are the
        # caller's job; this is the dependency-ordered backbone).
        nxt = calls[i + 1].step_name if i + 1 < len(calls) else None
        if nxt:
            step["next"] = nxt
        steps.append(step)
        if wired:
            wiring[call.step_name] = wired
        if unwired:
            gaps[call.step_name] = unwired

    # Point the trigger at the first real step.
    first = calls[0].step_name if calls else None
    return {
        "steps": steps,
        "wiring": wiring,
        "gaps": gaps,
        "start_step": start_step,
        "first_step": first,
    }


def assemble_playbook(
    compiled: Dict[str, Any],
    *,
    name: str = "Triage Playbook",
    collection: str = "00 - FSR Studio",
    trigger: str = "start",
) -> Dict[str, Any]:
    """Wrap the compiled steps into a full playbook doc (a `start` trigger
    that points at the first real step, then the value-matched steps)."""
    start = compiled.get("start_step", "Start")
    first = compiled.get("first_step")
    steps: List[Dict[str, Any]] = []
    if first:
        steps.append({"type": "start", "name": start, "next": first})
    steps.extend(compiled.get("steps", []))
    return {
        "collection": collection,
        "playbooks": [{
            "name": name,
            "trigger": trigger,
            "steps": steps,
        }],
    }


def to_yaml(doc: Dict[str, Any]) -> str:
    """Canonical YAML emission (matches the decompiler's dumper)."""
    import yaml
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def render_context(trace: SkillTrace, upto: Optional[int] = None) -> Dict[str, Any]:
    """Build a `vars.steps.*` render context from captured outputs, keyed
    exactly as runtime (honoring `ref_prefix`), for the §4 verify loop.
    `upto` limits to the first N calls (a step only sees earlier outputs)."""
    calls = trace.calls if upto is None else trace.calls[:upto]
    steps_ctx: Dict[str, Any] = {}
    for call in calls:
        payload = call.observed_output
        if call.ref_prefix:
            payload = {call.ref_prefix: payload}
        steps_ctx[_jkey(call.step_name)] = payload
    return {"vars": {"steps": steps_ctx}}
