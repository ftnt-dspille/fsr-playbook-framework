"""The consolidated `emit_card` routes to the right emitter (Phase 1).

Box-free: the constituents' own runtime validation is the contract, so these
pin only the ROUTING behavior -- card_type vocabulary, payload delegation,
actionable bad-payload errors, and (load-bearing) that the read-only-turn
refusal cannot be sidestepped by reaching a frontier card through emit_card.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import emit_card
from fsr_playbooks.mcp_server.tools_emit import CARD_TYPES


def test_unknown_card_type_names_the_vocabulary():
    r = emit_card("banner", {})
    assert r["ok"] is False and r["code"] == "unknown_card_type"
    assert "choice" in r["suggestions"][0]


def test_choice_payload_renders_the_card():
    r = emit_card("choice", {
        "id": "c1", "prompt": "Contain now or build a playbook?",
        "options": [{"label": "Contain", "value": "contain"},
                    {"label": "Build", "value": "build"}]})
    assert r["ok"] is True
    assert r["card"]["type"] == "choice_card" and r["card_type"] == "choice"


def test_constituent_validation_errors_pass_through():
    r = emit_card("choice", {"id": "c1", "prompt": "pick", "options": []})
    assert r["ok"] is False and r["code"] == "too_few_options"


def test_bad_payload_keys_name_the_real_signature():
    r = emit_card("choice", {"id": "c1", "prompt": "pick",
                             "options": [{"label": "a", "value": "a"},
                                         {"label": "b", "value": "b"}],
                             "chips": True})
    assert r["ok"] is False and r["code"] == "bad_payload"
    assert "emit_choice_card takes:" in r["suggestions"][0]


def test_every_card_type_resolves_to_a_registered_emitter():
    import fsr_playbooks.mcp_server as pkg
    for fn_name in CARD_TYPES.values():
        assert callable(getattr(pkg, fn_name))


def test_emit_card_is_in_the_llm_registry_with_the_enum_schema():
    from fsr_playbooks.llm.tools import REGISTRY, SAFE_TOOLS, TOOL_TIERS
    assert "emit_card" in SAFE_TOOLS and TOOL_TIERS["emit_card"] == 0
    spec = REGISTRY["emit_card"]
    kinds = spec.input_schema["properties"]["card_type"]["enum"]
    assert set(kinds) == set(CARD_TYPES)
    assert "Which card_type to pick" in spec.description


def test_read_only_turn_refuses_frontier_card_types():
    from fsr_playbooks.llm import tools as llm_tools
    tok = llm_tools.set_read_only_turn(True)
    try:
        r = llm_tools.dispatch("emit_card", {
            "card_type": "enhancement_offer",
            "payload": {"id": "e1", "summary": "s", "verified_id": "v1"}})
        assert r["ok"] is False and r["code"] == "read_only_turn"
    finally:
        llm_tools.reset_read_only_turn(tok)


def test_read_only_turn_still_allows_non_frontier_cards():
    from fsr_playbooks.llm import tools as llm_tools
    tok = llm_tools.set_read_only_turn(True)
    try:
        r = llm_tools.dispatch("emit_card", {
            "card_type": "choice",
            "payload": {"id": "c1", "prompt": "pick",
                        "options": [{"label": "a", "value": "a"},
                                    {"label": "b", "value": "b"}]}})
        assert r["ok"] is True and r["card"]["type"] == "choice_card"
    finally:
        llm_tools.reset_read_only_turn(tok)


def test_every_advertised_tool_declares_its_approval_behavior():
    """Assessment Phase 1.4: approval is a plan, not a surprise. The line is
    stamped in build_registry from TOOL_TIERS, so drift is impossible -- this
    pins that the stamp exists and matches dispatch for the frontier cases."""
    from fsr_playbooks.llm.tools import REGISTRY
    for spec in REGISTRY.values():
        assert spec.description.splitlines()[-1].startswith("Approval: "), \
            spec.name
    assert "always suspends" in REGISTRY["push_playbook"].description
    assert "auto-runs" in REGISTRY["find"].description.splitlines()[-1]
