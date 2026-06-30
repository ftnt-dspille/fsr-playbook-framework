"""Compile-time reference lint (PLAYBOOK_AUTHORING_DX_PLAN 2a).

Wires the typed walker's reference-existence diagnostics into the default
compile as *warnings*, so a bad `vars.steps.X.foo` is caught offline. The
headline case is a wrong parent->child output reference, which previously only
failed on a live run.
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

DB = default_db_path()


def _ref_warnings(text: str):
    r = compile_yaml(text, DB)
    return r, [e for e in r.errors if e.code.value == "bad_var_reference"]


# A parent that calls a child and reads its set_variable output. The child sets
# `is_valid`; the parent reads it. Swap the read key to exercise the lint.
_PARENT_CHILD = """
collection: Ref Lint
playbooks:
- name: Child
  is_active: true
  steps:
  - {{name: Start, type: start, next: SetIt}}
  - {{name: SetIt, type: set_variable, vars: {{is_valid: "{{{{ true }}}}"}}}}
- name: Parent
  is_active: true
  steps:
  - {{name: Start, type: start, next: CallChild}}
  - {{name: CallChild, type: workflow_reference, apply_async: false,
     arguments: {{target: Child}}, next: Stamp}}
  - {{name: Stamp, type: set_variable, vars: {{final: "{{{{ vars.steps.CallChild.{key} }}}}"}}}}
"""


def test_good_child_output_reference_compiles_clean():
    r, warns = _ref_warnings(_PARENT_CHILD.format(key="is_valid"))
    assert r.ok
    assert warns == []


def test_wrong_child_output_reference_is_flagged_offline():
    r, warns = _ref_warnings(_PARENT_CHILD.format(key="is_valdi"))
    # warning-only: the playbook still compiles (the runtime may tolerate it)
    assert r.ok
    assert len(warns) == 1
    w = warns[0]
    assert w.severity == "warning"
    assert "is_valdi" in w.message
    assert w.path.startswith("Parent.")


def test_reference_lint_can_be_disabled():
    from fsr_playbooks.compiler.pipeline import compile_yaml as compile_yaml_pipe

    r = compile_yaml_pipe(
        _PARENT_CHILD.format(key="is_valdi"), DB, reference_lint_enabled=False
    )
    assert [e for e in r.errors if e.code.value == "bad_var_reference"] == []


def test_no_duplicate_with_existing_intra_playbook_check():
    # An intra-playbook wrong set_variable key is already flagged by the
    # validator's jinja check; the reference lint must not double-report it.
    text = """
collection: Dup
playbooks:
- name: P
  is_active: true
  steps:
  - {name: Start, type: start, next: A}
  - {name: A, type: set_variable, vars: {foo: "{{ 1 }}"}, next: B}
  - {name: B, type: set_variable, vars: {bar: "{{ vars.steps.A.WRONGKEY }}"}}
"""
    r = compile_yaml(text, DB)
    mentions = [
        e for e in r.errors
        if "vars.steps.A.WRONGKEY" in (e.message or "")
    ]
    assert len(mentions) == 1  # exactly one check owns it, not two


# ---------------------------------------------------------------------------
# manual_input declared-input-field validation (PLAYBOOK_AUTHORING_DX_PLAN F3).
# Grounded in a live FortiSOAR playbook prompt (step_examples provenance
# `step:00c8a0b4-6633-4bd6-89d5-bf0abb6230d5`): an InputBased prompt declaring
# a single "Dynamic List" field. The friendly `kind: select` reproduces that
# field's wire tuple (formType/dataType=dynamicList, type=array). Reading a
# field the form actually declares is clean; reading an undeclared field is
# caught offline as a bad_var_reference — which only works once the step-level
# `inputs:` hoist makes the declared fields visible to the lint.
# ---------------------------------------------------------------------------
_MI_FORM = """
collection: MI Field Lint
playbooks:
- name: P
  is_active: true
  steps:
  - {{name: Start, type: start, next: Ask}}
  - name: Ask
    type: manual_input
    title: Pick from the dynamic list
    inputs:
      - {{name: choice, kind: select, label: Choice, options: "{{{{ vars.dyn_list }}}}"}}
    options:
      - {{display: Submit, primary: true, next: Use}}
  - {{name: Use, type: set_variable, vars: {{picked: "{{{{ vars.steps.Ask.input.{key} }}}}"}}}}
"""


def test_declared_manual_input_field_reference_is_clean():
    r, warns = _ref_warnings(_MI_FORM.format(key="choice"))
    assert r.ok
    assert warns == []


def test_undeclared_manual_input_field_reference_is_flagged_offline():
    r, warns = _ref_warnings(_MI_FORM.format(key="choize"))
    assert r.ok  # warning-only, doesn't block
    assert len(warns) == 1
    w = warns[0]
    # The message must name the ACTUAL missing field, not the first segment.
    assert "choize" in w.message
    assert "'input'" not in w.message  # regression: used to blame `input`
    assert "choice" in w.message  # available declared key surfaced


def test_button_only_manual_input_input_read_does_not_false_error():
    # No `inputs:` declared -> open form -> reading input.* degrades to a
    # warning at most, never a hard error (button-only prompts are legal).
    text = """
collection: Button Only
playbooks:
- name: P
  is_active: true
  steps:
  - {name: Start, type: start, next: Ask}
  - name: Ask
    type: manual_input
    title: Approve?
    options:
      - {display: Approve, primary: true, next: Use}
  - {name: Use, type: set_variable, vars: {x: "{{ vars.steps.Ask.input.comment }}"}}
"""
    r = compile_yaml(text, DB)
    assert r.ok
    assert not [e for e in r.errors if e.severity == "error"
                and "comment" in (e.message or "")]
