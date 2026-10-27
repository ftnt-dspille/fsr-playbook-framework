"""emit_card tolerates the card's fields passed at the TOP LEVEL.

The canonical shape is emit_card(card_type='verdict', payload={...}). But live
(.159, triage), the model reaches for the card's fields as SIBLINGS of
card_type instead of nesting them under payload:

    emit_card(card_type='verdict', disposition='suspicious', severity='high', ...)

The old contract rejected that at the arg-gate with
"disposition: not an argument of emit_card", which taught the model the fields
were FORBIDDEN -- so it resent an EMPTY payload, hit `bad_payload`, retried
identically, and tripped the repeated-call guard. The verdict card NEVER
rendered. Reproduced twice on current builds.

The fix: accept either shape. Top-level fields fold into payload (explicit
payload wins), and payload is no longer required, so a top-level-only call
passes the arg-gate and emits the card on the first try.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm.arg_gate import check
from fsr_playbooks.llm.tools import TOOL_SCHEMA_OVERRIDES
from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server.tools_emit import emit_card

_VERDICT = {
    "disposition": "suspicious",
    "severity": "high",
    "confidence": 0.95,
    "summary": "Two internal hosts beaconed to known-bad destinations.",
    "findings": [{"claim": "host 192.168.0.10 reached a C2 IP",
                  "evidence": ["tu1"]}],
}


@pytest.fixture
def turn():
    ev = cv.TurnEvidence()
    cv.set_turn_evidence(ev)
    cv.register_tool_result("tu1", "search_module_records", True, {"module": "alerts"})
    yield ev
    cv.set_turn_evidence(None)


def test_arg_gate_accepts_verdict_fields_at_top_level():
    """The run-1 failure: top-level fields were rejected as 'not an argument'."""
    args = {"card_type": "verdict", **_VERDICT}
    err = check("emit_card", TOOL_SCHEMA_OVERRIDES["emit_card"], emit_card, args)
    assert err is None, err


def test_top_level_fields_fold_into_payload_and_emit(turn):
    out = emit_card("verdict", **_VERDICT)
    assert out.get("ok"), out
    assert out.get("card_type") == "verdict"
    assert out["card"]["disposition"] == "suspicious"


def test_canonical_payload_shape_still_works(turn):
    out = emit_card("verdict", payload=dict(_VERDICT))
    assert out.get("ok"), out
    assert out.get("card_type") == "verdict"


def test_explicit_payload_wins_over_a_stray_top_level_key(turn):
    out = emit_card("verdict", payload=dict(_VERDICT, severity="high"),
                    severity="low")
    assert out.get("ok"), out
    assert out["card"]["severity"] == "high"
