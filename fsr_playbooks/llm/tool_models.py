"""Argument rules that sit beside each tool's advertised `input_schema`.

The schema is the ONE contract for a tool's arguments: it is built from the
function's typed signature (or a hand-written override), the model is shown it,
and `arg_gate` checks every call against it in dispatch. Two pydantic copies of
the same signatures used to re-check the call (one here, one in the connector);
replayed over 34,336 recorded calls they refused 6 that the schema passed, and
each of those was a gap in the schema, now closed at its source (a Literal, a
typed union).

What remains here is what a JSON schema cannot say:

  * `coerce_scalar_args` -- lossless repair of the strings some providers send
    for every argument, keyed on the schema;
  * `CROSS_FIELD_RULES` -- rules across arguments (get_record needs an iri, or a
    module plus an id).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

# Distinguishes "no coercion applies" from a legitimately coerced falsy value
# (False, 0, 0.0, [], {}) -- a plain `if coerced:` check would drop exactly the
# `probe="False" -> False` case this layer exists to fix.
_MISSING = object()


def _get_record_identifies_one(args: dict[str, Any]) -> str | None:
    if args.get("iri") or (args.get("module")
                           and (args.get("uuid") or args.get("record_id"))):
        return None
    return ("identify the record via `iri` alone, or `module` plus "
            "`uuid`/`record_id` -- e.g. "
            'get_record(iri="/api/3/alerts/<uuid>") or '
            'get_record(module="alerts", uuid="<uuid>"). '
            "get_record fetches ONE record -- to find records by a field or "
            "relationship (e.g. every step on a device), use "
            "search_module_records(module=..., filters={...}).")


#: tool -> rule over the (coerced, schema-valid) arguments: None, or why the
#: call cannot identify what it acts on.
CROSS_FIELD_RULES: dict[str, Callable[[dict[str, Any]], str | None]] = {
    "get_record": _get_record_identifies_one,
}


# Exact spellings only. A model that means False writes one of these; anything
# else ("maybe", "0.0", "") is NOT a boolean we are entitled to invent, and is
# left alone so validation or the tool body can reject it on its own terms.
_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})
_FALSE_STRINGS = frozenset({"false", "0", "no", "off"})

_INT_RE = re.compile(r"^[+-]?\d+$")


def _declared_type(prop: dict[str, Any], schema: dict[str, Any] | None,
                   _depth: int = 0) -> Any:
    """The one JSON type `prop` declares, following what pydantic/FastMCP MCP
    servers emit for a nested model: a local `$ref` with no `type` (FortiSIEM's
    `params`), a `$defs` entry with `properties` but no `type`, and
    `anyOf: [X, null]` for an optional one. None when the declared shape is
    ambiguous -- including any member that permits a string."""
    if _depth > 8 or not isinstance(prop, dict):
        return None
    ref = prop.get("$ref")
    if isinstance(ref, str):
        if not ref.startswith("#/"):
            return None
        node: Any = schema or {}
        for part in ref[2:].split("/"):
            node = node.get(part) if isinstance(node, dict) else None
        return _declared_type(node, schema, _depth + 1)
    jtype = prop.get("type")
    if jtype is not None:
        return jtype
    if isinstance(prop.get("properties"), dict):
        return "object"
    members = prop.get("anyOf") or prop.get("oneOf")
    if isinstance(members, list):
        types = {_declared_type(m, schema, _depth + 1) for m in members}
        types.discard("null")
        if len(types) == 1:
            only = types.pop()
            return only if isinstance(only, str) else None
    return None


def coerce_scalar_args(schema: dict[str, Any] | None,
                       args: dict[str, Any]) -> dict[str, Any]:
    """Return `args` with string scalars coerced to the types `schema` declares.

    Keyed on the tool's JSON Schema -- i.e. the contract we handed the model --
    so every registered tool is covered with no second list to keep in step.

    **Why this is not the model's problem to solve.** Some providers emit every
    argument as a string (`{"limit": "25", "probe": "False"}`) regardless of the
    declared schema. Two failure modes follow, and the quiet one is worse:

    - ``limit="25"`` reaches ``actions[:limit]`` → *"slice indices must be
      integers"*. Loud, and the model can often recover.
    - ``probe="False"`` is a NON-EMPTY string, so ``if probe:`` is **True**.
      The call runs with the opposite of the requested behaviour, returns
      plausible output, and nothing anywhere reports a problem.

    Conservative by construction: only `str` values are touched, only when the
    schema names exactly one non-string type, and only when the text parses
    unambiguously. Anything else is passed through untouched so the existing
    validation/TypeError path still produces its self-correctable error --
    coercion must never turn a loud rejection into a silent guess.
    """
    props = (schema or {}).get("properties")
    if not isinstance(props, dict) or not isinstance(args, dict) or not args:
        return args

    out: dict[str, Any] | None = None
    for key, value in args.items():
        if not isinstance(value, str):
            continue
        declared = props.get(key)
        if not isinstance(declared, dict):
            continue
        jtype = _declared_type(declared, schema)
        # A union of containers (`dict | list`) is advertised as a type list.
        # Any other list, or one that admits a string, is left alone: the
        # string may well be what the tool wants. Never second-guess that.
        if isinstance(jtype, list):
            kinds = set(jtype) - {"null"}
            jtype = "container" if kinds and kinds <= {"object", "array"} else None
        if not isinstance(jtype, str) or jtype == "string":
            continue

        text = value.strip()
        coerced: Any = _MISSING
        if not text and jtype in ("object", "array", "container"):
            # A blank string for a structured argument means "not given", the
            # same as null (run_op(params="") used to reach the tool as "").
            if out is None:
                out = dict(args)
            out.pop(key, None)
            continue
        if jtype == "container":
            if text[:1] in ("{", "["):
                try:
                    decoded = json.loads(text)
                except (ValueError, TypeError):
                    decoded = None
                if isinstance(decoded, (dict, list)):
                    coerced = decoded
        elif jtype == "boolean":
            low = text.lower()
            if low in _TRUE_STRINGS:
                coerced = True
            elif low in _FALSE_STRINGS:
                coerced = False
        elif jtype == "integer":
            if _INT_RE.match(text):
                coerced = int(text)
        elif jtype == "number":
            try:
                coerced = float(text)
            except ValueError:
                pass
        elif jtype in ("array", "object"):
            # A structured argument sent as a JSON string (run_op
            # params='{...}', search filters='[...]'): the structure is right,
            # only the wrapper is wrong, and the refusal would name types,
            # never "you sent a string".
            opener = "[" if jtype == "array" else "{"
            want = list if jtype == "array" else dict
            if text[:1] == opener:
                try:
                    decoded = json.loads(text)
                except (ValueError, TypeError):
                    decoded = None
                if isinstance(decoded, want):
                    coerced = decoded
            elif (jtype == "array" and text and "," not in text
                  and (declared.get("items") or {}).get("type") == "string"):
                # One bare value where a list of strings is declared
                # (`only="email"`). Wrapping it is lossless. Passing it through
                # was not: `set[str]`/`list[str]` bodies iterate or `in`-test
                # the string, i.e. match SUBSTRINGS, and returned plausible
                # output. A comma list is left for the arg gate to reject --
                # splitting it would be a guess.
                coerced = [text]

        if coerced is _MISSING:
            continue
        if out is None:
            out = dict(args)
        out[key] = coerced
    return out if out is not None else args


