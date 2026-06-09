"""Tests for the triage pre-flight (fetch → normalize → classify → emit)."""
from __future__ import annotations

import json
import pathlib

import pytest

from fsr_core.llm.intents import load_intent_prompt
from fsr_core.llm import triage_preflight as pf

FIX = pathlib.Path(__file__).parent / "fixtures" / "triage"


@pytest.fixture
def c2_raw() -> dict:
    return json.loads((FIX / "alert_c2_exfil.json").read_text())


def test_iri_to_path_shorthands():
    assert pf._iri_to_path("alerts:abc") == "/api/3/alerts/abc"
    assert pf._iri_to_path("alerts/abc") == "/api/3/alerts/abc"
    assert pf._iri_to_path("/api/3/alerts/abc") == "/api/3/alerts/abc"
    assert pf._iri_to_path("api/3/alerts/abc") == "/api/3/alerts/abc"


def test_preflight_from_raw_record_builds_scenario_prompt(c2_raw):
    events = []
    out = pf.triage_preflight(raw_record=c2_raw, emit=events.append)
    assert out["scenario_id"] == "c2_exfil"
    assert load_intent_prompt("triage") in out["system"]
    assert out["raw"] is c2_raw
    # activity trail: normalize → classify → ground (no fetch when raw given)
    phases = [e["phase"] for e in events]
    assert phases == ["normalize", "classify", "ground"]
    ground = next(e for e in events if e["phase"] == "ground")
    assert ground["events"] >= 1  # the embedded driving events were grounded


def test_preflight_no_record_degrades_to_plain_triage():
    out = pf.triage_preflight(raw_record={}, emit=None)
    assert out["scenario_id"] == "generic"
    assert load_intent_prompt("triage") in out["system"]
    assert out["raw"] == {}


def test_activity_emit_never_raises():
    def boom(_ev):
        raise RuntimeError("sink down")

    # a failing sink must not break pre-flight
    out = pf.triage_preflight(raw_record={"@id": "/api/3/alerts/x"}, emit=boom)
    assert out["scenario_id"] == "generic"


def test_fetch_raw_record_none_when_not_live(monkeypatch):
    monkeypatch.setattr("fsr_core.mcp_server._shared._live_client", lambda: None)
    assert pf.fetch_raw_record("alerts:abc") is None


# --- P1 back-fill: recover the SIEM incident id from a thin member alert ----

def test_backfill_fetches_member_alert_and_resolves_incident_id():
    """A case whose member alert arrived THIN (no sourcedata) gets the SIEM
    incident id back-filled by fetching that alert and splicing its sourcedata
    in, so normalize then surfaces it."""
    case = {"@id": "/api/3/incidents/abc",
            "alerts": [{"iri": "/api/3/alerts/1"}]}  # thin — no sourcedata

    def fake_fetch(iri):
        assert iri == "/api/3/alerts/1"
        return {"@id": iri, "source": "Fortinet FortiSIEM",
                "sourcedata": json.dumps(
                    {"incident_data": {"incidentId": 11594}})}

    events = []
    out = pf.backfill_siem_incident_id(case, fetch=fake_fetch, emit=events.append)
    from fsr_core.llm.triage_normalize import normalize_record
    assert normalize_record(out)["incident_id"] == "11594"
    assert any(e.get("phase") == "resolve" for e in events)


def test_backfill_noop_when_already_resolvable():
    """No fetch when the record already exposes an incident id."""
    rec = {"@id": "/api/3/alerts/x",
           "sourcedata": json.dumps({"incident_data": {"incidentId": 7}})}

    def boom(_iri):
        raise AssertionError("should not fetch when id already present")

    out = pf.backfill_siem_incident_id(rec, fetch=boom)
    assert out is rec


def test_backfill_bounded_and_safe_when_no_id_found():
    """Capped at _MAX_ALERT_BACKFILL fetches; returns cleanly when none hit."""
    case = {"@id": "/api/3/incidents/abc",
            "alerts": [{"iri": f"/api/3/alerts/{i}"} for i in range(10)]}
    calls = []

    def fake_fetch(iri):
        calls.append(iri)
        return {"@id": iri}  # no sourcedata → no id

    out = pf.backfill_siem_incident_id(case, fetch=fake_fetch)
    assert len(calls) <= pf._MAX_ALERT_BACKFILL
    from fsr_core.llm.triage_normalize import normalize_record
    assert normalize_record(out)["incident_id"] is None
