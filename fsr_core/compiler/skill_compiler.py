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
_SKIP_PARAMS = frozenset({"connector", "operation", "config"})


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


# Embedded (substring) wiring is riskier than whole-value match, so it is
# stricter: the prior-output scalar must be longer AND IOC-shaped (carry a digit
# or a `.`/`:`/`/` separator). That targets IPs/domains/hashes/CVEs embedded in
# query strings (`srcIpAddr = <ip>`) while excluding plain words like "Germany"
# that coincide across unrelated steps.
_MIN_EMBED_LEN = 7


def _looks_structured(s: str) -> bool:
    """IOC-ish: has a digit or a separator that plain prose words don't."""
    return any(c.isdigit() for c in s) or any(c in s for c in ".:/")


def _key_access(k: str) -> str:
    """Jinja key access; bracket-quote keys that aren't bare-identifier safe
    (e.g. `hydra:member`)."""
    if k.isidentifier():
        return f".{k}"
    return f"[{k!r}]"


def _find_value_path(output: Any, target: Any) -> Optional[str]:
    """Return a jinja access suffix (e.g. `.attributes.ip` or
    `['hydra:member'][0].ip`) into `output` whose leaf equals `target`, or
    None. Depth-first; returns the first (shallowest-leftmost) match."""
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


def _embeddable_scalars(output: Any) -> List[Tuple[str, str]]:
    """`(scalar, path)` for distinctive, IOC-shaped string leaves of an output —
    the candidates for embedded (substring) wiring."""
    found: List[Tuple[str, str]] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, str):
            if len(node.strip()) >= _MIN_EMBED_LEN and _looks_structured(node):
                found.append((node, path))
        elif isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str):
                    _walk(v, path + _key_access(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{path}[{i}]")

    _walk(output, "")
    return found


def _embedded_spans(value: str, scalar: str) -> List[Tuple[int, int]]:
    """All non-overlapping bounded-token spans of `scalar` in `value`. Each must
    be flanked by non-alphanumeric chars so we never wire a partial IOC
    (`1.2.3.4` inside `1.2.3.40`). `scalar == value` (a whole-value match,
    handled elsewhere) yields nothing. Returns every occurrence so a bidirectional
    hunt (`srcIpAddr = X OR destIpAddr = X`) wires BOTH, not just the first."""
    if scalar == value or not scalar:
        return []
    spans: List[Tuple[int, int]] = []
    start = 0
    while True:
        idx = value.find(scalar, start)
        if idx < 0:
            break
        end = idx + len(scalar)
        before = value[idx - 1] if idx > 0 else ""
        after = value[end] if end < len(value) else ""
        if not (before.isalnum() or after.isalnum()):
            spans.append((idx, end))
        start = end
    return spans


def _apply_spans(value: str, repls: List[Tuple[int, int, str]]) -> str:
    """Rewrite `value`, replacing each `(start, end, text)` span. Spans are
    applied left-to-right; overlapping spans (a later one starting before the
    previous ended) are dropped so the longest/earliest wins."""
    out: List[str] = []
    last = 0
    for start, end, text in sorted(repls, key=lambda r: (r[0], -(r[1] - r[0]))):
        if start < last:
            continue
        out.append(value[last:start])
        out.append(text)
        last = end
    out.append(value[last:])
    return "".join(out)


def _embedded_substitution(value: str, prior: List["SkillCall"]) -> Optional[str]:
    """If distinctive prior-output scalars appear as bounded tokens INSIDE the
    string `value` (e.g. the IP in `srcIpAddr = 1.2.3.4`), return `value` with
    EVERY such occurrence replaced by its `{{ vars.steps... }}` ref so the param
    is re-runnable, else None. Whole-value matches are handled by the caller;
    closest producer wins on overlap."""
    repls: List[Tuple[int, int, str]] = []
    for src in reversed(prior):           # closest producer first (stable on ties)
        for scalar, path in _embeddable_scalars(src.observed_output):
            ref = _ref_for(src, path)
            for span in _embedded_spans(value, scalar):
                repls.append((span[0], span[1], ref))
    if not repls:
        return None
    return _apply_spans(value, repls)


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
            # Whole-value match failed; for a string param, try wiring an
            # IOC-shaped value EMBEDDED in it (e.g. the IP in a SIEM query
            # `srcIpAddr = <ip>`) so a trace-built hunt is re-runnable instead
            # of baking the IOC in as a literal.
            sub = (_embedded_substitution(value, prior)
                   if isinstance(value, str) else None)
            if sub is not None:
                wired[param] = sub
            else:
                unwired.append(param)
    return wired, unwired


# Step name of the synthetic input-staging step that reads the trigger record.
_SET_INPUTS_STEP = "Set Inputs"


def _step_param_container(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The dict that holds a step's wirable params: `arguments` for connector
    steps, `vars` for set_variable. Returns None for step types with no
    param map to rewrite."""
    if step.get("type") == "connector":
        return step.get("arguments")
    if step.get("type") == "set_variable":
        return step.get("vars")
    return None


def _safe_var_name(param: str, used: set) -> str:
    """A jinja-safe, unique set_variable key derived from a param name."""
    base = "".join(c if (c.isalnum() or c == "_") else "_" for c in param) or "input"
    if base[0].isdigit():
        base = "v_" + base
    name, i = base, 2
    while name in used:
        name = f"{base}_{i}"
        i += 1
    used.add(name)
    return name


def wire_record_inputs(
    steps: List[Dict[str, Any]],
    gaps: Dict[str, List[str]],
    record_fields: Optional[Dict[str, Any]],
    first_step: Optional[str],
) -> Tuple[Dict[str, str], List[str], Optional[str]]:
    """Parameterize one-off triage IOCs to the trigger record.

    For every gap param (a value with no earlier producer that would
    otherwise bake in as a literal), value-match its literal against the
    triaged record's `record_fields`. On a hit at field path ``<suffix>``,
    stage it on a synthetic ``Set Inputs`` ``set_variable`` step as
    ``{{ vars.input.records[0]<suffix> }}`` and rewrite the consuming step's
    param to ``{{ vars.steps.Set_Inputs.<var> }}``. The same literal reuses
    one staged var (so two steps enriching the same IOC share it).

    Caller guarantees a per-record (module-bound) trigger so
    ``vars.input.records[0]`` resolves at runtime. Returns
    ``(record_vars, steps, first_step)`` — ``steps`` gains the Set Inputs
    step at the front and ``first_step`` becomes ``"Set Inputs"`` when any
    IOC was parameterized; otherwise all three are returned unchanged.
    Mutates `gaps` in place (matched params are removed)."""
    if not record_fields:
        return {}, steps, first_step
    by_name = {s.get("name"): s for s in steps}
    record_vars: Dict[str, str] = {}
    used_vars: set = set()
    val_to_var: Dict[Any, str] = {}

    for sname, params in list(gaps.items()):
        step = by_name.get(sname)
        container = _step_param_container(step) if step else None
        if container is None:
            continue
        remaining: List[str] = []
        for param in params:
            literal = container.get(param)
            suffix = (_find_value_path(record_fields, literal)
                      if _is_wirable_value(literal) else None)
            # Embedded fallback: an IOC-shaped record-field value sitting INSIDE
            # a query string (`srcIpAddr = <alert_ip>`) parameterizes too, so a
            # trace-built hunt re-runs on the triggering record's IOC. All
            # occurrences are replaced (bidirectional `src… OR dst…` hunts).
            embed_spans: List[Tuple[int, int]] = []
            if suffix is None and isinstance(literal, str):
                for fval, fsuffix in _embeddable_scalars(record_fields):
                    embed_spans = _embedded_spans(literal, fval)
                    if embed_spans:
                        suffix = fsuffix
                        break
            if suffix is None:
                remaining.append(param)
                continue
            key = (type(literal), literal, suffix)
            var = val_to_var.get(key)
            if var is None:
                var = _safe_var_name(param, used_vars)
                val_to_var[key] = var
                record_vars[var] = "{{ vars.input.records[0]" + suffix + " }}"
            staged = "{{ vars.steps." + _jkey(_SET_INPUTS_STEP) + "." + var + " }}"
            if embed_spans:
                container[param] = _apply_spans(
                    literal, [(s, e, staged) for s, e in embed_spans])
            else:
                container[param] = staged
        if remaining:
            gaps[sname] = remaining
        else:
            del gaps[sname]

    if not record_vars:
        return {}, steps, first_step
    set_inputs = {"type": "set_variable", "name": _SET_INPUTS_STEP,
                  "vars": record_vars}
    if first_step:
        set_inputs["next"] = first_step
    return record_vars, [set_inputs] + steps, _SET_INPUTS_STEP


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
    module: Optional[str] = None,
) -> Dict[str, Any]:
    """Wrap the compiled steps into a full playbook doc (a `start` trigger
    that points at the first real step, then the value-matched steps).

    When `module` is given (the module the investigation ran on — e.g.
    ``alerts`` / ``incidents``), the start trigger is bound to that module
    so it resolves to a manual Execute-menu trigger (``cybersponse.action``)
    on the module's record listing, NOT a designer-only Referenced trigger
    (``cybersponse.abstract_trigger``, the bare-`start` default). Playbooks
    authored from a triage session should run from the record they triage."""
    start = compiled.get("start_step", "Start")
    first = compiled.get("first_step")
    steps: List[Dict[str, Any]] = []
    if first:
        start_step: Dict[str, Any] = {"type": "start", "name": start, "next": first}
        if module:
            start_step["module"] = module
        steps.append(start_step)
    steps.extend(compiled.get("steps", []))
    return {
        "collection": collection,
        "playbooks": [{
            "name": name,
            "trigger": trigger,
            # Ship enabled: a playbook compiled from a triage session is meant to
            # run the next time the pattern shows up, so it imports as Active
            # (isActive=true) rather than a disabled draft the analyst has to
            # remember to toggle on.
            "is_active": True,
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


def _source_step_of(ref: str, jkey_to_name: Dict[str, str]) -> Optional[str]:
    """Recover the human step name a wire reads from (e.g.
    `{{ vars.steps.Enrich_Indicator.data.x }}` -> `Enrich Indicator`).
    Matches the `vars.steps.<jkey>` segment against actual trace step
    names so underscores inside a real name don't get clobbered."""
    import re
    m = re.search(r"vars\.steps\.([A-Za-z0-9_]+)", ref or "")
    if not m:
        return None
    return jkey_to_name.get(m.group(1))


def _wiring_label(wired: Dict[str, str], gaps: List[str],
                  jkey_to_name: Dict[str, str]) -> str:
    """Plain-English wiring summary for the reviewable-draft card (contract
    §5, 2.6.0) — never raw jinja. Surfaces gaps as an explicit confirm-me."""
    parts: List[str] = []
    for param, ref in wired.items():
        src = _source_step_of(ref, jkey_to_name)
        parts.append(f"{param} from {src}" if src else param)
    if parts:
        label = "uses " + "; ".join(parts)
        if gaps:
            label += f" — {', '.join(gaps)} needs confirming"
        return label
    if gaps:
        return f"{', '.join(gaps)} could not be auto-wired — confirm before run"
    return "uses fixed values"


def summarize_for_offer(
    trace: SkillTrace, compiled: Dict[str, Any]
) -> Dict[str, Any]:
    """Build the contract v2.6.0 reviewable-draft fields (`ops_summary` +
    `draft_steps`) from a compiled trace. Pure, no MCP/IO — the
    `emit_playbook_offer` tool calls this so per-step wiring labels and
    verify badges are derived from the SAME deterministic compile the push
    uses, never hand-written by the model.

    `verified` is true for a step with no remaining gaps (every input was
    auto-wired or is a fixed literal and survived the §4 verify loop);
    false flags a step whose value fell back to a manual gap.
    """
    wiring = compiled.get("wiring", {})
    gaps = compiled.get("gaps", {})
    jkey_to_name = {_jkey(c.step_name): c.step_name for c in trace.calls}

    ops_summary: List[Dict[str, Any]] = []
    draft_steps: List[Dict[str, Any]] = []
    for call in trace.calls:
        skill = get_skill(call.skill_id)
        if skill is None:
            continue
        name = call.step_name
        step_gaps = gaps.get(name, [])
        verified = not step_gaps
        ri = call.resolved_inputs or {}
        entry: Dict[str, Any] = {
            "skill_id": call.skill_id,
            "step_type": skill.step_type,
            "label": name,
            "wiring_label": _wiring_label(
                wiring.get(name, {}), step_gaps, jkey_to_name),
            "verified": verified,
        }
        connector = ri.get("connector") or skill.needs.get("connector")
        operation = ri.get("operation") or skill.needs.get("op")
        if connector:
            entry["connector"] = connector
        if operation:
            entry["operation"] = operation
        ops_summary.append(entry)
        draft_steps.append(
            {"node": name, "step_type": skill.step_type, "verified": verified})

    return {"ops_summary": ops_summary, "draft_steps": draft_steps}
