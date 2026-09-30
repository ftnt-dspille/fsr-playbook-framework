"""One argument gate for every tool, driven by the tool's own contract.

Before this, 31 of 71 registered tools had a typed argument check (two parallel
pydantic maps, one per repo) and the rest learned about a bad argument only when
the call blew up somewhere inside the tool: `verify_playbook(yaml_text=42)`
surfaced as "expected string or bytes-like object", which names nothing the
model sent. An unknown key surfaced as Python's own TypeError text, which names
the bad key but never the valid ones.

The gate reads what every tool already declares -- its `input_schema` (built
from the function signature, or a hand-written override) and the signature
itself -- so a tool added tomorrow is covered with no second list to keep in
step. It checks, in order:

  * unknown keys, against the real signature (skipped for a `**kwargs` fn,
    e.g. a native-MCP passthrough, whose contract is its schema alone);
  * required keys;
  * types / enums / nested shapes, via jsonschema against `input_schema`.

A rejection is written for the model to act on in ONE retry: every problem at
once, the valid argument names, the closest match for a misspelled key, and the
allowed values for an enum. Recovery rate tracks message quality -- in live
sessions every error that named the fix was recovered in one retry, and the
ones that didn't were where turns got stuck.

`null` for an optional argument means "not given": the key is dropped so the
function's own default applies, instead of a default of 10 silently becoming
None -- or `null` for an `Optional[str]` being rejected as "not a string".
"""
from __future__ import annotations

import difflib
import inspect
from collections.abc import Callable
from typing import Any

try:  # jsonschema is a declared dependency; the gate degrades, never breaks.
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - exercised only on a broken install
    Draft202012Validator = None  # type: ignore[assignment,misc]

CODE = "invalid_tool_args"

_MAX_PROBLEMS = 6
_MAX_ENUM = 12


def _signature(fn: Callable[..., Any]) -> inspect.Signature | None:
    try:
        return inspect.signature(fn)
    except (TypeError, ValueError):
        return None


def _takes_var_kw(sig: inspect.Signature | None) -> bool:
    return sig is None or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def _path(parts: Any) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "(arguments)"


def _short(v: Any, n: int = 60) -> str:
    s = repr(v)
    return s if len(s) <= n else s[: n - 3] + "..."


def _nested_rename(err: Any) -> str:
    """For a missing required key inside a nested object: the sibling the
    model put it under. Live: edit_playbook operations sent the op kind as
    `type: update_step` / `action: update_step` and read only "'op' is a
    required property", a round trip per slip. The value is the proof: a
    sibling holding one of the missing key's enum values is that key misnamed;
    otherwise an undeclared sibling spelled close to it."""
    inst, schema = err.instance, err.schema
    if not isinstance(inst, dict) or not isinstance(schema, dict):
        return ""
    props = schema.get("properties") or {}
    missing = [r for r in err.validator_value or [] if r not in inst]
    extra = [k for k in inst if k not in props]
    for r in missing:
        enum = (props.get(r) or {}).get("enum") or []
        for k, val in inst.items():
            if k != r and isinstance(val, str) and val in enum:
                return f"you sent it as '{k}': use {r}: {val!r}"
        close = difflib.get_close_matches(r, extra, n=1, cutoff=0.6)
        if close:
            return f"rename '{close[0]}' to '{r}'"
    return ""


def _describe(err: Any) -> str:
    """One line per schema violation, phrased as what to send instead."""
    where = _path(err.absolute_path)
    v = err.validator
    if v == "enum":
        allowed = list(err.validator_value)
        shown = ", ".join(repr(a) for a in allowed[:_MAX_ENUM])
        more = f" (+{len(allowed) - _MAX_ENUM} more)" if len(allowed) > _MAX_ENUM else ""
        return f"{where}: {_short(err.instance)} is not allowed; use one of {shown}{more}"
    if v == "type":
        want = err.validator_value
        want = " or ".join(want) if isinstance(want, list) else want
        return (f"{where}: expected {want}, got "
                f"{type(err.instance).__name__} {_short(err.instance)}")
    if v == "required":
        hint = _nested_rename(err)
        return f"{where}: {err.message}" + (f" -- {hint}" if hint else "")
    if v == "additionalProperties":
        return f"{where}: {err.message}"
    return f"{where}: {err.message}"


def normalize_nulls(schema: dict[str, Any] | None, fn: Callable[..., Any],
                    args: dict[str, Any]) -> dict[str, Any]:
    """Drop `key: None` for an optional argument, so the function default applies.

    Only for keys the function declares with a default: a required argument
    sent as null stays, and is reported as missing a value.
    """
    if not args:
        return args
    sig = _signature(fn)
    if sig is None:
        return args
    out = dict(args)
    for k, v in args.items():
        if v is not None:
            continue
        p = sig.parameters.get(k)
        if p is not None and p.default is not inspect.Parameter.empty:
            out.pop(k)
    return out


def check(name: str, schema: dict[str, Any] | None, fn: Callable[..., Any],
          args: dict[str, Any]) -> dict[str, Any] | None:
    """Return a refusal envelope for bad `args`, or None when they are fine.

    Keys starting with `_` are dispatch-internal (`_summary`,
    `_approval_token`, ...) and are never judged here.
    """
    schema = schema or {}
    props: dict[str, Any] = dict(schema.get("properties") or {})
    required = [r for r in (schema.get("required") or []) if isinstance(r, str)]
    sig = _signature(fn)
    user_args = {k: v for k, v in (args or {}).items() if not k.startswith("_")}

    problems: list[str] = []
    suggestions: list[str] = []

    # 1. Unknown keys. The signature is the truth for our own tools: a key the
    # function doesn't take would raise TypeError on the call anyway.
    if not _takes_var_kw(sig):
        # The contract is what we ADVERTISED: a signature parameter the schema
        # doesn't list (`db_path`, or one a hand-written override leaves out)
        # is plumbing the model has no business setting.
        accepted = [k for k in sig.parameters  # type: ignore[union-attr]
                    if not k.startswith("_") and (not props or k in props)]
        unknown = [k for k in user_args if k not in accepted]
        missing_req = [r for r in required if r not in user_args]
        for k in unknown:
            # One unknown key + one missing required key is a rename, whatever
            # the spelling (`query` for `q`): that structure beats string
            # similarity. Otherwise a prefix, then a close spelling.
            if len(unknown) == 1 and len(missing_req) == 1:
                close = missing_req
            else:
                close = ([a for a in accepted
                          if a.startswith(k) or k.startswith(a)][:1]
                         or difflib.get_close_matches(k, accepted, n=1, cutoff=0.7))
            if close:
                problems.append(f"{k}: not an argument of {name}; did you mean '{close[0]}'?")
                suggestions.append(f"rename '{k}' to '{close[0]}'")
            else:
                problems.append(f"{k}: not an argument of {name}")
        declared = accepted
    else:
        declared = list(props)

    # 2. Required keys (and a required key sent as null).
    for r in required:
        if r not in user_args:
            problems.append(f"{r}: required, missing")
        elif user_args[r] is None:
            problems.append(f"{r}: required, got null")

    # 3. Types / enums / nested shape. Validate only the keys the schema
    # declares and that carry a value: unknown keys and nulls are reported
    # above, and root-level `required` is already covered.
    if Draft202012Validator is not None and props:
        body = {k: v for k, v in user_args.items() if k in props and v is not None}
        sub = {k: v for k, v in schema.items() if k not in ("required", "additionalProperties")}
        try:
            errors = sorted(Draft202012Validator(sub).iter_errors(body),
                            key=lambda e: list(e.absolute_path))
        except Exception:  # noqa: BLE001 -- a malformed schema must not block the call
            errors = []
        for e in errors:
            problems.append(_describe(e))

    if not problems:
        return None

    shown = problems[:_MAX_PROBLEMS]
    if len(problems) > _MAX_PROBLEMS:
        shown.append(f"(+{len(problems) - _MAX_PROBLEMS} more)")
    req = set(required)
    valid = ", ".join(f"{k}*" if k in req else k for k in declared) or "(none)"
    return {
        "ok": False,
        "code": CODE,
        "tool": name,
        "error": (f"invalid arguments for {name} -- the call was NOT run. "
                  + "; ".join(shown)
                  + f". Valid arguments (* = required): {valid}."),
        "problems": problems,
        "suggestions": suggestions or [f"resend {name} with the arguments fixed"],
    }


def bind_error(name: str, fn: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any] | None:
    """Refusal when `args` can't bind to `fn`'s signature, else None.

    Used right before the call so a TypeError raised INSIDE the tool body is no
    longer reported to the model as "bad arguments" -- that misfiled tool bugs
    as model mistakes and sent the model off rewriting correct arguments.
    """
    sig = _signature(fn)
    if sig is None:
        return None
    try:
        sig.bind(**args)
    except TypeError as e:
        return {
            "ok": False,
            "code": CODE,
            "tool": name,
            "error": f"invalid arguments for {name} -- the call was NOT run: {e}",
            "problems": [str(e)],
            "suggestions": [f"resend {name} with the arguments fixed"],
        }
    return None
