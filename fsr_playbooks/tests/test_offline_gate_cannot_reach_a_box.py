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

    Skips when `probes._env` is not the real module. `test_list_configured
    _active_filter.py` installs a fake one into `sys.modules` (no `EnvConfig`),
    and under a randomized order this test can observe it. That case is not a
    hole: a seam replaced by a stub has no live path to reach. The socket
    backstop below is what holds unconditionally, and it is the reason this
    layer is allowed to be skippable rather than load-bearing.
    """
    probes_env = pytest.importorskip("probes._env")
    if not hasattr(probes_env, "EnvConfig"):
        pytest.skip("probes._env is a test stub; no live path to guard")
    assert probes_env.get_config().is_live() is False


def test_the_grounding_resolver_returns_none():
    """The resolver `emit_action_card` reaches by a function-local import, and
    the one whose per-module stub failed to hold in a full-suite run. It
    documents itself as failing open to None with no live target; this asserts
    it, through the real call rather than a patched stand-in."""
    from fsr_playbooks.mcp_server.tools_execution import _live_client_for_grounding

    client = _live_client_for_grounding()
    # None is the usual answer, but not the only acceptable one: under some
    # orderings a test has sim mode enabled and this returns a
    # `SimulatedFSRClient`, which is an offline fake and exactly what the gate
    # wants. Asserting `is None` here failed on that -- the test was wrong, not
    # the code. What must never come back is a real client.
    assert type(client).__name__ != "FortiSOAR", (
        "the grounding resolver handed back a real pyfsr client inside an "
        "unmarked test")
    assert client is None or "Sim" in type(client).__name__, (
        f"unexpected client type from an offline gate: {type(client).__name__}")


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


def test_a_non_local_socket_is_refused():
    """The backstop, and the only layer that holds unconditionally.

    Every other check here asserts that some resolver decided not to build a
    client -- which is a claim about code paths someone has read. This one does
    not care about paths: an unmarked test that opens a socket to anything
    off-box fails, whatever route it took to get there. That property is what
    lets the `is_live` layer above be skippable.
    """
    import socket

    with pytest.raises(AssertionError, match="not marked `live`"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
            ("10.255.255.1", 443))


def test_loopback_still_works():
    """Silencing case. The guard must not break local fixtures, stub servers or
    anything else bound to loopback -- a backstop that blocks those would get
    ripped out within a week, and then nothing guards the offline gate."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.05)
    try:
        # Nothing is listening; ConnectionRefused/timeout both prove the guard
        # let it through, which is the whole assertion.
        s.connect(("127.0.0.1", 9))
    except AssertionError:
        raise AssertionError("the guard blocked loopback")
    except OSError:
        pass
    finally:
        s.close()


def test_the_guard_file_triggers_the_test_hook():
    """The guard must not be removable without running the suite that checks it.

    `pytest-fast` in .pre-commit-config.yaml only runs when a path matching its
    `files:` pattern is staged. The repo-root `conftest.py` -- which holds the
    guard everything above depends on -- did not match, so deleting the guard
    was a commit the test hook never fired for. The gate that catches the
    removal would have been disarmed by the removal itself.

    `hook-liveness` cannot see this: it checks that each pattern still selects
    SOME tracked file, not that it selects the right ones.
    """
    import pathlib
    import re

    import yaml as _yaml

    root = pathlib.Path(__file__).resolve().parents[2]
    cfg = _yaml.safe_load((root / ".pre-commit-config.yaml").read_text())
    pattern = next(
        h["files"] for repo in cfg["repos"] for h in repo["hooks"]
        if h["id"] == "pytest-fast")
    assert re.match(pattern, "conftest.py"), (
        f"the repo-root conftest.py does not match pytest-fast's files pattern "
        f"({pattern!r}), so removing the offline-gate guard would not run the "
        "tests that detect its removal")


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
