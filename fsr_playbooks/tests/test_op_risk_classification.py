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
