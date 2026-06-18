"""Strict-whitelist enforcement on resolver normalizers.

Same trap that bit manual_input historically — unknown keys silently
dropped at compile time, surface as missing wire shape at FSR runtime.
Each normalizer now hard-errors on keys outside its friendly + canonical
sets.
"""
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode


def _unknown_param(r):
    return [e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM]


def test_delay_typo_minutes_rejected(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: d
      - name: d
        type: delay
        arguments:
          mins: 5
"""
    r = compile_yaml(text, db_path)
    errs = _unknown_param(r)
    assert errs and "'mins'" in errs[0].message


def test_delay_canonical_clean(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: d
      - name: d
        type: delay
        arguments:
          minutes: 5
"""
    r = compile_yaml(text, db_path)
    assert not _unknown_param(r), [e.to_dict() for e in r.errors]


def test_code_snippet_unknown_key_rejected(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: c
      - name: c
        type: code_snippet
        arguments:
          code: "print('hi')"
          script: "print('hi')"
"""
    r = compile_yaml(text, db_path)
    errs = _unknown_param(r)
    assert errs and "'script'" in errs[0].message


def test_record_crud_unknown_key_rejected(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: u
      - name: u
        type: update_record
        arguments:
          module: alerts
          severity: High
"""
    r = compile_yaml(text, db_path)
    errs = _unknown_param(r)
    assert errs and "'severity'" in errs[0].message


def test_start_on_create_unknown_key_rejected(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trg
        type: start_on_create
        arguments:
          module: alerts
          mocked: true
"""
    r = compile_yaml(text, db_path)
    errs = _unknown_param(r)
    assert errs and "'mocked'" in errs[0].message
