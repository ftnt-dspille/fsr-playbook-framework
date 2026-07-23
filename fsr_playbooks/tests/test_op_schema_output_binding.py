"""`get_op_schema` must teach output BINDING, not just input params.

A weak authoring model (haiku on GA) drove the correct build sequence but
bound a connector op's whole envelope — `vars.steps.X.data` — into an alert
description, which renders as `Array`/`[object Object]` instead of the scalar.
Root cause: the envelope rule (`.data.<field>`) lived only in
`get_step_type("connector")`, which the build sequence skips; `get_op_schema`
(which it DOES call) surfaced no output guidance. These pins keep the binding
hint present and, critically, CORRECT — never inventing a `.data.<field>` that
isn't real (that would just swap one wrong binding for another).
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_discovery import (
    _output_binding_hint,
    _output_field_names,
    get_op_schema,
)


def test_static_schema_keys_are_data_fields():
    # Static output schema `{"minutes": ""}` — untyped, but its key IS the
    # real `.data` field the author must bind to.
    assert _output_field_names({"output_schema_json": '{"minutes": ""}'}) == ["minutes"]


def test_observed_flat_envelope_is_not_treated_as_data_fields():
    # A run-derived schema that captured the flattened envelope
    # (status/message siblings) must NOT surface those as `.data.<field>` —
    # that would teach `vars.steps.X.data.status` when status is an envelope
    # sibling. No explicit nested `data` object → no field claim.
    observed = '{"status": "str", "message": "str", "policyId": "str"}'
    assert _output_field_names({"output_schema_observed": observed}) == []


def test_observed_with_nested_data_object_is_unwrapped():
    observed = '{"status": "str", "data": {"reputation": 1, "asn": "x"}}'
    assert _output_field_names({"output_schema_observed": observed}) == ["reputation", "asn"]


def test_static_preferred_over_observed():
    row = {
        "output_schema_json": '{"minutes": ""}',
        "output_schema_observed": '{"status": "str", "data": {"other": 1}}',
    }
    assert _output_field_names(row) == ["minutes"]


def test_hint_names_the_field_when_known():
    hint = _output_binding_hint({"output_schema_json": '{"minutes": ""}'})
    assert "data.minutes" in hint
    # and warns against the bare-envelope binding
    assert "Array" in hint or "object Object" in hint


def test_hint_falls_back_to_generic_envelope_rule_when_unknown():
    hint = _output_binding_hint({})
    assert "data.<key>" in hint
    # must not fabricate a specific field
    assert "data.minutes" not in hint


def test_get_op_schema_surfaces_binding_for_convert_periodic():
    # End-to-end against the packaged catalog: the op whose real failure this
    # fixes must now hand the author the `minutes` field name.
    r = get_op_schema("cyops_utilities", "convert_periodic_time_to_minutes")
    assert r.get("output_fields") == ["minutes"]
    assert "## output binding" in r["markdown"]
    assert "vars.steps.<step_name>.data.minutes" in r["markdown"]
