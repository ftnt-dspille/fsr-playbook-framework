"""Typed DAG walker for `verify_playbook`.

Treats a playbook as a typed program: at each step, synthesize the
*shape* of `vars.steps.<step>` from static sources, accumulate per
branch, then validate every downstream Jinja `vars.steps.<key>.<path>`
reference against the typed env on the branch where the reference
lives. Plan: VERIFY_PLAYBOOK_PLAN.md §"Architecture".

This module is offline-pure:
  - No MCP imports.
  - No live HTTP / DB calls of its own.
  - For connector_op shape synthesis the caller supplies a probe
    callback (or omits it; unsafe / un-probed ops degrade to
    `unknown_shape`).

The walker returns a list of branches, each with its own typed_env and
diagnostics, plus a flat list of per-branch issues using the
`Diagnostic` dataclass below (codes mirror plan §"Required-fix codes").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .ir import Collection, Playbook, Step
from .validator import _RESERVED_VARS_KEYS


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

# Shape is one of:
#   {"kind": "object", "keys": {<name>: Shape}}
#   {"kind": "list",   "item": Shape}
#   {"kind": "scalar", "type": "string"|"integer"|"boolean"|"any"}
#   {"kind": "unknown", "reason": str}
#   {"kind": "none"}                # step produces no output
Shape = dict[str, Any]


@dataclass
class Diagnostic:
    code: str
    message: str
    step: str = ""
    branch: str = ""
    path: str = ""               # YAML-ish path
    suggestion: Optional[str] = None
    severity: str = "error"      # "error" (required_fix) | "warning"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "message": self.message, "step": self.step,
            "branch": self.branch, "path": self.path,
            "suggestion": self.suggestion, "severity": self.severity,
        }


@dataclass
class BranchResult:
    name: str                              # human-readable branch label
    step_ids: list[str]                    # ordered along this branch
    typed_env: dict[str, Shape]            # vars.steps.<jinja_key> -> Shape
    var_env: dict[str, Shape] = field(default_factory=dict)  # vars.<name> -> Shape
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # Phase 5 — every connector-param source→target decision on this branch
    # (passes included), for the troubleshooting trace export.
    type_decisions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WalkResult:
    branches: list[BranchResult]
    diagnostics: list[Diagnostic]          # flat aggregate
    per_step_shapes: dict[str, Shape]      # last-known shape per step (debug)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branches": [
                {
                    "name": b.name,
                    "step_ids": b.step_ids,
                    "typed_env_keys": sorted(b.typed_env.keys()),
                    "var_env": {k: v for k, v in sorted(b.var_env.items())},
                    "diagnostics": [d.to_dict() for d in b.diagnostics],
                    "type_decisions": b.type_decisions,
                }
                for b in self.branches
            ],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


# Probe callback signature. Takes (connector, op, synthesized_inputs)
# and returns a Shape (or None to indicate "couldn't probe; fall back").
ProbeCallback = Callable[[str, str, dict[str, Any]], Optional[Shape]]


# Resolver hook for module field schemas. Takes module name → list of
# field-name strings. Optional; without it, record-shape steps degrade
# to {kind: object, keys: {}}.
ModuleFieldsFn = Callable[[str], list[str]]


# Resolver hook for "is this op safe?". Takes (connector, op) →
# 'safe' | 'unsafe' | 'unknown'. Optional; defaults to 'unknown'.
OpSafetyFn = Callable[[str, str], str]


# Resolver hook for a connector param's *target* type. Takes
# (connector, op, param) → a target tag ('int' | 'float' | 'bool' |
# 'json_object' | 'json_array' | 'ipv4' | 'url' | 'email' | 'iso8601' |
# 'ipv6' | …) or None when the param is untyped / picklist / unknown.
# Optional; without it Phase 4 source→target checking is skipped. The
# tag vocabulary mirrors the resolver's `_param_target_observed_type`.
ParamTypeFn = Callable[[str, str, str], Optional[str]]


# ---------------------------------------------------------------------------
# Phase 4 — source→target type comparison.
# STATIC_TYPE_FLOW_PLAN.md §"Phase 4". The half that knows *source* shapes
# (this walker) finally meets the half that knows *target* types (resolver,
# via ParamTypeFn). Two evidence-sound rules ship here:
#   (G2) shape-into-scalar: a list/object reference passed into a scalar
#        param is an unambiguous error (a list can't become an int/ipv4).
#   scalar↔scalar numeric/bool category crossings (e.g. a boolean var into
#        an integer param). String/any/null sources stay permissive because
#        FSR's runtime string coercion (the Phase 1b matrix) makes them
#        broadly acceptable, and the connector-param ingestion-coercion
#        matrix (Open Q #2) is not yet probed — so we never hard-error on a
#        case the runtime might coerce.
# ---------------------------------------------------------------------------

# Target tags that denote a single scalar value (not a JSON container /
# picklist). A list/object source into any of these is a hard mismatch.
_SCALAR_TARGET_TAGS = {
    "int", "float", "bool", "ipv4", "ipv6", "url", "email", "iso8601",
    "epoch_seconds", "epoch_millis",
}
_NUMERIC_TARGET_TAGS = {"int", "float"}


def _shape_to_src_tag(shape: Shape | None) -> str | None:
    """Collapse a source Shape into the tag vocabulary Phase 4 compares.

    Returns 'list' / 'dict' for structures, an 'int'/'float'/'bool'/'str'/
    'null' scalar tag, or None when the source is too vague to judge
    (scalar 'any', unknown, none) — None means "skip, don't guess"."""
    if not isinstance(shape, dict):
        return None
    kind = shape.get("kind")
    if kind == "list":
        return "list"
    if kind == "object":
        return "dict"
    if kind == "scalar":
        return {
            "integer": "int", "float": "float", "boolean": "bool",
            "string": "str", "null": "null",
        }.get(shape.get("type"))
    return None


def _source_target_compatible(src: str | None, tgt: str | None) -> bool:
    """True iff a source of tag `src` is acceptable for a param of tag `tgt`.

    Conservative by design: returns True whenever the runtime plausibly
    coerces, so a False is a confident bug. See the module-level note for
    why string/any/null sources are always tolerated."""
    if tgt is None or src is None:
        return True
    if src in {"any", "str", "null"}:
        return True
    # Structured sources: only a matching JSON container accepts them.
    if src == "list":
        return tgt == "json_array"
    if src == "dict":
        return tgt == "json_object"
    # src is now a concrete scalar: int / float / bool.
    if tgt in {"json_array", "json_object"}:
        return False  # a scalar can't fill a JSON container param
    if tgt not in _SCALAR_TARGET_TAGS:
        return True  # unknown/text/picklist target → permissive
    if src in _NUMERIC_TARGET_TAGS:
        return tgt in _NUMERIC_TARGET_TAGS  # 1 → ipv4/bool/etc is wrong
    if src == "bool":
        return tgt == "bool"
    return True


_PURE_JINJA_RE = re.compile(r"\A\{\{\s*(.+?)\s*\}\}\Z", re.DOTALL)
_PURE_STEP_REF_RE = re.compile(
    r"\Avars\.steps\.([A-Za-z_][A-Za-z0-9_]*)"
    r"((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\s*(?:\d+|'[^']*'|\"[^\"]*\")\s*\])*)\Z")
_PURE_VAR_REF_RE = re.compile(r"\Avars\.([A-Za-z_][A-Za-z0-9_]*)\Z")
_PURE_INPUT_PARAM_REF_RE = re.compile(
    r"\Avars\.input\.params\.([A-Za-z_][A-Za-z0-9_]*)\Z")


# Declared param-type string → source Shape (STATIC_TYPE_FLOW Phase 3). The
# vocabulary is validated in the parser (`_PARAM_TYPE_VOCAB`); anything not
# here (or `any`) leaves the param untyped → no shape → skip.
def _param_type_to_shape(decl: str) -> Shape | None:
    d = (decl or "").lower()
    if d in {"string", "datetime", "ipv4", "url", "email"}:
        return _shape_scalar("string")
    if d == "integer":
        return _shape_scalar("integer")
    if d == "boolean":
        return _shape_scalar("boolean")
    if d in {"float", "number"}:
        return _shape_scalar("float")
    if d in {"object", "json"}:
        return _shape_object()
    if d in {"list", "array"}:
        return _shape_list(_shape_scalar("any"))
    return None


def _pure_single_ref(value: Any) -> tuple[str, str, str] | None:
    """If `value` is a single `{{ … }}` block wrapping one bare reference
    (no filters, no surrounding text), classify it. Returns
    ('step', key, attr_chain), ('var', name, '') or ('param', name, '')
    (the last for `vars.input.params.<name>`), or None.

    Filtered refs (`{{ x | int }}`) and interpolations (`a {{ x }} b`) are
    skipped here — the resolver's Tier 3 already validates the former, and
    string interpolation coerces to str so there's nothing to mismatch."""
    if not isinstance(value, str):
        return None
    m = _PURE_JINJA_RE.match(value.strip())
    if not m:
        return None
    expr = m.group(1).strip()
    if "|" in expr or "(" in expr or "{%" in expr:
        return None
    sm = _PURE_STEP_REF_RE.match(expr)
    if sm:
        return ("step", sm.group(1), sm.group(2) or "")
    pm = _PURE_INPUT_PARAM_REF_RE.match(expr)
    if pm:
        return ("param", pm.group(1), "")
    vm = _PURE_VAR_REF_RE.match(expr)
    if vm:
        return ("var", vm.group(1), "")
    return None


# ---------------------------------------------------------------------------
# Walking
# ---------------------------------------------------------------------------

_VARS_STEPS_RE = re.compile(
    r"\bvars\.steps\.([A-Za-z_][A-Za-z0-9_]*)"
    r"((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\s*(?:\d+|'[^']*'|\"[^\"]*\")\s*\])*)"
)
_JINJA_EXPR_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.DOTALL)
# Top-level `vars.<name>` (NOT vars.steps / vars.input — those are reserved
# structural namespaces handled elsewhere). First segment only.
_VARS_TOPLEVEL_RE = re.compile(r"\bvars\.([A-Za-z_][A-Za-z0-9_]*)")
# Output keys FSR adds to every step's `vars.steps.<key>` envelope.
_UNIVERSAL_OUTPUT_KEYS = {"status", "result", "id", "name", "uuid",
                          "@id", "@type", "step_id"}


def _jinja_key(step: Step) -> str:
    """FSR builds vars.steps.<key> from the step's display name, lower-cased
    with whitespace → underscores. Empty name falls back to id."""
    base = (step.name or step.id or "").strip()
    return base.replace(" ", "_")


def _walk_strings(node: Any, prefix: str = ""):
    """Yield (path, string) for every string leaf in a nested structure."""
    if isinstance(node, str):
        yield prefix, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{prefix}[{i}]")


def _shape_unknown(reason: str) -> Shape:
    return {"kind": "unknown", "reason": reason}


def _shape_none() -> Shape:
    return {"kind": "none"}


def _shape_object(keys: dict[str, Shape] | None = None) -> Shape:
    return {"kind": "object", "keys": dict(keys or {})}


def _shape_list(item: Shape) -> Shape:
    return {"kind": "list", "item": item}


def _shape_scalar(t: str = "any") -> Shape:
    return {"kind": "scalar", "type": t}


def _code_snippet_envelope(probed: Shape) -> Shape:
    """Keep a grounded code_snippet envelope but widen `data.code_output` to any.

    The connector envelope keys are stable; the inner `code_output` is the
    snippet author's payload (arbitrary). Widening it avoids false positives on
    snippets that emit a structured code_output while preserving the envelope
    membership check that catches a spurious `.output` (pilot E5).
    """
    if not isinstance(probed, dict) or probed.get("kind") != "object":
        return probed
    keys = dict(probed.get("keys") or {})
    data = keys.get("data")
    if isinstance(data, dict) and data.get("kind") == "object":
        dkeys = dict(data.get("keys") or {})
        if "code_output" in dkeys:
            dkeys["code_output"] = _shape_scalar("any")
            keys["data"] = {"kind": "object", "keys": dkeys}
    return {"kind": "object", "keys": keys}


def _module_record_shape(
    module: str | None, module_fields_fn: ModuleFieldsFn | None,
) -> Shape:
    if module and module_fields_fn:
        try:
            fields = module_fields_fn(module) or []
        except Exception:  # noqa: BLE001
            fields = []
        return _shape_object({f: _shape_scalar("any") for f in fields})
    return _shape_object()


def _synth_manual_input_shape(step: Step) -> Shape:
    """`manual_input` exposes the collected inputs at
    `vars.steps.<step>.input.<name>`.

    Read the canonical resolved location first
    (`arguments.input.schema.inputVariables`) — by the time the reference lint
    runs, the resolver has moved the declared fields there and popped the
    friendly `inputs:`/top-level `inputVariables`. Falling through to those
    keeps any pre-resolve caller working. With this populated, a downstream read
    of an *undeclared* `input.<x>` is caught as missing_field_on_step_output; a
    prompt that declares nothing yields an empty (open) object, so button-only
    reads degrade to a warning rather than a false error."""
    args = step.arguments or {}
    iv = (((args.get("input") or {}).get("schema") or {}).get("inputVariables")
          or args.get("inputVariables")
          or args.get("inputs")
          or [])
    keys: dict[str, Shape] = {}
    for entry in iv:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        keys[str(name)] = _shape_scalar(_kind_to_scalar(entry))
    return _shape_object({"input": _shape_object(keys)})


def _kind_to_scalar(entry: dict[str, Any]) -> str:
    """Best-effort scalar-type label for an inputVariables entry."""
    kind = (entry.get("kind") or entry.get("type") or "").lower()
    data_type = (entry.get("dataType") or "").lower()
    if "int" in kind or "int" in data_type or "number" in kind:
        return "integer"
    if "bool" in kind or "checkbox" in kind:
        return "boolean"
    return "string"


# ---------------------------------------------------------------------------
# set_variable value → type inference (Phase 1b live coercion matrix).
# STATIC_TYPE_FLOW_PLAN.md §"Phase 1b RESULT". set_variable smart-casts its
# input: JSON tokens AND Python literals coerce; 0x1f / leading-zeros / dates
# stay strings. This classifier reproduces the matrix for author-relevant
# forms and degrades exotic/ambiguous forms to scalar `any` (never guesses).
# ---------------------------------------------------------------------------

_LIT_BOOL_TOKENS = {"true", "false", "True", "False"}      # exact match only
_LIT_NULL_TOKENS = {"null", "None"}                         # exact match only
_LIT_INT_RE = re.compile(r"\s*-?(?:0|[1-9][0-9]*)\s*\Z")
_LIT_FLOAT_RE = re.compile(
    r"\s*-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\s*\Z")


def _infer_literal_shape(value: Any) -> Shape:
    """Static type of a set_variable value, per the Phase 1b matrix."""
    # Native (non-string) values: the engine keeps these as-is.
    if isinstance(value, bool):
        return _shape_scalar("boolean")
    if isinstance(value, int):
        return _shape_scalar("integer")
    if isinstance(value, float):
        return _shape_scalar("float")
    if value is None:
        return _shape_scalar("null")
    if isinstance(value, list):
        return _shape_list(_shape_scalar("any"))
    if isinstance(value, dict):
        return _shape_object({str(k): _shape_scalar("any") for k in value})
    if not isinstance(value, str):
        return _shape_scalar("any")

    s = value
    # Jinja present: the engine renders THEN re-coerces (e.g. "{{ '123' }}"
    # → int 123). Can't predict statically without resolving the expr → any.
    if "{{" in s or "{%" in s:
        return _shape_scalar("any")
    if s in _LIT_BOOL_TOKENS:
        return _shape_scalar("boolean")
    if s in _LIT_NULL_TOKENS:
        return _shape_scalar("null")
    if _LIT_INT_RE.match(s):
        return _shape_scalar("integer")
    if _LIT_FLOAT_RE.match(s) and any(c in s for c in ".eE"):
        return _shape_scalar("float")
    st = s.lstrip()
    if st[:1] == "[":
        try:
            import json as _json
            _json.loads(s)
            return _shape_list(_shape_scalar("any"))
        except Exception:  # noqa: BLE001
            pass
    elif st[:1] == "{":
        try:
            import json as _json
            obj = _json.loads(s)
            if isinstance(obj, dict):
                return _shape_object(
                    {str(k): _shape_scalar("any") for k in obj})
        except Exception:  # noqa: BLE001
            pass
    return _shape_scalar("string")


def _set_variable_value_map(step: Step) -> dict[str, Any]:
    """{var_name: raw_value} a set_variable step defines. Handles both the
    normalized flat shape (resolver-unwrapped) and the canonical arg_list."""
    a = step.arguments
    if not isinstance(a, dict):
        return {}
    arg_list = a.get("arg_list")
    if isinstance(arg_list, list):
        out: dict[str, Any] = {}
        for item in arg_list:
            if isinstance(item, dict) and "name" in item:
                out[str(item["name"])] = item.get("value", "")
        return out
    # Flat form (post-normalize): every key except structural handoffs.
    return {k: v for k, v in a.items()
            if k not in {"arg_list", "step_variables", "message"}}


def _synth_set_variable_shape(step: Step) -> Shape:
    """`set_variable.arg_list` is a list of {key, value} dicts (canonical)
    or a friendly `vars:` mapping. Either way the output is
    `vars.steps.<step>.<key>`."""
    a = step.arguments
    keys: dict[str, Shape] = {}
    arg_list = a.get("arg_list") or a.get("vars") or {}
    if isinstance(arg_list, list):
        for entry in arg_list:
            if isinstance(entry, dict):
                k = entry.get("key") or entry.get("name")
                if k:
                    keys[str(k)] = _shape_scalar("any")
    elif isinstance(arg_list, dict):
        for k in arg_list:
            keys[str(k)] = _shape_scalar("any")
    return _shape_object(keys)


def _workflow_reference_output_shape(child: Playbook) -> Shape:
    """Output shape of a SYNC `workflow_reference` to `child`.

    Live ground truth (run 686622): a synchronous child's `set_variable` vars
    merge into the *reference step's* result namespace — i.e. `vars.steps.<ref
    step>.<childvar>` resolves to the child's var (NOT top-level `vars.<var>`).
    So the reference step's shape is the union of every `set_variable` key the
    child defines. Keys are typed `any` (the child's values are dynamic).
    """
    keys: dict[str, Shape] = {}
    for s in child.steps:
        if s.type == "set_variable":
            # _set_variable_value_map handles BOTH the friendly/arg_list form
            # and the resolver-flattened form (the resolved IR is what
            # verify_playbook walks); _synth_set_variable_shape misses the flat
            # form. Values are Jinja → typed `any`.
            for name in _set_variable_value_map(s):
                keys[name] = _shape_scalar("any")
    return _shape_object(keys)


def _child_wf_ref_shapes(coll: "Collection") -> dict[str, Shape]:
    """Map both child playbook NAME and its resolved IRI → reference output shape.

    The parsed IR carries `arguments.target: <name>`; the resolved IR carries
    `arguments.workflowReference: /api/3/workflows/<uuid>`. We key by both so the
    lookup works pre- and post-resolve. The uuid derivation mirrors the emitter
    (`uuid5(_NS, "workflow|<collection>|<name>")`).
    """
    from .emitter import _u
    out: dict[str, Shape] = {}
    for child in coll.playbooks:
        shape = _workflow_reference_output_shape(child)
        out[child.name] = shape
        out[f"/api/3/workflows/{_u('workflow', coll.name, child.name)}"] = shape
    return out


def _step_module(step: Step) -> str | None:
    a = step.arguments
    m = a.get("module") or a.get("resource")
    if isinstance(m, str):
        return m
    modules = a.get("modules") or a.get("resources")
    if isinstance(modules, list) and modules:
        return str(modules[0])
    return None


def _connector_op(step: Step) -> tuple[str | None, str | None]:
    a = step.arguments
    return (
        a.get("connector") or a.get("connector_name"),
        a.get("operation") or a.get("op_name") or a.get("op"),
    )


def _synth_step_shape(
    step: Step,
    *,
    probe: ProbeCallback | None,
    module_fields_fn: ModuleFieldsFn | None,
    op_safety_fn: OpSafetyFn | None,
    wf_ref_shapes: dict[str, Shape] | None = None,
) -> Shape:
    """Return the *output* shape for one step, ignoring branching."""
    # A `for_each` step runs its body once per element and FSR collects the
    # per-iteration results into a LIST — `vars.steps.<loop step>` is a list of
    # the normal per-iteration envelopes, NOT a bare envelope (live-grounded:
    # run on .205 — a looped code_snippet yields
    # `[{data:{code_output:…},status,…}, …]`, and reading `.data` on it
    # resolves to "" at runtime). Compute the per-iteration shape with
    # for_each cleared, then wrap. `__bulk` loops (IngestBulkFeed) aggregate
    # differently and aren't grounded, so leave those to the base shape.
    fe = getattr(step, "for_each", None)
    if (isinstance(fe, dict) and fe.get("item")
            and fe.get("__bulk") not in (True, "true")):
        import dataclasses
        inner = _synth_step_shape(
            dataclasses.replace(step, for_each=None),
            probe=probe, module_fields_fn=module_fields_fn,
            op_safety_fn=op_safety_fn, wf_ref_shapes=wf_ref_shapes)
        return _shape_list(inner)

    t = step.type
    if t in {"decision", "delay", "stop", "end"}:
        return _shape_none()
    if t in {"start", "start_on_create", "start_on_update", "start_on_delete"}:
        module = _step_module(step)
        rec = _module_record_shape(module, module_fields_fn)
        return _shape_object({"input": _shape_object(
            {"records": _shape_list(rec)})})
    if t == "manual_input":
        return _synth_manual_input_shape(step)
    if t == "set_variable":
        return _synth_set_variable_shape(step)
    if t == "find_record":
        rec = _module_record_shape(_step_module(step), module_fields_fn)
        return _shape_list(rec)
    if t in {"create_record", "insert_record", "update_record"}:
        return _module_record_shape(_step_module(step), module_fields_fn)
    if t in {"code_snippet"}:
        # The body returns arbitrary Python, so we can't infer the shape — but
        # a grounded probe (measured from a real run via grounded_shapes) knows
        # the connector's envelope: {data: {code_output: …}, status, message,
        # operation}. Consult it so refs like `vars.steps.X.output` (which the
        # envelope does NOT have — pilot E5) get flagged. The code-snippet
        # connector/op are fixed regardless of authoring shape.
        if probe:
            try:
                probed = probe("code-snippet", "python_inline_code_editor",
                               dict(step.arguments))
            except Exception:  # noqa: BLE001
                probed = None
            if probed is not None:
                # The envelope ({data, status, message, operation}) is stable
                # across snippets, but `data.code_output` is the user's payload
                # (any shape). Keep the envelope check (catches `.output` and
                # wrong top-level keys — pilot E5) without over-claiming the
                # snippet-defined inner value, which would false-positive on a
                # snippet that returns a structured code_output.
                return _code_snippet_envelope(probed)
        return _shape_unknown("code_snippet returns arbitrary Python value")
    if t == "workflow_reference":
        # Async fire-and-forget → no output. Sync reference → caller's
        # responsibility to recurse; we just declare unknown so refs
        # don't spuriously fail.
        if step.arguments.get("apply_async") is True:
            return _shape_none()
        # Sync reference: the child's set_variable vars surface at
        # `vars.steps.<this step>.<childvar>` (live-proven, run 686622). Look up
        # the child by friendly `target` name (parsed IR) or `workflowReference`
        # IRI (resolved IR) and synthesize its output shape.
        if wf_ref_shapes:
            tgt = (step.arguments.get("workflowReference")
                   or step.arguments.get("target"))
            shape = wf_ref_shapes.get(tgt) if isinstance(tgt, str) else None
            if shape is not None:
                return shape
        return _shape_unknown("workflow_reference outputs require recursion")
    if t in {"connector", "connector_op"}:
        connector, op = _connector_op(step)
        safety = "unknown"
        if op_safety_fn and connector and op:
            try:
                safety = op_safety_fn(connector, op) or "unknown"
            except Exception:  # noqa: BLE001
                safety = "unknown"
        if safety == "safe" and probe and connector and op:
            try:
                probed = probe(connector, op, dict(step.arguments))
            except Exception:  # noqa: BLE001
                probed = None
            if probed is not None:
                return probed
        return _shape_unknown(
            f"connector_op safety={safety}; live shape not available")
    return _shape_unknown(f"unhandled step type {t!r}")


# ---------------------------------------------------------------------------
# Branch enumeration
# ---------------------------------------------------------------------------

def _trigger_step(pb: Playbook) -> Step | None:
    if pb.trigger_step_id:
        for s in pb.steps:
            if s.id == pb.trigger_step_id:
                return s
    for s in pb.steps:
        if s.type in {"start", "start_on_create", "start_on_update", "start_on_delete"}:
            return s
    return pb.steps[0] if pb.steps else None


def _enumerate_branches(pb: Playbook) -> list[list[str]]:
    """Return every reachable linear path of step ids from trigger to a
    leaf. Branches fork at `decision` and `manual_input` steps. Cycles
    are broken by visited-set."""
    by_id = {s.id: s for s in pb.steps}
    trigger = _trigger_step(pb)
    if trigger is None:
        return []

    results: list[list[str]] = []

    def _walk(sid: str, path: list[str], visited: set[str]) -> None:
        if sid in visited:
            results.append(path + [sid])  # cycle ends the branch
            return
        s = by_id.get(sid)
        if s is None:
            results.append(path + [sid])  # missing target ends the branch
            return
        new_path = path + [sid]
        new_visited = visited | {sid}
        # Branching steps fork.
        if s.branches:
            for label, target in s.branches.items():
                if target:
                    _walk(target, new_path, new_visited)
            if not s.branches:
                results.append(new_path)
            return
        # manual_input: each input's `next` is a branch. Friendly form
        # may inline options that the resolver expands into inputVariables.
        if s.type == "manual_input":
            options = s.arguments.get("options") or []
            forked = False
            for opt in options if isinstance(options, list) else []:
                if isinstance(opt, dict) and opt.get("next"):
                    _walk(opt["next"], new_path, new_visited)
                    forked = True
            if forked:
                return
        if s.unlabeled_next:
            for nxt in s.unlabeled_next:
                _walk(nxt, new_path, new_visited)
            return
        if s.next:
            _walk(s.next, new_path, new_visited)
            return
        results.append(new_path)

    _walk(trigger.id, [], set())
    return results or [[trigger.id]]


def _branch_label(pb: Playbook, ids: list[str]) -> str:
    """Build a readable branch label by tracing fork choices."""
    by_id = {s.id: s for s in pb.steps}
    pieces = []
    for i, sid in enumerate(ids[:-1]):
        s = by_id.get(sid)
        if s is None:
            continue
        nxt = ids[i + 1]
        if s.branches:
            for label, target in s.branches.items():
                if target == nxt:
                    pieces.append(f"{s.id}:{label}")
                    break
        elif s.type == "manual_input":
            options = s.arguments.get("options") or []
            for opt in options if isinstance(options, list) else []:
                if isinstance(opt, dict) and opt.get("next") == nxt:
                    pieces.append(f"{s.id}:{opt.get('label') or opt.get('value') or '?'}")
                    break
    return " > ".join(pieces) or ids[0]


# ---------------------------------------------------------------------------
# Reference validation
# ---------------------------------------------------------------------------

def _resolve_path(env_key: str, attr_chain: str,
                  typed_env: dict[str, Shape],
                  fail_info: dict[str, Any] | None = None,
                  ) -> tuple[Shape | None, str]:
    """Walk `attr_chain` against `typed_env[env_key]`. Return (final_shape
    or None, error-code or '' if ok).

    When the walk fails on a missing object key, the *actual* failing segment
    can be deeper than the first attribute (e.g. `input.<undeclared>` fails on
    the second hop, not on `input`). Pass a mutable `fail_info` dict to capture
    `{"bad_attr", "valid"}` at the point of failure so callers can report the
    right field instead of guessing the first segment."""
    cur = typed_env.get(env_key)
    if cur is None:
        return None, "unreachable_step_reference"

    # Tokenize attr_chain into a sequence of (kind, value) where
    # kind is 'attr' or 'index'.
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(attr_chain):
        c = attr_chain[i]
        if c == ".":
            j = i + 1
            while j < len(attr_chain) and (attr_chain[j].isalnum() or attr_chain[j] == "_"):
                j += 1
            tokens.append(("attr", attr_chain[i + 1:j]))
            i = j
        elif c == "[":
            end = attr_chain.index("]", i)
            tokens.append(("index", attr_chain[i + 1:end].strip()))
            i = end + 1
        else:
            i += 1

    for kind, val in tokens:
        if kind == "attr":
            if val in _UNIVERSAL_OUTPUT_KEYS:
                # FSR exposes these on every step; accept.
                return _shape_scalar("any"), ""
            if cur.get("kind") == "object":
                keys = cur.get("keys") or {}
                if val not in keys:
                    if not keys:
                        # Empty/unknown object: degrade to warning, not error.
                        return _shape_unknown("no known keys"), ""
                    if fail_info is not None:
                        fail_info["bad_attr"] = val
                        fail_info["valid"] = sorted(keys.keys())
                    return None, "missing_field_on_step_output"
                cur = keys[val]
            elif cur.get("kind") == "list":
                # Accessing a property on a list (likely a Jinja filter
                # consumer); permit and degrade to unknown.
                return _shape_unknown("attr access on list"), ""
            elif cur.get("kind") == "unknown":
                return cur, ""
            else:
                return None, "missing_field_on_step_output"
        else:  # index
            if cur.get("kind") == "list":
                cur = cur.get("item") or _shape_scalar("any")
            elif cur.get("kind") == "unknown":
                return cur, ""
            else:
                return None, "non_list_indexed"
    return cur, ""


def _validate_branch_jinja(
    pb: Playbook, ids: list[str], typed_env: dict[str, Shape],
    branch_name: str, param_type_fn: ParamTypeFn | None = None,
    param_shapes: dict[str, Shape] | None = None,
) -> tuple[list[Diagnostic], dict[str, Shape], list[dict[str, Any]]]:
    by_id = {s.id: s for s in pb.steps}
    jinja_key_lookup = {_jinja_key(s): s for s in pb.steps}
    # Normalised lookup: lowercase + non-alphanumeric collapsed to `_`.
    # Used to distinguish "key doesn't resolve because of case/punctuation
    # typo" from "step really doesn't run on this branch".
    def _norm(k: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")
    normalised_lookup = {_norm(jk): jk for jk in jinja_key_lookup}
    diags: list[Diagnostic] = []
    type_decisions: list[dict[str, Any]] = []  # Phase 5 trace
    visible: set[str] = set()  # jinja_keys that have run by the time we visit this step

    # Phase 2 — branch-local `vars.<name>` typing + scoping. var_env grows as
    # the walk passes each predecessor set_variable on THIS branch; a ref is
    # validated against the env *before* its own step. `var_defs` (whole-pb)
    # lets us tell "defined later on this branch" (read-before-def) from
    # "defined only on another branch" — the never-defined-anywhere case is
    # left to validator._check_undefined_vars (disjoint, no double-report).
    var_env: dict[str, Shape] = {}
    var_defs: dict[str, set[str]] = {}
    for st in pb.steps:
        if st.type == "set_variable":
            for vn in _set_variable_value_map(st):
                var_defs.setdefault(vn, set()).add(st.id)
    ids_set = set(ids)
    pos = {sid: i for i, sid in enumerate(ids)}

    for sid in ids:
        s = by_id.get(sid)
        if s is None:
            continue
        # A set_variable's own vars are readable within its own step (intra-
        # step chaining is permitted), so seed them before validating refs.
        if s.type == "set_variable":
            for vn, vv in _set_variable_value_map(s).items():
                var_env[vn] = _infer_literal_shape(vv)
        # Branch-scoped `vars.<name>` reference checks for this step.
        diags.extend(_check_toplevel_vars(
            s, branch_name, var_env, var_defs, ids_set, pos))
        # Phase 4 — source→target type check on connector params that are a
        # pure reference to a step output or set_variable var.
        if param_type_fn is not None and s.type in {"connector", "connector_op"}:
            diags.extend(_check_connector_param_types(
                s, branch_name, typed_env, var_env, visible, param_type_fn,
                param_shapes, type_decisions))
        # Validate refs in this step's arguments using the env *before*
        # this step's own shape is added (a step can reference itself
        # only via universal keys, handled inside _resolve_path).
        for sub, val in _walk_strings(s.arguments):
            for jm in _JINJA_EXPR_RE.finditer(val):
                expr = jm.group(1)
                for m in _VARS_STEPS_RE.finditer(expr):
                    key = m.group(1)
                    rest = m.group(2) or ""
                    if key == _jinja_key(s):
                        # self-reference: only universal keys are valid
                        if rest.startswith("."):
                            first = rest.lstrip(".").split(".", 1)[0].split("[", 1)[0]
                            if first and first not in _UNIVERSAL_OUTPUT_KEYS:
                                diags.append(Diagnostic(
                                    code="missing_field_on_step_output",
                                    message=(f"self-reference vars.steps.{key}.{first} "
                                             f"in step {s.id!r}: only "
                                             "{status, result, id, …} are "
                                             "available on the producing step itself"),
                                    step=s.id, branch=branch_name,
                                    path=f"arguments.{sub}",
                                ))
                        continue
                    if key not in visible:
                        # Distinguish three sub-cases:
                        #  (a) typo / case-or-punct mismatch of a *visible* step
                        #  (b) step exists in the playbook but is on a different branch
                        #  (c) no such step at all
                        actual = normalised_lookup.get(_norm(key))
                        if actual is not None and actual in visible:
                            diags.append(Diagnostic(
                                code="unknown_step_reference",
                                message=(
                                    f"vars.steps.{key} referenced in step "
                                    f"{s.id!r}: step reference key is case- "
                                    f"and punctuation-sensitive. Did you "
                                    f"mean vars.steps.{actual}? (FSR builds "
                                    f"the key from the step's display name "
                                    f"by replacing spaces with '_'; other "
                                    f"characters are preserved verbatim)"),
                                step=s.id, branch=branch_name,
                                path=f"arguments.{sub}",
                            ))
                        elif actual is not None:
                            diags.append(Diagnostic(
                                code="unreachable_step_reference",
                                message=(
                                    f"vars.steps.{key} referenced in step "
                                    f"{s.id!r} but step {actual!r} does not "
                                    f"run on branch {branch_name!r} (it is "
                                    f"defined on a different branch)"),
                                step=s.id, branch=branch_name,
                                path=f"arguments.{sub}",
                            ))
                        else:
                            diags.append(Diagnostic(
                                code="unknown_step_reference",
                                message=(
                                    f"vars.steps.{key} referenced in step "
                                    f"{s.id!r} but no step named {key!r} "
                                    f"exists in this playbook"),
                                step=s.id, branch=branch_name,
                                path=f"arguments.{sub}",
                            ))
                        continue
                    fail_info: dict[str, Any] = {}
                    shape, err = _resolve_path(key, rest, typed_env, fail_info)
                    if err == "missing_field_on_step_output":
                        target = jinja_key_lookup.get(key)
                        # Prefer the actual failing segment + its container's
                        # keys (captured by `_resolve_path`); the failure can be
                        # deeper than the first attribute (e.g.
                        # `input.<undeclared>` fails on the second hop). Fall
                        # back to the first-attr heuristic + top-level keys when
                        # no fail_info was captured.
                        bad_attr = fail_info.get("bad_attr") or ""
                        valid = fail_info.get("valid")
                        if valid is None:
                            valid = (sorted((typed_env[key].get("keys") or {}).keys())
                                     if typed_env[key].get("kind") == "object" else [])
                        if not bad_attr and rest.startswith("."):
                            bad_attr = rest.lstrip(".").split(".", 1)[0].split("[", 1)[0]
                        # Case-insensitive exact match → typo; else
                        # difflib top-3 for fuzzy "did you mean".
                        case_match = next(
                            (v for v in valid if v.lower() == bad_attr.lower()
                             and v != bad_attr), None)
                        if case_match:
                            msg = (f"vars.steps.{key}{rest} in step "
                                   f"{s.id!r}: {bad_attr!r} not in known "
                                   f"shape of "
                                   f"{target.id if target else key!r} — "
                                   f"keys are case-sensitive. Did you "
                                   f"mean {case_match!r}?")
                        else:
                            import difflib
                            near = difflib.get_close_matches(
                                bad_attr, valid, n=3, cutoff=0.4)
                            if near:
                                msg = (f"vars.steps.{key}{rest} in step "
                                       f"{s.id!r}: {bad_attr!r} not in "
                                       f"known shape of "
                                       f"{target.id if target else key!r}. "
                                       f"Did you mean: "
                                       f"{', '.join(repr(n) for n in near)}?")
                            else:
                                head = ', '.join(valid[:8])
                                msg = (f"vars.steps.{key}{rest} in step "
                                       f"{s.id!r}: {bad_attr!r} not in "
                                       f"known shape of "
                                       f"{target.id if target else key!r}. "
                                       f"Available keys: {head}. "
                                       f"Universal output keys "
                                       f"(`status`, `result`, `id`, "
                                       f"`@id`) are also available on "
                                       f"every step.")
                        diags.append(Diagnostic(
                            code="missing_field_on_step_output",
                            message=msg,
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}",
                        ))
                    elif err == "non_list_indexed":
                        # Tell the agent what the actual shape is so it
                        # can pick the right access pattern (object →
                        # `.attr`, scalar → drop the index, common FSR
                        # envelope `{hydra:member: [...]}` → recommend
                        # the right key).
                        st = typed_env.get(key) or {}
                        kind = st.get("kind", "unknown")
                        suggestion = ""
                        if kind == "object":
                            obj_keys = list((st.get("keys") or {}).keys())
                            list_keys = [
                                k for k in obj_keys
                                if (st["keys"][k] or {}).get("kind") == "list"
                            ]
                            if "hydra:member" in obj_keys:
                                suggestion = (
                                    " — this resolves to a Hydra "
                                    "envelope; index the inner list: "
                                    "`vars.steps.{0}['hydra:member'][0]"
                                    "`".format(key))
                            elif list_keys:
                                suggestion = (
                                    " — this is an object; the list-"
                                    "valued keys are: "
                                    f"{', '.join(list_keys[:5])}")
                            else:
                                suggestion = (
                                    " — this is an object, not a list. "
                                    "Use `.<attr>` instead of `[…]`")
                        elif kind in ("scalar", "any"):
                            suggestion = (
                                " — this is a scalar; drop the index")
                        diags.append(Diagnostic(
                            code="non_list_indexed",
                            message=(f"vars.steps.{key}{rest} in step "
                                     f"{s.id!r}: indexing `[…]` on a "
                                     f"{kind} shape{suggestion}"),
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}",
                        ))
                    elif (shape and shape.get("kind") == "unknown"
                          and shape.get("reason") == "attr access on list"
                          and isinstance(getattr(
                              jinja_key_lookup.get(key), "for_each", None),
                              dict)):
                        # The producer is a `for_each` step → its output is a
                        # LIST (one envelope per iteration, live-grounded). A
                        # bare `.attr` on it resolves to "" at runtime, so this
                        # is a confident bug, not a soft unknown. Tell the
                        # author to index an iteration or aggregate the list.
                        bad_attr = (rest.lstrip(".").split(".", 1)[0]
                                    .split("[", 1)[0] if rest.startswith(".")
                                    else rest)
                        diags.append(Diagnostic(
                            code="missing_field_on_step_output",
                            message=(
                                f"vars.steps.{key}{rest} in step {s.id!r}: "
                                f"{key!r} is a for_each loop, so its output is "
                                f"a LIST of per-iteration results — `.{bad_attr}`"
                                f" on the list resolves to empty at runtime. "
                                f"Index an iteration "
                                f"(`vars.steps.{key}[0]{rest}`) or map over the "
                                f"list with a Jinja filter."),
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}",
                        ))
                    elif shape and shape.get("kind") == "unknown":
                        diags.append(Diagnostic(
                            code="unknown_shape_downstream_reference",
                            message=(f"vars.steps.{key}{rest} resolves through "
                                     f"unknown shape "
                                     f"({shape.get('reason', '')!s})"),
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}",
                            severity="warning",
                        ))
        visible.add(_jinja_key(s))
    return diags, var_env, type_decisions


# ---------------------------------------------------------------------------
# Branch-scoped `vars.<name>` reference checks (Phase 2)
# ---------------------------------------------------------------------------

def _check_toplevel_vars(
    s: Step, branch_name: str, var_env: dict[str, Shape],
    var_defs: dict[str, set[str]], ids_set: set[str], pos: dict[str, int],
) -> list[Diagnostic]:
    """Validate `{{ vars.<name> }}` refs in one step against the branch-local
    var env. Emits ONLY the branch-specific cases (the whole-playbook
    'never defined anywhere' warning stays in validator._check_undefined_vars):
      - loop_var_outside_for_each: `vars.item` read in a step without for_each
      - var_read_before_definition: defined later on THIS branch
      - var_defined_other_branch:  defined, but not on this branch
    All warnings (vars are run-global; avoid hard-blocking on a maybe-FP)."""
    diags: list[Diagnostic] = []
    has_for_each = bool(getattr(s, "for_each", None))
    my_pos = pos.get(s.id, -1)
    seen: set[str] = set()
    for sub, val in _walk_strings(s.arguments):
        if not isinstance(val, str) or "{{" not in val:
            continue
        for jm in _JINJA_EXPR_RE.finditer(val):
            for m in _VARS_TOPLEVEL_RE.finditer(jm.group(1)):
                name = m.group(1)
                if name in _RESERVED_VARS_KEYS or name in seen:
                    continue
                # `vars.item` is the per-iteration loop binding — live only
                # inside a step that carries for_each (proven Phase 1a).
                if name == "item":
                    if not has_for_each:
                        seen.add(name)
                        diags.append(Diagnostic(
                            code="loop_var_outside_for_each",
                            message=(f"vars.item read in step {s.id!r} which "
                                     f"has no for_each — the loop binding is "
                                     f"only live inside the looping step; "
                                     f"elsewhere it is undefined"),
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}", severity="warning",
                        ))
                    continue
                if name in var_env:
                    continue  # defined+visible on this branch — ok (typed)
                defs = var_defs.get(name)
                if not defs:
                    continue  # never defined anywhere → validator handles it
                seen.add(name)
                later_same_branch = any(
                    d in ids_set and pos.get(d, -1) >= my_pos for d in defs)
                if later_same_branch:
                    diags.append(Diagnostic(
                        code="var_read_before_definition",
                        message=(f"vars.{name} read in step {s.id!r} but its "
                                 f"defining set_variable runs later on this "
                                 f"branch — it will be empty here"),
                        step=s.id, branch=branch_name,
                        path=f"arguments.{sub}", severity="warning",
                    ))
                else:
                    diags.append(Diagnostic(
                        code="var_defined_other_branch",
                        message=(f"vars.{name} read in step {s.id!r} but is "
                                 f"only defined on a different branch (not on "
                                 f"{branch_name!r}) — it will be empty here"),
                        step=s.id, branch=branch_name,
                        path=f"arguments.{sub}", severity="warning",
                    ))
    return diags


# ---------------------------------------------------------------------------
# Phase 4 — connector param source→target type check
# ---------------------------------------------------------------------------

def _check_connector_param_types(
    s: Step, branch_name: str, typed_env: dict[str, Shape],
    var_env: dict[str, Shape], visible: set[str],
    param_type_fn: ParamTypeFn,
    param_shapes: dict[str, Shape] | None = None,
    decisions: list[dict[str, Any]] | None = None,
) -> list[Diagnostic]:
    """For each connector param whose value is a pure reference to a typed
    source (step output or set_variable var), compare the source's inferred
    type against the param's target type and emit `type_mismatch` on a
    confident incompatibility (shape-into-scalar, or a numeric/bool category
    crossing). Filtered/interpolated values are left to the resolver.

    When `decisions` is given, append a record per judged param (passes
    included) for the Phase 5 trace export."""
    connector, op = _connector_op(s)
    if not connector or not op:
        return []
    params = s.arguments.get("params")
    if not isinstance(params, dict):
        return []
    diags: list[Diagnostic] = []
    for p_name, p_val in params.items():
        ref = _pure_single_ref(p_val)
        if ref is None:
            # A literal value (not a reference) is validated against the param
            # widget type by the resolver's Tier-1/2.3 passes
            # (connector_args.py) at *compile* time — more precisely than this
            # walker could (it models the actual `int()`/`float()` coercion,
            # e.g. flags `"abc"`→int but allows `"007"`). Compile errors
            # short-circuit before the walk, so there's nothing to add here.
            continue
        kind, key, rest = ref
        if kind == "step":
            if key not in visible:
                continue  # visibility/typo already reported by the ref pass
            shape, err = _resolve_path(key, rest, typed_env)
            if err:
                continue  # missing-field / non-list etc. already reported
        elif kind == "param":
            shape = (param_shapes or {}).get(key)
            if shape is None:
                continue  # untyped playbook param → `any`, nothing to check
        else:  # var
            shape = var_env.get(key)
            if shape is None:
                continue  # undefined-var handled by _check_toplevel_vars
        src_tag = _shape_to_src_tag(shape)
        if src_tag is None:
            continue
        try:
            tgt_tag = param_type_fn(connector, op, p_name)
        except Exception:  # noqa: BLE001
            tgt_tag = None
        ok = _source_target_compatible(src_tag, tgt_tag)
        if decisions is not None:
            decisions.append({
                "step": s.id, "param": p_name,
                "connector": connector, "operation": op,
                "ref": str(p_val).strip(), "ref_kind": kind,
                "source_type": src_tag, "target_type": tgt_tag,
                "verdict": "ok" if ok else "type_mismatch",
            })
        if ok:
            continue
        src_desc = ("a list" if src_tag == "list"
                    else "an object" if src_tag == "dict"
                    else f"a {src_tag} value")
        diags.append(Diagnostic(
            code="type_mismatch",
            message=(
                f"param {p_name!r} on {connector}.{op} expects {tgt_tag!r} "
                f"but the reference {str(p_val).strip()} resolves to "
                f"{src_desc}"),
            step=s.id, branch=branch_name,
            path=f"arguments.params.{p_name}",
            suggestion=(
                "convert the value with a Jinja filter (e.g. `| int`) or "
                "reference a field of the matching type"),
        ))
    return diags


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def _validate_jinja_filter_chains(pb: Playbook) -> list[Diagnostic]:
    """Tier 3 chain validation across the whole playbook.

    The resolver only sees connector_op param values; this pass sweeps
    every string field on every step (set_variable, decision, manual_input,
    workflow_reference, for_each.item, ...) and flags filter-chain bugs
    like `| length | upper` regardless of context. Pure regex walk; no
    branch awareness needed since the diagnostic is purely syntactic.

    Uses `_HAND_CURATED` only (no DB) — the curated map covers ~90 of
    the most common filters and the resolver's connector-arg path
    handles the long tail with DB lookup.
    """
    from .jinja_typing import validate_chain
    diags: list[Diagnostic] = []
    # Each step exposes Jinja in `arguments` (most common) and `for_each`
    # (item / condition expressions). `branches` and `next` only carry
    # step ids; `comment` is a free-form label that may contain Jinja but
    # never executes against runtime data. Scan the first two.
    scan_fields = ("arguments", "for_each")
    for s in pb.steps:
        for field_name in scan_fields:
            container = getattr(s, field_name, None)
            if not container:
                continue
            for sub, val in _walk_strings(container):
                if not isinstance(val, str) or "{{" not in val:
                    continue
                for m in _JINJA_EXPR_RE.finditer(val):
                    inner = m.group(1).strip()
                    bad = validate_chain(inner, None)
                    if bad is None:
                        continue
                    prod, cons, want = bad
                    diags.append(Diagnostic(
                        code="bad_jinja_filter_chain",
                        message=(
                            f"Jinja filter {cons!r} expects {want!r} but "
                            f"the preceding filter {prod!r} produces a "
                            "different type"),
                        step=s.id, path=f"{field_name}.{sub}",
                        suggestion=(
                            "reorder or remove a filter so each `|` "
                            "boundary matches"),
                    ))
    return diags


def walk_playbook(
    coll: Collection,
    playbook_name: str | None = None,
    *,
    probe: ProbeCallback | None = None,
    module_fields_fn: ModuleFieldsFn | None = None,
    op_safety_fn: OpSafetyFn | None = None,
    param_type_fn: ParamTypeFn | None = None,
) -> WalkResult:
    """Walk every branch of the named playbook (or the first one) and
    return typed envs + Jinja-reference diagnostics."""
    pb: Playbook | None = None
    if playbook_name:
        for p in coll.playbooks:
            if p.name == playbook_name:
                pb = p
                break
    else:
        pb = coll.playbooks[0] if coll.playbooks else None
    if pb is None:
        return WalkResult(branches=[], diagnostics=[Diagnostic(
            code="branch_target_missing",
            message=f"playbook {playbook_name!r} not found in collection",
        )], per_step_shapes={})

    # Phase 3 — seed `vars.input.params.<name>` shapes from declared types.
    param_shapes: dict[str, Shape] = {}
    for pname, decl in (getattr(pb, "parameter_types", None) or {}).items():
        sh = _param_type_to_shape(decl)
        if sh is not None:
            param_shapes[pname] = sh

    wf_ref_shapes = _child_wf_ref_shapes(coll)
    per_step: dict[str, Shape] = {}
    for s in pb.steps:
        per_step[s.id] = _synth_step_shape(
            s, probe=probe, module_fields_fn=module_fields_fn,
            op_safety_fn=op_safety_fn, wf_ref_shapes=wf_ref_shapes,
        )

    branch_paths = _enumerate_branches(pb)
    by_id = {s.id: s for s in pb.steps}
    branches: list[BranchResult] = []
    # Tier 3 filter-chain check is playbook-level (purely syntactic),
    # not branch-level — emitting it once per step prevents the same
    # diagnostic firing in every branch the step appears on.
    all_diags: list[Diagnostic] = _validate_jinja_filter_chains(pb)

    for ids in branch_paths:
        typed_env: dict[str, Shape] = {}
        for sid in ids:
            s = by_id.get(sid)
            if s is None:
                continue
            typed_env[_jinja_key(s)] = per_step[s.id]
        label = _branch_label(pb, ids)
        diags, var_env, type_decisions = _validate_branch_jinja(
            pb, ids, typed_env, label, param_type_fn, param_shapes)
        branches.append(BranchResult(
            name=label, step_ids=ids,
            typed_env=typed_env, var_env=var_env, diagnostics=diags,
            type_decisions=type_decisions,
        ))
        all_diags.extend(diags)

    return WalkResult(
        branches=branches, diagnostics=all_diags,
        per_step_shapes=per_step,
    )
