"""Regression: list_configured_connectors must not advertise a connector whose
config is INACTIVE as "Available" — run_op's preflight would reject it as
`connector_not_configured`, so the agent calls a connector that can't run and
wastes a turn (matrix run 9 P1: whois-rdap listed Available, then run_op
rejected it). The listing now filters through the same active-config source
the preflight uses (_configured_rows), failing open only when that source
can't be resolved."""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from fsr_playbooks.mcp_server import tools_connector_discovery as tcd
from fsr_playbooks.mcp_server import tools_execution as te


def _install_env(monkeypatch, client):
    """Bind a fake client onto probes._env.get_client/get_config (the seam the
    connector bridge uses), mirroring test_sim_run_op_integration's fixture."""
    env_mod = types.ModuleType("probes._env")
    env_mod.get_client = lambda: client
    env_mod.get_config = lambda: SimpleNamespace(is_live=lambda: True)
    probes_mod = types.ModuleType("probes")
    probes_mod._env = env_mod
    monkeypatch.setitem(sys.modules, "probes", probes_mod)
    monkeypatch.setitem(sys.modules, "probes._env", env_mod)


class _PyfsrClient:
    """Fake pyfsr client: `.connectors.list_configured()` returns rows as
    SimpleNamespace objects (the shape pyfsr exposes: name/status/version/
    label/configurations)."""

    def __init__(self, rows):
        self._rows = rows

    @property
    def connectors(self):
        outer = self

        class _ConnectorsAPI:
            def list_configured(self):
                return [SimpleNamespace(**r) for r in outer._rows]

        return _ConnectorsAPI()


def test_inactive_config_connector_is_filtered_out(monkeypatch):
    """whois-rdap has a config RECORD (pyfsr lists it, status 'Available') but
    no ACTIVE config (preflight's _configured_rows excludes it). The listing
    must drop it so the agent never calls a connector run_op will reject."""
    pyfsr_rows = [
        {"name": "fortinet-fortiguard-ioc", "status": "Available",
         "version": "1.1.0", "label": "FortiGuard IOC", "configurations": [{}]},
        {"name": "whois-rdap", "status": "Available",
         "version": "2.0.0", "label": "WHOIS RDAP", "configurations": [{}]},
    ]
    # The active-config source the preflight uses: only fortiguard-ioc is
    # actually active. whois-rdap is NOT here → run_op would reject it.
    monkeypatch.setattr(te, "_configured_rows",
                        lambda client: [{"name": "fortinet-fortiguard-ioc"}])
    _install_env(monkeypatch, _PyfsrClient(pyfsr_rows))

    out = tcd.list_configured_connectors(probe=False)
    assert out["ok"] is True
    names = [c["name"] for c in out["configured"]]
    assert "fortinet-fortiguard-ioc" in names
    assert "whois-rdap" not in names, (
        "inactive-config connector advertised as configured; run_op would "
        "reject it as connector_not_configured"
    )


def test_fail_open_when_active_source_unresolved(monkeypatch):
    """If the active-config source can't be resolved (returns nothing — the
    preflight itself fails open on the same lookup), DON'T blank the listing:
    keep the unfiltered pyfsr set so a transient lookup error can't hide every
    configured connector from the agent."""
    pyfsr_rows = [
        {"name": "fortinet-fortiguard-ioc", "status": "Available",
         "version": "1.1.0", "label": "FortiGuard IOC", "configurations": [{}]},
        {"name": "whois-rdap", "status": "Available",
         "version": "2.0.0", "label": "WHOIS RDAP", "configurations": [{}]},
    ]
    # Active source unresolved (POST failed / empty box) → fail open.
    monkeypatch.setattr(te, "_configured_rows", lambda client: [])
    _install_env(monkeypatch, _PyfsrClient(pyfsr_rows))

    out = tcd.list_configured_connectors(probe=False)
    assert out["ok"] is True
    names = [c["name"] for c in out["configured"]]
    assert set(names) == {"fortinet-fortiguard-ioc", "whois-rdap"}, names


def test_active_source_error_does_not_raise(monkeypatch):
    """An exception from _configured_rows must never propagate out of the
    listing (it's a refinement, not the primary source)."""
    pyfsr_rows = [
        {"name": "fortinet-fortiguard-ioc", "status": "Available",
         "version": "1.1.0", "label": "FortiGuard IOC", "configurations": [{}]},
    ]

    def boom(client):
        raise RuntimeError("connector_details POST exploded")

    monkeypatch.setattr(te, "_configured_rows", boom)
    _install_env(monkeypatch, _PyfsrClient(pyfsr_rows))

    out = tcd.list_configured_connectors(probe=False)
    assert out["ok"] is True
    names = [c["name"] for c in out["configured"]]
    assert "fortinet-fortiguard-ioc" in names  # unfiltered, fail-open
