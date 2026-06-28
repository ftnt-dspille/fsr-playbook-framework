"""Typed-args model for `delete_record` steps — registry contract, the
friendly→canonical transform (the three targeting modes + showDeleted rule),
and the new scalar validation (`show_deleted` wrong-typed → clean BAD_VALUE).

delete_record compiles to a `cyops_utilities.make_cyops_request` DELETE connector
step, so the byte-identical contract is the authoring path (test_delete_record.py);
these tests pin the typed layer directly. `expand_delete_record` takes the
resolver's `resolve_module_name` as a callback — here a passthrough identity."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    DeleteRecordArgs,
    expand_delete_record,
    is_modeled,
)


def _ident(raw, _path, _errs):
    """Stand-in for resolver.resolve_module_name (passthrough, no catalog)."""
    return raw


def _expand(args, errs=None):
    return expand_delete_record(args, "p.steps[0]", errs if errs is not None else [], _ident)


def test_registry_models_delete_record():
    assert STEP_ARG_MODELS.get("delete_record") is DeleteRecordArgs
    assert is_modeled("delete_record") is True


def test_single_record_iri():
    out = _expand({"record": "/api/3/alerts/abc"})
    assert out["params"]["iri"] == "/api/3/alerts/abc"
    assert out["params"]["method"] == "DELETE"
    assert out["connector"] == "cyops_utilities"
    assert out["operation"] == "make_cyops_request"


def test_single_record_show_deleted_appends_flag():
    out = _expand({"record": "/api/3/alerts/abc", "show_deleted": True})
    assert out["params"]["iri"] == "/api/3/alerts/abc?$showDeleted=true"


def test_single_record_show_deleted_uses_amp_when_query_present():
    out = _expand({"record": "/api/3/alerts/abc?x=1", "show_deleted": True})
    assert out["params"]["iri"].endswith("?x=1&$showDeleted=true")


def test_module_plus_record_id():
    out = _expand({"module": "alerts", "record_id": "abc"})
    assert out["params"]["iri"] == "/api/3/alerts/abc"


def test_module_plus_query_bulk_delete():
    out = _expand({"module": "alerts",
                   "query": {"logic": "AND", "filters": []}})
    assert out["params"]["iri"] == "/api/3/delete-with-query/alerts?$showDeleted=true"
    assert out["params"]["body"] == '{"logic": "AND", "filters": []}'


def test_query_show_deleted_false_suppresses_flag():
    out = _expand({"module": "alerts", "query": {"logic": "AND", "filters": []},
                   "show_deleted": False})
    assert out["params"]["iri"] == "/api/3/delete-with-query/alerts"


def test_no_target_is_missing_field():
    errs: list[CompileError] = []
    out = _expand({}, errs)
    assert out is None
    assert errs and errs[0].code is ErrorCode.MISSING_FIELD


def test_two_targets_is_missing_field():
    errs: list[CompileError] = []
    out = _expand({"record": "/api/3/alerts/abc", "module": "alerts",
                   "query": {"logic": "AND", "filters": []}}, errs)
    assert out is None
    assert errs and errs[0].code is ErrorCode.MISSING_FIELD


def test_record_id_without_module_is_missing_field():
    errs: list[CompileError] = []
    out = _expand({"record_id": "abc"}, errs)
    # record_id alone yields zero targets (record_id and module is falsy).
    assert out is None
    assert errs and errs[0].code is ErrorCode.MISSING_FIELD


def test_raw_iri_escape_hatch_passes_through():
    out = _expand({"params": {"iri": "/api/3/alerts/zzz", "method": "DELETE"}})
    assert out["params"]["iri"] == "/api/3/alerts/zzz"


def test_non_bool_show_deleted_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"record": "/api/3/alerts/abc", "show_deleted": "maybe"}, errs)
    assert any(e.code is ErrorCode.BAD_VALUE
               and e.path.endswith("arguments.show_deleted") for e in errs)


def test_non_dict_returns_none():
    assert expand_delete_record("nope", "p", [], _ident) is None


def test_end_to_end_compile_delete_record(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: del
      - name: del
        type: delete_record
        arguments:
          module: alerts
          record_id: "{{ vars.id }}"
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
