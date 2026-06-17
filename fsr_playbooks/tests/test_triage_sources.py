"""Tests for source-aware tool routing (triage curation layer).

Covers: source label → toolset mapping, single-source pre-filled pivots,
multi-source case detection (related-alert source harvesting in the
normalizer), and the routing block the prompt builder appends.
"""
from __future__ import annotations

from fsr_playbooks.llm.triage_normalize import normalize_record
from fsr_playbooks.llm.triage_prompt import build_triage_prompt
from fsr_playbooks.llm.triage_sources import (
    build_source_routing_block,
    canonical_source,
    record_sources,
    toolset_for,
)


def test_canonical_source_maps_labels_and_connector_ids():
    assert canonical_source("Fortinet FortiSIEM") == "fortisiem"
    assert canonical_source("fortinet-fortisiem") == "fortisiem"
    assert canonical_source("Fortinet FortiAnalyzer") == "fortianalyzer"
    assert canonical_source("FAZ") == "fortianalyzer"
    assert canonical_source("Some Random SIEM") is None
    assert canonical_source(None) is None


def test_toolset_for_picks_right_tools():
    assert toolset_for("FortiSIEM")["ip"].startswith("siem_search_ip")
    assert toolset_for("FortiAnalyzer")["ip"].startswith("faz_search_ip")


def test_routing_block_single_source_uses_that_sources_tools():
    norm = {
        "source_connector": "Fortinet FortiAnalyzer",
        "related_sources": [],
        "incident_id": None,
        "indicators": {"ips": [{"value": "8.8.8.8", "internal": False}],
                       "hosts": [], "users": []},
    }
    block = build_source_routing_block(norm)
    assert "FortiAnalyzer" in block
    assert 'faz_search_ip(ip="8.8.8.8", direction="dst")' in block
    assert "siem_search_ip" not in block  # not a SIEM source


def test_routing_block_multi_source_recommends_both():
    norm = {
        "source_connector": "Fortinet FortiSIEM",
        "related_sources": ["Fortinet FortiAnalyzer"],
        "incident_id": "10868",
        "indicators": {"ips": [{"value": "203.0.113.9", "internal": False}],
                       "hosts": ["smithDesktop"], "users": []},
    }
    block = build_source_routing_block(norm)
    assert "multiple sources" in block
    # both sources' IP pivots are pre-filled for the same external IP
    assert 'siem_search_ip(ip="203.0.113.9", direction="dst")' in block
    assert 'faz_search_ip(ip="203.0.113.9", direction="dst")' in block
    # SIEM incident pivot uses the SIEM incident id
    assert 'siem_events_for_incident(incident_id="10868")' in block


def test_routing_block_unmapped_source_falls_back_to_run_op():
    norm = {"source_connector": "Acme SIEM 9000", "related_sources": [],
            "indicators": {"ips": [], "hosts": [], "users": []}}
    block = build_source_routing_block(norm)
    assert "run_op" in block and "Acme SIEM 9000" in block


def test_routing_block_empty_when_no_source():
    norm = {"source_connector": None, "related_sources": [],
            "indicators": {"ips": [], "hosts": [], "users": []}}
    assert build_source_routing_block(norm) == ""


# --- normalizer: harvest member-alert sources from an inlined case --------

def _case_with_members():
    """A case (thin shell) whose member alerts came from two different sources,
    as inlined by a $relationships=true fetch."""
    return {
        "@id": "/api/3/incidents/abc",
        "name": "Correlated activity for host smithDesktop",
        "source": {"itemValue": "Playbook"},
        "alerts": [
            {"@id": "/api/3/alerts/1", "source": {"itemValue": "Fortinet FortiSIEM"},
             "sourceIp": "10.1.1.5", "destinationIp": "203.0.113.9"},
            {"@id": "/api/3/alerts/2", "source": {"itemValue": "Fortinet FortiAnalyzer"},
             "sourceHostName": "smithDesktop"},
            "/api/3/alerts/3",  # bare IRI — must be tolerated
        ],
    }


def test_normalizer_harvests_member_sources_and_indicators():
    norm = normalize_record(_case_with_members())
    assert norm["related_sources"] == ["Fortinet FortiSIEM",
                                        "Fortinet FortiAnalyzer"]
    ip_vals = {i["value"] for i in norm["indicators"]["ips"]}
    assert {"10.1.1.5", "203.0.113.9"} <= ip_vals
    assert "smithDesktop" in norm["indicators"]["hosts"]


def test_build_prompt_appends_multi_source_routing():
    bundle = build_triage_prompt(_case_with_members())
    sys = bundle["system"]
    assert "source-aware pivots" in sys.lower()
    assert "FortiSIEM" in sys and "FortiAnalyzer" in sys
    # the case spans two sources → multi-source language present
    assert "multiple sources" in sys


def test_record_sources_dedups_primary_and_related():
    norm = {"source_connector": "Fortinet FortiSIEM",
            "related_sources": ["Fortinet FortiSIEM", "Fortinet FortiAnalyzer"]}
    assert record_sources(norm) == ["Fortinet FortiSIEM",
                                     "Fortinet FortiAnalyzer"]
