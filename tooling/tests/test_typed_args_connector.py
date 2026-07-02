"""Typed-args model for the ``connector`` step envelope -- the P3 keystone.

The connector step is the most-authored type and the shared backbone for the
whole connector family (Connector/Code Snippet/Utilities/Send Email all route
through ``/wf/workflow/tasks/connector``). `ConnectorArgs` types the **static
envelope** so an agent can introspect "what does a connector step take?" via
`get_step_arg_schema("connector")` -- was `None`, the discover gap this closes.

DESIGN SPLIT (the manual_input lesson): the typed model owns the envelope
schema + scalar validation; the resolver (`_resolve_connector_args`) owns the
runtime catalog checks (missing connector/op -> precise MISSING_FIELD, unknown
op/param -> difflib "did you mean", auto-lift, enum/visibility/required). The
typed layer does NOT re-validate presence (the resolver's MISSING_FIELD message
is more precise than pydantic's "Field required") -- it flags present-but-wrong-
typed values only. `params` stays Any (per-op catalog)."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    ConnectorArgs,
    STEP_ARG_MODELS,
    expand_connector,
    is_modeled,
)


def _expand(args, errs=None):
    return expand_connector(args, "p.steps[0]", errs if errs is not None else [])


def test_registry_models_connector():
    assert STEP_ARG_MODELS.get("connector") is ConnectorArgs
    assert is_modeled("connector") is True


def test_schema_now_introspectable():
    # The P3 discover win: an agent can now ask "what does a connector step
    # take?" and get a JSON Schema instead of None.
    s = emit_step_arg_schema("connector")
    assert s is not None
    props = set(s.get("properties", {}))
    # The static envelope.
    for expected in ("connector", "operation", "config", "version",
                     "agent", "operationTitle", "params"):
        assert expected in props, expected
    # NOTE: connector/operation are NOT in the schema's `required` -- they're
    # declared Optional so pydantic doesn't shadow the resolver's richer
    # "connector step requires arguments.connector" MISSING_FIELD message (the
    # manual_input lesson). The resolver enforces presence at runtime; the
    # schema's job here is to advertise the envelope fields, not re-assert the
    # resolver's required check. (A future `description` annotation could note
    # they're required, if agents need it pre-compile.)


def test_validation_only_returns_none_and_does_not_mutate():
    args = {"connector": "cyops_utilities", "operation": "make_cyops_request",
            "params": {"iri": "/api/3/alerts"}}
    snapshot = dict(args)
    assert _expand(args) is None
    assert args == snapshot


def test_valid_envelope_passes():
    errs = []
    _expand({"connector": "smtp", "operation": "send_email_new"}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_wrong_typed_connector_is_bad_value():
    errs = []
    _expand({"connector": 123, "operation": "x"}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.connector")
        for e in errs
    )


def test_wrong_typed_operation_is_bad_value():
    errs = []
    _expand({"connector": "smtp", "operation": ["x"]}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.operation")
        for e in errs
    )


def test_params_stays_any_not_typed():
    # params is the per-op catalog payload -- a mapping (or absent). It must
    # NOT be type-checked here (the resolver's catalog checks own that surface).
    for params in ({"a": 1}, None, []):
        errs = []
        _expand({"connector": "smtp", "operation": "x", "params": params}, errs)
        assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE
                    and "params" in (e.path or "")]


def test_non_dict_returns_none():
    assert expand_connector("nope", "p", []) is None


def test_resolver_missing_connector_message_unshadowed(db_path):
    # A MISSING connector must surface the resolver's precise message, not
    # pydantic's "Field required". (The typed layer does not re-validate
    # presence -- the resolver owns that.)
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: do
      - name: do
        type: connector
        arguments:
          operation: make_cyops_request
"""
    r = compile_yaml(text, db_path)
    missing = [e for e in r.errors
               if e.code is ErrorCode.MISSING_FIELD
               and e.path.endswith("arguments.connector")]
    assert missing, [e.to_dict() for e in r.errors]
    assert "connector step requires arguments.connector" in (missing[0].message or "")


def test_end_to_end_compile_connector_step(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: noop
      - name: noop
        type: connector
        arguments:
          connector: cyops_utilities
          operation: no_op
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]
