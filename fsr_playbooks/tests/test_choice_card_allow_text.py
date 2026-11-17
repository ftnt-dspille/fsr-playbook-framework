"""`allow_text` on a choice card: a free-text answer box for open questions."""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_emit import emit_card, emit_choice_card

OPTS = [{"label": "Start from an alert", "value": "alert_start"},
        {"label": "Start from an incident", "value": "incident_start"}]


def test_off_by_default_so_real_forks_stay_forks():
    card = emit_choice_card("q", "Pick", OPTS)["card"]
    assert "allow_text" not in card


def test_on_when_asked():
    card = emit_choice_card("q", "What should it do?", OPTS, allow_text=True)["card"]
    assert card["allow_text"] is True


def test_non_bool_is_refused():
    assert emit_choice_card("q", "Pick", OPTS, allow_text="yes")["code"] == "bad_allow_text"


def test_reaches_the_card_through_emit_card_and_its_aliases():
    for key in ("allow_text", "free_text"):
        out = emit_card("choice", {"prompt": "What should it do?", "options": OPTS,
                                   key: True})
        assert out["ok"], out
        assert out["card"]["allow_text"] is True, key
