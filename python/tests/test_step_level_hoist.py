"""Step-level cross-cutting fields hoisted into arguments at parse time.

Authors get to write `mock_result`, `when`, `step_variables`, and `set` at
the step level (siblings of `arguments:`) instead of buried under
`arguments:`. The parser folds them in so the resolver/emitter see the
canonical wire shape.
"""
import json

from compiler import compile_yaml
from compiler.errors import ErrorCode


def test_step_level_mock_result_hoists(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: f
      - name: f
        type: connector
        mock_result:
          status: ok
        arguments:
          connector: virustotal
          operation: query_ip
          params: { ip: "8.8.8.8" }
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    fsr = r.fsr_json
    step = next(
        s for s in fsr["data"][0]["workflows"][0]["steps"]
        if s["name"] == "f"
    )
    assert step["arguments"]["mock_result"] == {"status": "ok"}


def test_step_level_set_hoists_to_step_variables(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: c
      - name: c
        type: create_record
        set:
          counter: 1
          tag: alpha
        arguments:
          module: alerts
          resource:
            name: x
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    step = next(
        s for s in r.fsr_json["data"][0]["workflows"][0]["steps"]
        if s["name"] == "c"
    )
    assert step["arguments"]["step_variables"] == {"counter": 1, "tag": "alpha"}


def test_step_level_when_hoists_to_arguments(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trg
        type: start_on_create
        when:
          logic: AND
          filters:
            - { field: severity, op: eq, value: High }
        arguments:
          module: alerts
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # The resolver expands `when:` into `fieldbasedtrigger`. We only need to
    # confirm the hoist landed and the resolver consumed it.
    step = r.fsr_json["data"][0]["workflows"][0]["steps"][0]
    fbt = step["arguments"].get("fieldbasedtrigger") or {}
    assert any(
        f.get("field") == "severity" for f in (fbt.get("filters") or [])
    )


def test_step_level_set_conflicts_with_step_variables(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: c
      - name: c
        type: create_record
        set: { a: 1 }
        arguments:
          module: alerts
          resource: { name: x }
          step_variables: { b: 2 }
"""
    r = compile_yaml(text, db_path)
    bad = [
        e for e in r.errors if e.code is ErrorCode.BAD_VALUE
        and e.path.endswith(".set")
    ]
    assert bad, [e.to_dict() for e in r.errors]


def test_step_level_mock_result_double_set_errors(db_path):
    text = """
collection: T
playbooks:
  - name: P
    steps:
      - name: start
        type: start
        next: f
      - name: f
        type: connector
        mock_result: { a: 1 }
        arguments:
          connector: virustotal
          operation: query_ip
          params: { ip: "8.8.8.8" }
          mock_result: { a: 2 }
"""
    r = compile_yaml(text, db_path)
    bad = [
        e for e in r.errors if e.code is ErrorCode.BAD_VALUE
        and e.path.endswith(".mock_result")
    ]
    assert bad, [e.to_dict() for e in r.errors]
