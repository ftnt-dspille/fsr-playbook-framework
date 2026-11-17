"""Attr/index access on a scalar of UNKNOWN type (`any`) is soft, not an error.

A list whose element type could not be measured (e.g. make_cyops_request's
`data['hydra:member']`, whose records vary by queried module) folds to an item
shape of `{kind: scalar, type: any}`. Reaching a field on such an item
(`member[0].crontab`) is unknowable, not wrong -- it must degrade to a soft
unknown, never fire `missing_field_on_step_output`. A scalar of a KNOWN type
keeps erroring, so the check still has teeth."""
from __future__ import annotations

from fsr_playbooks.compiler.typed_walker import _resolve_path


def test_attr_on_untyped_scalar_is_soft():
    env = {"X": {"kind": "scalar", "type": "any"}}
    shape, code = _resolve_path("X", ".crontab", env)
    assert code == "", code
    assert shape["kind"] == "unknown"


def test_index_on_untyped_scalar_is_soft():
    env = {"X": {"kind": "scalar", "type": "any"}}
    _, code = _resolve_path("X", "[0]", env)
    assert code == "", code


def test_attr_on_known_scalar_still_errors():
    # teeth: a scalar of a KNOWN type has no fields, so this stays an error.
    env = {"X": {"kind": "scalar", "type": "string"}}
    _, code = _resolve_path("X", ".crontab", env)
    assert code == "missing_field_on_step_output", code


def test_hydra_member_field_chain_resolves_soft():
    # the make_cyops_request pattern: data['hydra:member'][0].<varying field>
    env = {"Q": {"kind": "object", "keys": {
        "data": {"kind": "object", "keys": {
            "hydra:member": {"kind": "list",
                             "item": {"kind": "scalar", "type": "any"}}}}}}}
    _, code = _resolve_path("Q", ".data['hydra:member'][0].crontab", env)
    assert code == "", code
