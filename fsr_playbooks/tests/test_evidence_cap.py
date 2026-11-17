"""I3: a committed verdict on all-thin evidence gets one coverage round, then
is capped at needs_more_info."""
from __future__ import annotations

from fsr_playbooks.mcp_server._citation_validator import (
    TurnEvidence,
    register_tool_result,
    result_is_thin,
    set_turn_evidence,
    set_turn_ready_sources,
)
from fsr_playbooks.mcp_server.tools_emit import emit_verdict

_THIN = {"ok": True, "count": 0, "events": []}
_FULL = {"ok": True, "count": 2, "events": [{"src": "10.0.0.5"}, {"src": "10.0.0.6"}]}


def _ev():
    ev = TurnEvidence()
    set_turn_evidence(ev)
    return ev


def _verdict(*ids, disposition="true_positive"):
    return emit_verdict(
        disposition=disposition, severity="high", confidence=0.9,
        summary="Traffic to a flagged host.",
        findings=[{"claim": "The host was contacted.", "evidence": list(ids)}],
    )


class TestResultIsThin:
    def test_empty_shapes_are_thin(self):
        for r in (None, [], {"ok": False}, {"error": "boom"},
                  {"ok": True, "code": "no_events"}, {"ok": True, "empty": True},
                  {"ok": True, "count": 0}, {"ok": True, "total": 0},
                  {"ok": True, "events": []}, {"ok": True, "data": None}):
            assert result_is_thin(r) is True, r

    def test_bodies_are_not_thin(self):
        for r in (_FULL, {"ok": True, "record": {"iri": "/x"}},
                  [{"id": 1}], {"ok": True, "data": {"a": 1}}, "text"):
            assert result_is_thin(r) is False, r


class TestEvidenceCap:
    def test_all_thin_committed_is_refused_once(self):
        _ev()
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        out = _verdict("c1")
        assert out["ok"] is False
        assert out["code"] == "evidence_all_thin"

    def test_second_committed_attempt_is_capped(self):
        _ev()
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        _verdict("c1")  # the coverage round is offered here
        out = _verdict("c1")
        assert out["ok"] is True
        card = out["card"]
        assert card["disposition"] == "needs_more_info"
        assert any("capped at needs_more_info" in u for u in card["unknowns"])

    def test_non_thin_evidence_commits_first_time(self):
        _ev()
        register_tool_result("c2", "siem_search", True, {}, _FULL)
        out = _verdict("c2")
        assert out["ok"] is True
        assert out["card"]["disposition"] == "true_positive"

    def test_mixed_evidence_is_not_capped(self):
        _ev()
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        register_tool_result("c2", "siem_search", True, {}, _FULL)
        out = _verdict("c1", "c2")
        assert out["ok"] is True
        assert out["card"]["disposition"] == "true_positive"

    def test_needs_more_info_is_never_refused(self):
        _ev()
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        out = _verdict("c1", disposition="needs_more_info")
        assert out["ok"] is True

    def test_refusal_count_survives_suspension(self):
        ev = _ev()
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        _verdict("c1")
        restored = TurnEvidence.from_dict(ev.to_dict())
        assert restored.thin_refusals() == 1
        set_turn_evidence(restored)
        out = _verdict("c1")
        assert out["ok"] is True
        assert out["card"]["disposition"] == "needs_more_info"


class TestUncheckedReadySources:
    def teardown_method(self):
        set_turn_ready_sources(None)

    def test_refusal_and_cap_name_ready_sources_never_queried(self):
        _ev()
        set_turn_ready_sources({"siem_": "FortiSIEM", "faz_": "FortiAnalyzer",
                                "edr_": "FortiEDR"})
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        refused = _verdict("c1")
        assert "FortiAnalyzer, FortiEDR" in refused["message"]
        assert "FortiSIEM" not in refused["message"].split("queried:")[-1]
        card = _verdict("c1")["card"]
        assert any("FortiAnalyzer" in u and "FortiEDR" in u for u in card["unknowns"])

    def test_no_ready_sources_known_names_none(self):
        _ev()
        register_tool_result("c1", "siem_search", True, {}, _THIN)
        card = (_verdict("c1"), _verdict("c1"))[1]["card"]
        assert not any("not checked" in u for u in card["unknowns"])
