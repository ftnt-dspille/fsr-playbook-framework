from compiler import compile_yaml
from compiler.errors import ErrorCode


def test_find_record_missing_query(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: f
      - name: f
        type: find_record
        arguments:
          module: alerts
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.MISSING_FIELD)
    assert e.path.endswith(".query")


def test_set_variable_kwargs_permissive(db_path):
    # set_multiple has **kwargs — arbitrary var names are fine.
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: s
      - name: s
        type: set_variable
        vars:
          x: "1"
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
      - name: start
        type: start
        next: d
      - name: d
        type: decision
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
      - name: trigger
        type: start
        next: stop
      - name: stop
        type: end
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
      - name: trigger
        type: start
        next: noop
      - name: noop
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


def test_decision_with_default_branch_is_valid(db_path):
    """Canonical Decision: every branch in conditions, exactly one
    `default: true`. Branch label "yes" is quoted to dodge YAML 1.1
    boolean coercion (see linter.py for the Norway-problem rule).
    """
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: choose
      - name: choose
        type: decision
        conditions:
          - display: "yes"
            when: "{{ vars.input.params.go == 'yes' }}"
            next: act
          - display: "Else"
            default: true
            next: skip
      - name: act
        type: set_variable
        vars:
          outcome: acted
      - name: skip
        type: set_variable
        vars:
          outcome: skipped
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


def test_manual_input_unknown_args_rejected_as_error(db_path):
    """`label` and `message` were originally rejected here; both keys
    are present in the live FSR ManualInput corpus (audit §1 / §0) and
    the resolver now accepts them. Genuine typos still hard-error."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
          floopwidget: 42
          bogon: hi
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "floopwidget" in e.message and "bogon" in e.message
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
      - name: trigger
        type: start
        next: ask
      - name: ask
        type: manual_input
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
      - name: trigger
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
          title: Block this?
        options:
          - display: block
            primary: true
            next: done
          - display: skip
            next: done
      - name: done
        type: end
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- audit-driven Decision validator tests (2026-05-06, I15 refined) -----

def _decision_yaml(conds_block: str) -> str:
    """conds_block is a step-level conditions: list. Each entry uses the
    canonical surface keys: display / when / next / default."""
    return f"""
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: d
      - name: d
        type: decision
        conditions:
{conds_block}
      - name: a
        type: set_variable
        vars:
          x: '1'
      - name: b
        type: set_variable
        vars:
          x: '2'
"""


def test_decision_two_default_branches_rejected(db_path):
    """Live FSR fires only the first default; >1 is an authoring bug."""
    text = _decision_yaml(
        "          - {display: 'yes', when: '{{ x }}', default: true, next: a}\n"
        "          - {display: 'no',  when: '{{ y }}', default: true, next: b}\n",
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("marked `default: true`" in e.message for e in r.errors)


def test_decision_default_with_condition_rejected(db_path):
    """Default entries must NOT carry a `when:` (defaults fire when
    every condition is false)."""
    text = _decision_yaml(
        "          - {display: 'yes', when: '{{ x }}', next: a}\n"
        "          - {display: 'no',  default: true, when: '{{ y }}', next: b}\n",
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("default branch must not carry" in e.message for e in r.errors)


def test_decision_non_default_missing_condition_rejected(db_path):
    text = _decision_yaml(
        "          - {display: 'yes', next: a}\n"
        "          - {display: 'no', default: true, next: b}\n",
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("missing `condition:`" in e.message for e in r.errors)


def test_decision_with_default_entry_is_clean(db_path):
    """The canonical Decision shape: every branch in conditions, exactly
    one with default: true. No warning should fire."""
    text = _decision_yaml(
        "          - {display: 'yes', when: '{{ x }}', next: a}\n"
        "          - {display: 'no', default: true, next: b}\n",
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    assert not any("no default/else branch" in e.message for e in r.errors)


def test_decision_no_default_warns(db_path):
    """No `default: true` entry — a false-condition run has no target."""
    text = _decision_yaml(
        "          - {display: 'yes', when: '{{ x }}', next: a}\n",
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    assert any("no default/else branch" in e.message and e.severity == "warning"
               for e in r.errors)


# ---- I28 — set_variable typo trap (2026-05-06) -----------------------

def test_set_variable_legacy_arguments_rejected(db_path):
    """Set-variable steps must use the top-level `vars:` mapping.
    Anything else under `arguments:` is rejected at parse time."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: s
      - name: s
        type: set_variable
        arguments:
          variables:
            - {name: greeting, value: 'hi'}
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("top-level `vars:` mapping" in e.message for e in r.errors)


def test_set_variable_canonical_vars_works(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: s
      - name: s
        type: set_variable
        vars:
          greeting: 'hi'
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_step_id_key_rejected(db_path):
    """`id:` on a step is a hard parser error — only `name:` is allowed."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: 550e8400-e29b-41d4-a716-446655440000
        type: start
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("step.id is not allowed" in e.message for e in r.errors)


# ---- I31 — validate_yaml next_fix summary (2026-05-06) ---------------

def test_mcp_validate_yaml_returns_next_fix():
    """The agent burns context iterating against the full error list;
    the `next_fix` field gives it the single most actionable next step."""
    import sys
    sys.path.insert(0, "python")
    from mcp_server import validate_yaml as mcp_validate
    # A bare `collection:` with no playbooks is a missing_field on the
    # `playbooks` path — canonical first error to test the next_fix
    # prioritization. (Omitting the collection key entirely no longer
    # errors; it defaults to per-playbook mode with the studio target.)
    yaml = "collection: A\n"
    r = mcp_validate(yaml)
    assert not r.get("ok"), r
    nf = r.get("next_fix")
    assert nf is not None
    assert nf["code"] == "missing_field"
    assert "playbooks" in nf["path"] or "playbooks" in (nf["message"] or "")
