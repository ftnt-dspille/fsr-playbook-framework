"""A bare `.attr` on a connector op whose grounded output is a LIST is a
confident bug, not a soft unknown.

Before this, the firm `missing_field_on_step_output` diagnosis fired only when
the list-producing step was a `for_each` step; a connector op whose grounded
shape is a list (e.g. cyops_utilities.get_macro_list, whose `.data` is a list of
strings) fell through to a non-surfaced `unknown_shape_downstream_reference`
warning, so `vars.steps.X.data.macros` passed verify. Now that grounded
connector-op list shapes are known, the same confident diagnosis applies.
"""
from __future__ import annotations

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.grounded_shapes import GroundedShapeStore, grounded_probe
from fsr_playbooks.compiler.pipeline import compile_yaml
from fsr_playbooks.compiler.typed_walker import walk_playbook

_ENVELOPE = {"operation": None, "status": "Success", "message": "",
             "data": ["Current_User", "Body", "mitre_version"]}  # data is a list[str]


def _coll(ref: str):
    y = f"""collection: G
visible: true
playbooks:
- name: Macro Digest
  is_active: true
  steps:
  - {{name: Start, type: start, next: Get Macros}}
  - {{name: Get Macros, type: connector, connector: cyops_utilities, operation: get_macro_list, config: "", params: {{}}, next: Record}}
  - name: Record
    type: create_record
    module: alerts
    resource: {{name: D, severity: Low, description: "{{{{ vars.steps.Get_Macros.data{ref} }}}}"}}
"""
    return compile_yaml(y, default_db_path()).ir


def _walk(coll):
    store = GroundedShapeStore()
    store.observe("cyops_utilities", "get_macro_list", _ENVELOPE)
    return walk_playbook(coll, "Macro Digest",
                         probe=grounded_probe(store),
                         op_safety_fn=lambda c, o: "safe")


def _codes(ref: str) -> list[str]:
    return [d.code for d in _walk(_coll(ref)).diagnostics
            if "Get_Macros" in (d.message or "")]


def test_attr_on_grounded_connector_list_is_missing_field():
    # `.data.macros` -- phantom attribute on a list -> confident bug.
    codes = _codes(".macros | join(', ')")
    assert "missing_field_on_step_output" in codes, codes
    # and NOT merely the soft unknown warning it used to be
    assert "unknown_shape_downstream_reference" not in codes, codes


def test_correct_list_reference_is_clean():
    # joining or indexing the list resolves -> no diagnostic on the ref.
    assert _codes(" | join(', ')") == []
    assert _codes("[0]") == []


def test_ungrounded_connector_op_stays_soft():
    """Without a grounded shape the op is genuinely unknown, so a `.attr` must
    stay a soft unknown (no false positive offline) -- NOT missing_field."""
    coll = _coll(".macros | join(', ')")
    res = walk_playbook(coll, "Macro Digest", probe=None,
                        op_safety_fn=lambda c, o: "safe")
    codes = [d.code for d in res.diagnostics if "Get_Macros" in (d.message or "")]
    assert "missing_field_on_step_output" not in codes, codes
