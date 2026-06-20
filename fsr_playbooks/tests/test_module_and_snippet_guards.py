"""Guards for two silent-pass bugs (see code-snippet-overload repro):

1. An empty code_snippet `python_function` used to compile green and deploy
   a no-op snippet — now a blocking error.
2. A trigger / record-CRUD `module:` was copied verbatim, so a UI-label
   'Alerts' shipped as a resource that never matched — now case-fixed to the
   canonical lowercase type name with a warning, against the shipped slim
   module-name catalog.
"""
from __future__ import annotations

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml


def _errs(yaml_text: str):
    res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
    return res, [e for e in res.errors if e.severity != "warning"]


def test_module_label_case_fixed_to_canonical_with_warning():
    yaml_text = """
collection: 00-test
playbooks:
  - name: Trigger
    steps:
      - name: On Create
        type: start_on_create
        module: Alerts
        next: Done
      - name: Done
        type: set_variable
        vars: {x: 1}
"""
    res, blocking = _errs(yaml_text)
    assert res.ok, blocking
    warns = [e for e in res.errors if e.severity == "warning"
             and "canonical" in e.message.lower()]
    assert warns, "expected a module canonicalization warning"
    assert "'alerts'" in warns[0].message


def test_empty_python_function_is_blocking():
    yaml_text = """
collection: 00-test
playbooks:
  - name: Empty Snippet
    steps:
      - name: Run
        type: code_snippet
        arguments:
          connector: code-snippet
          operation: python_inline_code_editor
          params:
            python_function: "   "
"""
    res, blocking = _errs(yaml_text)
    assert not res.ok
    assert any("python_function" in e.message for e in blocking), blocking


def test_invalid_trigger_operator_is_blocking_with_suggestion():
    yaml_text = """
collection: 00-test
playbooks:
  - name: Trigger
    steps:
      - name: On Create
        type: start_on_create
        module: alerts
        when:
          logic: AND
          filters:
            - {field: name, op: startswith, value: repro}
        next: Done
      - name: Done
        type: set_variable
        vars: {x: 1}
"""
    res, blocking = _errs(yaml_text)
    assert not res.ok
    bad = [e for e in blocking if "startswith" in e.message]
    assert bad and bad[0].near == "like", bad


def test_changed_operator_rejected_on_create():
    yaml_text = """
collection: 00-test
playbooks:
  - name: Trigger
    steps:
      - name: On Create
        type: start_on_create
        module: alerts
        when:
          logic: AND
          filters:
            - {field: status, op: changed}
        next: Done
      - name: Done
        type: set_variable
        vars: {x: 1}
"""
    res, blocking = _errs(yaml_text)
    assert not res.ok
    assert any("changed" in e.message for e in blocking), blocking


def _trigger_with_op(op: str) -> str:
    return f"""
collection: 00-test
playbooks:
  - name: Trigger
    steps:
      - name: On Create
        type: start_on_create
        module: alerts
        when:
          logic: AND
          filters:
            - {{field: tags, op: {op}, value: malware}}
        next: Done
      - name: Done
        type: set_variable
        vars: {{x: 1}}
"""


def test_contains_is_a_distinct_operator_not_rewritten_to_like():
    # `contains` (collection membership, UI "Contains") must survive verbatim —
    # it is NOT the same as `like` (substring match, UI "Matches Pattern").
    import json
    res, blocking = _errs(_trigger_with_op("contains"))
    assert res.ok, blocking
    blob = json.dumps(res.fsr_json)
    assert '"operator": "contains"' in blob
    assert '"operator": "like"' not in blob


def test_like_stays_like():
    import json
    res, blocking = _errs(_trigger_with_op("like"))
    assert res.ok, blocking
    assert '"operator": "like"' in json.dumps(res.fsr_json)


def test_notcontains_passes_and_aliases_fixed():
    res, blocking = _errs(_trigger_with_op("notcontains"))
    assert res.ok, blocking
    # friendly aliases canonicalize to notcontains (blocking-with-fixup, then
    # the author applies it) — assert the alias is recognized, not unknown.
    from fsr_playbooks.compiler.resolver.normalizers import (
        _TRIGGER_OP_FIXUPS,
        _TRIGGER_OPS,
    )
    assert "contains" in _TRIGGER_OPS and "notcontains" in _TRIGGER_OPS
    assert "contains" not in _TRIGGER_OP_FIXUPS  # never downgraded to like


def test_known_lowercase_module_passes_clean():
    yaml_text = """
collection: 00-test
playbooks:
  - name: Trigger
    steps:
      - name: On Create
        type: start_on_create
        module: alerts
        next: Done
      - name: Done
        type: set_variable
        vars: {x: 1}
"""
    res, _ = _errs(yaml_text)
    assert res.ok
    assert not [e for e in res.errors
                if e.severity == "warning" and "module" in e.path]
