"""Compile rule: every `vars.input.params.<name>` reference must correspond to
a declared playbook parameter, else the trigger never materializes it and the
jinja evaluates empty at runtime (the "set_variable assumed vars.input.params.X
but no parameter X was defined" bug). See `_validate_input_param_refs`.
"""
from __future__ import annotations

from types import SimpleNamespace

from fsr_playbooks.compiler.errors import ErrorCode
from fsr_playbooks.compiler.resolver import Resolver


def _resolver() -> Resolver:
    r = Resolver.__new__(Resolver)  # bypass __init__'s file open (rule needs no DB)
    return r


def _pb(parameters, *step_args):
    steps = [SimpleNamespace(arguments=a) for a in step_args]
    return SimpleNamespace(parameters=parameters, steps=steps)


def _validate(pb):
    errors: list = []
    _resolver()._validate_input_param_refs(pb, 0, errors)
    return errors


def test_undeclared_param_ref_errors():
    pb = _pb([], {"value": "{{ vars.input.params.src_ip }}"})
    errors = _validate(pb)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.BAD_VALUE
    assert errors[0].severity != "warning"  # hard error
    assert "src_ip" in errors[0].message


def test_declared_param_ref_ok():
    pb = _pb(["src_ip"], {"value": "{{ vars.input.params.src_ip }}"})
    assert _validate(pb) == []


def test_bracket_form_undeclared_errors():
    pb = _pb([], {"value": "{{ vars.input.params['host_name'] }}"})
    errors = _validate(pb)
    assert len(errors) == 1
    assert "host_name" in errors[0].message


def test_bracket_form_declared_ok():
    pb = _pb(["host_name"], {"value": '{{ vars.input.params["host_name"] }}'})
    assert _validate(pb) == []


def test_reserved_record_inputs_not_flagged():
    # vars.input.records / vars.input.record are built-in trigger inputs,
    # not declared parameters — must not error.
    pb = _pb([], {"value": "{{ vars.input.records[0].iri }} {{ vars.input.record }}"})
    assert _validate(pb) == []


def test_multiple_undeclared_one_error_each():
    pb = _pb(
        ["a"],
        {"value": "{{ vars.input.params.a }} {{ vars.input.params.b }}"},
        {"value": "{{ vars.input.params.c }}"},
    )
    errors = _validate(pb)
    names = sorted(e.message.split("`")[1] for e in errors)
    assert names == ["vars.input.params.b", "vars.input.params.c"]
