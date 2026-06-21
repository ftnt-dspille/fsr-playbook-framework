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


def test_startswith_autocorrects_to_anchored_like():
    # `startswith` is no longer blocked — it auto-corrects to an anchored
    # `like 'repro%'` pattern (forgiving authoring) with a warning.
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
    import json
    res, blocking = _errs(yaml_text)
    assert res.ok, blocking
    blob = json.dumps(res.fsr_json)
    assert '"operator": "like"' in blob and '"value": "repro%"' in blob
    assert any(e.severity == "warning" and "startswith" in e.message
               for e in res.errors)


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


def test_contains_rewrites_to_like_with_wildcards():
    # Live-verified (probe_trigger_matrix + SOAR designer): UI "Contains" on a
    # scalar field is `like` with the value wrapped in `%…%`. A raw
    # `operator: contains` never fires, so the compiler rewrites it.
    import json
    res, blocking = _errs(_trigger_with_op("contains"))
    assert res.ok, blocking
    blob = json.dumps(res.fsr_json)
    assert '"operator": "like"' in blob
    assert '"operator": "contains"' not in blob
    assert "%malware%" in blob  # value auto-wrapped
    # the warning explains the rewrite.
    assert any(e.severity == "warning" and "contains" in e.message.lower()
               for e in res.errors)


def test_notcontains_rewrites_to_notlike_with_wildcards():
    import json
    res, blocking = _errs(_trigger_with_op("notcontains"))
    assert res.ok, blocking
    blob = json.dumps(res.fsr_json)
    assert '"operator": "notlike"' in blob
    assert '"operator": "notcontains"' not in blob
    assert "%malware%" in blob


def test_like_bare_value_is_auto_wrapped_with_warning():
    # `like malware` (no wildcard) matches exactly and silently never fires —
    # auto-wrap to `%malware%` and warn.
    import json
    res, blocking = _errs(_trigger_with_op("like"))
    assert res.ok, blocking
    blob = json.dumps(res.fsr_json)
    assert '"operator": "like"' in blob
    assert "%malware%" in blob
    assert any(e.severity == "warning" and "wildcard" in e.message.lower()
               for e in res.errors)


def test_like_with_existing_wildcard_is_left_alone():
    import json
    res, blocking = _errs(_trigger_with_op("like").replace(
        "value: malware", "value: \"%mal%ware%\""))
    assert res.ok, blocking
    assert "%mal%ware%" in json.dumps(res.fsr_json)


def test_operator_shadow_mirrors_operator_not_like_pattern():
    # `_operator` must equal the emitted operator (corpus + UI: `like`),
    # never the bogus `like_pattern` we used to emit.
    import json
    res, _ = _errs(_trigger_with_op("like"))
    blob = json.dumps(res.fsr_json)
    assert '"_operator": "like"' in blob
    assert "like_pattern" not in blob


def test_contains_notcontains_recognized_inputs():
    from fsr_playbooks.compiler.resolver.normalizers import _TRIGGER_OPS
    assert "contains" in _TRIGGER_OPS and "notcontains" in _TRIGGER_OPS


def test_startswith_anchors_prefix_pattern():
    import json
    res, blocking = _errs(_trigger_with_op("startswith"))
    assert res.ok, blocking
    blob = json.dumps(res.fsr_json)
    assert '"operator": "like"' in blob
    assert '"value": "malware%"' in blob  # prefix-anchored, not %malware%


def test_endswith_anchors_suffix_pattern():
    import json
    res, blocking = _errs(_trigger_with_op("endswith"))
    assert res.ok, blocking
    assert '"value": "%malware"' in json.dumps(res.fsr_json)


def test_symbol_alias_autocorrected_not_blocked():
    # `==` should auto-correct to eq with a warning, not block.
    res, blocking = _errs(_trigger_with_op("=="))
    assert res.ok, blocking
    import json
    assert '"operator": "eq"' in json.dumps(res.fsr_json)
    assert any(e.severity == "warning" for e in res.errors)


def test_truly_unknown_operator_still_blocks():
    res, blocking = _errs(_trigger_with_op("frobnicate"))
    assert not res.ok
    assert any("frobnicate" in e.message for e in blocking)


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
