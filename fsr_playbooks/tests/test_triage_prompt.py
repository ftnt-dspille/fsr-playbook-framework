"""Tests for the dynamic triage prompt builder."""
from __future__ import annotations

import json
import pathlib

import pytest

from fsr_playbooks.llm.intents import load_intent_prompt
from fsr_playbooks.llm.triage_prompt import build_triage_prompt, build_what_we_know
from fsr_playbooks.llm.triage_normalize import normalize_record

FIX = pathlib.Path(__file__).parent / "fixtures" / "triage"


@pytest.fixture
def c2_raw() -> dict:
    return json.loads((FIX / "alert_c2_exfil.json").read_text())


def test_prompt_appends_to_full_base(c2_raw):
    base = load_intent_prompt("triage")
    out = build_triage_prompt(c2_raw)
    # base prompt preserved in full (graceful-degrade guarantee)
    assert base in out["system"]
    assert out["scenario_id"] == "c2_exfil"


def test_what_we_know_grounds_the_exfil_bytes(c2_raw):
    block = build_what_we_know(normalize_record(c2_raw))
    # the smoking gun must be surfaced in human-readable form
    assert "GB" in block
    assert "102.220.160.21 (EXTERNAL" in block
    assert "10.50.60.70 (internal" in block
    assert "smithDesktop" in block


def test_what_we_know_surfaces_siem_incident_id(c2_raw):
    block = build_what_we_know(normalize_record(c2_raw))
    # the SIEM's native incident id must be surfaced (10868), distinct from the
    # FortiSOAR record id, with the guidance to use it for SIEM ops.
    assert "SIEM incident id: 10868" in block
    assert "siem_events_for_incident" in block
    assert "NOT the" in block


def test_base_prompt_warns_against_soar_id_for_siem_ops():
    base = load_intent_prompt("triage")
    assert "SIEM's OWN incident id" in base
    assert "sourcedata.incident_data.incidentId" in base


def test_base_prompt_has_no_repeat_across_turns_rule():
    # P2 — the prompt must instruct the agent not to re-run prior turns'
    # enrichment/pivots and to advance instead of restart.
    base = load_intent_prompt("triage")
    assert "advance, don't restart" in base.lower() or "advance, don’t restart" in base.lower()
    assert "do not re-run" in base.lower()


def test_prompt_includes_scenario_recipes(c2_raw):
    sys = build_triage_prompt(c2_raw)["system"]
    assert "Known-good opening moves" in sys
    # the opening move now carries source_ip so the wrapper can coerce a stale
    # id / fall back to an IP event search
    assert "siem_events_for_incident(incident_id=\"10868\", source_ip=" in sys
    assert "Answer these before you conclude" in sys


def test_generic_record_still_gets_base_plus_checklist():
    raw = {"@id": "/api/3/alerts/x", "name": "disk latency",
           "sourceIp": "10.0.0.9"}
    out = build_triage_prompt(raw)
    assert out["scenario_id"] == "generic"
    assert load_intent_prompt("triage") in out["system"]
    assert "Before you conclude" in out["system"]
    # no scenario header for generic
    assert "Likely scenario" not in out["system"]


def test_humanize_bytes_in_event_line(c2_raw):
    block = build_what_we_know(normalize_record(c2_raw))
    # 4849007121 bytes ≈ 4.5GB
    assert "4.5GB" in block or "4.5 GB" in block.replace("GB", " GB")
