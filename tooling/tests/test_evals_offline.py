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
    offline.install()
    yield
    from fsr_playbooks.mcp_server import _shared
    _shared._LIVE_CLIENT_CACHE.pop("client", None)


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
    offline.install()
    assert _shared._LIVE_CLIENT_CACHE.get("client") is not sentinel
    assert "Sim" in offline.active_client_name()
    _shared._LIVE_CLIENT_CACHE.pop("client", None)


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
