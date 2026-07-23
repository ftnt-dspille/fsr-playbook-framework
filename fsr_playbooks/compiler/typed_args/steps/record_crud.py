"""Typed model for `create_record` / `insert_record` / `update_record` arguments.

These are the record-write step types (FSR handlers ``InsertData`` /
``UpdateRecord``). Their one friendly→canonical transform is the module→IRI
rewrite: a friendly ``module: alerts`` becomes the canonical collection IRI the
handler expects::

    create_record (InsertData):
        module → collection      ('/api/3/<module>')
    update_record (UpdateRecord):
        module → collectionType  ('/api/3/<module>')
        record → collection      (the targeted record IRI)
        (`collection:` is REJECTED on update_record — it carried the record
        IRI but collided with create_record's module-IRI `collection`, the #1
        record-CRUD footgun; use `record:` for the IRI and `module:` for the
        module.)

`module:` is mandatory on create_record / update_record (a record-CRUD step
with no resolvable module can't target a collection). An explicit canonical
`collection:` (create) / `collectionType:` (update) is an escape hatch for a
non-standard IRI and substitutes for `module:`.

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

from ...errors import CompileError, ErrorCode
from ..base import StrictArgs
from .._bridge import validate_args


class RecordCrudArgs(StrictArgs):
    """Typed view of a record-write step's arguments.

    `module` is the target module type name (a string, or a Jinja string that
    renders to one). `is_upsert` toggles upsert mode for create/insert: it is
    compiled away (never reaches the wire) and routes the step at
    ``/api/3/upsert/<module>`` with ``operation: Overwrite`` so a re-run updates
    the existing record by its natural key instead of appending a duplicate
    (pydantic coerces the usual ``true``/``1``/``"true"`` forms; ``"yes"`` is a
    clean BAD_VALUE). The natural key itself is carried on the ``resource`` as
    ``sourceId`` (or ``externalId``) — the data-ingest convention. `resource`
    (the record payload) and the canonical IRI keys ride through via
    ``extra="allow"`` — the resolver's `_check_unknown_keys` has already rejected
    anything genuinely unknown, and `_resolve_picklist_friendly_tokens` rewrites
    payload labels after this walk.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: Optional[str] = None
    is_upsert: Optional[bool] = None
    record: Optional[str] = None


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
    # Phase A1: `record:` is the friendly key for update_record's record IRI
    # (it compiles to the wire `collection:`). `collection:` on update_record
    # is rejected below — it was the record IRI but collided with create's
    # module-IRI `collection`, the #1 record-CRUD footgun.
    record_iri = a.pop("record", None)

    module = a.pop("module", None)
    if module and isinstance(module, str):
        module = resolve_module(module, f"{path}.arguments.module", errors)
        iri = f"/api/3/{module}" if not module.startswith("/api/") else module
        if step_type in ("create_record", "insert_record"):
            a.setdefault("collection", iri)
        elif step_type == "update_record":
            a.setdefault("collectionType", iri)

    if step_type == "update_record":
        # `collection:` on update_record is the old/wire record-IRI key —
        # reject it so authors can't confuse create's module-IRI `collection`
        # with update's record-IRI `collection`. The decompiler emits `record:`
        # (not `collection:`), so a decompiled step never trips this.
        if "collection" in a:
            errors.append(CompileError(
                code=ErrorCode.BAD_VALUE,
                message=(
                    "update_record: `collection:` was the record IRI; use "
                    "`record:` for the record IRI and `module:` for the module. "
                    "The wire `collection` key is reserved for create_record's "
                    "module IRI — reusing it on update is the record-CRUD footgun."
                ),
                path=f"{path}.arguments.collection",
                suggestion="rename `collection:` to `record:`",
            ))
            a.pop("collection", None)
        if record_iri is not None:
            a["collection"] = record_iri

    # `module:` is mandatory on create/update (no resolvable module -> the step
    # can't target a record collection). An explicit canonical IRI key already
    # present (`collection` on create / `collectionType` on update) is an escape
    # hatch for a non-standard path and substitutes for `module:`.
    if step_type in ("create_record", "update_record"):
        has_iri = ("collection" in a) if step_type == "create_record" \
            else ("collectionType" in a)
        if not module and not has_iri:
            errors.append(CompileError(
                code=ErrorCode.MISSING_FIELD,
                message=(
                    f"{step_type}: `module:` is required (the target module "
                    f"name, e.g. `module: alerts`)."
                ),
                path=f"{path}.arguments.module",
            ))

    # `is_upsert` is a friendly YAML lever, NOT a real InsertData wire arg —
    # pop it unconditionally so it never reaches the runtime. For create/insert
    # it routes the step at FortiSOAR's upsert endpoint so a re-run updates
    # the existing record by its natural key instead of appending a duplicate:
    #   collection `/api/3/<m>` -> `/api/3/upsert/<m>`
    #   operation defaults to `Overwrite` (the idempotent write op)
    # The natural key itself is carried on the resource as `sourceId`
    # (or `externalId`) — the data-ingest convention (see the `data_ingest`
    # ruleset). An already-`/api/3/upsert/...` collection (or any non-`/api/3/`
    # collection) is left untouched. `update_record` is already a partial patch
    # by IRI/query, so `is_upsert` has no effect there beyond being dropped.
    is_upsert = a.pop("is_upsert", None)
    if is_upsert and step_type in ("create_record", "insert_record"):
        coll = a.get("collection")
        if (isinstance(coll, str) and coll.startswith("/api/3/")
                and not coll.startswith("/api/3/upsert/")):
            a["collection"] = "/api/3/upsert/" + coll[len("/api/3/"):]
        a.setdefault("operation", "Overwrite")
    return a
