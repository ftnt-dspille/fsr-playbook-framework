"""validate_yaml: an advisory is a warning, never one of the "errors".

Live (session health): a failed validate reported "2 compiler error(s)" whose
first entry was the `button_label` advisory -- verify_playbook files the same
finding as a warning -- while the real blocker (a bad FortiGate enum) sat
second. The model is steered by the first error; it must be a real one.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_compile import validate_yaml

BAD_ENUM = """collection: C
playbooks:
  - name: test
    steps:
      - {name: Start, type: start, module: alerts, next: Block}
      - name: Block
        type: connector
        connector: fortigate-firewall
        operation: block_ip_new
        params: {method: address, ip_type: IPv4, ip: 1.2.3.4}
"""


def test_the_advisory_is_a_warning_and_the_blocker_is_the_error():
    r = validate_yaml(BAD_ENUM)
    assert r["ok"] is False
    codes = [(e["code"], e["severity"]) for e in r["errors"]]
    assert all(sev == "error" for _, sev in codes), codes
    assert not any("button_label" in e["message"] for e in r["errors"])
    assert any("button_label" in w["message"] for w in r.get("warnings", []))
    assert "button_label" not in (r.get("next_fix") or {}).get("message", "")
    assert r["message"].startswith(f"{len(r['errors'])} compiler error(s)")
