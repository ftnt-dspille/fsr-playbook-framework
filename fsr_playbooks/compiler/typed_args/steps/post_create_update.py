"""Typed model for `start_on_create` / `start_on_update` / `start_on_delete`
arguments — the field-based post-write record triggers (FSR handlers
``cybersponse.post_create`` / ``post_update`` / ``post_delete``).

These are the record-family trigger step types authored with a friendly
``module:`` (single name or ``modules:`` list) plus an optional ``when:``
filter that fires only when the query matches the post-write record state
(the pre-delete state for post_delete), or — for post_update — when the
listed fields *changed*.

`PostCreateUpdateArgs` types the scalar friendly ``module`` field so a
wrong-typed value is a clean ``BAD_VALUE`` (e.g. ``module: [1, 2]``)
instead of silently riding through to the runtime. ``modules`` (a list),
``when`` (a filter dict), and the canonical keys ride through via
``extra="allow"`` — the resolver's ``_check_unknown_keys`` has already
rejected anything genuinely unknown, and ``_validate_trigger_fields``
re-checks the filter against the catalog after this walk.

`expand_post_create_update` owns the friendly→canonical transform,
byte-for-byte with the imperative normalizer it replaces:

* ``module:``/``modules:`` -> resolved ``resource`` (single) + ``resources`` (list),
  with the empty-default-to-``[alerts, incidents]`` + warning,
* the ``step_variables``/``triggerOnSource``/``triggerOnReplicate``/
  ``__triggerLimit`` setdefaults,
* ``when:`` -> ``fieldbasedtrigger`` via the typed trigger layer's
  ``expand_when`` (pure — no catalog), else the empty-filter default.

Two pieces stay in the resolver, around this walk, because they are
catalog-bound and run before/after the transform:

* ``_check_unknown_keys`` (the strict friendly/canonical whitelist) — runs first.
* ``_validate_trigger_fields`` (filter fields/values vs the warmed modules
  table) — runs after, on the rewritten ``step.arguments``.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import ConfigDict

from ...errors import CompileError, ErrorCode
from ..base import StrictArgs
from .._bridge import validate_args
from ..trigger import expand_when


class PostCreateUpdateArgs(StrictArgs):
    """Typed view of a post-write record-trigger step's arguments.

    ``module`` is the target module type name (a string, or a Jinja string
    that renders to one). ``modules`` (the list form), ``when`` (the filter
    dict), ``mock_result``/``condition`` (escape hatches) and the canonical
    keys ride through ``extra="allow"`` — the resolver's
    ``_check_unknown_keys`` has already rejected anything genuinely unknown,
    and ``_validate_trigger_fields`` re-checks the filter after this walk.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: Optional[str] = None


def expand_post_create_update(
    args: Any,
    step_type: str,
    path: str,
    errors: list[CompileError],
    resolve_module: Callable[[str, str, list[CompileError]], str],
) -> Optional[dict]:
    """Rewrite friendly ``module:``/``modules:`` + ``when:`` into the canonical
    ``resource``/``resources`` + ``fieldbasedtrigger`` shape.

    Returns the transformed dict, or ``None`` to leave ``step.arguments``
    unchanged (when the input is not a dict). ``resolve_module`` is the
    resolver's ``resolve_module_name`` bound method, threaded in because
    module canonicalization needs the catalog. Canonical keys already set by
    the author win — the transform uses ``setdefault``, never clobbering an
    explicit ``resource``/``resources``/``fieldbasedtrigger``/``step_variables``.
    """
    if not isinstance(args, dict):
        return None
    # Additive scalar type-validation (diagnostics only; the transform below
    # reads the raw value to stay byte-identical with the imperative path).
    validate_args(PostCreateUpdateArgs, args, f"{path}.arguments", errors)

    a = dict(args)
    modules_raw = a.pop("module", None) or a.pop("modules", None) \
        or a.get("resources") or a.get("resource")
    if isinstance(modules_raw, str):
        modules = [modules_raw]
    elif isinstance(modules_raw, list):
        modules = [str(m) for m in modules_raw]
    else:
        modules = []
    if not modules:
        modules = ["alerts", "incidents"]
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message=(f"`module:` not set on {step_type} — defaulting to "
                     "[alerts, incidents]; set `module:` explicitly to "
                     "override"),
            path=f"{path}.arguments.module",
            severity="warning",
        ))
    # Canonicalize each module name against the catalog (case-fix
    # 'Alerts' -> 'alerts', warn on unknowns). Silent no-op when the
    # modules table is unwarmed/empty.
    modules = [
        resolve_module(m, f"{path}.arguments.module", errors)
        for m in modules
    ]
    a["resource"] = modules[0]
    a["resources"] = modules
    a.setdefault("step_variables",
                 {"input": {"records": ["{{vars.input.records[0]}}"]}})
    a.setdefault("triggerOnSource", True)
    a.setdefault("triggerOnReplicate", False)
    a.setdefault("__triggerLimit", True)

    when = a.pop("when", None)
    if when is not None:
        fbt = expand_when(when, step_type, path, errors)
        if fbt is not None:
            a["fieldbasedtrigger"] = fbt
    elif "fieldbasedtrigger" not in a:
        a["fieldbasedtrigger"] = {
            "sort": [], "limit": 30, "logic": "AND", "filters": [],
        }
    return a
