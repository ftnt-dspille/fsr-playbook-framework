"""The `live` marker was advisory. This makes it structural.

`-m "not live"` selected which tests to SKIP; nothing stopped an unmarked test
from opening a socket to an appliance anyway. So `make verify` -- the offline
gate -- silently depended on a box being up and on which connectors happened to
be installed on it (#113, then #119).

The failure mode is worse than flakiness. A box-dependent red in an offline gate
trains people to read that gate's failures as noise, so the next real regression
is dismissed too. And it is invisible in CI, which has no box and therefore
always passes -- meaning only the developer ever sees it.

The chokepoint is `probes._env.EnvConfig.is_live()`, which every live-client
resolver consults and which is False without `FSR_BASE_URL`. `conftest`'s
`_no_appliance_unless_marked_live` clears that for any test lacking the marker.
These tests pin that the guard is actually in force -- a guard nobody checks is
the thing it was built to prevent.
"""
from __future__ import annotations

import os

import pytest


def test_the_env_says_no_live_target():
    """The lever itself. Everything else here depends on this being cleared."""
    assert not os.environ.get("FSR_BASE_URL"), (
        "FSR_BASE_URL is set inside an unmarked test -- the conftest guard did "
        "not take, and every live-client resolver will happily build a client")


def test_probes_report_not_live():
    """One layer up: the chokepoint every resolver consults.

    Reads through `get_config()` rather than a fresh `EnvConfig()` on purpose --
    the cached module global is what production code sees, and a stale cache
    surviving the env change is exactly how the guard would silently do nothing.
    """
    probes_env = pytest.importorskip("probes._env")
    assert probes_env.get_config().is_live() is False


def test_the_grounding_resolver_returns_none():
    """The resolver `emit_action_card` reaches by a function-local import, and
    the one whose per-module stub failed to hold in a full-suite run. It
    documents itself as failing open to None with no live target; this asserts
    it, through the real call rather than a patched stand-in."""
    from fsr_playbooks.mcp_server.tools_execution import _live_client_for_grounding

    assert _live_client_for_grounding() is None


def test_emit_action_card_does_not_build_a_client(monkeypatch):
    """End to end, on the exact path that was reaching a box.

    Rather than assert on the card, assert that nothing ever constructs a
    client: `get_client` raises if called, so a resolver that slips past the
    guard fails loudly here instead of quietly returning a live handle. That
    keeps this test about reachability and not about whatever the catalog
    happens to say for this connector.
    """
    probes_env = pytest.importorskip("probes._env")

    def _boom():
        raise AssertionError(
            "an unmarked test built a live FSR client -- the offline gate can "
            "reach an appliance again")

    monkeypatch.setattr(probes_env, "get_client", _boom)

    from fsr_playbooks.mcp_server import emit_action_card

    # Whatever this returns is fine; the assertion is that it got there without
    # a socket.
    emit_action_card(id="card-offline-gate", connector="fortigate-firewall",
                     operation="block_ip_new", summary="test",
                     args={"ip_addresses": "203.0.113.77"},
                     editable_fields=[])


def test_the_marker_is_registered():
    """`live` has to exist as a real marker, or `get_closest_marker` in the
    conftest silently never matches and the guard clamps the env for the live
    suite too -- turning every box test into a confusing failure."""
    import configparser
    import pathlib

    ini = pathlib.Path(__file__).resolve().parents[2] / "pytest.ini"
    cfg = configparser.ConfigParser()
    cfg.read(ini)
    assert "live:" in cfg["pytest"]["markers"]
