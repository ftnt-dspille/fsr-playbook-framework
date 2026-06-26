"""Cross-cutting validation that runs after resolve.

The resolver already checks per-step references; this module covers
graph-level invariants: every playbook has a Start, exactly one Start,
linear paths terminate, etc.
"""
from __future__ import annotations

import json
import re
import sqlite3

from .._db import default_db_path
from .errors import CompileError, ErrorCode
from .ir import Collection, Playbook, Step

_DB_PATH = default_db_path()

# Find every Jinja expression. Non-greedy; tolerates whitespace.
_JINJA_EXPR_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.DOTALL)
# vars.steps.<key>.<path...> — capture the step jinja-key + the trailing
# attribute chain. Stops at any non-attribute character (operators,
# whitespace, brackets, pipes).
_VARS_STEPS_RE = re.compile(
    r"\bvars\.steps\.([A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z_][A-Za-z0-9_]*"
    r"|\[\s*(?:\d+|'[^']*'|\"[^\"]*\")\s*\])*)"
)


# Top-level keys present on every workflow's `vars` context at runtime.
# Setting one of these via SetVariable shadows the FSR-provided value
# silently, breaking later steps that read it. Sourced from the corpus
# + live runs (see store/JINJA_IDIOMS.md, /api/wf/api/workflows env dump).
_RESERVED_VARS_KEYS = {
    # Authoritative list per FSR docs ("Reserved Keywords"). Setting any
    # of these via SetVariable either silently shadows the FSR-provided
    # value OR makes the runtime crash (e.g. setting `message` to a
    # plain string triggers `'str' object has no attribute 'get'` because
    # the engine treats it as a structured envelope).
    "items",
    "result",
    "input",
    "request",
    "values",
    "keys",
    "files",
    "env",
    "message",
    "resources",
    "step_variables",
    "do_until",
    "ignore_errors",
    "when",
    "for_each",
    "cyops_playbook_iri",
    "cyops_playbook_name",
    "collaborationNote",
    "inputVariables",
    "displayConditions",
    "task_id",
    "wf_id",
    # Inferred-from-corpus additions (not in the public list, but
    # observed to break or silently shadow):
    "steps",          # per-step output namespace
    "vars",           # self-reference (infinite loop)
    "globalVars",     # collection-level globals
    "globals",        # alias used by some step handlers
    "parent_wf",      # set when invoked via workflow_reference
    "self",           # reserved by FSR's playbook runtime
}

# Jinja/Python tokens that would break `vars.steps.<name>` attribute access
# or get parsed as keywords. Short list — only the ones that actually break.
_INVALID_JINJA_KEY_TOKENS = {
    "true", "false", "none", "null",
    "and", "or", "not", "is", "in", "if", "else", "for",
    "class", "def", "return", "import", "from", "as", "with",
}


def _step_outgoing(s) -> list[str]:
    """Yield all outgoing step ids from a step (next + branches + unlabeled)."""
    out: list[str] = []
    if s.next:
        out.append(s.next)
    out.extend(s.branches.values())
    out.extend(s.unlabeled_next)
    return out


def _walk_strings(value, *, prefix: str = ""):
    """Yield (path, string_value) pairs from any nested args structure."""
    if isinstance(value, str):
        yield prefix, value
    elif isinstance(value, dict):
        for k, v in value.items():
            sub = f"{prefix}.{k}" if prefix else k
            yield from _walk_strings(v, prefix=sub)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk_strings(v, prefix=f"{prefix}[{i}]")


def _step_output_top_keys(s: Step) -> set[str] | None:
    """Best-effort top-level output key set for a step.
    Returns None if we don't know (don't lint that reference).
    The keys are what would appear immediately after `vars.steps.<name>.`."""
    if s.type == "set_variable" and isinstance(s.arguments, dict):
        # SetVariable's output keys are the variable names themselves.
        if isinstance(s.arguments.get("arg_list"), list):
            keys = {item["name"] for item in s.arguments["arg_list"]
                    if isinstance(item, dict) and "name" in item}
        else:
            keys = {k for k in s.arguments if k != "step_variables"}
        return keys

    if s.type == "connector" and isinstance(s.arguments, dict):
        connector = s.arguments.get("connector")
        op = s.arguments.get("operation")
        if not connector or not op:
            return None
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT output_schema_json, output_schema_observed "
                    "FROM operations WHERE connector_name=? AND op_name=?",
                    (connector, op),
                ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        if not row:
            return None
        for blob in (row[1], row[0]):  # observed wins
            if not blob:
                continue
            try:
                shape = json.loads(blob)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(shape, dict) and shape:
                return set(shape.keys())
        return None

    if s.type == "find_record":
        # FindRecords returns a hydra:Collection-shaped envelope. Top-level
        # keys are the canonical hydra ones. Skip strict validation for
        # this — most authors index `[0]` directly.
        return {"@context", "@id", "@type", "hydra:member",
                "hydra:totalItems", "hydra:itemsPerPage"}

    if s.type == "manual_input":
        # Output is the resumed input + chosen option.
        return {"input", "option", "user", "username", "datetime"}

    # Unknown — code_snippet, workflow_reference, decision, delay,
    # create_record, update_record, start*, etc.
    return None


def _has_cycle(pb: Playbook) -> bool:
    """Return True if the playbook's step graph contains a directed cycle.

    Used to short-circuit _check_jinja_paths: predecessor analysis on a cyclic
    graph produces unreliable reachability sets and may emit spurious errors.
    _check_graph will report the actual cycle as an error independently.
    """
    by_id = {s.id: s for s in pb.steps}
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in by_id}

    def _dfs(sid: str) -> bool:
        color[sid] = GREY
        s = by_id.get(sid)
        if s is not None:
            for nxt in _step_outgoing(s):
                if nxt not in by_id:
                    continue
                c = color.get(nxt, WHITE)
                if c == GREY:
                    return True
                if c == WHITE and _dfs(nxt):
                    return True
        color[sid] = BLACK
        return False

    return any(_dfs(sid) for sid in list(by_id) if color[sid] == WHITE)


def _compute_predecessors(pb: Playbook) -> dict[str, set[str]]:
    """For each step id, return the set of step ids that *can* run before it.

    Computed by forward BFS from each start step: when we visit a step
    via an edge from S, S is added to the predecessor set. We propagate
    transitively so cycles fold in correctly. Lenient by design: a step
    on *any* path reaching S counts as a predecessor; we don't try to
    enforce all-paths dominance (FSR runtime would reject the playbook
    on any path where the reference doesn't bind anyway).
    """
    by_id: dict[str, "Step"] = {s.id: s for s in pb.steps}
    preds: dict[str, set[str]] = {s.id: set() for s in pb.steps}
    starts = [s.id for s in pb.steps if s.type and s.type.startswith("start")]
    if not starts and pb.steps:
        starts = [pb.steps[0].id]
    # Iterate to fixed point (handles cycles and multi-branch joins).
    changed = True
    seen_path: set[tuple[str, str]] = set()
    while changed:
        changed = False
        for s in pb.steps:
            for nxt in _step_outgoing(s):
                if nxt not in by_id:
                    continue
                edge = (s.id, nxt)
                # Add s itself as predecessor of nxt.
                if s.id not in preds[nxt]:
                    preds[nxt].add(s.id)
                    changed = True
                # Inherit s's predecessors.
                inherited = preds[s.id] - preds[nxt]
                if inherited:
                    preds[nxt] |= inherited
                    changed = True
                seen_path.add(edge)
    # Steps unreachable from a start get an empty predecessor set —
    # references *into* them would fail; references *from* them won't
    # be checked because those steps are dead code (a separate lint).
    return preds


def _check_jinja_paths(pb: Playbook, pi: int,
                       errors: list[CompileError]) -> None:
    """Catch `{{ vars.steps.<name>... }}` references that don't resolve.

    Three failure modes:
      1. The named step doesn't exist (typo) — error.
      2. The named step exists but cannot run *before* the referencing
         step in the DAG — error (the reference would be undefined at
         runtime).
      3. The first attribute after the step name isn't in the step's
         declared/observed output schema — warning (we may have the
         wrong shape; observed schemas are more authoritative).
    """
    path = f"playbooks[{pi}]"
    # Skip Jinja path analysis on cyclic graphs — predecessor sets are
    # unreliable for cycles and produce spurious reachability errors.
    # _check_graph (always called before this) reports the cycle itself.
    if _has_cycle(pb):
        return
    by_jinja_key: dict[str, Step] = {}
    for s in pb.steps:
        sname = s.name or s.id
        by_jinja_key[sname.replace(" ", "_")] = s

    # Reachability: which step ids could have run before each step?
    preds = _compute_predecessors(pb)
    id_by_jinja_key = {k: v.id for k, v in by_jinja_key.items()}

    # `vars.steps.input` is also a valid alias on some FSR versions;
    # treat the literal token 'input' as never-a-step.
    for si, s in enumerate(pb.steps):
        spath = f"{path}.steps[{si}]"
        for sub, val in _walk_strings(s.arguments):
            for jm in _JINJA_EXPR_RE.finditer(val):
                expr = jm.group(1)
                for m in _VARS_STEPS_RE.finditer(expr):
                    key = m.group(1)
                    rest = m.group(2) or ""
                    target = by_jinja_key.get(key)
                    if target is None:
                        # Don't flag references to steps that exist with the
                        # same name but different casing/spaces — emitter
                        # already collisions-checks. Just unknown ones.
                        suggestion = _closest_step(key, by_jinja_key.keys())
                        errors.append(CompileError(
                            code=ErrorCode.BAD_VALUE,
                            message=(f"Jinja reference vars.steps.{key}{rest} "
                                     f"in step {s.id!r}: no step with "
                                     f"jinja-key {key!r} in this playbook"),
                            path=f"{spath}.arguments.{sub}",
                            near=suggestion,
                            suggestion=(f"did you mean vars.steps.{suggestion}?"
                                        if suggestion else None),
                            severity="error",
                        ))
                        continue
                    # Reachability: target must be able to run *before* s.
                    # Self-reference is always fine (e.g. delay step looking
                    # at its own status).
                    target_id = id_by_jinja_key.get(key)
                    if target_id and target_id != s.id:
                        if target_id not in preds.get(s.id, set()):
                            # Suggest steps that ARE reachable.
                            reachable_keys = sorted(
                                k for k, v in id_by_jinja_key.items()
                                if v in preds.get(s.id, set())
                            )[:5]
                            errors.append(CompileError(
                                code=ErrorCode.BAD_VALUE,
                                message=(
                                    f"Jinja reference vars.steps.{key}{rest} "
                                    f"in step {s.id!r}: step {key!r} cannot "
                                    f"run before {s.id!r} in any execution "
                                    "path; the reference would be undefined "
                                    "at runtime"),
                                path=f"{spath}.arguments.{sub}",
                                suggestion=(
                                    f"available predecessors: "
                                    f"{', '.join(reachable_keys)}"
                                    if reachable_keys else None),
                                severity="error",
                            ))
                            continue
                    # Validate first attribute against known top-level keys.
                    if not rest.startswith("."):
                        continue
                    first_attr = rest.lstrip(".").split(".", 1)[0].split("[", 1)[0]
                    if not first_attr:
                        continue
                    keys = _step_output_top_keys(target)
                    if keys is None or first_attr in keys:
                        continue
                    # FSR exposes `status`/`result` on every step in addition
                    # to the handler's payload — never flag those.
                    if first_attr in {"status", "result", "id", "name",
                                      "uuid", "@id", "@type", "step_id"}:
                        continue
                    valid = sorted(keys)[:8]
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(f"Jinja reference vars.steps.{key}.{first_attr} "
                                 f"in step {s.id!r}: {first_attr!r} is not in "
                                 f"step {target.id!r}'s output keys "
                                 f"({', '.join(valid)})"),
                        path=f"{spath}.arguments.{sub}",
                        severity="warning",
                    ))


def _check_malformed_jinja(pb: Playbook, pi: int,
                           errors: list[CompileError]) -> None:
    """Catch syntactically broken Jinja delimiters — an unclosed `{{` (or a
    stray `}}`, `{%`/`%}` mismatch). These compile clean today (the
    `{{ ... }}` extractor simply doesn't match an unterminated expression),
    so the only signal is a runtime template error. A delimiter-balance scan
    has effectively no false positives on playbook args (literal `}}` inside
    a value is vanishingly rare) and turns that runtime failure into an
    authoring-time error."""
    path = f"playbooks[{pi}]"
    for si, s in enumerate(pb.steps):
        for sub, val in _walk_strings(s.arguments):
            for open_tok, close_tok, label in (
                ("{{", "}}", "expression"), ("{%", "%}", "statement")):
                n_open = val.count(open_tok)
                n_close = val.count(close_tok)
                if n_open == n_close:
                    continue
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"malformed Jinja {label} in step {s.id!r}: "
                             f"{n_open} {open_tok!r} but {n_close} "
                             f"{close_tok!r} — the template is unbalanced and "
                             f"will fail at runtime"),
                    path=f"{path}.steps[{si}].arguments.{sub}",
                    suggestion=(f"close every {open_tok} with a matching "
                                f"{close_tok}"),
                    severity="error",
                ))


# `vars.<name>` top-level reference. Captures the first segment only.
_VARS_TOPLEVEL_RE = re.compile(r"\bvars\.([A-Za-z_][A-Za-z0-9_]*)")


def _check_undefined_vars(pb: Playbook, pi: int,
                          errors: list[CompileError]) -> None:
    """Flag `{{ vars.<name> }}` references whose `<name>` is never defined —
    not an FSR runtime key, not the loop binding, and not produced by any
    SetVariable in the playbook. A typo'd local var silently evaluates empty
    at runtime, so this is the only signal the author gets.

    Emitted as a *warning* (not a hard block): vars are playbook-global and
    can in principle be seeded by sources we don't fully model, so we surface
    the suspicion without failing ready_to_push on a possible false positive.
    """
    path = f"playbooks[{pi}]"
    # Runtime-provided + structural keys that are always legitimate to read.
    defined: set[str] = set(_RESERVED_VARS_KEYS)
    # `vars.item` (+ `vars.item.<field>`) is the per-iteration loop binding.
    defined.add("item")
    # Every SetVariable-defined name, gathered across the whole playbook
    # (vars are global; definition can lexically follow the read).
    for s in pb.steps:
        if s.type == "set_variable" and isinstance(s.arguments, dict):
            keys = _step_output_top_keys(s)
            if keys:
                defined |= keys
    for si, s in enumerate(pb.steps):
        for sub, val in _walk_strings(s.arguments):
            for jm in _JINJA_EXPR_RE.finditer(val):
                expr = jm.group(1)
                for m in _VARS_TOPLEVEL_RE.finditer(expr):
                    name = m.group(1)
                    if name in defined:
                        continue
                    suggestion = _closest_step(name, defined)
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(f"Jinja reference vars.{name} in step "
                                 f"{s.id!r}: {name!r} is never defined by a "
                                 f"SetVariable and is not a runtime key; it "
                                 f"will evaluate empty at runtime"),
                        path=f"{path}.steps[{si}].arguments.{sub}",
                        near=suggestion,
                        suggestion=(f"did you mean vars.{suggestion}?"
                                    if suggestion else
                                    "define it with a set_variable step first"),
                        severity="warning",
                    ))


def _closest_step(needle: str, hay) -> str | None:
    import difflib
    matches = difflib.get_close_matches(needle, list(hay), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _check_reserved_names(pb: Playbook, pi: int,
                          errors: list[CompileError]) -> None:
    """Catch SetVariable/parameters/step names that collide with FSR's
    runtime vars context. A SetVariable named `result` silently shadows
    `vars.result` (the last step's auto-result). A step named `for` or
    `class` produces a `vars.steps.for` key that breaks attribute-style
    Jinja access.
    """
    path = f"playbooks[{pi}]"

    # Playbook parameter names → vars.input.params.<name>; collisions with
    # `records` (the other key under vars.input) are silently shadowed.
    for j, p in enumerate(pb.parameters):
        if p in {"records"}:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"playbook parameter {p!r} shadows "
                         f"vars.input.records (the trigger record list)"),
                path=f"{path}.parameters[{j}]",
                severity="error",
            ))

    for si, s in enumerate(pb.steps):
        spath = f"{path}.steps[{si}]"
        # Step names → vars.steps.<name> Jinja keys. Spaces become
        # underscores; case is preserved.
        sname = s.name or s.id
        jinja_key = sname.replace(" ", "_")
        if jinja_key.lower() in _INVALID_JINJA_KEY_TOKENS:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"step name {sname!r} normalises to Jinja key "
                         f"{jinja_key!r}, which is a reserved keyword — "
                         f"`vars.steps.{jinja_key}` won't parse"),
                path=f"{spath}.name",
                severity="error",
            ))
        if jinja_key and not (jinja_key[0].isalpha() or jinja_key[0] == "_"):
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"step name {sname!r} starts with {jinja_key[0]!r}; "
                         f"Jinja attribute access `vars.steps.{jinja_key}` "
                         f"requires identifier-style names (letter or _)"),
                path=f"{spath}.name",
                severity="error",
            ))

        # SetVariable arg names → vars.<name>. Collisions with reserved
        # top-level keys silently overwrite the FSR-provided value.
        if s.type == "set_variable" and isinstance(s.arguments, dict):
            # Both shapes: flat dict {name: value} OR arg_list:[{name,value}]
            names: list[tuple[str, str]] = []  # (var_name, sub-path)
            if isinstance(s.arguments.get("arg_list"), list):
                for k, item in enumerate(s.arguments["arg_list"]):
                    if isinstance(item, dict) and "name" in item:
                        names.append((item["name"], f"arg_list[{k}].name"))
            else:
                for k in s.arguments:
                    if k in {"step_variables"}:  # framework key, not a var
                        continue
                    names.append((k, k))
            # Reserved-name collisions are auto-renamed in resolver
            # (_auto_rename_reserved_set_var_keys) which emits a warning.
            # No re-check here — the auto-renamer guarantees they're gone.


def _check_graph(pb: Playbook, pi: int, errors: list[CompileError]) -> None:
    """Graph-level lint: cycles, unreachable steps, decision branch
    coverage. Targeting non-existent step ids is already caught by
    resolver._check_routing (UNKNOWN_NEXT_STEP)."""
    path = f"playbooks[{pi}]"
    if not pb.steps:
        return
    by_id: dict[str, object] = {s.id: s for s in pb.steps}
    trigger_id = pb.trigger_step_id
    if not trigger_id:
        # First step whose type starts with 'start' is the canonical fallback.
        for s in pb.steps:
            if s.type.startswith("start"):
                trigger_id = s.id
                break
    if trigger_id is None or trigger_id not in by_id:
        return  # NO_TRIGGER already reported

    # 1. Reachability: BFS from trigger.
    reachable: set[str] = set()
    frontier = [trigger_id]
    while frontier:
        sid = frontier.pop()
        if sid in reachable:
            continue
        reachable.add(sid)
        s = by_id.get(sid)
        if s is None:
            continue
        for nxt in _step_outgoing(s):
            if nxt not in reachable and nxt in by_id:
                frontier.append(nxt)
    for si, s in enumerate(pb.steps):
        if s.id not in reachable:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"step {s.id!r} ({s.name or s.type}) is unreachable "
                         f"from the trigger — no step's next/branches "
                         f"point to it"),
                path=f"{path}.steps[{si}]",
                severity="warning",
            ))

    # 2. Cycles: directed-graph DFS with grey/black colouring.
    WHITE, GREY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in by_id}
    cycle_reported: set[tuple[str, str]] = set()

    def dfs(sid: str, stack: list[str]) -> None:
        s = by_id.get(sid)
        if s is None:
            return
        color[sid] = GREY
        stack.append(sid)
        for nxt in _step_outgoing(s):
            if nxt not in by_id:
                continue
            if color.get(nxt) == GREY:
                # Back-edge — found a cycle. Report once per (src, dst) pair.
                key = (sid, nxt)
                if key in cycle_reported:
                    continue
                cycle_reported.add(key)
                # Trim the stack to the cycle.
                if nxt in stack:
                    cycle = stack[stack.index(nxt):] + [nxt]
                else:
                    cycle = [nxt, sid, nxt]
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"cycle in playbook {pb.name!r}: "
                             f"{' → '.join(cycle)}; FSR will not loop, "
                             f"the run will stall or error"),
                    path=f"{path}.steps",
                    severity="error",
                ))
            elif color.get(nxt) == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[sid] = BLACK

    dfs(trigger_id, [])

    # 3. Decision branch coverage + per-condition coherence. Rules mined
    # from the live FSR corpus (see MI_DECISION_VALIDATION_AUDIT.md §8):
    #   - every conditions[].option needs a branch target (s.branches or
    #     a default `next:`),
    #   - non-default entries MUST have both `option` and `condition`,
    #   - default entries (default: true) MUST omit `condition` and may
    #     omit `option`,
    #   - at most one entry may be marked default (warn if zero).
    for si, s in enumerate(pb.steps):
        if s.type != "decision":
            continue
        args = s.arguments if isinstance(s.arguments, dict) else {}
        conds = args.get("conditions") or []
        if not isinstance(conds, list):
            continue
        option_labels: list[str] = []
        n_default = 0
        for ci, c in enumerate(conds):
            if not isinstance(c, dict):
                continue
            cpath = f"{path}.steps[{si}].arguments.conditions[{ci}]"
            is_default = bool(c.get("default"))
            if is_default:
                n_default += 1
                if c.get("condition"):
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(
                            f"decision {s.id!r}: default branch must not "
                            f"carry a `condition:` (defaults fire when "
                            f"every other condition is false)"
                        ),
                        path=f"{cpath}.condition",
                        severity="error",
                    ))
            else:
                if not c.get("option"):
                    errors.append(CompileError(
                        code=ErrorCode.MISSING_FIELD,
                        message=(
                            f"decision {s.id!r}: non-default branch is "
                            f"missing `option:` (button label)"
                        ),
                        path=f"{cpath}.option",
                        severity="error",
                    ))
                if not c.get("condition"):
                    errors.append(CompileError(
                        code=ErrorCode.MISSING_FIELD,
                        message=(
                            f"decision {s.id!r}: non-default branch is "
                            f"missing `condition:` (jinja expression)"
                        ),
                        path=f"{cpath}.condition",
                        severity="error",
                    ))
            if "option" in c:
                option_labels.append(c["option"])
        if n_default > 1:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"decision {s.id!r}: {n_default} branches marked "
                         f"`default: true`; FSR only fires the first one"),
                path=f"{path}.steps[{si}].arguments.conditions",
                severity="error",
            ))
        elif n_default == 0 and not s.next:
            # No `default: true` AND no step-level `next:` fall-through
            # means a false-condition run has no target. Either is fine
            # (8 live Decisions use the bare `next:` idiom); only warn
            # when neither is present.
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"decision {s.id!r}: no default/else branch and "
                         f"no fall-through `next:`; if every condition "
                         f"evaluates false the run will stall. Either "
                         f"add a branch with `default: true` or set "
                         f"`next:` on the decision step"),
                path=f"{path}.steps[{si}].arguments.conditions",
                severity="warning",
            ))
        for label in option_labels:
            if label not in s.branches and not s.next:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"decision {s.id!r}: option {label!r} has no "
                             f"branch target (add `branches: {{{label}: "
                             f"<step_id>}}` or a default `next:`)"),
                    path=f"{path}.steps[{si}].branches",
                    severity="error",
                ))
        # Stale branch keys (point to nothing in conditions list).
        for label in s.branches:
            if option_labels and label not in option_labels:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"decision {s.id!r}: branch label {label!r} is "
                             f"not in conditions[].option (typo? unused?)"),
                    path=f"{path}.steps[{si}].branches.{label}",
                    severity="warning",
                ))

    # 4. ManualInput branch coverage — same idea as decision: every
    # response_mapping option needs a branch target. Live data shows
    # ~4% of options are intentionally terminal (button ends the run);
    # warn-only for those if the prompt has multiple options.
    for si, s in enumerate(pb.steps):
        if s.type != "manual_input":
            continue
        args = s.arguments if isinstance(s.arguments, dict) else {}
        rmap = args.get("response_mapping") or {}
        if not isinstance(rmap, dict):
            continue
        opts = rmap.get("options") or []
        if not isinstance(opts, list):
            continue
        labels: list[str] = []
        n_primary = 0
        for oi, o in enumerate(opts):
            if not isinstance(o, dict):
                continue
            opath = f"{path}.steps[{si}].arguments.response_mapping.options[{oi}]"
            label = o.get("option")
            if not label:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message=(f"manual_input {s.id!r}: option is missing "
                             f"`option:` (button label)"),
                    path=f"{opath}.option",
                    severity="error",
                ))
                continue
            labels.append(label)
            if o.get("primary"):
                n_primary += 1
            has_target = bool(o.get("step_iri")) or label in s.branches or bool(s.next)
            if not has_target and len(opts) > 1:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"manual_input {s.id!r}: option {label!r} "
                             f"has no target — multi-button prompts where "
                             f"≥2 options end the run usually indicate "
                             f"forgotten wiring"),
                    path=f"{opath}.step_iri",
                    severity="warning",
                    suggestion=(f"add `next: <step_id>` on this option, "
                                f"or branches: {{{label}: <step_id>}} on the step"),
                ))
        if n_primary > 1:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(f"manual_input {s.id!r}: {n_primary} options "
                         f"marked `primary: true`; only one button can "
                         f"be the styled default"),
                path=f"{path}.steps[{si}].arguments.response_mapping.options",
                severity="error",
            ))
        # Soft check: branches keys that don't match any option label.
        for label in s.branches:
            if labels and label not in labels:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"manual_input {s.id!r}: branch label "
                             f"{label!r} doesn't match any option "
                             f"(typo? unused?)"),
                    path=f"{path}.steps[{si}].branches.{label}",
                    severity="warning",
                ))


def validate(collection: Collection) -> list[CompileError]:
    errors: list[CompileError] = []

    # Workflow names must be unique within a collection (FSR Doctrine
    # constraint: UniqueConstraint on (name, collection) — see
    # Entity/Workflow/Workflow.php). Catch this at compile time rather
    # than letting FSR's import_jobs return an opaque error.
    seen_names: dict[str, int] = {}
    for pi, pb in enumerate(collection.playbooks):
        if pb.name in seen_names:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=f"duplicate playbook name {pb.name!r} (FSR enforces unique workflow names per collection)",
                path=f"playbooks[{pi}].name",
            ))
        seen_names[pb.name] = pi

    for pi, pb in enumerate(collection.playbooks):
        path = f"playbooks[{pi}]"
        _check_graph(pb, pi, errors)
        _check_reserved_names(pb, pi, errors)
        _check_jinja_paths(pb, pi, errors)
        _check_malformed_jinja(pb, pi, errors)
        _check_undefined_vars(pb, pi, errors)

        # Step names must be unique within a playbook. FSR's Jinja runtime
        # exposes step output at `vars.steps.<Name_with_underscores>`, so
        # two steps sharing a name (or sharing an underscored form, e.g.
        # "Step One" and "Step_One") silently overwrite each other in the
        # context. The compiler catches this since FSR's importer doesn't.
        step_seen_names: dict[str, int] = {}
        step_seen_keys: dict[str, int] = {}
        for si, s in enumerate(pb.steps):
            sname = s.name or s.id
            sp = f"{path}.steps[{si}].name"
            if sname in step_seen_names:
                errors.append(CompileError(
                    code=ErrorCode.BAD_VALUE,
                    message=(f"duplicate step name {sname!r} in playbook "
                             f"{pb.name!r} (already used by step #"
                             f"{step_seen_names[sname]}); names must be "
                             f"unique — vars.steps.<name> would collide "
                             f"silently at runtime"),
                    path=sp,
                ))
            else:
                step_seen_names[sname] = si
            jinja_key = sname.replace(" ", "_")
            if jinja_key in step_seen_keys and step_seen_keys[jinja_key] != si:
                # Skip if it's already flagged as a literal duplicate above.
                if sname not in step_seen_names or step_seen_names[sname] != step_seen_keys[jinja_key]:
                    errors.append(CompileError(
                        code=ErrorCode.BAD_VALUE,
                        message=(f"step name {sname!r} normalises to Jinja key "
                                 f"{jinja_key!r}, which collides with step #"
                                 f"{step_seen_keys[jinja_key]}'s name; rename one"),
                        path=sp,
                    ))
            else:
                step_seen_keys[jinja_key] = si

        # A playbook's trigger can be `start` (manual / abstract_trigger),
        # `record_action`, `start_on_create`, `start_on_update`,
        # `start_on_delete`, or `api_endpoint` (the invokable
        # `POST /api/triggers/1/<route>` trigger). Exactly one trigger step
        # required, of any of those flavours.
        TRIGGER_TYPES = {"start", "start_on_create", "start_on_update",
                         "start_on_delete", "api_endpoint"}
        starts = [s for s in pb.steps if s.type in TRIGGER_TYPES]
        if not starts:
            errors.append(CompileError(
                code=ErrorCode.NO_TRIGGER,
                message=f"playbook {pb.name!r} has no 'start' step",
                path=path,
                suggestion="add `- id: start\\n  type: start` as the first step",
            ))
        elif len(starts) > 1:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=f"playbook {pb.name!r} has {len(starts)} 'start' steps; exactly one is required",
                path=path,
            ))
    return errors
