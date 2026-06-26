"""Pilot gap D — measured output-shape oracle (compiler.grounded_shapes)."""
from __future__ import annotations

from fsr_playbooks.compiler.grounded_shapes import (
    GroundedShapeStore,
    grounded_probe,
    merge_shape,
    shape_from_value,
)


def test_shape_from_scalars():
    assert shape_from_value("x") == {"kind": "scalar", "type": "string"}
    assert shape_from_value(3) == {"kind": "scalar", "type": "integer"}
    assert shape_from_value(True) == {"kind": "scalar", "type": "boolean"}
    assert shape_from_value(1.5) == {"kind": "scalar", "type": "float"}
    assert shape_from_value(None) == {"kind": "scalar", "type": "null"}


def test_shape_from_nested_dict_models_code_snippet_output():
    # The pilot's real shape: vars.steps.Reconcile.data.code_output.
    val = {"data": {"code_output": {"first": {"join_key": "abc"}}},
           "status": "Success"}
    shape = shape_from_value(val)
    assert shape["kind"] == "object"
    assert shape["keys"]["data"]["kind"] == "object"
    co = shape["keys"]["data"]["keys"]["code_output"]
    assert co["keys"]["first"]["keys"]["join_key"] == {
        "kind": "scalar", "type": "string"}
    # Crucially there is NO `.output` wrapper — E5 was a spurious .output level.
    assert "output" not in shape["keys"]


def test_shape_from_list_folds_items():
    shape = shape_from_value([{"id": 1}, {"id": 2}])
    assert shape["kind"] == "list"
    assert shape["item"]["keys"]["id"] == {"kind": "scalar", "type": "integer"}


def test_empty_list_item_is_any():
    assert shape_from_value([]) == {"kind": "list",
                                    "item": {"kind": "scalar", "type": "any"}}


def test_merge_marks_optional_keys():
    a = shape_from_value({"id": 1, "name": "x"})
    b = shape_from_value({"id": 2})  # no `name`
    merged = merge_shape(a, b)
    assert merged["keys"]["id"].get("optional") is not True
    assert merged["keys"]["name"].get("optional") is True


def test_merge_differing_scalar_widens_to_any():
    merged = merge_shape(shape_from_value("x"), shape_from_value(3))
    assert merged == {"kind": "scalar", "type": "any"}


def test_merge_null_marks_nullable():
    merged = merge_shape(shape_from_value("x"), shape_from_value(None))
    assert merged["type"] == "string" and merged.get("nullable") is True


def test_store_observe_and_probe_roundtrip(tmp_path):
    store = GroundedShapeStore()
    store.observe("code-snippet", "python_inline_code_editor",
                  {"data": {"code_output": [1, 2]}, "status": "Success"})
    probe = grounded_probe(store)
    shape = probe("code-snippet", "python_inline_code_editor", {})
    assert shape["keys"]["data"]["keys"]["code_output"]["kind"] == "list"
    # Un-observed op → None (walker falls back to inference).
    assert probe("smtp", "send_email", {}) is None


def test_store_persistence(tmp_path):
    p = tmp_path / "shapes.json"
    s1 = GroundedShapeStore(path=p)
    s1.observe("c", "op", {"a": 1})
    s1.save()
    s2 = GroundedShapeStore.load(p)
    assert s2.shape_for("c", "op")["keys"]["a"]["type"] == "integer"


def test_store_observe_accumulates_optionality(tmp_path):
    store = GroundedShapeStore()
    store.observe("c", "op", {"x": 1, "y": 2})
    store.observe("c", "op", {"x": 1})  # second run lacks y
    shape = store.shape_for("c", "op")
    assert shape["keys"]["y"].get("optional") is True
    assert shape["keys"]["x"].get("optional") is not True


# --------------------------------------------------------------------------- #
# Closed-loop: a grounded code_snippet shape catches the pilot E5 `.output` bug.
# The shape below is the EXACT envelope measured from live run 686525 on .205
# (code-snippet:python_inline_code_editor) — pinned here so the test is offline.
# --------------------------------------------------------------------------- #

_DEMO_CODE_SNIPPET_YAML = """
collection: T
playbooks:
  - name: P
    parameters: [first_name]
    steps:
      - name: trigger
        type: start
        next: Build greeting
      - name: Build greeting
        type: code_snippet
        next: Stamp greeting
        arguments:
          code: |
            print("hi")
      - name: Stamp greeting
        type: set_variable
        vars:
          greeting_text: "{{ vars.steps.Build_greeting.output }}"
"""


def test_grounded_probe_flags_spurious_output_path_E5():
    from fsr_playbooks.compiler.grounded_shapes import shape_from_value
    from fsr_playbooks.compiler.parser import parse_yaml
    from fsr_playbooks.compiler.typed_walker import walk_playbook

    measured = shape_from_value({
        "data": {"code_output": "hello Dylan"}, "status": "Success",
        "message": "", "operation": None})
    store = GroundedShapeStore(
        {"code-snippet:python_inline_code_editor": measured})

    coll, _ = parse_yaml(_DEMO_CODE_SNIPPET_YAML)

    # Without grounding the ref resolves through an unknown shape (no hard error).
    base = walk_playbook(coll, None)
    assert not any(
        d.code == "missing_field_on_step_output"
        for b in base.branches for d in b.diagnostics)

    # With the grounded shape, `.output` (absent from the real envelope) is a
    # hard error — the exact E5 failure the live run produced as greeting_text="".
    res = walk_playbook(coll, None, probe=grounded_probe(store))
    hits = [d for b in res.branches for d in b.diagnostics
            if d.code == "missing_field_on_step_output" and "output" in d.message]
    assert hits, "grounded probe should flag vars.steps.Build_greeting.output"


def _walk_connector_ref(path: str, store):
    from fsr_playbooks.compiler.parser import parse_yaml
    from fsr_playbooks.compiler.typed_walker import walk_playbook
    y = f"""
collection: T
playbooks:
  - name: P
    parameters: [ip]
    steps:
      - name: start
        type: start
        next: Query VirusTotal
      - name: Query VirusTotal
        type: connector
        arguments: {{connector: virustotal, operation: query_ip, params: {{ip: x}}}}
        next: Read
      - name: Read
        type: set_variable
        vars: {{x: "{{{{ vars.steps.Query_VirusTotal.{path} }}}}"}}
"""
    coll, _ = parse_yaml(y)
    res = walk_playbook(coll, None, probe=grounded_probe(store),
                        op_safety_fn=lambda c, o: "safe")
    return [d for b in res.branches for d in b.diagnostics
            if d.code == "missing_field_on_step_output"]


def test_grounded_connector_op_valid_passes_bogus_flagged():
    """A grounded connector-op shape: valid fields pass, bogus fields flag.

    Guards against the empty-shape failure mode (which would flag everything).
    """
    vt_shape = shape_from_value({
        "data": {"id": "8.8.8.8", "type": "ip_address",
                 "attributes": {"reputation": 0}},
        "status": "Success", "message": "", "operation": None})
    store = GroundedShapeStore({"virustotal:query_ip": vt_shape})
    assert _walk_connector_ref("data.id", store) == []
    assert _walk_connector_ref("status", store) == []
    assert _walk_connector_ref("data.NOPE", store), "bogus subfield must flag"
    assert _walk_connector_ref("topLevelNope", store), "bogus top key must flag"


# --------------------------------------------------------------------------- #
# Sync workflow_reference: child's set_variable vars surface at
# vars.steps.<refstep>.<childvar> (live-proven, run 686622). The walker
# synthesizes this statically from the child playbook in the same collection —
# works on both parsed (target: name) and resolved (workflowReference: IRI) IR.
# --------------------------------------------------------------------------- #

_PARENT_CHILD_YAML = """
collection: C
playbooks:
  - name: Child
    parameters: [base]
    steps:
      - name: start
        type: start
        next: Compute
      - name: Compute
        type: set_variable
        vars:
          product: "{{ (vars.input.params.base | int) * 10 }}"
  - name: Parent
    parameters: [base]
    steps:
      - name: start
        type: start
        next: Call child
      - name: Call child
        type: workflow_reference
        next: Stamp
        arguments:
          target: Child
          arguments: {base: "{{ vars.input.params.base }}"}
          apply_async: false
      - name: Stamp
        type: set_variable
        vars:
          out: "{{ vars.steps.Call_child.PRODUCT_PLACEHOLDER }}"
"""


def _wf_ref_diags(field: str):
    from fsr_playbooks.compiler.parser import parse_yaml
    from fsr_playbooks.compiler.typed_walker import walk_playbook
    y = _PARENT_CHILD_YAML.replace("PRODUCT_PLACEHOLDER", field)
    coll, _ = parse_yaml(y)
    res = walk_playbook(coll, "Parent")
    return [d for b in res.branches for d in b.diagnostics
            if d.code == "missing_field_on_step_output"]


def test_sync_workflow_reference_valid_child_var_passes():
    assert _wf_ref_diags("product") == []


def test_sync_workflow_reference_bogus_child_var_flagged():
    hits = _wf_ref_diags("not_a_var")
    assert hits and "not_a_var" in hits[0].message


def test_async_workflow_reference_does_not_expose_child_vars():
    # apply_async: true → fire-and-forget → no readable output. We must NOT
    # synthesize the child's vars for it; reading `.product` off an async ref is
    # itself a bug, so it's correctly flagged (not silently valid).
    from fsr_playbooks.compiler.parser import parse_yaml
    from fsr_playbooks.compiler.typed_walker import walk_playbook
    y = (_PARENT_CHILD_YAML.replace("PRODUCT_PLACEHOLDER", "product")
         .replace("apply_async: false", "apply_async: true"))
    coll, _ = parse_yaml(y)
    res = walk_playbook(coll, "Parent")
    # The same `.product` that PASSES on a sync ref must NOT pass on async —
    # the child's vars are not available from a fire-and-forget call.
    assert any(d.code == "missing_field_on_step_output"
               for b in res.branches for d in b.diagnostics)
