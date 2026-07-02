"""Typed model for the ``ingest_bulk_feed`` step (FSR handler
``IngestBulkFeed``) -- the editor's "Ingest Bulk Feed" palette entry.

A real step type (own uuid ``7b221880-716b-4726-a2ca-5e568d330b3e``, own
controller ``IngestBulkFeedCtrl`` which *inherits* ``InsertDataCtrl``). It is
the **bulk-ingest sibling of Create Record** -- both render ``insertData.html``
and share the ``collection``/``resource`` envelope, but IngestBulkFeed:

* POSTs to ``/api/ingest-feeds/{moduleName}`` (not ``/api/3/<module>``);
* deletes ``operation`` and ``fieldOperation`` (implicitly upsert -- no
  per-field op, unlike Create Record which defaults ``operation: "Overwrite"``);
* is bulk-by-default (``loopExecutionModes.bulk=true``).

The friendly inputs (grounded in ``docs/STEP_WIRE_SHAPES`` IngestBulkFeed +
``fsr-schema.ts`` ``IngestBulkFeedArgs``)::

    collection:   "/api/ingest-feeds/<module>"  -- auto-calculated by the
                  editor from the module name ($watch, bundle line 37009);
                  format enforced, cannot be hand-set to anything else.
    resource:     {field: value, ...}          -- the field mappings (incl. the
                  ``__replace`` key); inherited from InsertDataCtrl.
    for_each:     {item, parallel, condition, __bulk, batch_size, break_loop}
                  -- loop config. NOTE: ``for_each`` is a *step-level* IR field
                  (sibling of ``arguments`` in friendly YAML), not an
                  arguments-dict key -- so it is NOT declared on this model. Its
                  MODE LOGIC (__bulk vs parallel vs sequential; ``parallel``/
                  ``batch_size`` pruning; ``batch_size`` defaulting to 100) is
                  owned by the emitter's ``_clean_step_arguments`` (editor
                  save-time cleanup).
    step_variables / when / __recommend / _showJson -- system/UI-state keys;
                  ride through ``extra="allow"``.

DESIGN SPLIT (the connector / trigger_tenant_playbook precedent):
  * This typed model owns the **envelope schema** (the discover win --
    ``get_step_arg_schema("ingest_bulk_feed")`` returns a JSON Schema, was
    ``None``) + scalar validation (a present-but-wrong-typed ``collection``
    or ``resource`` -> clean ``BAD_VALUE``).
  * The **lint layer** owns the semantic invariants the editor enforces:
    ``rulesets/_shared.py`` checks ``collection`` starts with
    ``/api/ingest-feeds/`` (``shared.ingest_bulk_feed_collection_prefix``) and
    rejects a stray ``operation`` (``shared.ingest_bulk_feed_unexpected_operation``).
  * The **emitter** (``_clean_step_arguments``) owns the ``for_each`` loop-mode
    normalization. Validation-only here never mutates, so it cannot collide
    with either.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class IngestBulkFeedArgs(StrictArgs):
    """Typed view of an ingest_bulk_feed step's envelope scalars.

    ``collection`` is the ingest-feed target IRI (``/api/ingest-feeds/<module>``);
    declared Optional so a missing value does NOT raise here (the lint layer
    flags a wrong-prefix ``collection``; the engine rejects a missing one).
    ``resource`` is the field-mappings body (a mapping incl. ``__replace``);
    wrong-typed (e.g. a string) is a clean ``BAD_VALUE``.

    ``for_each`` is NOT declared here -- it is a *step-level* IR field
    (``ir.Step.for_each``), a sibling of ``arguments`` in the friendly YAML,
    and the emitter moves it into the wire args dict at emit time
    (``emitter.py``: "for_each lives inside arguments on the wire"). So the
    normalizer never sees ``for_each`` inside ``step.arguments``; declaring it
    on this model would be misleading. Its mode logic (``__bulk``/
    ``parallel``/``sequential``, ``batch_size`` defaulting, ``parallel``
    pruning) is owned by the emitter's ``_clean_step_arguments``. The rest of
    the envelope (``step_variables``, ``when``, ``__recommend``, ``_showJson``,
    ``mock_result``, ``condition``, ``message``, ``ignore_errors``) rides
    through ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    collection: Optional[str] = None
    resource: Optional[Any] = None


def expand_ingest_bulk_feed(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate an ingest_bulk_feed step's envelope scalars.

    Validation-only: always returns ``None`` (there is no friendly->canonical
    transform to own -- the author writes canonical-shaped ``collection``/
    ``resource``/``for_each`` directly; the emitter owns ``for_each`` mode
    cleanup, and the lint layer owns the ``collection``-prefix / ``operation``
    checks). A bad envelope scalar (e.g. ``collection: 123``,
    ``resource: "x"``) appends a ``BAD_VALUE`` and leaves the step for the
    emitter + lint to also run. Does NOT re-validate ``collection`` presence or
    prefix (the lint layer's ``shared.ingest_bulk_feed_collection_prefix``
    message is more precise than a generic pydantic error).
    """
    if not isinstance(args, dict):
        return None
    validate_args(IngestBulkFeedArgs, args, f"{path}.arguments", errors)
    return None
