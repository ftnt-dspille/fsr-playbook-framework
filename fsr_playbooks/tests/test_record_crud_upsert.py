"""`is_upsert` on create_record/insert_record routes the step at the upsert endpoint.

FortiSOAR exposes record upsert as a *separate collection* —
``/api/3/upsert/<module>``, not a flag on InsertData. So ``is_upsert`` is a
friendly YAML lever that ``expand_record_crud`` compiles away: it rewrites the
collection, defaults ``operation: Overwrite`` (the idempotent write op), and is
dropped from the wire args. The natural key is carried on the ``resource`` as
``sourceId`` (the data-ingest convention; see the ``data_ingest`` ruleset).

The normalizer transform is unit-tested directly (no connector metadata needed),
mirroring ``test_delete_record``.
"""
from __future__ import annotations

from fsr_playbooks.compiler.ir import Step
from fsr_playbooks.compiler.resolver import Resolver
from fsr_playbooks._db import PACKAGED_SLIM_DB


def _normalize(arguments: dict, step_type: str = "create_record") -> tuple[dict, list]:
    """Run only the record-CRUD normalizer against a step, return its args."""
    r = Resolver(PACKAGED_SLIM_DB)
    step = Step(id="c", type=step_type, name="C", arguments=dict(arguments))
    errors: list = []
    r._normalize_record_crud_args(step, "p.steps[1]", errors)
    return step.arguments, [e for e in errors if e.severity != "warning"]


def test_is_upsert_rewrites_collection_and_sets_overwrite():
    args, errs = _normalize({
        "module": "alerts",
        "is_upsert": True,
        "resource": {"sourceId": "{{ vars.item.serial }}", "name": "n"},
    })
    assert not errs, errs
    assert args["collection"] == "/api/3/upsert/alerts"
    assert args["operation"] == "Overwrite"
    # The friendly lever is compiled away — it is not a real InsertData wire arg.
    assert "is_upsert" not in args


def test_is_upsert_absent_leaves_collection_plain():
    args, errs = _normalize({
        "module": "alerts",
        "resource": {"sourceId": "{{ vars.item.serial }}", "name": "n"},
    })
    assert not errs, errs
    assert args["collection"] == "/api/3/alerts"
    assert "operation" not in args  # not forced when not upserting


def test_is_upsert_preserves_explicit_overwrite():
    args, errs = _normalize({
        "module": "alerts",
        "is_upsert": True,
        "operation": "Update",
        "resource": {"sourceId": "x", "name": "n"},
    })
    assert not errs, errs
    assert args["collection"] == "/api/3/upsert/alerts"
    assert args["operation"] == "Update"  # already-set wins, not clobbered


def test_is_upsert_does_not_double_rewrite_upsert_collection():
    args, errs = _normalize({
        "collection": "/api/3/upsert/alerts",
        "is_upsert": True,
        "resource": {"sourceId": "x", "name": "n"},
    })
    assert not errs, errs
    assert args["collection"] == "/api/3/upsert/alerts"  # unchanged
    assert args["operation"] == "Overwrite"


def test_is_upsert_dropped_from_update_record_without_rewrite():
    # update_record is already a partial patch by IRI/query; is_upsert has no
    # endpoint meaning there, but the lever is still dropped (never a wire arg).
    # For update_record the record IRI is carried in `collection` (module ->
    # collectionType); it is preserved, not rewritten to the upsert endpoint.
    args, errs = _normalize({
        "module": "alerts",
        "is_upsert": True,
        "collection": "/api/3/alerts/abc",
        "resource": {"name": "n"},
    }, step_type="update_record")
    assert not errs, errs
    assert args["collectionType"] == "/api/3/alerts"
    assert args["collection"] == "/api/3/alerts/abc"  # record IRI preserved
    assert "is_upsert" not in args
    assert "operation" not in args  # no Overwrite default on update


def test_insert_record_also_upserts():
    # insert_record is the alias for create_record (both InsertData).
    args, errs = _normalize({
        "module": "alerts",
        "is_upsert": True,
        "resource": {"sourceId": "x", "name": "n"},
    }, step_type="insert_record")
    assert not errs, errs
    assert args["collection"] == "/api/3/upsert/alerts"
    assert args["operation"] == "Overwrite"
    assert "is_upsert" not in args
