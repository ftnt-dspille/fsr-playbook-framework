"""Repo-root pytest config.

The offline-gate guard lives HERE, not in `fsr_playbooks/tests/conftest.py`,
because `pytest.ini` has two testpaths and the leak was in the other one.
Scoped to a single suite it left `tooling/tests` uncovered, and three tests
there kept opening sockets to an appliance -- a guard that covers half the
gate reads exactly like one that covers all of it.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_appliance_unless_marked_live(request, monkeypatch):
    """A test without the `live` marker must not be able to reach an appliance.

    `live` was advisory: it selected what `-m "not live"` deselects, and nothing
    stopped an unmarked test from opening a socket anyway. So the offline gate
    quietly depended on a box (#113, #119). `test_staged_action_coverage.py`
    is the worked example -- it carries its own fixture stubbing
    `_live_client_for_grounding`, and a full-suite run still built a real
    `pyfsr.client.FortiSOAR` three times, then failed on whether
    `fortigate-firewall` happened to be installed on whatever box `.env` names.

    Stubbing the resolver per module cannot hold: `emit_action_card` reaches it
    by a function-local `from .tools_execution import ...`, `run_op` by another
    path, and each new caller is a new hole. So the guard is placed at the one
    chokepoint they all funnel through -- `probes._env.EnvConfig.is_live()`,
    which is False without `FSR_BASE_URL`. Clearing that env var turns every
    resolver into its documented fail-open None, no matter who calls it.

    `_cached_cfg` is a module global built once from the environment, so it is
    reset around the test too; otherwise a config cached by an earlier import
    outlives the env change and the guard silently does nothing -- which is the
    same failure shape as the fixture it replaces.

    A test that genuinely wants a box marks itself `live`. A test that wants to
    exercise config parsing can still `monkeypatch.setenv` its own values:
    function-scoped fixtures run before the test body, so its setenv wins.
    """
    if request.node.get_closest_marker("live"):
        yield
        return

    for var in ("FSR_BASE_URL", "FSR_API_KEY", "FSR_USERNAME", "FSR_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    env = None
    try:  # `probes` lives under tooling/ and is not always importable
        from probes import _env as env
    except Exception:  # noqa: BLE001 -- absent probes means nothing to reset
        pass
    if env is not None and hasattr(env, "EnvConfig"):
        # Clearing the environment is NOT sufficient on its own, and assuming
        # it was is what made the first version of this guard pass its own
        # smoke test while still reaching a box: `EnvConfig.__init__` reloads
        # a `.env` file through `os.environ.setdefault`, so a deleted var is
        # simply re-populated on the next construction.
        #
        # So the guard is placed on the predicate itself. Patching the CLASS
        # covers instances that already exist -- including the `_cached_cfg`
        # global built during some earlier import, which no amount of env
        # manipulation can reach.
        monkeypatch.setattr(env.EnvConfig, "is_live", lambda self: False)
        monkeypatch.setattr(env, "_cached_cfg", None, raising=False)
    # `hasattr` rather than a bare attribute access, because `probes._env` does
    # not always resolve to tooling/probes/_env.py -- there is a stale
    # `build/lib/probes/` in the tree, and running this suite alongside
    # `tooling/tests` produced a `probes._env` with no `EnvConfig` at all. A
    # guard that raises during setup takes down every test in the suite, which
    # is a far worse outcome than the leak it prevents. It stays tolerant here;
    # `test_offline_gate_cannot_reach_a_box.py` is what proves it took effect.

    try:
        from fsr_playbooks.mcp_server import _shared
    except Exception:  # noqa: BLE001
        _shared = None
    if _shared is not None:
        _shared._LIVE_CLIENT_CACHE.clear()
    # Belt and braces. `is_live()` is the chokepoint every resolver is SUPPOSED
    # to consult, but that is a claim about code I have read, and the whole
    # reason this fixture exists is that a previous guard was defeated by a path
    # nobody had read. So the socket itself is the backstop: it cannot be routed
    # around, whatever a future caller does. Loopback stays open -- local
    # fixtures, sqlite over unix sockets and any localhost stub are not the
    # thing being prevented.
    import socket

    _real_connect = socket.socket.connect

    def _guarded(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) and address else None
        if host not in ("127.0.0.1", "::1", "localhost", "0.0.0.0", None):
            raise AssertionError(
                f"{request.node.nodeid} opened a socket to {address!r}. This "
                "test is not marked `live`, so it belongs to the offline gate "
                "-- which must not depend on an appliance being up, or on what "
                "happens to be installed on it (#113, #119). Either mark it "
                "`live`, or stub the client it is resolving.")
        return _real_connect(self, address, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", _guarded)
    try:
        yield
    finally:
        if _shared is not None:
            _shared._LIVE_CLIENT_CACHE.clear()
