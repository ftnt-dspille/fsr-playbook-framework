"""arg_validator's skip-list is gated by `step.handler`, not `step.type`.

The original gate (`step.type == "connector"`) failed for short types
that *resolve* to the connector handler (`stop`, `end`) and ignored
other resolver-validated handlers (`update_data`, `delay`, `set_multiple`,
…). That mis-gating produced a flood of false-positive `unknown_param`
warnings on resolver-injected wire-format keys (`name`, `operationTitle`,
`operation`, `collectionType`, `type`, `rule`, etc.) — which is what
the user originally complained about in the screenshot.

These tests pin the new behavior so the regression doesn't return.
"""
from __future__ import annotations

from fsr_core.compiler import compile_yaml
from fsr_core.compiler.errors import ErrorCode


def _no_unknown_param_warnings(res) -> list:
    return [
        e for e in res.errors
        if e.code is ErrorCode.UNKNOWN_PARAM and e.severity != "error"
    ]


def test_connector_step_no_false_positives(db_path):
    """The resolver auto-injects `name` and `operationTitle` onto
    connector steps. Validator must not flag them."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: Hello
      - name: Hello
        type: connector
        arguments:
          connector: cyops_utilities
          operation: no_op
          config: ""
        next: stop
      - name: stop
        type: end
"""
    res = compile_yaml(text, db_path)
    assert res.ok, [str(e) for e in res.errors]
    bad = [w for w in _no_unknown_param_warnings(res)
           if "name" in w.message or "operationTitle" in w.message]
    assert not bad, [str(e) for e in bad]


def test_stop_step_no_false_positives(db_path):
    """`type: end` resolves to handler='connector' under the hood
    (no_op idiom). The skip-list is keyed on handler, so this works."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: stop
      - name: stop
        type: end
"""
    res = compile_yaml(text, db_path)
    assert res.ok, [str(e) for e in res.errors]
    assert not _no_unknown_param_warnings(res)


def test_update_record_no_false_positives(db_path):
    """update_data handler gets `operation`/`collectionType` injected
    by the resolver. They aren't on the Python signature, but the
    skip-list keeps the validator quiet."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: u
      - name: Update
        type: update_record
        arguments:
          module: alerts
          resource:
            severity: "{{ 'High' | picklist('severity') }}"
        next: stop
      - name: stop
        type: end
"""
    res = compile_yaml(text, db_path)
    bad = [w for w in _no_unknown_param_warnings(res)
           if "operation" in w.message or "collectionType" in w.message]
    assert not bad, [str(e) for e in bad]


def test_delay_no_false_positives(db_path):
    """delay handler gets `type`/`rule` injected by the resolver."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: d
      - name: Wait
        type: delay
        arguments:
          seconds: 5
        next: stop
      - name: stop
        type: end
"""
    res = compile_yaml(text, db_path)
    bad = [w for w in _no_unknown_param_warnings(res)
           if "'type'" in w.message or "'rule'" in w.message]
    assert not bad, [str(e) for e in bad]


def test_set_variable_flat_dict_no_false_positives(db_path):
    """set_multiple takes **kwargs so the validator's old behavior
    flagged every var name as 'technically legal but FSR may error'.
    The handler-skip nukes that."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: s
      - name: Stash
        type: set_variable
        arguments:
          source_ip: "1.2.3.4"
          verdict: pending
        next: stop
      - name: stop
        type: end
"""
    res = compile_yaml(text, db_path)
    bad = [w for w in _no_unknown_param_warnings(res)
           if "source_ip" in w.message or "verdict" in w.message]
    assert not bad, [str(e) for e in bad]


def test_code_snippet_no_false_positives(db_path):
    """code_snippet handler has injected connector/operation/version
    that aren't on the bare Python signature."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: c
      - name: Compute
        type: code_snippet
        arguments:
          code: |
            result = 1 + 1
        next: stop
      - name: stop
        type: end
"""
    res = compile_yaml(text, db_path)
    bad = _no_unknown_param_warnings(res)
    # connector/operation/version are all auto-injected
    bad = [w for w in bad if any(k in w.message for k in
                                 ("connector", "operation", "version", "config"))]
    assert not bad, [str(e) for e in bad]
