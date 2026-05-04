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


def test_decision_with_default_next_is_valid(db_path):
    """One condition + decision-level `next:` for the fallthrough case is
    the canonical FSR idiom. Inverse conditions for the default branch
    are overspecified and not required by the validator."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: choose
      - id: choose
        type: decision
        arguments:
          conditions:
            - option: yes
              condition: "{{ vars.input.params.go == 'yes' }}"
        branches:
          yes: act
        next: skip
      - id: act
        type: set_variable
        arguments:
          arg_list:
            - name: outcome
              value: acted
      - id: skip
        type: set_variable
        arguments:
          arg_list:
            - name: outcome
              value: skipped
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


def test_manual_input_unknown_args_rejected_as_error(db_path):
    """Repro of a Claude failure mode: passing `label` and `message` at
    the top of arguments. Earlier we surfaced these as warnings; the
    silent-drop screenshot bug taught us that's not strong enough.
    Resolver now hard-errors on unknown manual_input keys."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: ask
      - id: ask
        type: manual_input
        name: ask
        arguments:
          label: Message
          message: hi
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "label" in e.message and "message" in e.message
    assert e.severity == "error"


def test_manual_input_input_must_be_dict(db_path):
    """FSR's manual_input handler calls .get() on `input`. A string
    crashes the workflow with `'str' object has no attribute 'get'`.
    Catch it at compile time."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: ask
      - id: ask
        type: manual_input
        name: ask
        arguments:
          record: "{{ vars.input.records[0]['@id'] }}"
          type: single-select
          input: just a string
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(
        "input must be a mapping" in e.message for e in r.errors
    ), [e.to_dict() for e in r.errors]


def test_manual_input_correct_shape_validates(db_path):
    """The friendly form (title / description / options / inputs) is
    the supported authoring shape. Old-style `type: single-select` and
    `timeout:` were silently ignored by FSR; resolver now hard-rejects
    both, so this test uses the canonical friendly form."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: ask
      - id: ask
        type: manual_input
        name: ask
        arguments:
          title: Block this?
          options:
            - {option: block, primary: true}
            - {option: skip}
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
