"""Risk classification for run_op's confirm gate (`_op_risk`).

Regression: `ioc_search` (category 'investigation') resolved to 'unknown' and
was needlessly gated as requires_confirmation during a live triage run, even
though find_enrichment_actions had surfaced it as a tier<=2 read-only action.
A safe category must resolve to 'safe' so the gate agrees with the dispatch
tier model — while destructive name/category signals still win.
"""
from fsr_playbooks.mcp_server.tools_discovery import _op_risk


def test_safe_name_prefix_is_safe():
    assert _op_risk("get_ip_context", None) == "safe"
    assert _op_risk("search_events", "investigation") == "safe"


def test_investigation_category_without_safe_prefix_is_safe():
    # The regression case: name has no safe prefix, category is investigation.
    assert _op_risk("ioc_search", "investigation") == "safe"


def test_other_safe_categories_are_safe():
    assert _op_risk("ioc_search", "enrichment") == "safe"
    assert _op_risk("reputation", "query") == "safe"
    assert _op_risk("anything", "utilities") == "safe"
    assert _op_risk("anything", "verification") == "safe"


def test_destructive_category_still_destructive():
    assert _op_risk("apply_policy", "remediation") == "destructive"
    assert _op_risk("update_record", "management") == "destructive"


def test_destructive_name_wins_over_safe_category():
    # A block_* op miscategorised as investigation must stay destructive.
    assert _op_risk("block_ip", "investigation") == "destructive"


def test_unknown_when_no_signal():
    assert _op_risk("frobnicate", None) == "unknown"
    assert _op_risk("frobnicate", "mystery") == "unknown"


def test_case_insensitive_category():
    assert _op_risk("ioc_search", "Investigation") == "safe"
    assert _op_risk("apply_policy", "Remediation") == "destructive"


# --- read-only name substrings (lookup verbs not at the prefix) -------------

def test_lookup_substrings_are_safe_without_category():
    # The user's case: ioc_search is a lookup even with no category at all.
    assert _op_risk("ioc_search", None) == "safe"
    assert _op_risk("domain_lookup", None) == "safe"
    assert _op_risk("ip_reputation", None) == "safe"
    assert _op_risk("entity_enrich", None) == "safe"


# --- HTTP passthrough ops classified by method ------------------------------

def test_get_execute_api_request_is_safe():
    assert _op_risk("execute_api_request", None, {"method": "GET"}) == "safe"
    assert _op_risk("execute_api_request", None, {"method": "get"}) == "safe"
    assert _op_risk("execute_api_request", None, {"method": "HEAD"}) == "safe"


def test_mutating_or_unspecified_execute_api_request_stays_gated():
    # POST/PUT/PATCH or no method → unknown, so run_op's confirm gate fires (HITL).
    assert _op_risk("execute_api_request", None, {"method": "POST"}) == "unknown"
    assert _op_risk("execute_api_request", None, {"method": "PUT"}) == "unknown"
    assert _op_risk("execute_api_request", None, {}) == "unknown"
    assert _op_risk("execute_api_request", None, None) == "unknown"


def test_delete_execute_api_request_is_destructive():
    assert _op_risk("execute_api_request", None, {"method": "DELETE"}) == "destructive"


def test_other_passthrough_op_names_method_aware():
    assert _op_risk("make_rest_call", None, {"method": "GET"}) == "safe"
    assert _op_risk("make_rest_call", None, {"method": "POST"}) == "unknown"


def test_safe_prefix_still_wins_over_incidental_destructive_substring():
    # `get_close_events` is a read despite containing 'close_'.
    assert _op_risk("get_close_events", None) == "safe"


# ───────── the host family must mean the same thing in both classifiers ─────────

def test_edr_collector_inventory_is_host_enrichment():
    """Regression (GA demo): FortiEDR's `get_collector_list` was invisible to
    find_enrichment_actions because `collector`/`agent` were in the CONTAINMENT
    keyword list but missing from the ENRICHMENT indicator tokens. An
    investigation therefore could not ask "does this host even have an EDR
    agent?", and the host's absence from EDR only surfaced when the containment
    action failed at execution time with a 400."""
    from fsr_playbooks.mcp_server.tools_connector_discovery import (
        _INDICATOR_TOKENS, _TARGET_KEYWORDS, _is_enrichment_op)

    assert _is_enrichment_op("get_collector_list", "get collector list", "host")
    assert _is_enrichment_op("get_collector_list", "get collector list", "endpoint")
    assert _is_enrichment_op("get_agent_group", "get agent groups", "host")
    # A collector op is NOT an IP enrichment — it names a different indicator.
    assert not _is_enrichment_op("get_collector_list", "get collector list", "ip")
    # ...but widening the host family must not drag in mutations or self-plumbing.
    assert not _is_enrichment_op("move_collectors", "move collectors", "host")
    assert not _is_enrichment_op("list_agent_tools", "list agent tools", "host")

    # The two lists may diverge elsewhere on purpose (ip drops address/blacklist),
    # but every host/endpoint term the containment finder knows must be here too.
    for target in ("host", "endpoint"):
        missing = set(_TARGET_KEYWORDS[target]) - set(_INDICATOR_TOKENS[target])
        assert not missing, f"{target} tokens drifted: {missing}"


def test_isolate_is_never_offered_as_enrichment():
    """`isolate_collector` matches the host name heuristic, so only the tier
    guard keeps a containment op out of the enrichment list. Pin that."""
    from fsr_playbooks.mcp_server.tools_connector_discovery import _is_enrichment_op
    from fsr_playbooks.llm.tools import _tier_for_run_op

    assert _is_enrichment_op("isolate_collector", "isolate collector", "host")
    assert _tier_for_run_op(
        {"connector": "fortinet-fortiedr", "op": "isolate_collector"}) > 2
