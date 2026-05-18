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
    diagnostics: list[Diagnostic] = field(default_factory=list)


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
                    "diagnostics": [d.to_dict() for d in b.diagnostics],
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


# ---------------------------------------------------------------------------
# Walking
# ---------------------------------------------------------------------------

_VARS_STEPS_RE = re.compile(
    r"\bvars\.steps\.([A-Za-z_][A-Za-z0-9_]*)"
    r"((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\s*(?:\d+|'[^']*'|\"[^\"]*\")\s*\])*)"
)
_JINJA_EXPR_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.DOTALL)
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
    `vars.steps.<step>.input.<name>`."""
    iv = step.arguments.get("inputVariables") or []
    # Friendly form may stash as `inputs:`.
    if not iv:
        iv = step.arguments.get("inputs") or []
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
) -> Shape:
    """Return the *output* shape for one step, ignoring branching."""
    t = step.type
    if t in {"decision", "delay", "stop", "end"}:
        return _shape_none()
    if t in {"start", "start_on_create", "start_on_update"}:
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
        return _shape_unknown("code_snippet returns arbitrary Python value")
    if t == "workflow_reference":
        # Async fire-and-forget → no output. Sync reference → caller's
        # responsibility to recurse; we just declare unknown so refs
        # don't spuriously fail.
        if step.arguments.get("apply_async") is True:
            return _shape_none()
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
        if s.type in {"start", "start_on_create", "start_on_update"}:
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
                  typed_env: dict[str, Shape]) -> tuple[Shape | None, str]:
    """Walk `attr_chain` against `typed_env[env_key]`. Return (final_shape
    or None, error-code or '' if ok)."""
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
    branch_name: str,
) -> list[Diagnostic]:
    by_id = {s.id: s for s in pb.steps}
    jinja_key_lookup = {_jinja_key(s): s for s in pb.steps}
    diags: list[Diagnostic] = []
    visible: set[str] = set()  # jinja_keys that have run by the time we visit this step

    for sid in ids:
        s = by_id.get(sid)
        if s is None:
            continue
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
                        diags.append(Diagnostic(
                            code="unreachable_step_reference",
                            message=(f"vars.steps.{key} referenced in step "
                                     f"{s.id!r} but {key!r} does not run on "
                                     f"branch {branch_name!r}"),
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}",
                        ))
                        continue
                    shape, err = _resolve_path(key, rest, typed_env)
                    if err == "missing_field_on_step_output":
                        target = jinja_key_lookup.get(key)
                        valid = (sorted((typed_env[key].get("keys") or {}).keys())
                                 if typed_env[key].get("kind") == "object" else [])
                        diags.append(Diagnostic(
                            code="missing_field_on_step_output",
                            message=(f"vars.steps.{key}{rest} in step "
                                     f"{s.id!r}: path not in known shape "
                                     f"of {target.id if target else key!r} "
                                     f"({', '.join(valid[:8])})"),
                            step=s.id, branch=branch_name,
                            path=f"arguments.{sub}",
                        ))
                    elif err == "non_list_indexed":
                        diags.append(Diagnostic(
                            code="non_list_indexed",
                            message=(f"vars.steps.{key}{rest} in step "
                                     f"{s.id!r}: indexing `[…]` on a "
                                     "non-list shape"),
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
    return diags


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def walk_playbook(
    coll: Collection,
    playbook_name: str | None = None,
    *,
    probe: ProbeCallback | None = None,
    module_fields_fn: ModuleFieldsFn | None = None,
    op_safety_fn: OpSafetyFn | None = None,
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

    per_step: dict[str, Shape] = {}
    for s in pb.steps:
        per_step[s.id] = _synth_step_shape(
            s, probe=probe, module_fields_fn=module_fields_fn,
            op_safety_fn=op_safety_fn,
        )

    branch_paths = _enumerate_branches(pb)
    by_id = {s.id: s for s in pb.steps}
    branches: list[BranchResult] = []
    all_diags: list[Diagnostic] = []

    for ids in branch_paths:
        typed_env: dict[str, Shape] = {}
        for sid in ids:
            s = by_id.get(sid)
            if s is None:
                continue
            typed_env[_jinja_key(s)] = per_step[s.id]
        label = _branch_label(pb, ids)
        diags = _validate_branch_jinja(pb, ids, typed_env, label)
        branches.append(BranchResult(
            name=label, step_ids=ids,
            typed_env=typed_env, diagnostics=diags,
        ))
        all_diags.extend(diags)

    return WalkResult(
        branches=branches, diagnostics=all_diags,
        per_step_shapes=per_step,
    )
