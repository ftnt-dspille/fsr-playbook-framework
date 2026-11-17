"""A connector step key that is neither an op param nor a step argument is an
error, not a silent drop.

Step-level keys that ARE op params are lifted into `params:`. Anything else
stayed beside `params` on the wire, where FSR ignores it -- the playbook
compiled green and ran without the value. The same gap hid a key the authoring
example itself taught (`output_ref_example` inside get_step_type's connector
example). A key set both at step level and under params with different values
also lost one silently.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server.tools_verify import verify_playbook

BASE = """\
playbooks:
  - name: P
    parameters: []
    steps:
      - name: Start
        type: start
        module: alerts
        button_label: Go
        next: Block
      - name: Block
        type: connector
        connector: fortigate-firewall
        operation: block_ip
        params: {method: "Quarantine Based", ip_addresses: "1.2.3.4"}
%s"""


def _fixes(extra: str) -> list[dict]:
    v = verify_playbook(BASE % extra)
    return v["required_fixes"]


def test_a_misspelt_param_at_step_level_is_an_error_naming_the_real_one():
    (fix,) = _fixes('        ip_addresss: "5.6.7.8"\n')
    assert fix["code"] == "unknown_param"
    assert "ip_addresss" in fix["message"] and "ignores" in fix["message"]
    assert fix["suggestion"] == "did you mean params.ip_addresses?"


def test_a_conflicting_duplicate_is_an_error():
    (fix,) = _fixes('        ip_addresses: "9.9.9.9"\n')
    assert fix["code"] == "bad_value"
    assert "set twice" in fix["message"]


@pytest.mark.parametrize("extra", [
    "",
    '        ip_addresses: "1.2.3.4"\n',     # same value twice: harmless
    "        display_name: Block it\n",      # friendly spelling of wire name
    "        ignore_errors: true\n",         # universal step argument
    '        when: "{{ true }}"\n',
])
def test_legitimate_keys_stay_clean(extra):
    assert _fixes(extra) == []


def test_the_authoring_example_carries_no_stray_key():
    from fsr_playbooks.mcp_server.tools_discovery import _FRIENDLY_FORMS
    ex = _FRIENDLY_FORMS["connector"]["example"]
    assert "output_ref_example" not in ex
    assert _FRIENDLY_FORMS["connector"]["output_ref_example"]
