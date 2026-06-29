"""Typed model for `create_record` / `insert_record` / `update_record` arguments.

These are the record-write step types (FSR handlers ``InsertData`` /
``UpdateRecord``). Their one friendly→canonical transform is the module→IRI
rewrite: a friendly ``module: alerts`` becomes the canonical collection IRI the
handler expects::

    create_record / insert_record (InsertData):
        module → collection      ('/api/3/<module>')
    update_record (UpdateRecord):
        module → collectionType  ('/api/3/<module>')
        (here `collection:` is the *record* IRI — never overwritten.)

`RecordCrudArgs` types the scalar friendly/flag fields so a wrong-typed value is
a clean `BAD_VALUE` (e.g. ``module: [1, 2]`` or ``is_upsert: "yes"``) instead of
silently riding through to the runtime. `resource` (the record payload) stays
untyped — it is an arbitrary field dict. `expand_record_crud` owns the
module→IRI transform, byte-for-byte with the imperative normalizer it replaces
(same `setdefault` keys, same `/api/`-passthrough, same already-set-wins rule).

Two pieces stay in the resolver, around this walk, because they are
catalog-bound and run before/after the transform:

* `_check_unknown_keys` (the strict friendly/canonical whitelist) — runs first.
* `_resolve_picklist_friendly_tokens` (friendly picklist labels → IRIs in the
  `resource` payload) — runs after, on the rewritten `step.arguments`.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import ConfigDict

from ...errors import CompileError
from ..base import StrictArgs
from .._bridge import validate_args


class RecordCrudArgs(StrictArgs):
    """Typed view of a record-write step's arguments.

    `module` is the target module type name (a string, or a Jinja string that
    renders to one). `is_upsert` toggles InsertData's upsert mode (pydantic
    coerces the usual ``true``/``1``/``"true"`` forms). `resource` (the record
    payload) and the canonical IRI keys ride through via ``extra="allow"`` — the
    resolver's `_check_unknown_keys` has already rejected anything genuinely
    unknown, and `_resolve_picklist_friendly_tokens` rewrites payload labels
    after this walk.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: Optional[str] = None
    is_upsert: Optional[bool] = None


def expand_record_crud(
    args: Any,
    step_type: str,
    path: str,
    errors: list[CompileError],
    resolve_module: Callable[[str, str, list[CompileError]], str],
) -> Optional[dict]:
    """Rewrite a friendly `module:` into the canonical collection IRI.

    Returns the transformed dict, or ``None`` to leave `step.arguments`
    unchanged (when the input is not a dict). `resolve_module` is the resolver's
    ``resolve_module_name`` bound method, threaded in because module
    canonicalization needs the catalog. Already-set canonical keys win — the
    transform uses `setdefault`, never clobbering an explicit `collection` /
    `collectionType`.
    """
    if not isinstance(args, dict):
        return None
    # Additive scalar type-validation (diagnostics only; the transform below
    # reads the raw value to stay byte-identical).
    validate_args(RecordCrudArgs, args, f"{path}.arguments", errors)

    a = dict(args)
    module = a.pop("module", None)
    if module and isinstance(module, str):
        module = resolve_module(module, f"{path}.arguments.module", errors)
        iri = f"/api/3/{module}" if not module.startswith("/api/") else module
        if step_type in ("create_record", "insert_record"):
            a.setdefault("collection", iri)
        elif step_type == "update_record":
            a.setdefault("collectionType", iri)
    return a
