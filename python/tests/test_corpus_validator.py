"""Corpus-driven enum-drift validation.

The classic catch: lowercase `operation: append` when the live corpus
shows every UpdateRecord step uses `Append` or `Overwrite` (capitalized).
"""
from compiler import compile_yaml
from compiler.errors import ErrorCode


def test_update_record_lowercase_operation_warns(db_path):
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
          resource:
            "@id": "/api/3/alerts/abc"
            description: "x"
          operation: append
"""
    r = compile_yaml(text, db_path)
    drift = [
        e for e in r.errors
        if e.code is ErrorCode.BAD_VALUE
        and e.severity == "warning"
        and e.path.endswith(".operation")
    ]
    assert drift, [e.to_dict() for e in r.errors]
    assert drift[0].near == "Append"


def test_update_record_canonical_operation_clean(db_path):
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
          resource:
            "@id": "/api/3/alerts/abc"
            description: "x"
          operation: Append
"""
    r = compile_yaml(text, db_path)
    drift = [
        e for e in r.errors
        if e.code is ErrorCode.BAD_VALUE
        and e.severity == "warning"
        and e.path.endswith(".operation")
    ]
    assert not drift, [e.to_dict() for e in r.errors]


def test_likely_required_key_missing_warns(db_path):
    # Hand-author a Decision in wire shape and omit `conditions:`,
    # which 100% of corpus Decision steps set. The resolver doesn't
    # inject it (it's user-supplied semantic content), so the absence
    # surfaces as a likely-required-key warning.
    from compiler.parser import parse_yaml
    from compiler.ir import Step
    from compiler.corpus_validator import CorpusValidator
    import sqlite3
    coll, _ = parse_yaml("""
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: d
      - name: d
        type: decision
        conditions: []
""")
    # Simulate a Decision step that lost its `conditions` key after
    # resolution (regression scenario).
    d = coll.playbooks[0].steps[1]
    d.step_type_name = "Decision"
    d.handler = "cond"
    d.arguments = {}
    conn = sqlite3.connect(str(db_path))
    errs = CorpusValidator(conn).validate(coll)
    miss = [e for e in errs if e.path.endswith(".conditions")]
    assert miss, [e.to_dict() for e in errs]
    assert miss[0].severity == "warning"


def test_jinja_value_skipped(db_path):
    # Jinja values resolve at runtime — never warn on them.
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
          resource:
            "@id": "/api/3/alerts/abc"
            description: "x"
          operation: "{{ vars.op }}"
"""
    r = compile_yaml(text, db_path)
    drift = [
        e for e in r.errors
        if e.code is ErrorCode.BAD_VALUE
        and e.severity == "warning"
        and e.path.endswith(".operation")
    ]
    assert not drift, [e.to_dict() for e in r.errors]
