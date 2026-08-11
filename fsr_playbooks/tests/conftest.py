"""Suite-wide isolation for `fsr_playbooks/tests/`.

Everything here exists because a test's outcome must not depend on which other
tests ran first. That property is only observable under randomized collection
order (`pytest-randomly`, wired into `make tests-random`), which is exactly why
these leaks survived for so long: in the one fixed order the suite always ran
in, they were invisible.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_approval_grants():
    """Empty the process-global approval-grant table around every test.

    `fsr_playbooks.llm.tools._APPROVAL_GRANTS` is module state keyed by
    (session, tool, op_key) and nothing in the suite cleaned it up, so grants
    accumulated across tests. `test_clear_session_grants_removes_all_grants_for
    _session` counts the table's absolute size, and under a randomized order it
    saw a `('session-1', 'tool_b', ...)` grant left behind by an earlier test
    and read 4 where it asserts 3.

    A dispatch-authorization table that carries over between tests is also the
    worst possible thing to leave dirty: a P2-gating test could pass because
    some earlier test had already granted the approval it means to require.
    """
    from fsr_playbooks.llm import tools as tools_mod

    tools_mod._APPROVAL_GRANTS.clear()
    try:
        yield
    finally:
        tools_mod._APPROVAL_GRANTS.clear()


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
    if env is not None:
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

    try:
        from fsr_playbooks.mcp_server import _shared
    except Exception:  # noqa: BLE001
        _shared = None
    if _shared is not None:
        _shared._LIVE_CLIENT_CACHE.clear()
    try:
        yield
    finally:
        if _shared is not None:
            _shared._LIVE_CLIENT_CACHE.clear()
