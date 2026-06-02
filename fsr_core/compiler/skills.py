"""Skill descriptors — typed, tested playbook-block templates.

A **skill** is a typed playbook-block descriptor: an `id`, the FSR step
type it compiles to, an optional `(connector, op)` binding, an input
schema, and a `compile()` hook that emits a canonical YAML *source-form*
step dict (the same shape `compiler.parser` consumes — not the resolved
FSR JSON). The session→YAML compiler records each executed action as a
`SkillCall` and compiles the **typed trace** instead of the prose
transcript, recovering step wiring by static value-match over captured
outputs rather than by the model guessing jinja paths.

See `docs/plans/SKILL_BASED_PLAYBOOK_PLAN.md` §1. This module is the
Phase-1 registry: pure descriptors, no behavior change. The trace
recorder (§2) and the trace compiler (§3) consume it.

Hard rule (§1, non-negotiable): **1 skill ↔ 1 FSR step type.** A skill
that spans more than one step type breaks the 1:1 compile and is
rejected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Descriptor schema
# ---------------------------------------------------------------------------


@dataclass
class ParamSpec:
    """One input parameter of a skill.

    `jinja_bindable` marks a param whose literal value may be replaced by
    a `{{ vars.steps.<source>.<path> }}` reference during value-match
    wiring (§3). `required` params with neither a literal nor a wire are
    a compile-time gap (surfaced as a `set_variable`/`manual_input`).
    """
    type: str = "string"
    jinja_bindable: bool = True
    required: bool = False


# A compile hook turns the resolved inputs + wired references into a
# single YAML source-form step dict. `wired_refs` maps a param name to a
# jinja expression string that *overrides* the literal in
# `resolved_inputs` (the value-match wiring result). The hook must emit
# exactly one step (the 1:1 rule).
CompileHook = Callable[[Dict[str, Any], Dict[str, str], str], Dict[str, Any]]


@dataclass
class Skill:
    id: str
    step_type: str                       # YAML source `type:` (one of the 21 FSR step types)
    compile: CompileHook
    needs: Dict[str, Optional[str]] = field(default_factory=dict)   # {connector?, op?}
    input_schema: Dict[str, ParamSpec] = field(default_factory=dict)
    description: str = ""

    def required_params(self) -> List[str]:
        return [k for k, s in self.input_schema.items() if s.required]

    def bindable_params(self) -> List[str]:
        return [k for k, s in self.input_schema.items() if s.jinja_bindable]


# ---------------------------------------------------------------------------
# compile() hooks — emit YAML source-form step dicts
# ---------------------------------------------------------------------------
#
# Each hook returns the *authoring* shape (what a human would write in
# the .yaml), which `compiler.parser` already understands — NOT the
# resolved FSR JSON. This keeps skills decoupled from the resolver and
# means every emitted step flows through the same validate path as a
# hand-authored one.


def _apply_wires(inputs: Dict[str, Any], wired_refs: Dict[str, str]) -> Dict[str, Any]:
    """Overlay value-match jinja wires onto the resolved literals."""
    merged = dict(inputs)
    for param, ref in (wired_refs or {}).items():
        merged[param] = ref
    return merged


def _compile_run_connector_action(
    inputs: Dict[str, Any], wired_refs: Dict[str, str], step_name: str
) -> Dict[str, Any]:
    """RunConnectorAction. `inputs` carries `connector`, `operation`, and
    the op params; wired params have their literal swapped for a jinja
    ref. Emits the canonical `type: connector` step with everything under
    `arguments:` (the wire shape the resolver expects)."""
    merged = _apply_wires(inputs, wired_refs)
    connector = merged.pop("connector", None)
    operation = merged.pop("operation", None)
    # The config id run_op resolved at execution time (recorded on the trace),
    # so the step runs against the same configuration the agent used. Carried
    # at the step level, not as an op param.
    config = merged.pop("config", None)
    # The FortiSOAR Agent id when run_op routed the op through an agent
    # (agent-bound connectors). The step needs the agent binding alongside the
    # config id or the workflow engine can't reach the connector.
    agent = merged.pop("agent", None)
    arguments: Dict[str, Any] = {}
    if connector is not None:
        arguments["connector"] = connector
    if operation is not None:
        arguments["operation"] = operation
    if config is not None:
        arguments["config"] = config
    if agent:
        arguments["agent"] = agent
    # Remaining keys are the op params.
    for k, v in merged.items():
        arguments[k] = v
    return {"type": "connector", "name": step_name, "arguments": arguments}


def _compile_set_variable(
    inputs: Dict[str, Any], wired_refs: Dict[str, str], step_name: str
) -> Dict[str, Any]:
    """SetVariable. `inputs` is the name→value mapping to stage; wired
    values become jinja refs. Emits the top-level `vars:` form (no
    `arguments:` — the parser rejects that for set_variable)."""
    merged = _apply_wires(inputs, wired_refs)
    return {"type": "set_variable", "name": step_name, "vars": dict(merged)}


def _compile_manual_input(
    inputs: Dict[str, Any], wired_refs: Dict[str, str], step_name: str
) -> Dict[str, Any]:
    """ManualTask. Two modes (§1):

    - extra-input form: `inputs.fields` → emitted as-is for the form.
    - yes/no confirmation that routes: `inputs.options` (a list of
      `{display, next}`) renders the fork whose answer a following
      `decision` consumes.

    `message`/`question` is the prompt text. Manual input never wires its
    own params from prior outputs, so `wired_refs` is unused here."""
    step: Dict[str, Any] = {"type": "manual_input", "name": step_name}
    msg = inputs.get("message") or inputs.get("question")
    if msg:
        step["message"] = msg
    options = inputs.get("options")
    if isinstance(options, list) and options:
        step["options"] = options
    fields = inputs.get("fields")
    if isinstance(fields, list) and fields:
        step["fields"] = fields
    return step


def _compile_decision(
    inputs: Dict[str, Any], wired_refs: Dict[str, str], step_name: str
) -> Dict[str, Any]:
    """Decision (branch). Branch conditions come from the recorded
    `choice`/`capability_gap`/manual-input `value`s, so branch logic is
    preserved rather than flattened (§3). `inputs.conditions` is a list of
    `{display, when, next}`; `inputs.default` is the else target step
    name. Emits the step-level `conditions:`/`default:` source form."""
    step: Dict[str, Any] = {"type": "decision", "name": step_name}
    conditions = inputs.get("conditions")
    if isinstance(conditions, list) and conditions:
        step["conditions"] = conditions
    default = inputs.get("default")
    if isinstance(default, str) and default.strip():
        step["default"] = default.strip()
    return step


# ---------------------------------------------------------------------------
# Registry — the four demo-core skills (§1)
# ---------------------------------------------------------------------------


_REGISTRY: Dict[str, Skill] = {}


def register(skill: Skill) -> Skill:
    """Add a skill to the registry, enforcing the 1:1 step-type rule and
    unique ids."""
    if not skill.step_type:
        raise ValueError(f"skill {skill.id!r} has no step_type (1 skill ↔ 1 step type)")
    if skill.id in _REGISTRY:
        raise ValueError(f"duplicate skill id {skill.id!r}")
    _REGISTRY[skill.id] = skill
    return skill


register(Skill(
    id="run_connector_action",
    step_type="connector",
    compile=_compile_run_connector_action,
    needs={"connector": None, "op": None},
    input_schema={
        "connector": ParamSpec(type="string", jinja_bindable=False, required=True),
        "operation": ParamSpec(type="string", jinja_bindable=False, required=True),
    },
    description=(
        "The real work — maps 1:1 to a run_op call's I/O. Parameterized by "
        "get_op_schema (input) and the observed run_op output (output), so "
        "the connector long tail is covered by one generic skill."
    ),
))

register(Skill(
    id="set_variable",
    step_type="set_variable",
    compile=_compile_set_variable,
    input_schema={},   # dynamic name→value mapping; no fixed params
    description="Stage/normalize a value for downstream steps.",
))

register(Skill(
    id="manual_input",
    step_type="manual_input",
    compile=_compile_manual_input,
    input_schema={
        "message": ParamSpec(type="string", jinja_bindable=False, required=False),
        "options": ParamSpec(type="list", jinja_bindable=False, required=False),
        "fields": ParamSpec(type="list", jinja_bindable=False, required=False),
    },
    description=(
        "Collect extra input the playbook needs, or a yes/no confirmation "
        "whose answer a following decision step consumes to fork the playbook."
    ),
))

register(Skill(
    id="decision",
    step_type="decision",
    compile=_compile_decision,
    input_schema={
        "conditions": ParamSpec(type="list", jinja_bindable=False, required=True),
        "default": ParamSpec(type="string", jinja_bindable=False, required=False),
    },
    description="Route on a true/false condition over prior outputs.",
))


# ---------------------------------------------------------------------------
# Lookup API
# ---------------------------------------------------------------------------


def get_skill(skill_id: str) -> Optional[Skill]:
    return _REGISTRY.get(skill_id)


def all_skills() -> Dict[str, Skill]:
    return dict(_REGISTRY)


def skill_for_step_type(step_type: str) -> Optional[Skill]:
    """First registered skill compiling to `step_type` (the demo-core set
    is 1:1, so this is unambiguous)."""
    for skill in _REGISTRY.values():
        if skill.step_type == step_type:
            return skill
    return None
