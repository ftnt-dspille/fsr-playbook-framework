"""Tests for the scenario classifier + recipe renderer."""
from __future__ import annotations

import json
import pathlib

import pytest

from fsr_core.llm.triage_normalize import normalize_record
from fsr_core.llm.triage_scenarios import classify_alert, render_recipes

FIX = pathlib.Path(__file__).parent / "fixtures" / "triage"


@pytest.fixture
def c2_norm() -> dict:
    return normalize_record(json.loads((FIX / "alert_c2_exfil.json").read_text()))


def test_c2_alert_classifies_as_c2_exfil(c2_norm):
    sc = classify_alert(c2_norm)
    assert sc["id"] == "c2_exfil"


def test_recipes_prefilled_with_entities(c2_norm):
    recipes = render_recipes(classify_alert(c2_norm), c2_norm)
    blob = "\n".join(recipes)
    # incident id, host, external C2, and internal IP all filled in
    assert "10868" in blob                       # siem_events_for_incident
    assert "smithDesktop" in blob                # siem_search_host
    assert "102.220.160.21" in blob              # external C2 enrichment
    assert "10.50.60.70" in blob                 # internal get_ip_context
    # internal IP must be steered AWAY from external TI
    assert "do NOT run external TI" in blob
    # external C2 line must NOT appear as an internal-context call
    assert "siem_search_ip(ip=\"102.220.160.21\", direction=\"dst\")" in blob


def test_generic_fallback_for_unmatched():
    norm = normalize_record({"@id": "/api/3/alerts/x", "name": "disk latency high",
                             "sourceIp": "10.0.0.5"})
    sc = classify_alert(norm)
    assert sc["id"] == "generic"
    assert render_recipes(sc, norm) == []


def test_bad_matcher_never_raises(monkeypatch):
    import fsr_core.llm.triage_scenarios as ts

    def boom(norm):
        raise RuntimeError("matcher blew up")

    monkeypatch.setitem(ts.SCENARIOS[0], "match", boom)
    # classification must degrade to generic, not raise
    sc = classify_alert({"indicators": {"ips": []}, "mitre": []})
    assert sc["id"] == "generic"


def test_every_scenario_has_required_keys():
    import fsr_core.llm.triage_scenarios as ts
    for sc in ts.SCENARIOS + [ts.GENERIC]:
        assert {"id", "title", "match", "siem_recipes",
                "verdict_checklist", "fragment"} <= set(sc)
