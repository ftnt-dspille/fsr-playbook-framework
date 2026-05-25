"""Render-path analyzer — heuristic diagnostics over a step-through
trace (RENDER_PATH_VALIDATOR_PLAN.md Phase 3).

Pure data-in/data-out: takes the trace produced by
``mcp_server.step_through_playbook`` and returns a list of
``Diagnostic`` objects pinpointing data-access bugs that would surface
at runtime in FSR.

Initial v1 ships the three highest-ROI checks:

* **C1 unreachable_var_path** — `vars.steps.X.Y` where X isn't a step,
  or X comes after the consumer in the executed path.
* **C2 missing_key** — path key absent from the producer's output
  shape (downgraded to warning when provenance is `default_empty` so
  we don't over-warn on never-simulated steps).
* **C3 required_arg_empty** — rendered_args contains an empty/None
  value at a path the schema marks required. Schema is best-effort
  per step type; missing schema means the check skips silently.

Severity:
* ``error`` — almost certainly broken at runtime (wrong step name,
  unreachable path).
* ``warning`` — suspicious but defensible (missing key on a step
  whose output we couldn't fully simulate).
* ``info`` — stylistic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    kind: str  # "unreachable_var_path", "missing_key", "required_arg_empty", ...
    severity: str  # "error" | "warning" | "info"
    step_id: str
    path: str  # the vars.… path (or arg path) that failed the check
    location: str  # arguments.<...> dotted location of the offending template
    message: str
    suggestion: str = ""
    expected: Any = None
    actual: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def analyze(trace: list[dict[str, Any]],
            playbook: dict[str, Any] | None = None,
            *,
            picklist_validator: "callable | None" = None,
            ) -> list[Diagnostic]:
    """Run all heuristic checks against a step-through trace.

    ``playbook`` is the parsed YAML playbook dict (with ``steps``);
    used for ``required`` field detection on connector / record_crud
    steps when the trace alone doesn't carry schema. Optional —
    checks that need it skip cleanly when it's missing.
    """
    diagnostics: list[Diagnostic] = []

    # Index trace records by their FSR jinja key (name with spaces →
    # underscores) AND by step_id so consumers using either form land
    # on the producer.
    by_jkey: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []  # jinja keys in execution order
    for rec in trace:
        sid = rec.get("step_id", "")
        # FSR's runtime keys vars.steps.* off the step name (spaces →
        # underscores). The trace carries `name` since P3 so we don't
        # need the playbook tree to derive it. Index under both the
        # jkey AND the raw step_id so consumers using either form
        # land on the same record.
        name = rec.get("name") or sid
        jkey = name.replace(" ", "_")
        by_id[sid] = rec
        by_jkey[jkey] = rec
        if jkey != sid:
            by_jkey[sid] = rec
        rec["_jkey"] = jkey
        order.append(jkey)

    # Build "executed before" index for unreachable-path detection.
    # A reference vars.steps.X.Y on step S is unreachable if either X
    # isn't in the trace at all OR X appears AFTER S in `order`.
    pos: dict[str, int] = {jkey: i for i, jkey in enumerate(order)}

    diagnostics.extend(_c1_unreachable(trace, by_jkey, pos))
    diagnostics.extend(_c2_missing_key(trace, by_jkey))
    diagnostics.extend(_c3_required_empty(trace, playbook))
    if picklist_validator is not None:
        diagnostics.extend(_c4_picklist_drift(trace, picklist_validator))
    diagnostics.extend(_c6_index_non_list(trace, by_jkey))
    diagnostics.extend(_c9_loop_var_leak(trace, playbook))
    diagnostics.extend(_c10_dead_step(trace, by_jkey))
    return diagnostics


# ---------------------------------------------------------------------
# C1 unreachable_var_path
# ---------------------------------------------------------------------

def _c1_unreachable(trace: list[dict[str, Any]],
                    by_jkey: dict[str, dict[str, Any]],
                    pos: dict[str, int]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for i, rec in enumerate(trace):
        sid = rec.get("step_id", "")
        for ref in rec.get("consumed_paths", []):
            if ref.get("root") != "steps":
                continue
            producer = ref.get("source_step_id", "")
            if not producer:
                continue
            prod_rec = by_jkey.get(producer)
            if prod_rec is None:
                out.append(Diagnostic(
                    kind="unreachable_var_path",
                    severity="error",
                    step_id=sid,
                    path=ref["path"],
                    location=ref.get("location", ""),
                    message=(f"references step {producer!r} which "
                             "doesn't exist in this playbook"),
                    suggestion=(
                        "rename to an existing step, or remove the ref"),
                    extra={"missing_step": producer},
                ))
                continue
            # Producer exists but came after this consumer — runtime
            # will see an empty value because the step hasn't run yet.
            # Look up by the producer's canonical jkey, since the
            # consumer might have written it as the step_id form.
            prod_jkey = prod_rec.get("_jkey", producer)
            producer_pos = pos.get(prod_jkey, -1)
            if producer_pos > i:
                out.append(Diagnostic(
                    kind="unreachable_var_path",
                    severity="error",
                    step_id=sid,
                    path=ref["path"],
                    location=ref.get("location", ""),
                    message=(f"step {producer!r} executes AFTER this "
                             "step; its output isn't available yet"),
                    suggestion=("reorder steps so the producer runs "
                                "before the consumer"),
                    extra={"producer_step": producer,
                           "consumer_index": i,
                           "producer_index": producer_pos},
                ))
    return out


# ---------------------------------------------------------------------
# C2 missing_key
# ---------------------------------------------------------------------

def _c2_missing_key(trace: list[dict[str, Any]],
                    by_jkey: dict[str, dict[str, Any]]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for rec in trace:
        sid = rec.get("step_id", "")
        for ref in rec.get("consumed_paths", []):
            if ref.get("root") != "steps":
                continue
            producer = ref.get("source_step_id", "")
            prod_rec = by_jkey.get(producer)
            if not prod_rec:
                continue  # C1 catches this
            shape = prod_rec.get("output_shape") or {}
            segments = ref.get("segments") or []
            # segments[0] == 'steps', segments[1] == producer; from
            # segments[2:] onward we're walking into the output.
            sub_segments = segments[2:]
            missing_at = _check_path_against_shape(shape, sub_segments)
            if missing_at is None:
                continue
            # Downgrade severity when the producer's output shape
            # isn't trustworthy: either we couldn't simulate it
            # (default_empty) or it's gated by a runtime condition
            # that may have skipped it entirely.
            weak_provenance = (
                prod_rec.get("simulated_from") == "default_empty"
                or prod_rec.get("conditionally_executed") is True
            )
            severity = "warning" if weak_provenance else "error"
            top_keys = shape.get("top_keys") or shape.get("item_keys") or []
            out.append(Diagnostic(
                kind="missing_key",
                severity=severity,
                step_id=sid,
                path=ref["path"],
                location=ref.get("location", ""),
                message=(
                    f"key {missing_at!r} not in {producer!r}'s output "
                    f"(known keys: {top_keys[:8]})"),
                suggestion=_suggest_close_key(missing_at, top_keys),
                expected=top_keys,
                actual=missing_at,
                extra={
                    "producer_step": producer,
                    "producer_simulated_from":
                        prod_rec.get("simulated_from"),
                },
            ))
    return out


def _check_path_against_shape(shape: dict[str, Any],
                              segments: list[str]) -> str | None:
    """Walk the producer's output_shape against a list of attribute
    segments. Return the first segment that's missing, or None if the
    chain resolves cleanly. Stops walking once the shape becomes
    opaque (e.g. nested dict whose keys aren't recorded)."""
    cur = shape
    for seg in segments:
        if not isinstance(cur, dict):
            return None  # opaque; can't check further
        kind = cur.get("kind")
        if kind == "dict":
            top_keys = cur.get("top_keys") or []
            if not top_keys:
                return None  # empty / unknown — give it the benefit
            if seg not in top_keys:
                return seg
            # We don't recurse into nested shapes (only top-level
            # types are recorded); stop here without flagging deeper
            # segments.
            return None
        if kind == "list":
            # Bare attribute access on a list (no [N]) is suspicious
            # but C6 (Phase 5) handles index-into-non-list cleanly.
            item_keys = cur.get("item_keys") or []
            if item_keys and seg not in item_keys:
                return seg
            return None
        # scalar / null / unknown — opaque
        return None
    return None


def _suggest_close_key(needle: str, haystack: list[str]) -> str:
    """Return a small suggestion if the user probably typo'd a key."""
    if not haystack:
        return ""
    n = needle.lower()
    for k in haystack:
        if k.lower() == n:
            return f"did you mean {k!r}? (case mismatch)"
    # Substring match.
    near = [k for k in haystack if n in k.lower() or k.lower() in n]
    if near:
        return f"did you mean {near[0]!r}?"
    return ""


# ---------------------------------------------------------------------
# C3 required_arg_empty
# ---------------------------------------------------------------------

# Per-step-type required-arg lists. Keep narrow on purpose — only
# fields the FSR runtime will reject if blank. Schema-driven discovery
# (`get_op_schema`) comes in Phase 5; this is the deterministic baseline.
# Required-field entries can be either a single key (string) or a tuple
# of keys, where the tuple means "any of these satisfies the requirement"
# (e.g. update_record accepts either `module:` for the bulk-update path
# or `collection:` for the targeted-record path — see system_prompt §9).
_REQUIRED_FIELDS: dict[str, list] = {
    "connector": ["connector", "operation"],
    "create_record": ["module"],
    "update_record": [("module", "collection")],
    "find_records": ["module"],
    "delete_record": ["module"],
    "decision": ["conditions"],
    "manual_input": ["options"],
    "set_variable": ["arg_list"],
    "code_snippet": ["code"],
    "utils_delay": [],  # delay accepts seconds OR minutes OR hours OR days
}


# Step types whose canonical "required" fields live at the *step* level
# in friendly YAML (not under `arguments:`). The trace's `rendered_args`
# only captures `arguments.*` after Jinja substitution, so it's always
# empty for these fields and would false-positive every set_variable /
# decision / manual_input in the corpus. For these types we additionally
# check the step dict for the step-level alias.
#
# Map: type → list of (rendered_args_key, step_level_aliases_to_check).
# `vars` and `arg_list` are both accepted for set_variable (typed_walker
# already treats them as interchangeable at line 205).
_STEP_LEVEL_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "set_variable": {"arg_list": ("vars", "arg_list")},
    "decision":     {"conditions": ("conditions",)},
    "manual_input": {"options": ("options",)},
}


def _is_empty(v: Any) -> bool:
    if v is None: return True
    if isinstance(v, str): return v.strip() == ""
    if isinstance(v, (list, dict)): return len(v) == 0
    return False


def _c3_required_empty(trace: list[dict[str, Any]],
                       playbook: dict[str, Any] | None) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    # Index step dicts by id and by name so step-level alias lookups work
    # regardless of whether the trace's step_id is the parser's local
    # refname or the display name.
    steps_by_key: dict[str, dict[str, Any]] = {}
    for s in (playbook or {}).get("steps") or []:
        for k in (s.get("name"), s.get("id")):
            if k:
                steps_by_key[k] = s

    for rec in trace:
        stype = rec.get("type", "")
        required = _REQUIRED_FIELDS.get(stype, [])
        if not required:
            continue
        rendered = rec.get("rendered_args") or {}
        aliases = _STEP_LEVEL_ALIASES.get(stype, {})
        step_node = steps_by_key.get(rec.get("step_id", "")) \
            or steps_by_key.get(rec.get("name", ""))

        # Mode-aware skip: manual_input has two modes (default Behavior
        # vs InputBased). `options:` is required for Behavior; InputBased
        # uses `arguments.input.schema` and a separate per-step check
        # (tools_verify.py) covers the InputBased shape. Don't double-
        # flag here.
        if stype == "manual_input":
            mi_type = (rendered.get("type")
                       or (step_node or {}).get("arguments", {}).get("type")
                       or "").lower()
            if mi_type == "inputbased":
                continue

        for field_spec in required:
            # Tuple = any-of: requirement satisfied when ANY listed key
            # has a non-empty value in either rendered_args or (for
            # step-level types) the step dict.
            field_keys = (field_spec,) if isinstance(field_spec, str) else field_spec
            satisfied = False
            for field_name in field_keys:
                v = rendered.get(field_name)
                if _is_empty(v) and step_node is not None:
                    for alias in aliases.get(field_name, ()):
                        av = step_node.get(alias)
                        if not _is_empty(av):
                            v = av
                            break
                # Also accept the bare key on the step dict for any-of
                # alternatives (update_record's `collection:` is sometimes
                # at the step level, sometimes nested under arguments —
                # be liberal here).
                if _is_empty(v) and step_node is not None:
                    av = (step_node.get("arguments") or {}).get(field_name)
                    if not _is_empty(av):
                        v = av
                if not _is_empty(v):
                    satisfied = True
                    break
            if satisfied:
                continue
            # All any-of alternatives empty — emit diagnostic against
            # the first listed key for stable location.
            field_name = field_keys[0]
            v = None
            if True:
                out.append(Diagnostic(
                    kind="required_arg_empty",
                    severity="error",
                    step_id=rec.get("step_id", ""),
                    path=field_name,
                    location=f"arguments.{field_name}",
                    message=(f"required arg {field_name!r} is empty "
                             f"after render (got {v!r})"),
                    suggestion=("set a literal value or fix the jinja "
                                "expression that resolved to empty"),
                    expected="non-empty",
                    actual=v,
                ))
    return out


# ---------------------------------------------------------------------
# C4 picklist_drift
# ---------------------------------------------------------------------

def _c4_picklist_drift(trace: list[dict[str, Any]],
                       validator) -> list[Diagnostic]:
    """For every ``{{ 'PL' | picklist('value') }}`` reference, ask
    the validator (typically ``mcp_server.precheck_picklist_value``)
    whether the value resolves on the live FSR. Validator returns
    ``{ok: bool, suggestions?: list[str], message?: str}``.

    Skipped silently when no validator is supplied (offline mode).
    Cached per (picklist, value) so re-used pairs hit FSR once.
    """
    out: list[Diagnostic] = []
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in trace:
        for ref in rec.get("picklist_refs") or []:
            picklist = ref.get("picklist") or ""
            value = ref.get("value") or ""
            cache_key = (picklist, value)
            if cache_key not in cache:
                try:
                    cache[cache_key] = validator(picklist, value) or {}
                except Exception as exc:  # noqa: BLE001
                    cache[cache_key] = {
                        "ok": False, "code": "validator_error",
                        "message": str(exc),
                    }
            result = cache[cache_key]
            if result.get("ok"):
                continue
            # Don't flag when the validator itself couldn't reach FSR —
            # that's a connectivity issue, not a playbook bug.
            if result.get("code") in ("no_live_fsr", "validator_error"):
                continue
            suggestions = result.get("suggestions") or []
            sugg_text = (f"close matches: {', '.join(suggestions[:3])}"
                         if suggestions else "")
            out.append(Diagnostic(
                kind="picklist_drift",
                severity="error",
                step_id=rec.get("step_id", ""),
                path=f"{picklist}:{value}",
                location=ref.get("location", ""),
                message=(f"value {value!r} not found on picklist "
                         f"{picklist!r}"
                         + (f" — {result.get('message')}"
                            if result.get('message') else "")),
                suggestion=sugg_text,
                expected=suggestions,
                actual=value,
                extra={"picklist": picklist},
            ))
    return out


# ---------------------------------------------------------------------
# C6 index_into_non_list
# ---------------------------------------------------------------------

def _c6_index_non_list(trace: list[dict[str, Any]],
                       by_jkey: dict[str, dict[str, Any]]) -> list[Diagnostic]:
    """Flag `vars.steps.X.Y[N]` (or `[*]`) when the producer's
    output_shape says Y is a dict or scalar — indexing it raises
    `'dict' object is not subscriptable` at runtime. The render path
    walker records subscripts on `segments` as the literal `"[0]"`-
    shaped strings; we read them off the consumed_paths entry.
    """
    out: list[Diagnostic] = []
    for rec in trace:
        sid = rec.get("step_id", "")
        for ref in rec.get("consumed_paths", []):
            if ref.get("root") != "steps":
                continue
            segments = ref.get("segments") or []
            if not segments:
                continue
            # Find a subscript that isn't the first segment — `X[N]` on
            # the producer key itself is fine (means "first record of
            # the step's output list").
            sub_idx = next(
                (i for i, s in enumerate(segments)
                 if isinstance(s, str) and s.startswith("[")),
                None,
            )
            if sub_idx is None or sub_idx == 0:
                continue
            producer = ref.get("source_step_id", "")
            prod_rec = by_jkey.get(producer)
            if prod_rec is None:
                continue
            shape = prod_rec.get("output_shape")
            if not isinstance(shape, dict) or shape.get("kind") != "dict":
                continue
            # Walk to the attr being indexed.
            cur_top_keys = shape.get("top_keys") or []
            attr_chain = [s for s in segments[:sub_idx]
                          if isinstance(s, str) and not s.startswith("[")]
            target = attr_chain[-1] if attr_chain else None
            if target is None or target not in cur_top_keys:
                continue
            types = shape.get("types") or {}
            t = types.get(target, "")
            if t in {"list", "tuple"} or t == "":
                continue
            out.append(Diagnostic(
                kind="index_into_non_list",
                severity="warning",
                step_id=sid,
                path=ref["path"],
                location=ref.get("location", ""),
                message=(f"indexing into {target!r} which is "
                         f"{t!r} on {producer!r}, not a list — "
                         "this raises at runtime"),
                suggestion=("remove the [N] index, or fix the upstream "
                            "step to produce a list"),
                extra={"producer": producer, "attr": target,
                       "shape_kind": t},
            ))
    return out


# ---------------------------------------------------------------------
# C9 loop_var_leak
# ---------------------------------------------------------------------

def _c9_loop_var_leak(trace: list[dict[str, Any]],
                      playbook: dict[str, Any] | None) -> list[Diagnostic]:
    """`vars.item` (and `vars.item_index`) only exist inside the body
    of a `for_each` step. Authors sometimes paste a Jinja from a
    loop-internal step into a downstream consumer; that ref evaluates
    to undefined at runtime. Detect by scanning consumed_paths for
    `root == 'item'` and checking whether the step is inside an
    enclosing for_each scope.
    """
    if not playbook:
        return []
    steps = playbook.get("steps") or []
    # Build a set of step ids that live in a for_each body. The
    # simplified IR carries for_each at the loop step itself, so
    # everything that's downstream-while-still-on-this-iteration is
    # the loop body. Cheapest heuristic: any step whose own dict has
    # `for_each` set is itself a loop step (vars.item is valid in
    # *its* arguments); steps reachable only via the loop's `next`
    # are downstream of the loop — vars.item is not valid there.
    loop_step_ids = {
        s.get("id") or s.get("name") for s in steps
        if isinstance(s, dict) and s.get("for_each")
    }
    out: list[Diagnostic] = []
    for rec in trace:
        sid = rec.get("step_id", "")
        if sid in loop_step_ids:
            continue
        for ref in rec.get("consumed_paths", []):
            if ref.get("root") != "item":
                continue
            out.append(Diagnostic(
                kind="loop_var_leak",
                severity="error",
                step_id=sid,
                path=ref["path"],
                location=ref.get("location", ""),
                message=(f"references `vars.item` outside a for_each "
                         "body — undefined at runtime"),
                suggestion=("either move this step inside the for_each, "
                            "or refer to the for_each step's output "
                            "(`vars.steps.<loop>.<key>`) which collects "
                            "the per-iteration results"),
            ))
    return out


# ---------------------------------------------------------------------
# C10 dead_step
# ---------------------------------------------------------------------

def _c10_dead_step(trace: list[dict[str, Any]],
                   by_jkey: dict[str, dict[str, Any]]) -> list[Diagnostic]:
    """A step whose output is never read by any downstream consumer.
    Info-level only — sometimes intentional (logging, side-effect
    record_crud writes that the next step doesn't need). Skip step
    types whose primary value is the side effect: connector_op writes
    (unsafe), record_crud writes, code_snippet (assumed intentional),
    decision (no output), delay, manual_input (output by definition
    consumed downstream when used). Focus on set_variable + safe
    connector reads + find_records that nobody references.
    """
    skip_types = {
        "decision", "delay", "manual_input", "start",
        "code_snippet", "workflow_reference",
    }
    referenced_producers: set[str] = set()
    for rec in trace:
        for ref in rec.get("consumed_paths") or []:
            if ref.get("root") != "steps":
                continue
            src = ref.get("source_step_id")
            if src:
                referenced_producers.add(src)
    out: list[Diagnostic] = []
    for rec in trace:
        sid = rec.get("step_id", "")
        jkey = rec.get("_jkey", sid)
        if rec.get("type", "") in skip_types:
            continue
        # Don't flag connector ops that wrote to the world — those are
        # side-effect-positive even if their output isn't consumed.
        # `simulated_from == 'mock_result'` + status "unsafe_simulated"
        # is the agent's signal that this step was a destructive write.
        status = (rec.get("status") or "").lower()
        if status in {"unsafe_simulated", "simulated_destructive"}:
            continue
        if jkey in referenced_producers or sid in referenced_producers:
            continue
        # Only flag steps that *did* produce something — skipping
        # default-empty / errored frames keeps the noise down.
        if not rec.get("output"):
            continue
        out.append(Diagnostic(
            kind="dead_step",
            severity="info",
            step_id=sid,
            path="",
            location="",
            message=(f"step output is never consumed by a downstream "
                     "step — confirm this is intentional (logging / "
                     "side effect) or remove the step"),
            suggestion=("delete the step if you don't need its output; "
                        "or reference it from a later step's args"),
        ))
    return out


# ---------------------------------------------------------------------
# Convenience: dict form for the MCP tool layer.
# ---------------------------------------------------------------------

def diagnostics_dict(trace: list[dict[str, Any]],
                     playbook: dict[str, Any] | None = None,
                     *,
                     picklist_validator=None,
                     ) -> list[dict[str, Any]]:
    return [d.to_dict() for d in analyze(
        trace, playbook, picklist_validator=picklist_validator)]
