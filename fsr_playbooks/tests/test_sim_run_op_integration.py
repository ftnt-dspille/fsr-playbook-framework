"""End-to-end: drive run_op through the simulated client.

Binds the simulated client onto the same seam the connector's
`simulation_mode` bridge uses (`probes._env.get_client`), then calls the real
`run_op` tool. This exercises the uncommitted WIP — the connector preflight /
healthcheck gate and the enrichment-output summarizer — against the sim
substrate, with NO live FortiSOAR and NO Anthropic.
"""
from __future__ import annotations

import sys
import types

import pytest

from fsr_playbooks.mcp_server import _sim_client as sc
from fsr_playbooks.mcp_server import tools_execution as te


@pytest.fixture
def sim_bridge(monkeypatch):
    """Install probes._env -> sim client, mirroring the connector bridge.
    Also reset the in-process preflight caches so each test is independent."""
    env_mod = types.ModuleType("probes._env")
    env_mod.get_client = sc.get_client
    env_mod.get_config = sc.get_config
    probes_mod = types.ModuleType("probes")
    probes_mod._env = env_mod
    monkeypatch.setitem(sys.modules, "probes", probes_mod)
    monkeypatch.setitem(sys.modules, "probes._env", env_mod)
    # run_op closes over a module-level `get_client` import inside the func,
    # so the sys.modules swap is enough. Clear preflight caches.
    te._CONFIGURED_CACHE["rows"] = None
    te._CONFIGURED_CACHE["ts"] = 0.0
    yield


def _has_connector(name: str) -> bool:
    import sqlite3
    try:
        with sqlite3.connect(f"file:{te.DB_PATH}?mode=ro", uri=True) as con:
            row = con.execute(
                "SELECT 1 FROM connectors WHERE name=? LIMIT 1", (name,)
            ).fetchone()
            return row is not None
    except Exception:
        return False


def test_healthy_siem_passes_preflight_and_returns_context(sim_bridge):
    if not _has_connector("fortinet-fortisiem"):
        pytest.skip("fortinet-fortisiem not in reference DB")
    out = te.run_op("fortinet-fortisiem", "get_ip_context",
                    params={"value": "185.220.101.47"})
    assert out["ok"] is True, out
    assert out["data"]["ipAddress"] == "185.220.101.47"
    assert out["data"]["knownMalicious"] is True


def test_search_events_returns_ordered_sequence(sim_bridge):
    if not _has_connector("fortinet-fortisiem"):
        pytest.skip("fortinet-fortisiem not in reference DB")
    # `attribute` + `select_clause` are required (enforced by the 1.1
    # param-validation guard); supply minimal valid values.
    out = te.run_op("fortinet-fortisiem", "search_events",
                    params={"attribute": "srcIpAddr = 185.220.101.47",
                            "select_clause": "eventType, srcIpAddr"})
    assert out["ok"] is True, out
    assert out["output_is_list"] is True
    assert len(out["data"]) >= 2


def test_vt_enrichment_is_summarized(sim_bridge):
    """The VT blob must be field-pruned by _summarize_op_output to the
    verdict-driving attributes (the summarization WIP)."""
    if not _has_connector("virustotal"):
        pytest.skip("virustotal not in reference DB")
    out = te.run_op("virustotal", "query_ip",
                    params={"ip": "185.220.101.47"})
    assert out["ok"] is True, out
    attrs = out["data"]["attributes"]
    assert "last_analysis_stats" in attrs
    # certs / rdap / whois must NOT survive the prune
    assert "last_https_certificate" not in attrs
    assert "rdap" not in attrs
