"""grounded_help: resolvable reference paths from the grounded oracle.

This is the answer an agent gets when a step-output reference renders empty --
the concrete paths that DO resolve, read from the recorded shape (no live run).
"""
from __future__ import annotations

from fsr_playbooks import output_shape as os_


def test_list_op_suggests_join_and_index():
    h = os_.grounded_help("cyops_utilities", "get_macro_list", step_name="Enrich")
    assert h["grounded"] and h["is_list"]
    paths = [s["path"] for s in h["suggested_references"]]
    assert "vars.steps.Enrich.data | join(', ')" in paths
    assert "vars.steps.Enrich.data[0]" in paths
    # never a phantom attribute on a list of scalars
    assert not any(p.endswith(".macros") for p in paths)


def test_object_op_suggests_real_field_names():
    h = os_.grounded_help("fortinet-fortiguard-threat-intelligence",
                          "threat_intel_search", step_name="TI")
    assert h["grounded"] and not h["is_list"]
    paths = [s["path"] for s in h["suggested_references"]]
    # the real nested fields an author would otherwise guess wrong
    assert any(p.startswith("vars.steps.TI.data.") for p in paths)


def test_ungrounded_op_is_honest_not_a_guess():
    h = os_.grounded_help("nowhere", "no_such_op", step_name="X")
    assert h["grounded"] is False
    assert "not grounded" in h["message"]
    assert "suggested_references" not in h


def test_step_name_spaces_are_normalized():
    h = os_.grounded_help("cyops_utilities", "get_macro_list", step_name="Get Macros")
    assert all("Get_Macros" in s["path"] for s in h["suggested_references"])


def test_from_grounded_converts_kinds():
    assert os_._from_grounded({"kind": "scalar", "type": "integer"}) == "int"
    assert os_._from_grounded(
        {"kind": "list", "item": {"kind": "scalar", "type": "string"}}
    ) == {"__list_of__": "str", "__len__": 1}
    assert os_._from_grounded(
        {"kind": "object", "keys": {"a": {"kind": "scalar", "type": "boolean"}}}
    ) == {"a": "bool"}
