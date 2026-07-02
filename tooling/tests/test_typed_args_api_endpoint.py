"""Typed-args model for the api_endpoint trigger (Custom API Endpoint,
FSR handler ``cybersponse.api_call``) -- the 6th start variant.

Validation-only (the `record_action` / `find_record` precedent): the canonical
transform (the token-based auth default + trigger-infra setdefaults) stays in
the resolver, so `expand_api_endpoint` never mutates and always returns ``None``.
These tests pin the scalar validation -- the headline win is catching a
wrong-typed `route` (the endpoint name) that would otherwise silently produce a
malformed trigger, plus a non-list `authentication_methods`.

Also asserts the P1 front-door trigger coverage: `start` (Manual + Referenced)
and `api_endpoint` (Custom API Endpoint) now have introspectable schemas via
`get_step_arg_schema`, closing the discover gap for 2 of the 3 previously-
unmodeled trigger variants."""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import CompileError, ErrorCode
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import (
    STEP_ARG_MODELS,
    ApiEndpointArgs,
    RecordActionArgs,
    expand_api_endpoint,
    is_modeled,
)


def _expand(args, errs=None):
    return expand_api_endpoint(args, "p.steps[0]", errs if errs is not None else [])


def test_registry_models_api_endpoint_and_start():
    assert STEP_ARG_MODELS.get("api_endpoint") is ApiEndpointArgs
    assert is_modeled("api_endpoint") is True
    # P1b: `start` reuses RecordActionArgs (the Manual variant contract; the
    # plain Referenced form validates clean via all-Optional fields).
    assert STEP_ARG_MODELS.get("start") is RecordActionArgs
    assert is_modeled("start") is True


def test_schema_now_introspectable_for_both_trigger_variants():
    # The P1 discover win: an agent can now ask "what does a start / api_endpoint
    # step take?" and get a JSON Schema instead of None.
    assert emit_step_arg_schema("api_endpoint") is not None
    assert emit_step_arg_schema("start") is not None


def test_validation_only_returns_none_and_does_not_mutate():
    args = {"route": "lookup_ip", "authentication_methods": [""]}
    snapshot = dict(args)
    assert _expand(args) is None
    assert args == snapshot


def test_valid_route_and_auth_pass():
    errs: list[CompileError] = []
    _expand({"route": "lookup_ip"}, errs)
    assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]
    # Explicit auth modes are all valid lists.
    for auth in ([""], ["anonymous"], ["Basic"]):
        errs = []
        _expand({"route": "lookup_ip", "authentication_methods": auth}, errs)
        assert not [e for e in errs if e.code is ErrorCode.BAD_VALUE]


def test_non_string_route_is_clean_bad_value():
    errs: list[CompileError] = []
    _expand({"route": 123}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.route")
        for e in errs
    )


def test_non_list_authentication_methods_is_clean_bad_value():
    # The wire value is a list (e.g. [""]); a bare string is a common mistake.
    errs: list[CompileError] = []
    _expand({"route": "lookup_ip", "authentication_methods": "token"}, errs)
    assert any(
        e.code is ErrorCode.BAD_VALUE
        and e.path.endswith("arguments.authentication_methods")
        for e in errs
    )


def test_non_dict_returns_none():
    assert expand_api_endpoint("nope", "p", []) is None


def test_end_to_end_compile_minimal_route_only(db_path):
    # The minimal clean form -- `route` only. The compiler fills token-based
    # auth ([""]) + the trigger-infra fields. A valid route must compile clean.
    text = """
collection: T
playbooks:
  - name: Lookup IP
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: lookup_ip
"""
    r = compile_yaml(text, db_path)
    assert not [e for e in r.errors if e.severity == "error"], \
        [e.to_dict() for e in r.errors]


def test_end_to_end_compile_bad_route_surfaces_bad_value(db_path):
    text = """
collection: T
playbooks:
  - name: Lookup IP
    steps:
      - name: Start
        type: api_endpoint
        arguments:
          route: 123
"""
    r = compile_yaml(text, db_path)
    assert any(
        e.code is ErrorCode.BAD_VALUE and e.path.endswith("arguments.route")
        for e in r.errors
    ), [e.to_dict() for e in r.errors]
