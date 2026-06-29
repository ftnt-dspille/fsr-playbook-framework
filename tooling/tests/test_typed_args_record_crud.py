"""Typed-args model for record-write steps (`create_record` / `insert_record` /
`update_record`) — registry contract, the friendly module->IRI transform (the
collection-vs-collectionType split + already-set-wins + /api/ passthrough), and
the new scalar validation (`module`/`is_upsert` wrong-typed -> clean BAD_VALUE).

These steps emit to fixed-field connector wire, so the byte-identical contract is
pinned by the corpus round-trip + wire-shape suites; here we pin the typed layer
directly. `expand_record_crud` takes the resolver's `resolve_module_name` as a
callback — here a passthrough identity (no catalog)."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    RecordCrudArgs,
    expand_record_crud,
    is_modeled,
)


def _ident(raw, _path, _errs):
    """Stand-in for resolver.resolve_module_name (passthrough, no catalog)."""
    return raw


def _expand(args, step_type="create_record", errs=None):
    return expand_record_crud(
        args, step_type, "p.steps[0]", errs if errs is not None else [], _ident
    )


def test_registry_models_all_three_record_types():
    for t in ("create_record", "insert_record", "update_record"):
        assert STEP_ARG_MODELS.get(t) is RecordCrudArgs
        assert is_modeled(t) is True


def test_create_record_module_to_collection():
    out = _expand({"module": "alerts"}, "create_record")
    assert out["collection"] == "/api/3/alerts"
    assert "module" not in out


def test_insert_record_module_to_collection():
    out = _expand({"module": "alerts"}, "insert_record")
    assert out["collection"] == "/api/3/alerts"


def test_update_record_module_to_collection_type():
    out = _expand({"module": "alerts"}, "update_record")
    assert out["collectionType"] == "/api/3/alerts"
    # update never touches `collection` — that's the record IRI.
    assert "collection" not in out


def test_update_record_does_not_clobber_record_iri():
    out = _expand(
        {"module": "alerts", "collection": "/api/3/alerts/abc"}, "update_record"
    )
    assert out["collection"] == "/api/3/alerts/abc"
    assert out["collectionType"] == "/api/3/alerts"


def test_already_set_collection_wins():
    out = _expand(
        {"module": "alerts", "collection": "/api/3/incidents"}, "create_record"
    )
    assert out["collection"] == "/api/3/incidents"


def test_module_already_an_iri_passes_through():
    out = _expand({"module": "/api/3/alerts"}, "create_record")
    assert out["collection"] == "/api/3/alerts"


def test_resource_payload_rides_through_untouched():
    out = _expand(
        {"module": "alerts", "resource": {"name": "x", "severity": "High"}},
        "create_record",
    )
    assert out["resource"] == {"name": "x", "severity": "High"}


def test_no_module_is_noop():
    out = _expand({"resource": {"name": "x"}}, "create_record")
    assert out == {"resource": {"name": "x"}}


def test_non_string_module_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"module": [1, 2]}, "create_record", errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.module")
        for e in errs
    )


def test_non_bool_is_upsert_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"module": "alerts", "is_upsert": "yes please"}, "create_record", errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.is_upsert")
        for e in errs
    )


def test_is_upsert_truthy_coerces():
    # pydantic coerces the usual true/1/"true" forms — no BAD_VALUE.
    errs: list[CompileError] = []
    _expand({"module": "alerts", "is_upsert": "true"}, "insert_record", errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_non_dict_returns_none():
    assert expand_record_crud("nope", "create_record", "p", [], _ident) is None


def test_end_to_end_compile_create_record(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: mk
      - name: mk
        type: create_record
        arguments:
          module: alerts
          resource:
            name: "{{ vars.name }}"
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
