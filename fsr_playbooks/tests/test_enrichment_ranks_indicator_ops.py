"""find(enrichment) puts the lookups that can take the indicator first.

Live, the slate for an IP listed eleven ops in connector-then-name order, and
the agent took `get_threat_categories(title)` as its FortiGuard IP lookup. It
returned "Information not found", the agent read that as FortiGuard disagreeing
with VirusTotal, and called a C2 address both sources rate malicious only
"suspicious" -- so no containment was proposed. Whether an op can take the
indicator is in its own signature, so rank on that.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.mcp_server import tools_connector_discovery as tcd
from fsr_playbooks.mcp_server.tools_connector_discovery import (
    _indicator_param,
    find_enrichment_actions,
)

CONNECTORS = ("virustotal", "fortinet-fortiguard-ioc",
              "fortinet-fortiguard-threat-intelligence")


def test_indicator_param_reads_the_signature():
    assert _indicator_param([{"name": "ip"}, {"name": "relationships"}], "ip") == "ip"
    assert _indicator_param([{"name": "indicator"}], "ip") == "indicator"
    assert _indicator_param([{"name": "ip_address"}], "ip") == "ip_address"
    assert _indicator_param([{"name": "title"}], "ip") is None
    assert _indicator_param([{"name": "slug"}], "ip") is None
    assert _indicator_param([{"name": "ip"}], None) is None


@pytest.fixture
def slate(monkeypatch):
    with sqlite3.connect(f"file:{tcd.DB_PATH}?mode=ro", uri=True) as c:
        have = {r[0] for r in c.execute(
            "SELECT DISTINCT connector_name FROM operations")}
    if not set(CONNECTORS) <= have:
        pytest.skip("reference store lacks the threat-intel connectors")
    monkeypatch.setattr(tcd, "list_configured_connectors", lambda **_: {
        "configured": [{"name": n, "status": "Available"} for n in CONNECTORS]})
    return find_enrichment_actions(target_type="ip", probe=False, limit=25)["actions"]


def test_lookups_that_take_the_ip_come_first(slate):
    ops = [(a["connector"], a["op"]) for a in slate]
    takes = [a for a in slate if a.get("indicator_param")]
    assert ("virustotal", "query_ip") in [(a["connector"], a["op"]) for a in takes]
    assert ("fortinet-fortiguard-ioc", "ioc_search") in [
        (a["connector"], a["op"]) for a in takes]
    # Every op that can take the IP precedes every op that cannot.
    first_without = next((i for i, a in enumerate(slate)
                          if not a.get("indicator_param")), len(slate))
    assert all(a.get("indicator_param") for a in slate[:first_without])
    assert not any(a.get("indicator_param") for a in slate[first_without:]), ops
    cats = ("fortinet-fortiguard-threat-intelligence", "get_threat_categories")
    if cats in ops:
        assert ops.index(cats) >= first_without
