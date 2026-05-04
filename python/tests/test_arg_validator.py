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


def test_no_op_with_no_params_emits_no_warning(db_path):
    """Regression: `stop`/`end` compile to cyops_utilities.no_op which has
    zero param rows in the reference store. The validator must NOT emit
    the "params passed through unvalidated" warning when the user
    provided no params — only when they did and we can't verify them.
    """
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: stop
      - id: stop
        type: stop
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # No warnings about no_op passing through unvalidated.
    msgs = [e.message for e in r.errors]
    assert not any(
        "no param schema in store for cyops_utilities.no_op" in m for m in msgs
    ), msgs


def test_unknown_op_with_provided_params_still_warns(db_path):
    """Counterpart: when the user DOES supply params but we have no
    schema for them, the warning still fires — that's its real purpose.
    Uses a deliberately unknown connector/op pair so the warning path
    can't be mistaken for a strict-validation pass.
    """
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: noop
      - id: noop
        type: connector
        arguments:
          connector: cyops_utilities
          operation: no_op
          params:
            unverifiable: 1
"""
    r = compile_yaml(text, db_path)
    msgs = [e.message for e in r.errors]
    assert any(
        "no param schema in store for cyops_utilities.no_op" in m for m in msgs
    ), msgs
