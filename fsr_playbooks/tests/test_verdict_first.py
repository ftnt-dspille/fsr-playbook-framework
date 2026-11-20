"""An investigation delivers its verdict before it stages a change that rests on it."""
from fsr_playbooks.llm import ask_scope, tools
from fsr_playbooks.mcp_server import _citation_validator as cv

CLOSE = {"module": "alerts", "uuid": "x", "fields": {"status": "Closed"}}


def _turn(scope):
    token = ask_scope.bind_scope(scope) if scope else None
    ev = cv.TurnEvidence()
    cv.set_turn_evidence(ev)
    return token, ev


def _end(token):
    cv.set_turn_evidence(None)
    if token is not None:
        ask_scope.reset_scope(token)


def test_write_before_verdict_is_refused_once_then_allowed():
    token, _ = _turn("investigate")
    try:
        first = tools.verdict_first_refusal("update_record", CLOSE)
        assert first and first["code"] == "verdict_first"
        assert "emit_card(card_type='verdict')" in first["error"]
        assert tools.verdict_first_refusal("update_record", CLOSE) is None
    finally:
        _end(token)


def test_action_card_before_verdict_is_refused():
    token, _ = _turn("investigate")
    try:
        r = tools.verdict_first_refusal("emit_card", {"card_type": "action"})
        assert r and r["code"] == "verdict_first"
    finally:
        _end(token)


def test_after_a_verdict_the_write_goes_through():
    token, ev = _turn("investigate")
    try:
        ev.record_verdict({"disposition": "false_positive"})
        assert tools.verdict_first_refusal("update_record", CLOSE) is None
    finally:
        _end(token)


def test_other_scopes_and_reads_are_untouched():
    for scope in (None, "act", "lookup", "answer", "build"):
        token, _ = _turn(scope)
        try:
            assert tools.verdict_first_refusal("update_record", CLOSE) is None
        finally:
            _end(token)
    token, _ = _turn("investigate")
    try:
        assert tools.verdict_first_refusal("get_record", {}) is None
        assert tools.verdict_first_refusal("emit_card", {"card_type": "verdict"}) is None
    finally:
        _end(token)


def test_never_hides_update_record_from_the_advertised_tools():
    token, _ = _turn("investigate")
    try:
        assert tools.turn_refusal("update_record", {}) is None
    finally:
        _end(token)
