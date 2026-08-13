"""`EVAL_OFFLINE=1` -- the eval harness with no appliance behind it.

Every agentic eval dispatches tool calls through one seam
(`probes._env.get_client`, memoised by `_shared._live_client`), so until now a
degrading box scored as agent regression: pool exhaustion and 8s healthcheck
read timeouts poisoned a screening run mid-flight and the matrix could not say
so (docs/AGENT_INTELLIGENCE_PLAN.md, Phase 1).

Two properties matter, and the second is the one worth testing: the tools are
bound to the simulated client, AND nothing can reach a box anyway. An offline
mode that silently fell through to a live appliance would be worse than none,
because its numbers would look trustworthy.
"""
from __future__ import annotations

import importlib
import os

import pytest

offline = importlib.import_module("evals.offline")


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setenv("FSR_BASE_URL", "https://box.example.com")
    monkeypatch.setenv("FSR_API_KEY", "not-a-real-key")
    saved = offline.install()
    yield
    offline.uninstall(saved)


def test_the_flag_reads_the_usual_truthy_spellings(monkeypatch):
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv("EVAL_OFFLINE", v)
        assert offline.enabled() is True, v
    for v in ("", "0", "false", "no"):
        monkeypatch.setenv("EVAL_OFFLINE", v)
        assert offline.enabled() is False, v


def test_the_tools_bind_to_the_simulated_client(installed):
    assert "Sim" in offline.active_client_name()


def test_the_live_credentials_are_stripped_from_the_process(installed):
    # Substitution alone is not enough: a tool that resolves its client by a
    # path this module does not know about must find nothing, not a box.
    assert not os.environ.get("FSR_BASE_URL")
    assert not os.environ.get("FSR_API_KEY")


def test_a_client_cached_before_the_swap_does_not_survive_it(monkeypatch):
    from fsr_playbooks.mcp_server import _shared
    sentinel = object()
    _shared._LIVE_CLIENT_CACHE["client"] = sentinel
    saved = offline.install()
    try:
        assert _shared._LIVE_CLIENT_CACHE.get("client") is not sentinel
        assert "Sim" in offline.active_client_name()
    finally:
        offline.uninstall(saved)


def test_run_op_returns_fixture_data_with_no_socket(installed, monkeypatch):
    # The end-to-end property: a real tool call, through the real dispatch
    # path, with the network amputated. Any attempt to open a connection is a
    # failure of the seal, not a slow test.
    import socket

    def _no(*a, **k):  # pragma: no cover - only runs if the seal leaks
        raise AssertionError("offline eval opened a socket")

    monkeypatch.setattr(socket.socket, "connect", _no)
    monkeypatch.setattr(socket, "create_connection", _no)

    from fsr_playbooks.mcp_server.tools_execution import run_op
    out = run_op("virustotal", "query_ip", {"ip": "8.8.8.8"})
    assert isinstance(out, dict)
    assert out.get("ok") is not False, out


def test_the_matrix_records_which_substrate_produced_it():
    # A run that does not say whether it was offline invites its rows being
    # compared against ones taken on a box.
    import inspect

    from evals import harness
    src = inspect.getsource(harness.run_matrix)
    assert '"offline": offline_run' in src


def test_the_seal_survives_a_dotenv_reload(monkeypatch, tmp_path):
    # `cmd_evals` calls probes._env._load_dotenv() before the matrix runs, and
    # this repo's .env names a real box. If that reload could put FSR_BASE_URL
    # back after install(), the seal would hold only until the next tool call.
    saved = offline.install()
    try:
        env = tmp_path / ".env"
        env.write_text("FSR_BASE_URL=https://box.example.com\n")
        import probes._env as pe
        # The swapped-in module carries the real one's attributes across, so
        # this is normally a real call. Another test installs its own fake
        # `probes._env` (no `_load_dotenv`) into sys.modules, and under a
        # randomized order we can inherit it -- a seam already replaced by a
        # stub has no dotenv to reload, so there is nothing to test there.
        if not hasattr(pe, "_load_dotenv"):
            pytest.skip("probes._env is a test stub; no dotenv path to guard")
        monkeypatch.chdir(tmp_path)
        pe._load_dotenv()
        # Whatever the reload did, the client the tools resolve must not be a
        # live one.
        assert "Sim" in offline.active_client_name()
    finally:
        offline.uninstall(saved)


#: The tools an investigation reaches for that are NOT reads. Each one must
#: return usable data offline, or the turn silently changes shape.
_DISCOVERY_TOOLS = ("list_configured_connectors",
                    "find_enrichment_actions",
                    "find_containment_actions")


def test_the_discovery_shortcuts_work_offline(installed):
    """Offline must not turn the shortcut into a dead end.

    `find_enrichment_actions` / `find_containment_actions` exist so the agent
    does NOT have to walk `find_connector` -> `find_operation` ->
    `get_op_schema` by hand. Offline they returned `no_fsr_configured` on 9 of
    9 calls, because `list_configured_connectors` reaches for a typed
    `client.connectors` the simulated client did not have, and the resulting
    `AttributeError` was caught into a generic error string.

    Nothing announced that. The agent asked the right question first, got a
    hard failure, fell back to manual discovery -- and **half** of every
    investigation's tool budget went there. It read as the agent overspending,
    and it was scored as such.

    So this asserts the shortcuts return ACTIONS, not merely `ok`. A tool that
    answers "no connectors here" successfully is the same dead end wearing a
    200.
    """
    from fsr_playbooks.mcp_server import tools_connector_discovery as tcd

    listing = tcd.list_configured_connectors(probe=False, verbose=True)
    assert not listing.get("error"), listing.get("error")
    assert listing.get("configured"), "the simulated roster resolved empty"

    enrich = tcd.find_enrichment_actions(target_type="ip", probe=True)
    assert enrich.get("ok") is not False, enrich
    assert enrich.get("actions"), (
        "no enrichment action for an IP offline -- the agent must fall back "
        "to manual connector discovery, which is what blew the tool budget")

    contain = tcd.find_containment_actions(target_type="ip", probe=True)
    assert contain.get("ok") is not False, contain
    assert contain.get("actions"), "no containment action for an IP offline"
    # P2: containment is tier-gated. If it ever comes back approval-free
    # offline, the gating promise is being measured against a lie.
    assert all(a.get("requires_approval") for a in contain["actions"]), (
        "a containment action offered offline without requiring approval")


def test_no_discovery_tool_reports_no_fsr_configured_offline(installed):
    """The specific code that made this invisible, pinned by name.

    `no_fsr_configured` is the honest answer when there is genuinely no
    instance. Under `--offline` there IS one -- the simulated client -- so this
    code is always a harness gap, never a turn outcome.
    """
    from fsr_playbooks.mcp_server import tools_connector_discovery as tcd

    for name in _DISCOVERY_TOOLS:
        fn = getattr(tcd, name)
        out = fn(target_type="ip") if name != "list_configured_connectors" \
            else fn(probe=False)
        code = out.get("code") if isinstance(out, dict) else None
        assert code != "no_fsr_configured", (
            f"{name} reports no_fsr_configured with the simulated client "
            f"bound: {out.get('message')!r}")
