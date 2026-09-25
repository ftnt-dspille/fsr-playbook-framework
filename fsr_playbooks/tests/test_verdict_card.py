"""Structured verdict card: payload validation, citation enforcement, delivery guard."""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import emit_card
from fsr_playbooks.mcp_server.tools_emit import emit_verdict
from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry, register_tool_result, validate_evidence_ids,
)


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
        assert r["card"]["type"] == "verdict"
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
        assert r["card"]["type"] == "verdict"
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
    """VerdictDeliveryGuard fires when evidence tools run but no verdict."""

    def test_guard_inert_on_build_turns(self):
        from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
        guard = VerdictDeliveryGuard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        # Authoring=True (build turn)
        assert guard.outstanding(set(), authoring=True) is False

    def test_guard_inert_without_evidence_tools(self):
        from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
        guard = VerdictDeliveryGuard()
        guard.note_result("find_connector", {}, {"ok": True})
        assert guard.outstanding(set(), authoring=False) is False

    def test_guard_fires_on_evidence_then_prose(self):
        from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
        guard = VerdictDeliveryGuard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        assert guard.outstanding(set(), authoring=False) is True

    def test_guard_inert_after_verdict(self):
        from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
        guard = VerdictDeliveryGuard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        guard.note_result("emit_card", {"card_type": "verdict"}, {"ok": True})
        assert guard.outstanding(set(), authoring=False) is False

    def test_guard_inert_after_forced(self):
        from fsr_playbooks.llm._loop_helpers import VerdictDeliveryGuard
        guard = VerdictDeliveryGuard()
        guard.note_result("get_record", {"record": "x"}, {"ok": True})
        guard.mark_forced()
        assert guard.outstanding(set(), authoring=False) is False


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
        assert card["type"] == "verdict"
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
