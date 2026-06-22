"""Typed model for field-based-trigger `when:` filters.

Grounded in live FSR wire shapes pulled from box 198.51.100.205
(`tooling/probes/fixtures/live_trigger_filter_shapes.json`). The designer
stores five filter shapes inside `arguments.fieldbasedtrigger.filters`:

  * primitive — scalar `eq`/`neq`/`like`/…:
      {type, field, value, operator, _operator}
  * object    — picklist / IRI-backed field:
      {type, field, value:<iri>, _value:{@id, display, itemValue}, operator}
  * array     — tags / multi-value (`in`/`in_all`):
      {type, field, value:[iri…], module, operator, template,
       OPERATOR_KEY, previousOperator, previousTemplate}
  * datetime  — date field (`isnull`/…):
      {type, field, value, operator}
  * changed   — update-only "field changed" sentinel (object-typed)

and a filter entry can itself be a nested `{logic, filters:[…]}` group —
the AND/OR nesting the old flat `_expand_when` could not author (25 such
groups live in the corpus).

`WhenGroup`/`WhenLeaf` enforce the *structure* (known keys via
`extra="forbid"`, value types, recursive nesting). The operator semantics —
alias rewriting, the `contains → like %…%` rewrite, the bare-`like` wildcard
wrap, the `changed`-only-on-update rule — live in `expand_when`, which walks
the validated tree with precise `filters[i].op` paths so warning/error
messages stay byte-identical to the imperative normalizer they replace.
"""
from __future__ import annotations

import difflib
from typing import Annotated, Any, Optional, Union

from pydantic import AliasChoices, ConfigDict, Discriminator, Field, Tag

from ..errors import CompileError, ErrorCode
from .base import StrictArgs
from ._bridge import validate_args

# ── operator vocabulary (single source of truth; normalizers re-imports) ──
# Valid operators FSR's field-based-trigger evaluator honors. A wrong operator
# does not error at deploy — the trigger silently never matches — so unknowns
# are rejected at compile time. `changed` is update-only (enforced below).
_TRIGGER_OPS: frozenset[str] = frozenset({
    "eq", "neq", "gt", "gte", "lt", "lte",
    "isnull", "isnotnull",
    "in", "nin", "in_all",
    # `like`/`notlike` = case-insensitive SQL-LIKE on a scalar. `contains`/
    # `notcontains` are accepted authoring sugar but rewrite to `like`/`notlike`
    # with a `%…%`-wrapped value (a raw scalar `contains` never fires — the
    # query layer 400s it). Live-verified via probe_trigger_matrix.
    "like", "notlike",
    "contains", "notcontains",
    "changed",
})
# Token-only aliases (friendly / near-miss spellings → canonical token).
# Auto-applied with a warning; no value change.
_TRIGGER_OP_ALIASES: dict[str, str] = {
    "equals": "eq", "==": "eq", "=": "eq", "is": "eq",
    "!=": "neq", "ne": "neq", "<>": "neq",
    "not_equals": "neq", "notequals": "neq", "not_equal": "neq",
    "greater_than": "gt", ">": "gt",
    "greater_than_equals": "gte", "greater_or_equal": "gte", ">=": "gte",
    "less_than": "lt", "<": "lt",
    "less_than_equals": "lte", "less_or_equal": "lte", "<=": "lte",
    "not_in": "nin", "notin": "nin",
    "in_list": "in", "is_in_list": "in", "is_one_of": "in",
    "is_not_in_list": "nin", "is_not_one_of": "nin",
    "is_null": "isnull", "null": "isnull", "is_empty": "isnull",
    "is_not_null": "isnotnull", "not_null": "isnotnull", "exists": "isnotnull",
    "matches_pattern": "like", "matches": "like", "ilike": "like",
    "does_not_match": "notlike", "does_not_match_pattern": "notlike",
    "not_like": "notlike",
    "is_changed": "changed", "has_changed": "changed",
}
# Pattern-producing rewrites: op → (canonical operator, wildcard wrap mode).
# FSR has no scalar startswith/endswith/contains operator — they are all `like`
# (or `notlike`) with the value wrapped. Live-verified. Auto-applied + warned.
_TRIGGER_OP_REWRITE: dict[str, tuple[str, str]] = {
    "contains": ("like", "both"), "icontains": ("like", "both"),
    "notcontains": ("notlike", "both"), "not_contains": ("notlike", "both"),
    "does_not_contain": ("notlike", "both"),
    "startswith": ("like", "prefix"), "starts_with": ("like", "prefix"),
    "endswith": ("like", "suffix"), "ends_with": ("like", "suffix"),
}


def _wrap_like_value(val, mode: str):
    """Wrap a plain substring for SQL LIKE. Returns (new_value, changed).
    Leaves values that already contain `%`/`_` wildcards untouched."""
    if not isinstance(val, str) or not val:
        return val, False
    if "%" in val or "_" in val:
        return val, False
    if mode == "prefix":
        return f"{val}%", True
    if mode == "suffix":
        return f"%{val}", True
    return f"%{val}%", True


# ── typed structure ───────────────────────────────────────────────────────
class WhenLeaf(StrictArgs):
    """One filter condition. Friendly authoring keys (`field`, `op`, `value`)
    plus the wire-passthrough keys real exported filters carry, so a
    decompiled `fieldbasedtrigger` round-trips through the same model.

    `extra="forbid"` catches authoring typos (`feild:`, `opp:`) structurally.
    `type` is the wire filter type hint — None/primitive emit the scalar shape;
    object/array/datetime emit the IRI-backed shapes (live-grounded).
    """

    field: Optional[str] = None
    op: str = Field(default="eq", validation_alias=AliasChoices("op", "operator"))
    value: Any = None
    type: Optional[str] = None
    # Wire-passthrough (object/array shapes + the `_operator` mirror).
    value_meta: Optional[dict] = Field(default=None, alias="_value")
    operator_wire: Optional[str] = Field(default=None, alias="_operator")
    module: Optional[str] = None
    template: Optional[str] = None
    operator_key: Optional[str] = Field(default=None, alias="OPERATOR_KEY")
    previous_operator: Optional[str] = Field(default=None, alias="previousOperator")
    previous_template: Optional[str] = Field(default=None, alias="previousTemplate")


def _filter_kind(v: Any) -> str:
    """Discriminate a `filters[]` entry: a nested group (has `logic`/`filters`)
    vs. a leaf condition. Routing each entry to exactly one model keeps the
    validation errors clean (no untagged-union explosion across both branches)."""
    if isinstance(v, WhenGroup):
        return "group"
    if isinstance(v, dict) and ("filters" in v or "logic" in v):
        return "group"
    return "leaf"


# Discriminated union so a malformed leaf reports one precise error
# (`filters[i].<key>`) instead of one per branch.
FilterItem = Annotated[
    Union[Annotated["WhenGroup", Tag("group")], Annotated["WhenLeaf", Tag("leaf")]],
    Discriminator(_filter_kind),
]


class WhenGroup(StrictArgs):
    """A logic group: `{logic: AND|OR, filters: [leaf | group, …]}`.

    `filters` is a recursive union — a nested group is itself a `WhenGroup`,
    which is the AND/OR nesting the flat expander could not author. `sort`/
    `limit` only appear on the top-level group in the wire output.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    logic: str = "AND"
    filters: list[FilterItem] = Field(default_factory=list)
    sort: list = Field(default_factory=list)
    limit: int = 30


WhenGroup.model_rebuild()


# ── normalization walk (op semantics + exact warning paths) ───────────────
def _normalize_op(
    orig_op: str, leaf_path: str, errors: list[CompileError],
) -> Optional[tuple[str, Optional[str]]]:
    """Resolve a friendly operator to a canonical one.

    Returns (canonical_op, wrap_mode) or None if the operator is invalid
    (a blocking error has been appended). Emits the same alias/rewrite
    warnings the imperative normalizer did, at `<leaf_path>.op`.
    """
    op = orig_op.lower()
    wrap: Optional[str] = None
    opath = f"{leaf_path}.op"
    if op in _TRIGGER_OP_REWRITE:
        op, wrap = _TRIGGER_OP_REWRITE[op]
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE, severity="warning",
            message=(f"operator {orig_op!r} has no scalar FSR equivalent "
                     f"— compiling to {op!r} with a {wrap}-wrapped "
                     f"`%` pattern (SQL LIKE)"),
            path=opath,
        ))
    elif op in _TRIGGER_OP_ALIASES:
        canon = _TRIGGER_OP_ALIASES[op]
        if canon != op:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE, severity="warning",
                message=f"operator {orig_op!r} → {canon!r}",
                path=opath,
            ))
        op = canon
    if op not in _TRIGGER_OPS:
        m = difflib.get_close_matches(op, sorted(_TRIGGER_OPS), n=1, cutoff=0.6)
        fix = m[0] if m else None
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(
                f"invalid trigger operator {orig_op!r} — not a valid "
                f"field-based-trigger operator (valid: "
                f"{', '.join(sorted(_TRIGGER_OPS))})"
            ),
            path=opath, near=fix,
            suggestion=(f"did you mean {fix!r}?" if fix else None),
        ))
        return None
    return op, wrap


def _leaf_to_filter(
    leaf: WhenLeaf, step_type: str, leaf_path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Build the FSR wire filter dict for one leaf (or None if invalid)."""
    if not leaf.field:
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message="filter requires `field:`",
            path=f"{leaf_path}.field",
        ))
        return None
    resolved = _normalize_op(str(leaf.op).strip(), leaf_path, errors)
    if resolved is None:
        return None
    op, wrap = resolved
    opath = f"{leaf_path}.op"

    if op == "changed":
        if step_type != "start_on_update":
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="`op: changed` only valid on start_on_update",
                path=opath,
            ))
            return None
        # Preserved byte-for-byte from the imperative normalizer. NOTE: the live
        # designer emits `_value: {"@id": null, …}`; the historical emitter omits
        # `@id`. Left as-is to keep emit byte-identical — see the fidelity TODO
        # in docs/plans/PLAYBOOK_PYDANTIC_TYPING_PLAN.md.
        return {
            "type": "object", "field": leaf.field, "value": None,
            "_value": {"display": "", "itemValue": ""},
            "operator": "changed",
        }

    # Advanced (live-grounded) wire shapes: when the author/decompiler sets an
    # explicit non-primitive `type`, emit that shape with the supplied
    # passthrough keys instead of forcing the scalar `primitive` form.
    wire_type = (leaf.type or "primitive").lower()
    if wire_type in ("object", "array", "datetime"):
        out: dict[str, Any] = {
            "type": wire_type, "field": leaf.field, "value": leaf.value,
            "operator": op,
        }
        if wire_type == "object":
            out["_value"] = leaf.value_meta or {
                "@id": leaf.value, "display": "", "itemValue": ""}
        if wire_type == "array":
            for k, v in (("module", leaf.module), ("template", leaf.template),
                         ("OPERATOR_KEY", leaf.operator_key),
                         ("previousOperator", leaf.previous_operator),
                         ("previousTemplate", leaf.previous_template)):
                if v is not None:
                    out[k] = v
        return out

    # Default: scalar primitive. `like`/`notlike` apply the LIKE wildcard wrap.
    emit_val = leaf.value
    if op in ("like", "notlike"):
        mode = wrap or "both"
        emit_val, changed = _wrap_like_value(leaf.value, mode)
        if changed and wrap is None:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE, severity="warning",
                message=(f"`{op}` value {leaf.value!r} has no `%`/`_` "
                         f"wildcard — auto-wrapped to {emit_val!r} so "
                         f"it substring-matches instead of matching "
                         f"exactly (which silently never fires)"),
                path=opath,
            ))
    return {
        "type": "primitive", "field": leaf.field, "value": emit_val,
        "operator": op, "_operator": leaf.operator_wire or op,
    }


def _group_to_dict(
    group: WhenGroup, step_type: str, path: str,
    errors: list[CompileError], *, top: bool,
) -> dict:
    """Walk a validated group into its FSR wire dict. Nested groups recurse
    and omit sort/limit (matching the live designer output)."""
    logic = str(group.logic).upper()
    if logic not in ("AND", "OR"):
        logic = "AND"
    out_filters: list[dict] = []
    for i, f in enumerate(group.filters):
        fpath = f"{path}.filters[{i}]"
        if isinstance(f, WhenGroup):
            out_filters.append(
                _group_to_dict(f, step_type, fpath, errors, top=False))
        else:
            wire = _leaf_to_filter(f, step_type, fpath, errors)
            if wire is not None:
                out_filters.append(wire)
    if top:
        return {"sort": list(group.sort), "limit": group.limit,
                "logic": logic, "filters": out_filters}
    return {"logic": logic, "filters": out_filters}


def expand_when(
    when: Any, step_type: str, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Compile a friendly `when:` block into a `fieldbasedtrigger` dict.

    Drop-in replacement for the imperative `_expand_when`: same friendly
    top-level messages, same per-leaf op warnings/errors, byte-identical
    output for the flat primitive/`changed` authoring path — plus typed
    structural validation (`extra="forbid"` catches key typos) and nested
    AND/OR group authoring the flat expander could not produce.
    """
    when_path = f"{path}.arguments.when"
    if not isinstance(when, dict):
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message="`when:` must be a mapping with logic/filters",
            path=when_path,
        ))
        return None
    if not isinstance(when.get("filters", []), list):
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message="`when.filters` must be a list",
            path=f"{when_path}.filters",
        ))
        return None
    group = validate_args(WhenGroup, when, when_path, errors)
    if group is None:
        return None
    return _group_to_dict(group, step_type, when_path, errors, top=True)
