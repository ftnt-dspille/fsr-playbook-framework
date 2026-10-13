"""A verdict summary a little over the cap is trimmed, not refused.

The 600-character cap is not advertised up front (emit_card's payload is a
bare object, and the prompt never states it), so the model learns it only
from a refusal. Live, a 612-character summary cost a whole re-emit round of
about 1,400 output tokens.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import emit_card
from fsr_playbooks.mcp_server._citation_validator import (
    clear_tool_registry,
    register_tool_result,
)
from fsr_playbooks.mcp_server.tools_emit import VERDICT_SUMMARY_MAX, emit_verdict

_LIVE_SUMMARY = (
    "The-Flame shows an active likely-ransomware intrusion, not a one-off alert. "
    "FortiEDR logged 28 Critical events in a ~45min window today: an in-memory "
    "Metasploit meterpreter payload, process injection/stack-pivot, and an explicit "
    "shadow-copy-deletion attempt, matching the alert's vssadmin/mshta/T1490 scenario. "
    "Caveats: the EDR action is 'SimulationBlock' (enforcement unconfirmed), and the "
    "alert's user (jdoe) doesn't match the EDR-logged user (jlocke). FortiSIEM shows "
    "nothing for this host in 24h, so network corroboration is missing. Isolation is "
    "the lever that is left while the console confirms enforcement mode.")


def _payload(summary: str) -> dict:
    return {"disposition": "true_positive", "severity": "critical", "confidence": 0.85,
            "summary": summary,
            "findings": [{"claim": "28 critical EDR events", "evidence": ["c0"]}]}


def _registry():
    clear_tool_registry()
    register_tool_result("c0", "edr_host", True)


def test_the_live_summary_is_over_the_cap():
    assert len(_LIVE_SUMMARY) > VERDICT_SUMMARY_MAX


def test_an_over_long_summary_is_cut_at_a_sentence_and_said_so():
    _registry()
    r = emit_card("verdict", _payload(_LIVE_SUMMARY))
    assert r["ok"] is True, r
    s = r["card"]["summary"]
    assert len(s) <= VERDICT_SUMMARY_MAX
    assert s.endswith(".") and _LIVE_SUMMARY.startswith(s)
    assert str(len(_LIVE_SUMMARY)) in r["summary_clipped"]


def test_a_summary_with_no_sentence_break_is_cut_at_a_word():
    _registry()
    r = emit_card("verdict", _payload("word " * 200))
    assert r["ok"] is True
    s = r["card"]["summary"]
    assert len(s) <= VERDICT_SUMMARY_MAX and s.endswith("...")
    assert "wor..." not in s


def test_a_summary_within_the_cap_is_untouched():
    _registry()
    r = emit_card("verdict", _payload("Short and complete."))
    assert r["card"]["summary"] == "Short and complete."
    assert "summary_clipped" not in r


def test_the_internal_validator_still_holds_the_cap():
    _registry()
    r = emit_verdict(**_payload("x" * (VERDICT_SUMMARY_MAX + 1)))
    assert r["ok"] is False and r["code"] == "summary_too_long"
