"""step_output + runtime_dep logic, pure and box-free.

Pins sanitization (no captured values or box tokens survive), sampling, and the
render-against-real-shape resolver that the runtime eval grades on.
"""
from __future__ import annotations

from tooling.evals.corpus_authoring import runtime_dep, step_output


def test_shape_drops_values_and_id_keys():
    raw = {"status": "Success", "message": "",
           "data": ["Current_User", "mitre_version"],
           "FortiSIEMLastPullTime_de2f8ff1_476c_4363_9f04_0565d0e7a994": 123456789012}
    shape = step_output.shape_of(raw)
    assert shape["status"] == "str" and shape["message"] == "str"
    assert shape["data"] == {"__list_of__": "str", "__len__": 2}
    # the id-bearing key is genericized; no captured string value survives
    assert "<id>" in shape and not any("FortiSIEM" in k for k in shape)
    import json
    txt = json.dumps(shape)
    assert "Current_User" not in txt and "mitre_version" not in txt


def test_sample_builds_renderable_value():
    shape = {"status": "str", "data": {"__list_of__": "str", "__len__": 8}}
    s = step_output.sample_of(shape)
    assert isinstance(s["data"], list) and s["data"] and isinstance(s["data"][0], str)


def test_resolver_true_for_list_ref_false_for_phantom_attr():
    shape = {"data": {"__list_of__": "str", "__len__": 3}}
    shapes = {"Get_Macros": shape}
    assert step_output.reference_resolves(
        "{{ vars.steps.Get_Macros.data | join(', ') }}", shapes)
    # a phantom attribute on a list of strings renders empty
    assert not step_output.reference_resolves(
        "{{ vars.steps.Get_Macros.data.macros }}", shapes)
    assert not step_output.reference_resolves(
        "{{ vars.steps.Get_Macros.data[0].name }}", shapes)


def test_refs_to_step_normalizes_spaces():
    coll = {"playbooks": [{"steps": [
        {"name": "Record", "resource": {"d": "{{ vars.steps.Get_Macros.data }}"}}]}]}
    refs = runtime_dep.refs_to_step(coll, "Get Macros")
    assert len(refs) == 1 and "Get_Macros" in refs[0][1]


def test_inject_wrong_path_breaks_a_resolving_ref():
    shape = {"data": {"__list_of__": "str", "__len__": 3}}
    good = ("collection: X\nplaybooks:\n- name: P\n  steps:\n"
            "  - name: Get Macros\n    type: connector\n    connector: cyops_utilities\n"
            "    operation: get_macro_list\n    next: Rec\n"
            "  - name: Rec\n    type: create_record\n    module: alerts\n"
            "    resource:\n      description: \"{{ vars.steps.Get_Macros.data | join(', ') }}\"\n")
    d = runtime_dep.inject_wrong_output_path(good, "Get Macros", shape)
    assert d and d["runtime_only"]
    # broken no longer resolves; restoring the original does
    assert not runtime_dep.grade_runtime_dependency(d["yaml"], "Get Macros", shape)["resolves"]
    assert runtime_dep.grade_runtime_dependency(good, "Get Macros", shape)["resolves"]
