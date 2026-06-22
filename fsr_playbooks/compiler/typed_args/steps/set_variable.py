"""Typed model for `set_variable` step arguments.

By the time the resolver sees a set_variable step, the parser has converted
the author's top-level `vars:` mapping into the handoff shape
`{arg_list: [{name, value}, ...], **siblings}` (the parser rejects a raw
`arguments:` block on set_variable, so `arg_list` is always parser-built).
The reserved-keyword rename (`message` → `message_var`) runs earlier, in the
resolver's `RewriterMixin`, so it has already mutated `arg_list` before this
model is consulted.

The FSR wire shape is the *flat* `{name: value, ...}` mapping. `SetVariableArgs`
types that handoff shape; `expand_set_variable` walks it into the flat dict,
preserving `NormalizerMixin._normalize_set_variable_args`' behaviour
byte-for-byte (same output, same per-entry guard message/path, same
leave-unchanged early-return).

This is the first per-step-type model (Phase 2). It mirrors the trigger
layer's split: the pydantic model owns *structure*, a small walk owns the
semantic transform + precise CompileError paths.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict, Field

from ...errors import CompileError, ErrorCode
from ..base import StrictArgs
from .._bridge import validate_args


class ArgListEntry(StrictArgs):
    """One `{name, value}` assignment from the parser's `vars:` conversion.

    `extra="allow"` because only `name`/`value` are consumed — any stray key
    on an entry is ignored, matching the imperative normalizer (which read
    `item["name"]` / `item.get("value", "")` and dropped the rest). `name`
    and `value` are `Any`: a YAML mapping key can be non-string, and the
    legacy code used it verbatim as the flat-dict key.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: Any = None
    value: Any = ""


class SetVariableArgs(StrictArgs):
    """Typed view of a set_variable step's post-parser arguments.

    `arg_list` is the parser handoff; every other key is a sibling that
    survives into the flat wire dict (e.g. `step_variables`, `mock_result`,
    `condition`). `extra="allow"` because variable names — and those
    siblings — are arbitrary author-chosen keys.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    arg_list: list[ArgListEntry] = Field(default_factory=list)


def expand_set_variable(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Unwrap a set_variable step's `arg_list` into the flat wire dict.

    Drop-in replacement for the imperative unwrap in
    `_normalize_set_variable_args`: returns the flat `{**vars, **siblings}`
    dict on success, or ``None`` to signal "leave step.arguments unchanged"
    — exactly when the legacy code took its early `return` (no `arg_list`,
    a non-list `arg_list`, or a malformed entry). Sibling keys win over a
    same-named variable, matching the legacy `{**unwrapped, **siblings}`.
    """
    if not isinstance(args, dict) or not isinstance(args.get("arg_list"), list):
        return None
    apath = f"{path}.arguments"
    # Per-entry guard — preserved byte-for-byte (message + path + the
    # leave-unchanged early-return). Defensive: the parser only ever builds
    # well-formed `{name, value}` entries, but decompile/pull paths can hand
    # us a raw IR, so keep the check.
    for i, item in enumerate(args["arg_list"]):
        if not isinstance(item, dict) or "name" not in item:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message="arg_list entries must be {name, value} mappings",
                path=f"{apath}.arg_list[{i}]",
            ))
            return None
    model = validate_args(SetVariableArgs, args, apath, errors)
    if model is None:
        return None
    unwrapped = {e.name: e.value for e in model.arg_list}
    siblings = {k: v for k, v in args.items() if k != "arg_list"}
    return {**unwrapped, **siblings}
