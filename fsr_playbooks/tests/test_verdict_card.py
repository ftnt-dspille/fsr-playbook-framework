"""Structured verdict card: payload validation, citation enforcement, delivery guard."""
from __future__ import annotations

from fsr_playbooks.mcp_server import emit_card
from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry,
    register_tool_result,
)
from fsr_playbooks.mcp_server.tools_emit import emit_verdict


class TestVerdictPayloadValidation:
    """Payload validation: disposition, severity, confidence, summary, findings."""

    def test_good_verdict_payload(self):
        clear_tool_registry()
        register_tool_result("call_id_1", "get_record", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.95,
            summary="The IP 1.2.3.4 is a known C2 beacon.",
            findings=[
                {
                    "claim": "IP enrichment returned malware tag",
                    "evidence": ["call_id_1"],
                }
            ],
        )
        assert r["ok"] is True
        assert r["card"]["type"] == "verdict_card"
        assert r["card"]["disposition"] == "true_positive"
        assert len(r["card"]["findings"]) == 1

    def test_disposition_validation(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="unknown",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
        )
        assert r["ok"] is False and r["code"] == "bad_disposition"
        assert "true_positive" in r["message"]

    def test_severity_validation(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="extreme",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
        )
        assert r["ok"] is False and r["code"] == "bad_severity"

    def test_confidence_bounds(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=1.5,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
        )
        assert r["ok"] is False and r["code"] == "bad_confidence"

    def test_summary_length(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        long_summary = "x" * 601
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary=long_summary,
            findings=[{"claim": "x", "evidence": ["id1"]}],
        )
        assert r["ok"] is False and r["code"] == "summary_too_long"

    def test_findings_must_be_nonempty(self):
        clear_tool_registry()
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[],
        )
        assert r["ok"] is False and r["code"] == "no_findings"

    def test_finding_requires_claim_and_evidence(self):
        clear_tool_registry()
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "no evidence"}],
        )
        assert r["ok"] is False and r["code"] == "bad_finding_evidence"

    def test_evidence_ids_must_be_nonempty(self):
        clear_tool_registry()
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": []}],
        )
        assert r["ok"] is False and r["code"] == "bad_finding_evidence"

    def test_unknowns_consistency_with_confidence(self):
        # Low confidence with empty unknowns should fail
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.6,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
            unknowns=[],
        )
        assert r["ok"] is False and r["code"] == "confidence_unknowns_conflict"

    def test_high_confidence_allows_empty_unknowns(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.95,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
            unknowns=[],
        )
        assert r["ok"] is True

    def test_recommended_actions_validation(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
            recommended_actions=[{"label": "Block IP"}],
        )
        assert r["ok"] is True
        assert len(r["card"]["recommended_actions"]) == 1

    def test_bad_recommended_actions(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["id1"]}],
            recommended_actions=[{"no_label_field": "x"}],
        )
        assert r["ok"] is False and r["code"] == "bad_action"


class TestCitationValidation:
    """Citation enforcement: evidence ids must be known tool_use ids."""

    def test_unknown_evidence_id(self):
        clear_tool_registry()
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["unknown_id"]}],
        )
        assert r["ok"] is False and r["code"] == "invalid_evidence_ids"
        assert "Unknown tool_use_ids" in r["message"]

    def test_failed_tool_result_cannot_be_evidence(self):
        clear_tool_registry()
        register_tool_result("call_1", "get_record", False)  # Failed
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["call_1"]}],
        )
        assert r["ok"] is False and r["code"] == "invalid_evidence_ids"
        assert "Failed tool calls" in r["message"]

    def test_emit_tools_cannot_be_evidence(self):
        clear_tool_registry()
        register_tool_result("call_1", "emit_card", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["call_1"]}],
        )
        assert r["ok"] is False and r["code"] == "invalid_evidence_ids"
        assert "Emit tools are actions" in r["message"]

    def test_valid_evidence_passes(self):
        clear_tool_registry()
        register_tool_result("call_1", "get_record", True)
        register_tool_result("call_2", "search_records", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[
                {
                    "claim": "Record shows malware",
                    "evidence": ["call_1", "call_2"],
                }
            ],
        )
        assert r["ok"] is True

    def test_suggestions_list_valid_ids(self):
        clear_tool_registry()
        register_tool_result("call_1", "get_record", True)
        register_tool_result("call_2", "search_records", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["bad_id"]}],
        )
        assert r["ok"] is False
        assert "call_1" in r["suggestions"][0] or "call_2" in r["suggestions"][0]

    def test_a_cited_tool_name_is_pointed_at_its_calls(self):
        """Live: models cited `functions.get_record` and
        `multi_tool_use.parallel#1` -- wrapper names, not call ids -- and
        needed a retry to find the ids. The refusal names the calls, and every
        valid id carries its tool."""
        clear_tool_registry()
        register_tool_result("call_a", "get_record", True)
        register_tool_result("call_b", "siem_search", True)
        register_tool_result("call_c", "emit_card", True)
        r = emit_verdict(
            disposition="true_positive",
            severity="high",
            confidence=0.8,
            summary="Test",
            findings=[{"claim": "x", "evidence": ["functions.get_record"]}],
        )
        assert r["ok"] is False
        assert ("'functions.get_record' names the tool get_record, not a call: "
                "cite one of its call ids ['call_a'].") in r["message"]
        assert "call_a (get_record)" in r["suggestions"][0]
        assert "call_b (siem_search)" in r["suggestions"][0]
        assert "call_c" not in r["suggestions"][0]  # an emit is not evidence


class TestVerdictViaEmitCard:
    """Verdict card via emit_card routing."""

    def test_emit_card_with_verdict_type(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_card("verdict", {
            "disposition": "true_positive",
            "severity": "high",
            "confidence": 0.9,
            "summary": "Confirmed malware",
            "findings": [{"claim": "x", "evidence": ["id1"]}],
        })
        assert r["ok"] is True
        assert r["card"]["type"] == "verdict_card"
        assert r["card_type"] == "verdict"

    def test_emit_card_unknown_verdict_type(self):
        r = emit_card("verdict", {"bad": "payload"})
        assert r["ok"] is False


class TestVerdictDeliveryCarrier:
    """Verdict counts as a delivery carrier for turns."""

    def test_carries_delivery_verdict_with_disposition(self):
        from fsr_playbooks.llm._loop_helpers import _carries_delivery
        result = _carries_delivery("emit_card", {
            "card_type": "verdict",
            "payload": {"disposition": "true_positive"},
        })
        assert result is True

    def test_carries_delivery_verdict_no_disposition(self):
        from fsr_playbooks.llm._loop_helpers import _carries_delivery
        result = _carries_delivery("emit_card", {
            "card_type": "verdict",
            "payload": {},
        })
        assert result is False


class TestVerdictGuardFires:
    """VerdictDeliveryGuard fires when evidence tools run but no verdict.

    Live, triage and build advertise the SAME full surface (verify_playbook,
    push_playbook, emit_card ...), so every test here uses it. The guard used to
    decide "build turn" from that slice -- true on every live turn -- and never
    fired; and its evidence list held pre-consolidation names, so `siem_search`
    counted as nothing."""

    FULL = {"get_record", "siem_search", "faz_search", "run_op", "emit_card",
            "verify_playbook", "push_playbook", "verify_enhancement",
            "validate_yaml", "compile_yaml"}

    def _guard(self):
        from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
        return VerdictDeliveryGuard()

    def test_fires_on_the_full_surface_after_evidence(self):
        guard = self._guard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        assert guard.outstanding(self.FULL) is True

    def test_consolidated_hunt_tools_count_as_evidence(self):
        for name in ("siem_search", "siem_events_for_incident", "faz_search",
                     "faz_get_alerts", "search_module_records", "fmg_device"):
            guard = self._guard()
            guard.note_result(name, {}, {"ok": True})
            assert guard.outstanding(self.FULL) is True, name

    def test_inert_once_the_turn_authored(self):
        for name, args in (("validate_yaml", {}), ("verify_playbook", {}),
                           ("emit_card", {"card_type": "playbook_offer"})):
            guard = self._guard()
            guard.note_result("get_record", {"record": "x"}, {"ok": True})
            guard.note_result(name, args, {"ok": True})
            assert guard.outstanding(self.FULL) is False, name

    def test_a_capability_gap_card_is_not_authoring(self):
        guard = self._guard()
        guard.note_result("siem_search", {}, {"ok": True})
        guard.note_result("emit_card", {"card_type": "capability_gap"}, {"ok": True})
        assert guard.outstanding(self.FULL) is True

    def test_inert_without_evidence_tools(self):
        guard = self._guard()
        guard.note_result("find", {"kind": "connector"}, {"ok": True})
        assert guard.outstanding(self.FULL) is False

    def test_inert_after_verdict(self):
        guard = self._guard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        guard.note_result("emit_card", {"card_type": "verdict"}, {"ok": True})
        assert guard.outstanding(self.FULL) is False

    def test_inert_after_forced(self):
        guard = self._guard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        guard.mark_forced()
        assert guard.outstanding(self.FULL) is False

    def test_inert_when_no_card_tool_is_advertised(self):
        guard = self._guard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        assert guard.outstanding({"get_record"}) is False


class TestWireEventShape:
    """Verdict card renders to the expected wire event shape."""

    def test_verdict_card_event_shape(self):
        clear_tool_registry()
        register_tool_result("id1", "get_record", True)
        r = emit_verdict(
            disposition="false_positive",
            severity="low",
            confidence=0.75,
            summary="Not a threat",
            findings=[{
                "claim": "Record shows benign activity",
                "evidence": ["id1"],
            }],
            unknowns=["Is the user on the approved list?"],
            recommended_actions=[{
                "label": "Whitelist domain",
                "tool": "firewall_block",
            }],
        )
        assert r["ok"] is True
        card = r["card"]
        assert card["type"] == "verdict_card"
        assert card["disposition"] == "false_positive"
        assert card["severity"] == "low"
        assert card["confidence"] == 0.75
        assert card["summary"] == "Not a threat"
        assert len(card["findings"]) == 1
        assert card["findings"][0]["claim"] == "Record shows benign activity"
        assert card["findings"][0]["evidence"] == ["id1"]
        assert card["unknowns"] == ["Is the user on the approved list?"]
        assert len(card["recommended_actions"]) == 1
        assert card["recommended_actions"][0]["label"] == "Whitelist domain"


class TestToolNameReferences:
    """Verdict card is registered and discoverable."""

    def test_emit_card_includes_verdict_schema(self):
        from fsr_playbooks.llm.tools import REGISTRY
        spec = REGISTRY.get("emit_card")
        assert spec is not None
        kinds = spec.input_schema["properties"]["card_type"]["enum"]
        assert "verdict" in kinds

    def test_verdict_schema_exists_in_overrides(self):
        from fsr_playbooks.llm.tools import TOOL_SCHEMA_OVERRIDES
        assert "emit_verdict" in TOOL_SCHEMA_OVERRIDES
        schema = TOOL_SCHEMA_OVERRIDES["emit_verdict"]
        assert schema["type"] == "object"
        assert "disposition" in schema["properties"]
        assert "severity" in schema["properties"]
        assert "confidence" in schema["properties"]
        assert "findings" in schema["properties"]


class TestEvidenceSurvivesSuspension:
    """Evidence recorded before tier-3 suspension is citable after resume."""

    def test_evidence_survives_suspend_resume_cycle(self):
        """Verify that TurnEvidence is preserved across suspend/resume."""
        from fsr_playbooks.llm.approvals import SuspendedSession
        from fsr_playbooks.mcp_server._citation_validator import (
            TurnEvidence,
            get_turn_evidence,
            set_turn_evidence,
        )

        # Create evidence before suspension
        evidence = TurnEvidence()
        evidence.register("id1", "get_record", True)
        evidence.register("id2", "search_records", True)
        set_turn_evidence(evidence)

        # Simulate suspension: serialize evidence into SuspendedSession
        evidence_state = evidence.to_dict()
        suspended = SuspendedSession(
            approval_id="ap-test",
            session_id="s-test",
            tool="some_tool",
            tool_use_id="tu-test",
            args={},
            tier=3,
            history_snapshot=[],
            prior_tool_result_blocks=[],
            remaining_tool_calls=[],
            system="sys",
            tags={},
            tools=[],
            turn_evidence_state=evidence_state,
        )

        # Simulate resuming on a different thread: restore evidence
        restored_evidence = TurnEvidence.from_dict(suspended.turn_evidence_state)
        set_turn_evidence(restored_evidence)

        # Verify evidence is intact after restore
        current_evidence = get_turn_evidence()
        assert current_evidence is not None
        ids = current_evidence.valid_ids()
        assert "id1" in ids
        assert ids["id1"]["name"] == "get_record"
        assert ids["id1"]["ok"] is True
        assert "id2" in ids
        assert ids["id2"]["name"] == "search_records"
        assert ids["id2"]["ok"] is True

    def test_restored_evidence_passes_citation_check(self):
        """Verdict can cite evidence after resume."""
        from fsr_playbooks.llm.approvals import SuspendedSession
        from fsr_playbooks.mcp_server._citation_validator import (
            TurnEvidence,
            set_turn_evidence,
        )

        # Create evidence before suspension
        evidence = TurnEvidence()
        evidence.register("id1", "get_record", True)
        set_turn_evidence(evidence)

        # Serialize for suspension
        evidence_state = evidence.to_dict()
        suspended = SuspendedSession(
            approval_id="ap-test",
            session_id="s-test",
            tool="some_tool",
            tool_use_id="tu-test",
            args={},
            tier=3,
            history_snapshot=[],
            prior_tool_result_blocks=[],
            remaining_tool_calls=[],
            system="sys",
            tags={},
            tools=[],
            turn_evidence_state=evidence_state,
        )

        # Resume: restore evidence
        restored = TurnEvidence.from_dict(suspended.turn_evidence_state)
        set_turn_evidence(restored)

        # Now emit_verdict should succeed using restored evidence
        r = emit_verdict(
            disposition="benign",
            severity="low",
            confidence=0.9,
            summary="Activity is normal",
            findings=[{"claim": "All checks passed", "evidence": ["id1"]}],
        )
        assert r["ok"] is True
        assert r["card"]["type"] == "verdict_card"


class TestVerdictRefusalNamesTheFix:
    """Session health: every recorded bad_disposition retry repaired the same
    shapes. The refusal names each fix, and rewrites none of them -- which
    verdict to give stays the model's call."""

    def _refuse(self, **over):
        clear_tool_registry()
        register_tool_result("call_1", "get_record", True)
        kw = dict(disposition="true_positive", severity="high", confidence=0.9,
                  summary="s", findings=[{"claim": "c", "evidence": ["call_1"]}])
        kw.update(over)
        r = emit_verdict(**kw)
        assert r["ok"] is False, r
        return r["message"]

    def test_the_recorded_live_payload_gets_one_complete_repair(self):
        """The recorded payload: hedged disposition, word confidence, finding
        text under 'title', evidence as objects."""
        m = self._refuse(
            disposition="likely_false_positive", confidence="low",
            findings=[{"title": "No SIEM rows for the host",
                       "evidence": [{"tool_use_id": "call_1"}]}])
        assert "use 'false_positive' and put the doubt in confidence" in m
        assert "for 'low' send e.g. 0.35" in m
        assert "you sent 'title': put the finding's sentence in 'claim'" in m
        assert "cite the id itself, 'call_1'" in m

    def test_hedged_malicious_offers_both_calls(self):
        m = self._refuse(disposition="likely_malicious")
        assert "use 'true_positive'" in m and "'needs_more_info'" in m

    def test_inconclusive_maps_without_the_hedge_clause(self):
        m = self._refuse(disposition="Inconclusive")
        assert "use 'needs_more_info'" in m
        assert "doubt" not in m

    def test_an_unmappable_word_gets_the_list_only(self):
        m = self._refuse(disposition="spicy")
        assert "(got 'spicy')" in m and "use '" not in m

    def test_numeric_strings_say_send_the_number(self):
        assert "send 0.85, not a string" in self._refuse(confidence="85%")
        assert "send 0.7, not a string" in self._refuse(confidence="0.7")

    def test_a_single_evidence_string_says_wrap_it(self):
        m = self._refuse(findings=[{"claim": "c", "evidence": "call_1"}])
        assert "wrap it, ['call_1']" in m
