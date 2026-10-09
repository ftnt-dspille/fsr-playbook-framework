"""An error-route key on a step points at `ignore_errors`.

Analyst sim: `on_error` then `onError` on a create_record were refused as
unknown arguments with no pointer to the real mechanism.
"""
from __future__ import annotations

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

_PB = """
collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start_on_create, module: alerts, next: Make}
      - name: Make
        type: create_record
        module: incidents
        fields: {name: x}
        __KEY__: __VAL__
"""


def test_on_error_is_refused_with_the_ignore_errors_hint():
    res = compile_yaml(_PB.replace("__KEY__", "on_error").replace("__VAL__", "Email"),
                       default_db_path())
    err = next(e for e in res.errors if e.code.value == "unknown_param")
    assert "ignore_errors" in err.message


def test_ignore_errors_itself_compiles():
    res = compile_yaml(_PB.replace("__KEY__", "ignore_errors").replace("__VAL__", "true"),
                       default_db_path())
    assert not [e for e in res.errors if e.code.value == "unknown_param"], res.errors
