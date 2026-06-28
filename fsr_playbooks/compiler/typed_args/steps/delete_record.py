"""Typed model for `delete_record` step arguments.

FortiSOAR has no first-class delete step type; deletion is a connector step
hitting the internal API via ``cyops_utilities.make_cyops_request`` (method
DELETE). `delete_record` is the friendly authoring surface for that — grounded
on real corpus playbooks (4 DELETE-method cyops_utilities steps). Because it
compiles *to* a connector step, it never appears in the decompiled wire, so the
byte-identical contract here is the authoring path (``test_delete_record.py``),
not the corpus round-trip.

Friendly inputs (exactly one targeting mode required)::

    record:              a single record IRI ('/api/3/<module>/<uuid>') or
                         '@id' jinja — deleted directly.
    module + record_id:  build '/api/3/<module>/<record_id>'.
    module + query:      bulk delete via '/api/3/delete-with-query/<module>';
                         `query` is a filter dict {logic, filters:[…]} json-
                         encoded into the body, or a raw jinja/string body.
    show_deleted:        bool — append '?$showDeleted=true' (default true for
                         the query form, false for single-record).
    iri / method / body: raw escape hatches inside `params` (passed verbatim).

`DeleteRecordArgs` types the scalar friendly fields so a wrong-typed value
becomes a clean `BAD_VALUE` (e.g. ``show_deleted: "maybe"``). `record`,
`record_id`, and `query` stay `Any` — they are IRIs / jinja / filter dicts whose
shape the transform branches on directly. `expand_delete_record` owns the
friendly→canonical transform, byte-for-byte with the imperative normalizer it
replaces (same param key order, same connector defaults, same showDeleted rule).

The unknown-key strict-whitelist guard stays in the resolver
(`_check_unknown_keys`) and runs *before* this walk, mirroring delay/set_variable.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from pydantic import ConfigDict

from ...errors import CompileError, ErrorCode
from ..base import StrictArgs
from .._bridge import validate_args


class DeleteRecordArgs(StrictArgs):
    """Typed view of a friendly delete_record step's arguments.

    `module` is the target module type name; `show_deleted` toggles the
    soft-delete query flag (pydantic coerces the usual ``true``/``1``/``"true"``
    forms). `record`/`record_id`/`query` stay `Any` (IRI / id / filter-dict or
    jinja). `extra="allow"` because canonical/escape-hatch keys (`params`,
    `connector`, `operation`, …) ride through untouched — the resolver's
    `_check_unknown_keys` has already rejected anything genuinely unknown.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: Optional[str] = None
    modules: Optional[str] = None
    record: Optional[Any] = None
    record_id: Optional[Any] = None
    query: Optional[Any] = None
    show_deleted: Optional[bool] = None


def expand_delete_record(
    args: Any,
    path: str,
    errors: list[CompileError],
    resolve_module: Callable[[str, str, list[CompileError]], str],
) -> Optional[dict]:
    """Expand a friendly delete_record step into the canonical cyops_utilities
    DELETE connector shape.

    Returns the canonical dict, or ``None`` to leave `step.arguments` unchanged
    — when the input is not a dict or a hard targeting error is appended (the
    step is left for the author to fix; compilation fails so nothing emits).
    `resolve_module` is the resolver's ``resolve_module_name`` bound method,
    threaded in because module canonicalization needs the catalog.
    """
    if not isinstance(args, dict):
        return None
    # Additive type-validation of the scalar friendly fields (diagnostics only;
    # the transform below reads the raw values to stay byte-identical).
    validate_args(DeleteRecordArgs, args, f"{path}.arguments", errors)

    a = dict(args)
    record = a.pop("record", None)
    record_id = a.pop("record_id", None)
    query = a.pop("query", None)
    module_raw = a.pop("module", None) or a.pop("modules", None)
    module = (resolve_module(module_raw, f"{path}.arguments.module", errors)
              if isinstance(module_raw, str) and module_raw else module_raw)
    show_deleted = a.pop("show_deleted", None)

    # Build the existing params (raw escape hatch wins if fully specified).
    params = a.get("params") if isinstance(a.get("params"), dict) else {}
    iri = params.get("iri")
    body = params.get("body", "")

    targets = [t for t in (record, record_id and module, query) if t]
    if iri is None and len(targets) != 1:
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message=("delete_record needs exactly one target: `record:` (an "
                     "IRI/@id), `module:`+`record_id:`, or `module:`+`query:`"),
            path=f"{path}.arguments",
        ))
        return None

    if iri is None:
        if record is not None:
            iri = str(record)
            if show_deleted:
                iri += ("&" if "?" in iri else "?") + "$showDeleted=true"
        elif record_id is not None:
            if not module:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="delete_record with `record_id:` also needs `module:`",
                    path=f"{path}.arguments.module",
                ))
                return None
            iri = f"/api/3/{module}/{record_id}"
            if show_deleted:
                iri += "?$showDeleted=true"
        else:  # query form
            if not module:
                errors.append(CompileError(
                    code=ErrorCode.MISSING_FIELD,
                    message="delete_record with `query:` also needs `module:`",
                    path=f"{path}.arguments.module",
                ))
                return None
            iri = f"/api/3/delete-with-query/{module}"
            if show_deleted is not False:
                iri += "?$showDeleted=true"
            if isinstance(query, (dict, list)):
                body = json.dumps(query)
            elif query is not None:
                body = str(query)

    params["iri"] = iri
    params["method"] = params.get("method", "DELETE")
    params["body"] = body
    a["params"] = params
    a.setdefault("connector", "cyops_utilities")
    a.setdefault("operation", "make_cyops_request")
    a.setdefault("operationTitle", "FSR: Make FortiSOAR API Call")
    a.setdefault("config", "")
    return a
