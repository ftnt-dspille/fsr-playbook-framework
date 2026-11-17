"""I5: the source coverage ledger.

Three things the model and the analyst see about which ready log sources a turn
has queried:

* the prompt tail, every round: a note naming ready sources not yet queried;
* every verdict card, capped or not: ``sources_checked`` lists the ready
  sources the turn queried;
* the unchecked note is derived from the same ready-source set the evidence
  cap names (I3), so the two cannot disagree.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from test_fenced_playbook_connector_gate import _reply_round
from test_openai_build_progress_forced import (
    _BUILD_TOOLS,
    _delta_chunk,
    _FakeStream,
    _tc,
    _usage_chunk,
)
from test_unexecuted_tool_calls_not_replayed import (
    _close_round,
    _drain,
    _openai_provider,
    _snapshotting,
)

from fsr_playbooks.llm.openai_provider import OpenAIProvider
from fsr_playbooks.llm.provider import Message
from fsr_playbooks.mcp_server._citation_validator import (
    TurnEvidence,
    checked_ready_sources,
    register_tool_result,
    set_turn_evidence,
    set_turn_ready_connectors,
    set_turn_ready_sources,
    unchecked_ready_note,
    unchecked_ready_sources,
)
from fsr_playbooks.mcp_server.tools_emit import emit_verdict

READY = {"siem_": "FortiSIEM", "faz_": "FortiAnalyzer"}
_THIN = {"ok": True, "count": 0, "events": []}
_FULL = {"ok": True, "count": 2, "events": [{"src": "10.0.0.5"}, {"src": "10.0.0.6"}]}


def _ev():
    ev = TurnEvidence()
    set_turn_evidence(ev)
    return ev


def _verdict(*ids):
    return emit_verdict(
        disposition="true_positive", severity="high", confidence=0.9,
        summary="Traffic to a flagged host.",
        findings=[{"claim": "The host was contacted.", "evidence": list(ids)}],
    )


class TestCheckedSources:
    def teardown_method(self):
        set_turn_ready_sources(None)

    def test_lists_only_ready_sources_the_turn_queried(self):
        ev = _ev()
        set_turn_ready_sources(READY)
        register_tool_result("c1", "siem_search", True, {}, _FULL)
        assert checked_ready_sources(ev.valid_ids()) == ["FortiSIEM"]

    def test_empty_without_ready_sources(self):
        ev = _ev()
        register_tool_result("c1", "siem_search", True, {}, _FULL)
        assert checked_ready_sources(ev.valid_ids()) == []

    def test_unchecked_note_names_ready_sources_not_queried(self):
        ev = _ev()
        set_turn_ready_sources(READY)
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        note = unchecked_ready_note(ev.valid_ids())
        assert "FortiAnalyzer" in note
        assert "FortiSIEM" not in note

    def test_unchecked_note_is_empty_once_every_ready_source_is_queried(self):
        ev = _ev()
        set_turn_ready_sources(READY)
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        register_tool_result("c2", "faz_search", True, {}, _THIN)
        assert unchecked_ready_note(ev.valid_ids()) == ""


class TestVerdictCardSourcesChecked:
    def teardown_method(self):
        set_turn_ready_sources(None)

    def test_full_evidence_card_lists_sources_checked(self):
        """Not capped: the card still carries the ledger line."""
        _ev()
        set_turn_ready_sources(READY)
        register_tool_result("c1", "siem_search", True, {}, _FULL)
        out = _verdict("c1")
        assert out["ok"] is True
        assert out["card"]["sources_checked"] == ["FortiSIEM"]

    def test_card_field_is_present_and_empty_when_nothing_was_checked(self):
        _ev()
        register_tool_result("c1", "siem_search", True, {}, _FULL)
        out = _verdict("c1")
        assert out["ok"] is True
        assert out["card"]["sources_checked"] == []


def _siem_round(call_id: str):
    return [
        _delta_chunk(tool_calls=[_tc(index=0, id=call_id, name="siem_search", args="{}")]),
        _delta_chunk(finish="tool_calls"), _usage_chunk(),
    ]


def _run(rounds, *, max_tool_turns: int = 4):
    call, sent = _snapshotting([_FakeStream(r) for r in rounds])
    create = AsyncMock(side_effect=call)
    p = _openai_provider(OpenAIProvider, create)
    tools = _BUILD_TOOLS + [{"type": "function", "function": {
        "name": "siem_search", "description": "siem_search",
        "parameters": {"type": "object", "properties": {}}}}]

    async def go():
        return await _drain(p.stream(
            system="s", messages=[Message(role="user", content="triage this alert")],
            tools=tools, tags={}, max_tool_turns=max_tool_turns))

    _ev()
    set_turn_ready_sources(READY)
    try:
        with patch("fsr_playbooks.llm.agent_loop.dispatch",
                   MagicMock(return_value=_FULL)), \
             patch("fsr_playbooks.llm.agent_loop._tier_for", return_value=0):
            asyncio.run(go())
    finally:
        set_turn_ready_sources(None)
    return sent


def test_each_round_after_a_tool_result_carries_the_unchecked_note():
    """Red before the fix: no request ever names the ready source the turn
    skipped (FortiAnalyzer) as not yet queried."""
    sent = _run([_siem_round("c1"), _reply_round("Looks benign."), _close_round()])
    assert len(sent) >= 2, "the loop never reached a second request"
    texts = [str(m.get("content")) for msgs in sent for m in msgs
             if m.get("role") == "user" and "not yet queried" in str(m.get("content"))]
    assert texts, "no request carried the ready-not-queried note"
    assert all("FortiAnalyzer" in t for t in texts)
    assert not any("FortiSIEM" in t for t in texts)


# ---- configured ticket and threat-intel connectors (not log sources) ----------
SNOW = {"servicenow": {"label": "ServiceNow", "kind": "tickets"}}
VT = {"virustotal": {"label": "VirusTotal", "kind": "intel"}}
_TOOL_WORDS = ("run_op", "siem_search", "faz_search", "run_connector_operation",
               "advance_search", "fetch_incidents", "query_ip", "emit_card")


class TestConnectorLedger:
    def teardown_method(self):
        set_turn_ready_sources(None)
        set_turn_ready_connectors(None)

    def test_ticket_connector_is_listed_when_configured_and_unqueried(self):
        ev = _ev()
        set_turn_ready_connectors(SNOW)
        register_tool_result("c1", "run_op", True,
                             {"connector": "virustotal", "op": "query_ip"}, _FULL)
        assert unchecked_ready_sources(ev.valid_ids()) == ["ServiceNow"]
        assert "ServiceNow" in unchecked_ready_note(ev.valid_ids())

    def test_it_disappears_once_the_connector_is_queried(self):
        ev = _ev()
        set_turn_ready_connectors(SNOW)
        register_tool_result("c1", "run_op", True,
                             {"connector": "servicenow", "op": "advance_search"}, _FULL)
        assert unchecked_ready_sources(ev.valid_ids()) == []
        assert checked_ready_sources(ev.valid_ids()) == ["ServiceNow"]
        assert unchecked_ready_note(ev.valid_ids()) == ""

    def test_not_listed_when_not_configured(self):
        ev = _ev()
        set_turn_ready_connectors(None)
        register_tool_result("c1", "run_op", True,
                             {"connector": "virustotal", "op": "query_ip"}, _FULL)
        assert unchecked_ready_sources(ev.valid_ids()) == []
        assert unchecked_ready_note(ev.valid_ids()) == ""

    def test_a_connector_of_an_unknown_kind_is_ignored(self):
        ev = _ev()
        set_turn_ready_connectors({"x": {"label": "X", "kind": "weather"}})
        assert unchecked_ready_sources(ev.valid_ids()) == []

    def test_unqueried_intel_is_listed_without_the_ticket_steer(self):
        ev = _ev()
        set_turn_ready_connectors(VT)
        register_tool_result("c1", "run_op", True,
                             {"connector": "fortiguard", "op": "ioc_search"}, _FULL)
        note = unchecked_ready_note(ev.valid_ids())
        assert "VirusTotal" in note and "ticket" not in note.lower()

    def test_a_plain_record_read_is_not_nudged_to_connectors(self):
        # Live: "tell me this alert's name" became a fifteen-call intel sweep
        # that sometimes never quoted the name. Connectors join the note only
        # once the turn has queried a source itself.
        ev = _ev()
        set_turn_ready_connectors({**VT, "servicenow": {"label": "ServiceNow", "kind": "tickets"}})
        register_tool_result("c1", "get_record", True, {"iri": "/api/3/alerts/x"}, _FULL)
        assert unchecked_ready_note(ev.valid_ids()) == ""
        register_tool_result("c2", "run_op", True,
                             {"connector": "fortiguard", "op": "ioc_search"}, _FULL)
        note = unchecked_ready_note(ev.valid_ids())
        assert "VirusTotal" in note and "ServiceNow" in note

    def test_empty_log_search_steers_to_tickets_by_host_and_indicator(self):
        ev = _ev()
        set_turn_ready_sources(READY)
        set_turn_ready_connectors(SNOW)
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        note = unchecked_ready_note(ev.valid_ids())
        assert "ServiceNow" in note and "FortiAnalyzer" in note
        assert "came back empty" in note
        assert "host name" in note and "indicator" in note

    def test_no_steer_to_tickets_once_they_are_queried(self):
        ev = _ev()
        set_turn_ready_sources(READY)
        set_turn_ready_connectors(SNOW)
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        register_tool_result("c2", "run_op", True, {"connector": "servicenow"}, _FULL)
        note = unchecked_ready_note(ev.valid_ids())
        assert "ticket" not in note.lower()

    def test_analyst_text_names_no_tools(self):
        """The verdict card's ledger and the note's steer are plain words."""
        ev = _ev()
        set_turn_ready_sources(READY)
        set_turn_ready_connectors({**SNOW, **VT})
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        note = unchecked_ready_note(ev.valid_ids())
        for w in _TOOL_WORDS:
            assert w not in note
        register_tool_result("c2", "run_op", True, {"connector": "virustotal"}, _FULL)
        out = _verdict("c2")
        assert out["card"]["sources_checked"] == ["FortiSIEM", "VirusTotal"]
        for label in out["card"]["sources_checked"] + out["card"].get("unknowns", []):
            assert not any(w in label for w in _TOOL_WORDS)

    def test_card_lists_a_queried_ticket_source(self):
        _ev()
        set_turn_ready_connectors(SNOW)
        register_tool_result("c1", "run_op", True,
                             {"connector": "servicenow", "op": "advance_search"}, _FULL)
        assert _verdict("c1")["card"]["sources_checked"] == ["ServiceNow"]


class TestConnectorSourceKind:
    def test_ticket_category_beats_intel(self, monkeypatch):
        from fsr_playbooks.llm import autonomy
        cats = {"servicenow": "cmdb,threat intelligence", "jira": "itsm",
                "virustotal": "threat intelligence", "slack": "messaging"}
        monkeypatch.setattr(autonomy, "_connector_category", cats.get)
        assert autonomy.connector_source_kind("servicenow") == "tickets"
        assert autonomy.connector_source_kind("jira") == "tickets"
        assert autonomy.connector_source_kind("virustotal") == "intel"
        assert autonomy.connector_source_kind("slack") is None
        assert autonomy.connector_source_kind("unknown") is None
