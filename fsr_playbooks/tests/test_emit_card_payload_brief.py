"""`emit_card.payload` advertises each card's fields, generated from the
card's own schema -- so the first call can be right.

The payload used to say only "identical to the matching emit_<card_type>
tool's arguments", and those tools are not advertised: the model guessed
(verdicts with `title` for `claim`, confidence "low", evidence objects).
These pin the brief to its sources so it cannot drift from them.
"""
from __future__ import annotations

from fsr_playbooks.llm import tools as T
from fsr_playbooks.mcp_server.tools_emit import CARD_TYPES, VERDICT_DISPOSITIONS


def _brief() -> str:
    return T.TOOL_SCHEMA_OVERRIDES["emit_card"]["properties"]["payload"]["description"]


def test_card_type_enum_matches_the_routes():
    enum = T.TOOL_SCHEMA_OVERRIDES["emit_card"]["properties"]["card_type"]["enum"]
    assert set(enum) == set(CARD_TYPES)


def test_every_card_type_has_a_line():
    lines = {ln.split(":", 1)[0] for ln in _brief().splitlines()[1:]}
    assert lines == set(CARD_TYPES)


def test_verdict_line_carries_the_shapes_the_model_got_wrong():
    line = next(ln for ln in _brief().splitlines() if ln.startswith("verdict:"))
    assert "|".join(VERDICT_DISPOSITIONS) in line
    assert "confidence* (number 0.0-1.0)" in line
    assert "findings* [{claim*, evidence* [string]}]" in line


def test_a_card_without_a_schema_falls_back_to_its_signature():
    line = next(ln for ln in _brief().splitlines()
                if ln.startswith("enhancement_offer:"))
    assert "verified_id*" in line


def test_the_payload_is_still_only_typed_as_an_object():
    """Advertising, not validating: the emitters own the per-card refusals
    (a schema pre-check was tried and reverted, W2)."""
    payload = T.TOOL_SCHEMA_OVERRIDES["emit_card"]["properties"]["payload"]
    assert set(payload) == {"type", "description"}
