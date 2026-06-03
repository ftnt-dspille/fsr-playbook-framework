"""Tests for the triage record normalizer.

Uses real captured fixtures (a FortiSIEM-sourced C2/exfil *alert* with embedded
associated_events, and a sparse *incident* whose only indicators are in prose)
to lock in that both record types collapse to the same canonical shape.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from fsr_core.llm.triage_normalize import normalize_record

FIX = pathlib.Path(__file__).parent / "fixtures" / "triage"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


@pytest.fixture
def alert() -> dict:
    return normalize_record(_load("alert_c2_exfil.json"))


@pytest.fixture
def incident() -> dict:
    return normalize_record(_load("incident_smithdesktop.json"))


# --- alert: field-rich, sourcedata-carrying ------------------------------

def test_alert_module_and_source(alert):
    assert alert["module"] == "alerts"
    assert alert["source_connector"] == "Fortinet FortiSIEM"
    assert alert["severity"] == "High"


def test_alert_extracts_both_ips_with_roles(alert):
    by_val = {i["value"]: i for i in alert["indicators"]["ips"]}
    assert "10.50.60.70" in by_val and "102.220.160.21" in by_val
    assert by_val["10.50.60.70"]["role"] == "src"
    assert by_val["102.220.160.21"]["role"] == "dst"


def test_alert_tags_internal_vs_external(alert):
    by_val = {i["value"]: i for i in alert["indicators"]["ips"]}
    assert by_val["10.50.60.70"]["internal"] is True       # RFC1918
    assert by_val["102.220.160.21"]["internal"] is False   # external C2


def test_alert_surfaces_embedded_events(alert):
    """The whole point: associated_events must NOT be truncated away."""
    evs = alert["evidence_events"]
    assert len(evs) >= 1
    # the 6.8 GB exfil session is the smoking gun — bytes must survive
    big = max(evs, key=lambda e: e.get("bytes_in", 0) or 0)
    assert big["bytes_in"] > 1_000_000_000
    assert big["dst"] == "102.220.160.21"
    assert big["dst_country"] == "Nigeria"


def test_alert_extracts_mitre(alert):
    ids = {m["id"] for m in alert["mitre"]}
    assert "T1041" in ids
    assert alert["mitre"][0]["tactic"] == "Exfiltration"


def test_alert_incident_id_for_siem_pivot(alert):
    # needed to drive get_associated_events_new back into FortiSIEM
    assert alert["incident_id"] == "10868"


def test_alert_host_from_events(alert):
    assert "smithDesktop" in alert["indicators"]["hosts"]


# --- incident: sparse, indicators only in prose --------------------------

def test_incident_same_shape(incident):
    # uniform contract regardless of record type
    assert set(incident) >= {"module", "indicators", "mitre",
                             "evidence_events", "incident_summary"}
    assert incident["module"] == "incidents"
    assert incident["source_connector"] == "Fortinet FortiSIEM"


def test_incident_has_no_sourcedata_events(incident):
    # this incident carries no sourcedata; digest is empty, not an error
    assert incident["evidence_events"] == []


# --- robustness ----------------------------------------------------------

def test_handles_garbage_input():
    assert normalize_record({})["indicators"]["ips"] == []
    assert normalize_record(None)["module"] == ""  # type: ignore[arg-type]


def test_sourcedata_as_unparseable_string():
    rec = {"@id": "/api/3/alerts/x", "sourcedata": "{not json",
           "sourceIp": "8.8.8.8"}
    out = normalize_record(rec)
    assert out["indicators"]["ips"][0]["value"] == "8.8.8.8"
    assert out["evidence_events"] == []


# --- P1: recover the FortiSIEM incident id from a member alert -------------

def test_incident_id_recovered_from_member_alert_sourcedata():
    """A case has no incidentId of its own; it lives on a FortiSIEM member
    alert's sourcedata. When that alert arrives hydrated, normalize surfaces
    the SIEM id so SIEM incident ops get the right one (not the record id)."""
    case = {
        "@id": "/api/3/incidents/abc",
        "alerts": [
            {"@id": "/api/3/alerts/1", "source": "Fortinet FortiSIEM",
             "sourcedata": json.dumps({"incident_data": {"incidentId": 11594}})},
        ],
    }
    assert normalize_record(case)["incident_id"] == "11594"


def test_record_level_incident_id_wins_over_member():
    rec = {
        "@id": "/api/3/alerts/x",
        "sourcedata": json.dumps({"incident_data": {"incidentId": 555}}),
        "alerts": [
            {"@id": "/api/3/alerts/1",
             "sourcedata": json.dumps({"incident_data": {"incidentId": 999}})},
        ],
    }
    assert normalize_record(rec)["incident_id"] == "555"


def test_no_incident_id_when_members_thin():
    """Bare-IRI / thin member alerts (no sourcedata) leave incident_id None —
    that's the case the pre-flight back-fill exists to resolve."""
    case = {"@id": "/api/3/incidents/abc",
            "alerts": [{"@id": "/api/3/alerts/1", "source": "Fortinet FortiSIEM"}]}
    assert normalize_record(case)["incident_id"] is None
