"""Typed model for `create_record` / `update_record` arguments.

These are the record-write step types (FSR handlers ``InsertData`` /
``UpdateRecord``). Their one friendly→canonical transform is the module→IRI
rewrite: a friendly ``module: alerts`` becomes the canonical collection IRI the
handler expects::

    create_record (InsertData):
        module → collection      ('/api/3/<module>')
    update_record (UpdateRecord):
        module → collectionType  ('/api/3/<module>')
        record → collection      (the targeted record IRI)
        (`collection:` is REJECTED on update_record -- it carried the record
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
untyped -- it is an arbitrary field dict. `expand_record_crud` owns the
module→IRI transform, byte-for-byte with the imperative normalizer it replaces
(same `setdefault` keys, same `/api/`-passthrough, same already-set-wins rule).

Two pieces stay in the resolver, around this walk, because they are
catalog-bound and run before/after the transform:

* `_check_unknown_keys` (the strict friendly/canonical whitelist) -- runs first.
* `_resolve_picklist_friendly_tokens` (friendly picklist labels → IRIs in the
  `resource` payload) -- runs after, on the rewritten `step.arguments`.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ConfigDict

from ...errors import CompileError, ErrorCode
from .._bridge import validate_args
from ..base import StrictArgs


class RecordCrudArgs(StrictArgs):
    """Typed view of a record-write step's arguments.

    `module` is the target module type name (a string, or a Jinja string that
    renders to one). `is_upsert` toggles upsert mode for create/insert: it is
    compiled away (never reaches the wire) and routes the step at
    ``/api/3/upsert/<module>`` with ``operation: Overwrite`` so a re-run updates
    the existing record by its natural key instead of appending a duplicate
    (pydantic coerces the usual ``true``/``1``/``"true"`` forms; ``"yes"`` is a
    clean BAD_VALUE). The natural key itself is carried on the ``resource`` as
    ``sourceId`` (or ``externalId``) -- the data-ingest convention. `resource`
    (the record payload) and the canonical IRI keys ride through via
    ``extra="allow"`` -- the resolver's `_check_unknown_keys` has already rejected
    anything genuinely unknown, and `_resolve_picklist_friendly_tokens` rewrites
    payload labels after this walk.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    module: str | None = None
    is_upsert: bool | None = None
    on_conflict: str | None = None
    update_fields: list | str | None = None
    record: str | None = None
    field_operations: dict | None = None
    link: dict | None = None
    unlink: dict | None = None
    tags_operation: str | None = None


def expand_record_crud(
    args: Any,
    step_type: str,
    path: str,
    errors: list[CompileError],
    resolve_module: Callable[[str, str, list[CompileError]], str],
) -> dict | None:
    """Rewrite a friendly `module:` into the canonical collection IRI.

    Returns the transformed dict, or ``None`` to leave `step.arguments`
    unchanged (when the input is not a dict). `resolve_module` is the resolver's
    ``resolve_module_name`` bound method, threaded in because module
    canonicalization needs the catalog. Already-set canonical keys win -- the
    transform uses `setdefault`, never clobbering an explicit `collection` /
    `collectionType`.
    """
    if not isinstance(args, dict):
        return None
    # Additive scalar type-validation (diagnostics only; the transform below
    # reads the raw value to stay byte-identical).
    validate_args(RecordCrudArgs, args, f"{path}.arguments", errors)

    a = dict(args)
    # `fields:` is the friendly alias for the wire `resource:` key (the
    # record payload). Authors think "set these fields" -- `resource:` is
    # an FSR API term. Both compile to the same wire key; `resource:`
    # stays accepted for back-compat.
    if "fields" in a and "resource" not in a:
        a["resource"] = a.pop("fields")
    elif isinstance(a.get("fields"), dict) and isinstance(a.get("resource"), dict):
        # `link:`/`unlink:` build `resource` (as `resource.__link` /
        # `resource.__unlink`) before this runs, so a step with BOTH keys must
        # merge rather than discard `fields` -- dropping it silently shipped an
        # update that wrote nothing.
        merged = dict(a.pop("fields"))
        merged.update(a["resource"])       # explicit resource/__link wins
        a["resource"] = merged
    else:
        a.pop("fields", None)
    # Phase A1: `record:` is the friendly key for update_record's record IRI
    # (it compiles to the wire `collection:`). `collection:` on update_record
    # is rejected below -- it was the record IRI but collided with create's
    # module-IRI `collection`, the #1 record-CRUD footgun.
    record_iri = a.pop("record", None)

    module = a.pop("module", None)
    if module and isinstance(module, str):
        module = resolve_module(module, f"{path}.arguments.module", errors)
        iri = f"/api/3/{module}" if not module.startswith("/api/") else module
        if step_type == "create_record":
            a.setdefault("collection", iri)
        elif step_type == "update_record":
            a.setdefault("collectionType", iri)

    if step_type == "update_record":
        # `collection:` on update_record is the old/wire record-IRI key --
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
                    "module IRI -- reusing it on update is the record-CRUD footgun."
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

    # `is_upsert` is a friendly YAML lever, NOT a real InsertData wire arg --
    # pop it unconditionally so it never reaches the runtime. For create/insert
    # it routes the step at FortiSOAR's upsert endpoint so a re-run updates
    # the existing record by its natural key instead of appending a duplicate:
    #   collection `/api/3/<m>` -> `/api/3/upsert/<m>`
    #   operation defaults to `Overwrite` (the idempotent write op)
    # The natural key itself is carried on the resource as `sourceId`
    # (or `externalId`) -- the data-ingest convention (see the `data_ingest`
    # ruleset). An already-`/api/3/upsert/...` collection (or any non-`/api/3/`
    # collection) is left untouched. `update_record` is already a partial patch
    # by IRI/query, so `is_upsert` has no effect there beyond being dropped.
    is_upsert = a.pop("is_upsert", None)

    # `on_conflict:` / `update_fields:` -- the step editor's "Uniqueness
    # conflict settings", which decide what happens when the record being
    # created already exists. Friendly levers; neither reaches the wire under
    # these names.
    #
    # MEASURED on 8.0, each case run twice (no record present, then against a
    # seeded one). The first position is a DIFFERENT ENDPOINT, not a value:
    #
    #   endpoint /api/3/<m>          collision -> 409, step FAILS, run HALTS
    #   upsert + __replace "false"   existing record untouched
    #   upsert + __replace "true"    existing record fully overwritten
    #   upsert + __fieldsToUpdate    only the listed fields are written
    #
    # `__replace` is ignored outright on the plain endpoint, and OMITTING it on
    # the upsert endpoint does NOT fall through to "fail" -- it overwrites
    # everything. That default is why an upsert silently erases whatever a run
    # could not fetch, so `on_conflict:` exists to make the choice explicit.
    #
    # Both keys live INSIDE `resource` on the wire (the PUT body), and
    # `__replace` is the STRING "true"/"false", not a boolean.
    on_conflict = a.pop("on_conflict", None)
    update_fields = a.pop("update_fields", None)

    if update_fields is not None and on_conflict is None:
        # Naming the fields IS the intent; requiring both is ceremony.
        on_conflict = "update_listed"

    if (on_conflict is not None or update_fields is not None) \
            and step_type != "create_record":
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(
                f"{step_type}: `on_conflict:` / `update_fields:` apply to "
                "create_record only -- update_record already targets one "
                "record by IRI, so there is no uniqueness conflict to settle."
            ),
            path=f"{path}.arguments.on_conflict",
        ))
        on_conflict = update_fields = None

    _CONFLICT = {"fail", "keep_existing", "update_all", "update_listed"}
    if on_conflict is not None and on_conflict not in _CONFLICT:
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(
                f"`on_conflict: {on_conflict!r}` is not a valid setting. "
                f"Use one of: {', '.join(sorted(_CONFLICT))}."
            ),
            path=f"{path}.arguments.on_conflict",
            suggestion=(
                "fail = let the collision fail the step; keep_existing = leave "
                "the existing record alone; update_all = overwrite every field; "
                "update_listed = write only `update_fields:`"
            ),
        ))
        on_conflict = None

    if on_conflict == "update_listed" and update_fields is None:
        errors.append(CompileError(
            code=ErrorCode.MISSING_FIELD,
            message=(
                "`on_conflict: update_listed` needs `update_fields:` naming "
                "which fields may be written on an existing record."
            ),
            path=f"{path}.arguments.update_fields",
            suggestion=(
                "list the fields this step is entitled to overwrite, or use "
                "`on_conflict: update_all`"
            ),
        ))
        on_conflict = None

    if on_conflict == "fail" and is_upsert:
        errors.append(CompileError(
            code=ErrorCode.BAD_VALUE,
            message=(
                "`on_conflict: fail` and `is_upsert: true` contradict: "
                "failing on a collision means NOT using the upsert endpoint, "
                "which is the only place the other settings apply."
            ),
            path=f"{path}.arguments.on_conflict",
            suggestion="drop `is_upsert: true`, or choose another on_conflict",
        ))
        on_conflict = None

    if on_conflict in ("keep_existing", "update_all", "update_listed"):
        # These are upsert-endpoint settings; asking for one IS asking to
        # reconcile duplicates, so the routing follows without a second key.
        is_upsert = True
        res = a.setdefault("resource", {})
        if isinstance(res, dict):
            res["__replace"] = "false" if on_conflict == "keep_existing" else "true"
            if on_conflict == "update_listed":
                res["__fieldsToUpdate"] = update_fields

    if is_upsert and step_type == "create_record":
        coll = a.get("collection")
        if (isinstance(coll, str) and coll.startswith("/api/3/")
                and not coll.startswith("/api/3/upsert/")):
            a["collection"] = "/api/3/upsert/" + coll[len("/api/3/"):]
        a.setdefault("operation", "Overwrite")
    return a
