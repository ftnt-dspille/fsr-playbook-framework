"""A direct-build offer refuses a connector THIS box has not configured.

Live sweep (boundary_absent_connector): asked to isolate a host "with
CrowdStrike Falcon", the model said Falcon was unavailable -- then offered a
playbook whose isolate step called it. Saved, that step fails on the first
run. The offer now checks the connectors it calls against the box's configured
inventory, and fails open when the box cannot be asked.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import tools_connector_discovery as tcd
from fsr_playbooks.mcp_server.tools_emit import _offer_from_yaml

YAML = """\
playbooks:
  - name: Block bad IP
    parameters: []
    steps:
      - name: Start
        type: start
        module: alerts
        next: Block IP
      - name: Block IP
        type: connector
        connector: fortigate-firewall
        operation: block_ip
"""


def _offer():
    return _offer_from_yaml("c1", "save it", YAML,
                            title_suggestion=None, editable_title=True)


def _inventory(monkeypatch, listing):
    def fake(probe=False, verbose=False, only=None, **kw):
        if isinstance(listing, Exception):
            raise listing
        return listing
    monkeypatch.setattr(tcd, "list_configured_connectors", fake)


def test_unconfigured_connector_is_refused_with_the_alternatives(monkeypatch):
    _inventory(monkeypatch, {"configured": [{"name": "fortinet-fortiedr"},
                                            {"name": "smtp"}]})
    res = _offer()
    assert res["ok"] is False
    assert res["code"] == "offer_uses_unconfigured_connector"
    assert res["unconfigured"] == ["fortigate-firewall"]
    assert any("fortinet-fortiedr" in s for s in res["suggestions"])


def test_configured_connector_is_offered(monkeypatch):
    _inventory(monkeypatch, {"configured": [{"name": "fortigate-firewall"}]})
    assert _offer()["ok"] is True


@pytest.mark.parametrize("listing", [
    {"error": "FSR instance not configured"},
    {"configured": []},
    RuntimeError("listing endpoint down"),
])
def test_fails_open_when_the_box_cannot_be_asked(monkeypatch, listing):
    _inventory(monkeypatch, listing)
    assert _offer()["ok"] is True


def test_a_connector_that_needs_no_configuration_is_never_refused(monkeypatch):
    # cyops_utilities declares no config fields: it runs without one.
    from fsr_playbooks.mcp_server.tools_emit import _needs_configuration
    assert _needs_configuration("cyops_utilities") is False
    assert _needs_configuration("fortigate-firewall") is True
    # Unknown to the catalog (a slim DB without a built-in): not this gate's
    # call -- verify owns unknown connectors.
    assert _needs_configuration("no-such-connector-xyz") is False
