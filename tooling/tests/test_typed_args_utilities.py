"""Typed-args model for the ``utilities`` step -- the P4 editor-palette gap
closure for the "Utilities" entry (canonical ``CyopsUtilices``).

``utilities`` is a connector-family alias, not a distinct step type: it routes
through ``ConnectorStepCtrl`` + ``connector.html``, so its wire shape IS the
connector envelope. The normalizer defaults ``connector: cyops_utilities``
(one of 55 utility ops) and falls through to ``_resolve_connector_args``; it
reuses the P3 ``ConnectorArgs`` envelope model (the way create/insert/update
share ``RecordCrudArgs``). These tests pin the registry contract, the alias
defaulting, the discover win (schema now introspectable), and the e2e compile."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    ConnectorArgs,
    STEP_ARG_MODELS,
    is_modeled,
)


def test_registry_models_utilities():
    # The alias reuses the P3 ConnectorArgs envelope model (no new model).
    assert STEP_ARG_MODELS.get("utilities") is ConnectorArgs
    assert is_modeled("utilities") is True


def test_schema_now_introspectable():
    # The discover win: an agent asking "what does a utilities step take?" gets
    # the connector envelope schema, not None.
    s = emit_step_arg_schema("utilities")
    assert s is not None
    props = set(s.get("properties", {}))
    for expected in ("connector", "operation", "config", "version",
                     "agent", "operationTitle", "params"):
        assert expected in props, expected


def test_end_to_end_compile_defaults_connector(db_path):
    # The alias surface: `type: utilities` with just an operation compiles to a
    # Connectors step with `connector: cyops_utilities` auto-stamped (the
    # normalizer default), operation/params passing through. This is what makes
    # the editor's "Utilities" palette entry authorable from YAML.
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: util
      - name: util
        type: utilities
        arguments:
          operation: no_op
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]

    def _find_steps(o):
        if isinstance(o, dict):
            if ("steps" in o and isinstance(o["steps"], list) and o["steps"]
                    and isinstance(o["steps"][0], dict)):
                return o["steps"]
            for v in o.values():
                s = _find_steps(v)
                if s:
                    return s
        elif isinstance(o, list):
            for v in o:
                s = _find_steps(v)
                if s:
                    return s
        return None

    steps = _find_steps(r.fsr_json)
    util = next(s for s in steps if s.get("name") == "util")
    args = util.get("arguments", {})
    assert args.get("connector") == "cyops_utilities"  # auto-stamped
    assert args.get("operation") == "no_op"             # authored, passed through


def test_end_to_end_compile_with_params(db_path):
    # A real utility op (make_cyops_request) with a params payload compiles
    # clean through the connector resolver's catalog checks.
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: util
      - name: util
        type: utilities
        arguments:
          operation: make_cyops_request
          params:
            iri: "/api/3/alerts"
            method: GET
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]


def test_wrong_typed_envelope_is_bad_value(db_path):
    # The alias reuses ConnectorArgs, so a wrong-typed envelope scalar is a
    # clean BAD_VALUE (the P3 validation-only win applies to utilities too).
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: util
      - name: util
        type: utilities
        arguments:
          operation: no_op
          connector: 123
"""
    r = compile_yaml(text, db_path)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.connector")
        for e in r.errors
    ), [e.to_dict() for e in r.errors]


def test_resolver_missing_operation_message_unshadowed(db_path):
    # `utilities` defaults `connector` but NOT `operation` -- the author picks
    # the utility op. A missing operation surfaces the connector resolver's
    # precise MISSING_FIELD message, not pydantic's "Field required".
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: util
      - name: util
        type: utilities
        arguments: {}
"""
    r = compile_yaml(text, db_path)
    missing = [e for e in r.errors
               if e.code is ErrorCode.MISSING_FIELD
               and e.path.endswith("arguments.operation")]
    assert missing, [e.to_dict() for e in r.errors]
    assert "connector step requires arguments.operation" in (missing[0].message or "")
