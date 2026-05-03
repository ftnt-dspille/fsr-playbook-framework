from compiler import compile_yaml
from compiler.errors import ErrorCode


def test_find_record_missing_query(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: start
        type: start
        next: f
      - id: f
        type: find_record
        arguments:
          module: alerts
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.MISSING_FIELD)
    assert e.path.endswith(".query")


def test_set_variable_kwargs_permissive(db_path):
    # set_multiple has **kwargs, so extras are accepted at validate time
    # (FSR runtime permits arbitrary keys).
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: start
        type: start
        next: s
      - id: s
        type: set_variable
        arguments:
          arg_list:
            - name: x
              value: "1"
          extra_kw: ok
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


def test_framework_params_excluded(db_path):
    # `cond(step, conditions, ...)` — `step` is framework-injected and
    # should NOT be required of the user.
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: start
        type: start
        next: d
      - id: d
        type: decision
        arguments:
          conditions: []
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
