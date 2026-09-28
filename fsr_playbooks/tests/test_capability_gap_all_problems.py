"""A refused capability_gap card names EVERY problem at once.

Live (build_plain_request_no_record, deepseek): the validator reported one
problem per refusal -- bad_payload, then bad_resume, then bad_tips, then
bad_alternatives -- so each card cost 4-5 full LLM rounds. emit_verdict already
returns all problems in one refusal; this card now does the same.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_emit import emit_capability_gap_card

_OK = dict(id="gap-1", missing="IP containment", why="no firewall configured",
           fix_steps=["Configure the fortigate-firewall connector"],
           resume={"label": "Re-check", "value": "recheck"})


def test_three_problems_come_back_in_one_refusal():
    r = emit_capability_gap_card(**{**_OK, "why": "", "resume": {"label": "Re-check"},
                                    "tips": [{"hint": "no text"}]})
    assert r["ok"] is False
    codes = [p["code"] for p in r["problems"]]
    assert codes == ["missing_field", "bad_resume", "bad_tips"]
    assert "3 problems" in r["message"]


def test_a_single_problem_keeps_its_own_code_and_message():
    r = emit_capability_gap_card(**{**_OK, "fix_steps": []})
    assert r["code"] == "bad_fix_steps" and "problems --" not in r["message"]


def test_a_valid_card_still_emits():
    r = emit_capability_gap_card(**_OK)
    assert r["ok"] is True and r["card"]["type"] == "capability_gap"


def test_duplicate_alternative_value_is_still_refused():
    r = emit_capability_gap_card(**{**_OK, "alternatives": [
        {"label": "Escalate", "value": "recheck"}]})
    assert r["code"] == "duplicate_value"
