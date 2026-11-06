"""A connector step's `dynamicallySelected` wire field must pass through, not be
flagged as an unknown connector param.

It is a real FortiSOAR connector-step field (the "select config at runtime"
toggle) that appears at step level in exported playbook JSON. The 0.10.x
resolver rejected it as unknown_param, which broke a pyfsr doc example that
validated cleanly under older compilers.
"""
from __future__ import annotations

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml

_YAML = """
collection: Dynamically Selected Passthrough
playbooks:
  - name: P
    steps:
      - name: Start
        type: start
      - name: Block IP
        type: connector
        connector: fortigate-firewall
        operation: block_ip_new
        operationTitle: Block IP Address
        dynamicallySelected: false
        params:
          ip: '1.2.3.4'
"""


def test_dynamically_selected_is_not_unknown_param():
    res = compile_yaml(_YAML, default_db_path())
    bad = [e for e in res.errors
           if e.code.value == "unknown_param" and "dynamicallySelected" in e.message]
    assert not bad, [str(e) for e in bad]
    # and it survives onto the wire step, not lifted into params
    if res.ok:
        step = next(s for c in res.fsr_json["data"] for w in c["workflows"]
                    for s in w["steps"] if s.get("name") == "Block IP")
        assert step["arguments"].get("dynamicallySelected") is False
        assert "dynamicallySelected" not in step["arguments"].get("params", {})
