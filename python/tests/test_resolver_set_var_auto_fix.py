"""Resolver auto-fixes for SetVariable foot-guns.

Two rewriters land in the resolver before validation:
  1. Reserved-keyword rename + downstream `vars.<old>` rewrite.
  2. `vars.steps.<set_var>.<key>` → `vars.<key>` rewrite.

Both must catch every Jinja access form (dotted, single-quoted bracket,
double-quoted bracket, .get('...') / .get("...")) so the agent doesn't
need a prompt rule about which access shape to use.
"""
from compiler import compile_yaml


def _show_popup_description(fsr_json: dict) -> str:
    for c in fsr_json.get("data", []):
        for wf in c.get("workflows", []):
            for s in wf.get("steps", []):
                if s.get("name") == "M":
                    return s["arguments"]["input"]["schema"]["description"]
    return ""


def _set_var_args(fsr_json: dict) -> dict:
    for c in fsr_json.get("data", []):
        for wf in c.get("workflows", []):
            for s in wf.get("steps", []):
                if s.get("name") == "SV":
                    return s["arguments"]
    return {}


def _playbook(description_yaml: str) -> str:
    """Build a playbook where SV writes a reserved key and M's
    description templates the access forms under test."""
    return f"""\
collection: T
playbooks:
  - name: T
    steps:
      - type: start
        name: Start
        next: SV
      - type: set_variable
        name: SV
        vars:
          message: hi
        next: M
      - type: manual_input
        name: M
        arguments:
          title: t
          description: |
{description_yaml}
        options:
          - display: OK
            primary: true
            next: End
      - type: end
        name: End
"""


# ---------------------------------------------------------------------
# 1. Reserved-keyword rename
# ---------------------------------------------------------------------

def test_reserved_key_message_renamed_in_set_variable_args(db_path):
    """`vars: {message: hi}` must compile and emit `message_var` on the
    wire — `message` itself crashes the FSR runtime."""
    r = compile_yaml(_playbook("            x: 1"), db_path)
    assert r.ok, [e.message for e in r.errors]
    args = _set_var_args(r.fsr_json)
    assert args == {"message_var": "hi"}


def test_reserved_key_emits_warning_with_rename_path(db_path):
    r = compile_yaml(_playbook("            x: 1"), db_path)
    assert any(
        "auto-renamed to 'message_var'" in w.message
        for w in r.warnings
    ), [w.message for w in r.warnings]


# ---------------------------------------------------------------------
# 2. Top-level vars.<reserved> rewrite — three access forms
# ---------------------------------------------------------------------

def test_top_level_dotted_access_rewritten(db_path):
    r = compile_yaml(_playbook("            A: '{{ vars.message }}'"), db_path)
    assert r.ok
    assert "vars.message_var" in _show_popup_description(r.fsr_json)
    assert "vars.message " not in _show_popup_description(r.fsr_json)


def test_top_level_bracket_quote_access_rewritten(db_path):
    for q in ("'", '"'):
        body = f"            A: '{{{{ vars[{q}message{q}] }}}}'"
        r = compile_yaml(_playbook(body), db_path)
        assert r.ok
        desc = _show_popup_description(r.fsr_json)
        assert "vars.message_var" in desc, desc


def test_top_level_get_call_access_rewritten(db_path):
    """`vars.get('message')` keeps the .get() call (soft-fail
    semantics the author chose) but swaps the key string."""
    for q in ("'", '"'):
        body = f"            A: '{{{{ vars.get({q}message{q}) }}}}'"
        r = compile_yaml(_playbook(body), db_path)
        assert r.ok
        desc = _show_popup_description(r.fsr_json)
        # Must keep `.get(...)` form — only the key string changes.
        assert "vars.get(" in desc and "message_var" in desc, desc


# ---------------------------------------------------------------------
# 3. vars.steps.<set_var>.<key> namespace rewrite — six access forms
# ---------------------------------------------------------------------

def test_step_ref_dotted_dotted(db_path):
    r = compile_yaml(_playbook(
        "            A: '{{ vars.steps.SV.message }}'"), db_path)
    assert r.ok
    assert "vars.message_var" in _show_popup_description(r.fsr_json)


def test_step_ref_dotted_bracket(db_path):
    for q in ("'", '"'):
        body = f"            A: '{{{{ vars.steps.SV[{q}message{q}] }}}}'"
        r = compile_yaml(_playbook(body), db_path)
        assert r.ok, [e.message for e in r.errors]
        assert "vars.message_var" in _show_popup_description(r.fsr_json)


def test_step_ref_bracket_dotted(db_path):
    for q in ("'", '"'):
        body = f"            A: '{{{{ vars.steps[{q}SV{q}].message }}}}'"
        r = compile_yaml(_playbook(body), db_path)
        assert r.ok
        assert "vars.message_var" in _show_popup_description(r.fsr_json)


def test_step_ref_bracket_bracket(db_path):
    body = "            A: '{{ vars.steps[\"SV\"][\"message\"] }}'"
    r = compile_yaml(_playbook(body), db_path)
    assert r.ok
    assert "vars.message_var" in _show_popup_description(r.fsr_json)


def test_step_ref_get_form(db_path):
    """`vars.steps.SV.get('message')` and the bracketed-step variant
    both rewrite to the canonical top-level form."""
    for body in (
        '            A: \'{{ vars.steps.SV.get("message") }}\'',
        '            A: \'{{ vars.steps["SV"].get("message") }}\'',
    ):
        r = compile_yaml(_playbook(body), db_path)
        assert r.ok
        desc = _show_popup_description(r.fsr_json)
        assert "vars.message_var" in desc, desc


# ---------------------------------------------------------------------
# 4. Cross-cutting — both rewrites happen in the same playbook
# ---------------------------------------------------------------------

def test_combined_reserved_rename_and_step_ref_rewrite(db_path):
    """The user's actual chat-failure case: one playbook that needs
    BOTH the reserved-keyword rename AND the wrong-namespace rewrite."""
    r = compile_yaml(_playbook(
        "            A: 'plain {{ vars.message }} step "
        "{{ vars.steps.SV.message }}'"), db_path)
    assert r.ok
    desc = _show_popup_description(r.fsr_json)
    assert desc.count("vars.message_var") == 2, desc


# ---------------------------------------------------------------------
# 5. Negative — vars.steps.<X>.<reserved> on a NON-set_variable step
#    must NOT be rewritten (that's a legitimate connector/find_record
#    output namespace).
# ---------------------------------------------------------------------

def test_step_ref_on_non_set_variable_step_left_alone(db_path):
    """`vars.steps.<X>.message` on a NON-set_variable step must not be
    rewritten — connector / find_record outputs legitimately live in
    that namespace. The rewriter only fires for keys actually written
    by a SetVariable step in the same playbook."""
    text = """\
collection: T
playbooks:
  - name: T
    steps:
      - type: start
        name: Start
        next: Lookup
      - type: connector
        name: Lookup
        arguments:
          connector: cyops_utilities
          operation: no_op
        next: SV
      - type: set_variable
        name: SV
        vars:
          greeting: hi
        next: M
      - type: manual_input
        name: M
        arguments:
          title: t
          description: 'out: {{ vars.steps.Lookup.message }}'
        options:
          - display: OK
            primary: true
            next: End
      - type: end
        name: End
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.message for e in r.errors]
    # SV doesn't write `message`, and `Lookup` isn't a SetVariable, so
    # the reference must survive untouched.
    desc = _show_popup_description(r.fsr_json)
    assert "vars.steps.Lookup.message" in desc, desc
    assert "vars.message" not in desc
