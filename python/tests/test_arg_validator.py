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
    are overspecified and not required by the validator.

    The option / branch label is quoted ("yes") so YAML 1.1 doesn't
    coerce it to a boolean — see linter.py for the Norway-problem rule.
    """
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
            - option: "yes"
              condition: "{{ vars.input.params.go == 'yes' }}"
        branches:
          "yes": act
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
    """`label` and `message` were originally rejected here; both keys
    are present in the live FSR ManualInput corpus (audit §1 / §0) and
    the resolver now accepts them. Genuine typos still hard-error."""
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


# ---- audit-driven Decision validator tests (2026-05-06, I15 refined) -----

def _decision_yaml(conds_block: str, branches_block: str = "") -> str:
    return f"""
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
          conditions:
{conds_block}
{branches_block}
      - id: a
        type: set_variable
        arguments:
          arg_list:
            - {{name: x, value: '1'}}
      - id: b
        type: set_variable
        arguments:
          arg_list:
            - {{name: x, value: '2'}}
"""


def test_decision_two_default_branches_rejected(db_path):
    """Live FSR fires only the first default; >1 is an authoring bug."""
    text = _decision_yaml(
        "            - {option: 'yes', condition: '{{ x }}', default: true}\n"
        "            - {option: 'no',  condition: '{{ y }}', default: true}\n",
        "        branches:\n          'yes': a\n          'no': b\n",
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("marked `default: true`" in e.message for e in r.errors)


def test_decision_default_with_condition_rejected(db_path):
    """Default entries must NOT carry a `condition:` (defaults fire when
    every condition is false)."""
    text = _decision_yaml(
        "            - {option: 'yes', condition: '{{ x }}'}\n"
        "            - {option: 'no',  default: true, condition: '{{ y }}'}\n",
        "        branches:\n          'yes': a\n          'no': b\n",
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("default branch must not carry" in e.message for e in r.errors)


def test_decision_non_default_missing_condition_rejected(db_path):
    text = _decision_yaml(
        "            - {option: 'yes'}\n"
        "            - {option: 'no', default: true}\n",
        "        branches:\n          'yes': a\n          'no': b\n",
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("missing `condition:`" in e.message for e in r.errors)


def test_decision_no_default_with_step_next_is_clean(db_path):
    """The canonical FSR idiom: one condition + decision-level `next:`
    for the false-fall-through case. No warning should fire — the
    `next:` IS the implicit default. 8 of 352 live Decisions use this."""
    text = _decision_yaml(
        "            - {option: 'yes', condition: '{{ x }}'}\n",
        "        branches:\n          'yes': a\n        next: b\n",
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    assert not any("no default/else branch" in e.message for e in r.errors), \
        "next: fall-through is a valid default; should not warn"


def test_decision_no_default_no_next_warns(db_path):
    """Truly stuck: no default entry AND no step-level next: — a
    false-condition run has no target. Warn (don't error)."""
    text = _decision_yaml(
        "            - {option: 'yes', condition: '{{ x }}'}\n",
        "        branches:\n          'yes': a\n",
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    assert any("no default/else branch" in e.message and e.severity == "warning"
               for e in r.errors)


# ---- I28 — set_variable typo trap (2026-05-06) -----------------------

def test_set_variable_variables_key_caught(db_path):
    """`variables:` is a common LLM typo; without the trap it gets passed
    through as a single var literally named 'variables'. Real-world bug
    from feedback session 60743f70."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: s
      - id: s
        type: set_variable
        arguments:
          variables:
            - {name: greeting, value: 'hi'}
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "'variables'" in e.message
    assert "arg_list" in (e.suggestion or "")


def test_set_variable_canonical_arg_list_still_works(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: trigger
        type: start
        next: s
      - id: s
        type: set_variable
        arguments:
          arg_list:
            - {name: greeting, value: 'hi'}
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


# ---- I29 — UUID step id linter (2026-05-06) --------------------------

def test_step_id_uuid_warns(db_path):
    """Real-world failure mode 60743f70 — agent emitted full UUIDs as
    step `id:` slugs, breaking every cross-reference idiom."""
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - id: 550e8400-e29b-41d4-a716-446655440000
        type: start
        next: 550e8400-e29b-41d4-a716-446655440001
      - id: 550e8400-e29b-41d4-a716-446655440001
        type: stop
"""
    r = compile_yaml(text, db_path)
    # Doesn't block compilation (it's a warning) — just must surface.
    msgs = [(e.message, e.severity) for e in r.errors]
    assert any("UUID" in m and sev == "warning" for m, sev in msgs), msgs


# ---- I31 — validate_yaml next_fix summary (2026-05-06) ---------------

def test_mcp_validate_yaml_returns_next_fix():
    """The agent burns context iterating against the full error list;
    the `next_fix` field gives it the single most actionable next step."""
    import sys
    sys.path.insert(0, "python")
    from mcp_server import validate_yaml as mcp_validate
    yaml = """
playbooks:
  - name: P
    steps:
      - id: s
        type: start
"""
    r = mcp_validate(yaml)
    assert not r.get("ok"), r
    nf = r.get("next_fix")
    assert nf is not None
    assert nf["code"] == "missing_field"
    # Highest priority is missing_field — collection is the canonical first error.
    assert "collection" in nf["path"] or "collection" in (nf["message"] or "")
