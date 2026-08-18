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


def test_an_extra_key_no_longer_costs_a_round_trip():
    """This used to refuse with bad_payload. It now emits the card and NAMES
    the key it could not hold: the model's repair dropped `chips` anyway, so
    the refusal only bought a wasted call (see the vocabulary tests below)."""
    r = emit_card("choice", {"id": "c1", "prompt": "pick",
                             "options": [{"label": "a", "value": "a"},
                                         {"label": "b", "value": "b"}],
                             "chips": True})
    assert r["ok"] is True and r["card"]["type"] == "choice_card"
    assert r["ignored_fields"] == ["chips"]


def test_bad_payload_keys_name_the_real_signature():
    """A payload MISSING a required field is still a refusal, and still says
    what the card takes -- that is the case the model cannot repair blind."""
    r = emit_card("choice", {"id": "c1"})
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


# ---------------------------------------------------------------------------
# The payload vocabulary the model actually reaches for.
#
# In the 2026-08-18 offline investigation sweep every one of the four fixtures
# that emitted a card had its FIRST emission refused and self-repaired on the
# second -- three `bad_payload`, one `bad_option`. That is a guaranteed wasted
# tool call and LLM round-trip on every carding turn, and the repaired call
# arrives at the same card minus the extra keys. The payloads below are copied
# verbatim from that run (run_ids 20260818T111122Z / 20260818T111405Z).
# ---------------------------------------------------------------------------

_REFUSED_ACTION_PAYLOAD = {
    "id": "block-108-17-204-5",
    "title": "Block malicious Tor exit node 108.17.204.5 on FortiGate",
    "description": "Stage containment of the external exfiltration endpoint.",
    "connector": "fortigate-firewall",
    "operation": "block_ip_new",
    "config": "",
    "params": {"method": "Quarantine Based", "ip_addresses": "108.17.204.5",
               "time_to_live": "6 Hour"},
    "target": {"type": "ip", "value": "108.17.204.5"},
    "severity": "High",
    "rationale": "Quarantine Based needs only the IP and a TTL.",
}

_REFUSED_CHOICE_PAYLOAD = {
    "id": "orders-erp-triage-followup",
    "prompt": "ORDERS-ERP triage verdict. How would you like to proceed?",
    "options": [
        {"id": "create_incident", "label": "Create ITOps Incident",
         "detail": "Link both alerts as one capacity issue."},
        {"id": "comment_and_close", "label": "Comment & Mark Resolved",
         "detail": "Document the correlation, then resolve."},
    ],
}


def test_action_payload_in_the_models_vocabulary_is_accepted():
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    r = emit_card("action", dict(_REFUSED_ACTION_PAYLOAD))
    assert r["ok"] is True, r
    card = r["card"]
    # `params` is what run_op takes, so the model writes `params` here too.
    assert card["args"] == _REFUSED_ACTION_PAYLOAD["params"]
    # `title` becomes the summary the card renders.
    assert card["summary"] == _REFUSED_ACTION_PAYLOAD["title"]


def test_an_action_card_defaults_to_editing_the_args_it_carries():
    """Omitting editable_fields must not cost a round-trip -- and the analyst
    has to be able to fix a wrong IP, which is the point of the card."""
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    r = emit_card("action", dict(_REFUSED_ACTION_PAYLOAD))
    assert set(r["card"]["editable_fields"]) == set(
        _REFUSED_ACTION_PAYLOAD["params"])


def test_keys_the_card_cannot_hold_are_dropped_but_named():
    """Dropping is not silent. The refusal path dropped these too, one
    round-trip later; saying so keeps that visible."""
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    r = emit_card("action", dict(_REFUSED_ACTION_PAYLOAD))
    assert r["ignored_fields"] == ["config", "description", "rationale",
                                   "severity", "target"]


def test_choice_options_in_the_models_vocabulary_are_accepted():
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    r = emit_card("choice", dict(_REFUSED_CHOICE_PAYLOAD))
    assert r["ok"] is True, r
    assert r["card"]["options"] == [
        {"label": "Create ITOps Incident", "value": "create_incident",
         "hint": "Link both alerts as one capacity issue."},
        {"label": "Comment & Mark Resolved", "value": "comment_and_close",
         "hint": "Document the correlation, then resolve."},
    ]


def test_a_payload_already_in_the_declared_vocabulary_is_untouched():
    """The normalizer only ever fills an ABSENT canonical key -- a correct
    payload must not be rewritten by it."""
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    r = emit_card("action", {
        "id": "a1", "connector": "c", "operation": "o", "summary": "real",
        "args": {"ip": "1.2.3.4"}, "editable_fields": ["ip"],
        "title": "decoy"})
    assert r["ok"] is True
    assert r["card"]["summary"] == "real"
    assert r["card"]["editable_fields"] == ["ip"]
    assert r["ignored_fields"] == ["title"]


def test_a_genuinely_unusable_payload_still_refuses():
    """Normalizing must not turn a real error into a half-built card."""
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    r = emit_card("action", {"title": "no connector, no operation"})
    assert r["ok"] is False


def test_the_run_op_dialect_action_payload_is_accepted():
    """The exact first-attempt payload a live approve turn sent (2026-08-18):
    run_op vocabulary (`op`/`params`/`title`), extra `step_name`, and no id.
    It was refused twice before the model converged; every attempt carried a
    complete, renderable card."""
    r = emit_card("action", {
        "connector": "fortigate-firewall", "op": "block_ip_new",
        "params": {"method": "Quarantine Based", "ip_addresses": "198.51.100.7",
                   "ip_type": "IPv4", "time_to_live": "Never", "duration": 0,
                   "ip_block_policy": "", "ip_group_name": ""},
        "step_name": "Block Malicious IP", "title": "Block IP Address"})
    assert r["ok"] is True, r
    card = r["card"]
    assert card["operation"] == "block_ip_new"
    assert card["args"]["ip_addresses"] == "198.51.100.7"
    assert card["summary"] == "Block IP Address"
    assert "step_name" in r.get("ignored_fields", [])


def test_a_missing_card_id_is_generated_not_refused():
    r = emit_card("action", {
        "connector": "fortigate-firewall", "operation": "block_ip_new",
        "args": {"method": "Quarantine Based", "ip_addresses": "198.51.100.7",
                 "ip_type": "IPv4", "time_to_live": "Never", "duration": 0,
                 "ip_block_policy": "", "ip_group_name": ""},
        "summary": "Block IP"})
    assert r["ok"] is True, r
    assert r["card"]["id"]
