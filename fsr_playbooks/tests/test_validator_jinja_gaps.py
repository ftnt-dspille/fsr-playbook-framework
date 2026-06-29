"""Authoring-flow validator gaps surfaced by the broken-playbook audit.

Two checks that previously let a broken playbook compile clean (and
verify_playbook report ready_to_push=True):

  * #3 malformed Jinja delimiters — an unclosed ``{{`` / mismatched ``{%`` →
    *error* (the template fails at runtime; nearly zero false-positive risk).
  * #2 undefined ``vars.<name>`` — a local var no SetVariable ever defines →
    *warning* (vars are playbook-global; surface the suspicion without
    hard-blocking on a possible false positive).
"""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

# Resolve via the standard order so CI falls back to the packaged slim DB.
DB = default_db_path()


def _errs(yaml_text: str):
    res = compile_yaml(yaml_text, DB)
    return res.errors


def _by_severity(errs, sev):
    return [e for e in errs if getattr(e, "severity", "error") == sev]


# ---- #3 malformed Jinja ----------------------------------------------------

_UNCLOSED_EXPR = """
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {foo: "value {{ 1 + 2 is broken"}
"""

_STMT_MISMATCH = """
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {foo: "{% if x }}"}
"""

_BALANCED = """
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {foo: "{{ vars.bar }}", bar: "x"}
"""


def test_unclosed_expression_is_error():
    errs = _errs(_UNCLOSED_EXPR)
    hits = [e for e in errs if e.code.value == "jinja_syntax_error"]
    assert hits and all(e.severity == "error" for e in hits)


def test_statement_delimiter_mismatch_is_error():
    errs = _errs(_STMT_MISMATCH)
    assert any(e.code.value == "jinja_syntax_error"
               and e.severity == "error" for e in errs)


def test_balanced_jinja_is_clean():
    errs = _errs(_BALANCED)
    assert not [e for e in errs if e.code.value == "jinja_syntax_error"]


# A code-step body that injects two real Jinja refs AND builds a Python
# nested-dict literal whose adjacent `}}` the old brace-count mistook for Jinja
# (the archetype_pilot_reconcile_and_report false positive). The real parser
# treats the stray `}}` as literal text, so this must compile clean.
_CODE_STEP_DICT_BRACES = '''
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars:
          code: |
            fc = {{ vars.steps.Start.data.x }}
            sn = {{ vars.steps.Start.data.y }}
            blocks = [{"type": "header", "text": {"type": "plain_text", "text": "CMDB Reconciliation"}}]
            return blocks
'''


def test_code_step_dict_braces_not_flagged():
    errs = _errs(_CODE_STEP_DICT_BRACES)
    jinja = [e for e in errs if e.code.value == "jinja_syntax_error"]
    bad = [e for e in errs if e.code.value == "bad_value"
           and "Jinja" in e.message]
    assert not jinja, [e.message for e in jinja]
    assert not bad, [e.message for e in bad]


# An unknown filter name on a compiling playbook -> warning, never a block.
_UNKNOWN_FILTER = '''
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {foo: "{{ vars.bar | defualt('x') }}", bar: "ok"}
'''


def test_unknown_filter_is_warning_not_blocking():
    errs = _errs(_UNKNOWN_FILTER)
    hits = [e for e in errs if e.code.value == "unknown_jinja_filter"]
    assert hits and all(e.severity == "warning" for e in hits)
    assert not [e for e in errs if e.severity == "error"]


# ---- #2 undefined vars.<name> ---------------------------------------------

_UNDEFINED_VAR = """
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {foo: "{{ vars.totally_undefined }}"}
"""

_DEFINED_THEN_READ = """
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {bar: "x", baz: "{{ vars.bar }}"}
"""

_RUNTIME_KEYS_OK = """
collection: t
playbooks:
  - name: g
    steps:
      - name: Start
        type: start
        next: Set
      - name: Set
        type: set_variable
        vars: {a: "{{ vars.input.records }}", b: "{{ vars.item }}"}
"""


def test_undefined_var_is_warning_not_blocking():
    errs = _errs(_UNDEFINED_VAR)
    hits = [e for e in errs if "is never defined by a SetVariable" in e.message]
    assert hits
    assert all(e.severity == "warning" for e in hits)
    # Warning must not block ready_to_push → compile stays ok.
    assert not _by_severity(errs, "error")


def test_setvariable_defined_var_not_flagged():
    errs = _errs(_DEFINED_THEN_READ)
    assert not [e for e in errs if "is never defined" in e.message]


def test_runtime_keys_and_loop_item_not_flagged():
    # vars.input / vars.item are runtime-provided, never authored.
    errs = _errs(_RUNTIME_KEYS_OK)
    assert not [e for e in errs if "is never defined" in e.message]
