"""Regression tests for the two framework fixes that came out of the
investigation-calibration run (3/5 → diagnose):

  Fix #1 — `_tier_for_run_op` must NOT escalate a guessed/mistyped op to
  human approval. A non-existent op on a *known* connector can't run, so it
  should dispatch (tier 1) and let `run_op` self-correct with
  `unknown_operation` — instead of suspending the hunt behind an approval
  prompt (the c2 failure: a guessed `virustotal.ip_reputation` halted the run
  before the deliverable card could be staged).

  Fix #2 — `_is_enrichment_op` selects indicator-lookup ops (the read-side
  mirror of the containment classifier) without an op-name allow-list, so it
  generalizes to any connector: keep reputation/query/IOC lookups, drop the
  write-ish `re_analyze` / `upload` / `scan` and schema/widget plumbing that
  share the catch-all `investigation` category.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks.llm.tools import _DB_PATH, _op_presence, _tier_for_run_op
from fsr_playbooks.mcp_server.tools_connector_discovery import (
    _enrich_connector_rank,
    _is_enrichment_op,
)


# --- Fix #1: tier resolution for guessed vs. real ops -----------------------

requires_db = pytest.mark.skipif(
    not _DB_PATH.exists(), reason="reference DB not present")


@requires_db
def test_guessed_op_on_known_connector_does_not_escalate():
    """A mistyped op on a connector we have a catalog for stays tier 1 so it
    dispatches to a self-correcting unknown_operation, not an approval halt."""
    # `virustotal` is in the catalog; `ip_reputation` is not a real op (the
    # exact c2 guess — the real op is `query_ip`).
    assert _op_presence("virustotal", "ip_reputation") == (False, True)
    assert _tier_for_run_op({"connector": "virustotal", "op": "ip_reputation"}) == 1


@requires_db
def test_real_safe_lookup_is_autoallowed():
    assert _tier_for_run_op({"connector": "virustotal", "op": "query_ip"}) <= 2


@requires_db
def test_unknown_connector_stays_conservative():
    """No catalog for the connector → we can't prove the op is bogus, so it
    must keep escalating to approval (could be a real mutating op)."""
    assert _op_presence("totally-unknown-conn-xyz", "foo") == (False, False)
    assert _tier_for_run_op(
        {"connector": "totally-unknown-conn-xyz", "op": "foo"}) == 3


# --- Fix #3: probe-flagged unsafe ops win over the catch-all category -------
#
# FortiEDR's host-containment ops (`isolate_collector`, `set_collector_state`)
# carry the catalog category `investigation` but are flagged `unsafe` in
# op_safety. The category-first ordering used to downgrade them to tier 2
# (auto-allow, no approval card) and they were dropped from
# find_containment_actions' tier>=3 guard — so "isolate this host" would run
# ungated. An `unsafe` safety verdict must escalate to tier 4 regardless of a
# catch-all category.


@requires_db
def test_unsafe_op_with_investigation_category_escalates_to_tier_4():
    # isolate_collector: op_safety='unsafe', operations.category='investigation'.
    assert _tier_for_run_op(
        {"connector": "fortinet-fortiedr", "op": "isolate_collector"}) == 4


@requires_db
def test_safe_fortiedr_reads_stay_auto_allowed():
    # Read ops on the same connector must NOT be swept up by the fix.
    for op in ("search_ioc", "get_collector_list", "get_event_list"):
        assert _tier_for_run_op(
            {"connector": "fortinet-fortiedr", "op": op}) <= 2


# --- Fix #2: enrichment-op classifier (target = indicator type string) ------


@pytest.mark.parametrize("op", [
    "query_ip", "get_ip_reputation", "search_ip", "ioc_search",
    "get_ip_context", "get_reputation",
])
def test_keeps_real_intel_lookups(op):
    assert _is_enrichment_op(op, "", "ip")


@pytest.mark.parametrize("op", [
    "ip_re_analyze",        # re-scan, not a lookup
    "upload_sample",        # submission
    "scan_url",             # submission
    "get_output_schema_ip",  # schema plumbing
    "get_widget_html_content",
    "execute_an_api_request",
    "custom_endpoint",
])
def test_drops_writeish_and_plumbing_ops(op):
    assert not _is_enrichment_op(op, "", "ip")


@pytest.mark.parametrize("op", [
    "get_domain_reputation",   # TRIAGE_BUILD_AUDIT B1: wrong indicator for ip
    "get_url_reputation",
    "get_file_reputation",
    "get_addresses",           # firewall address-objects, not IP intel
])
def test_drops_wrong_indicator_and_config_reads_for_ip(op):
    assert not _is_enrichment_op(op, "", "ip")


def test_epss_score_dropped_after_score_token_removed():
    # `score` is no longer an intel token, so EPSS scoring isn't enrichment.
    assert not _is_enrichment_op(
        "exploit_prediction", "epss score for a cve", "ip")


def test_no_target_requires_intel_token():
    """With no target_type, only clearly-intel ops qualify (keeps the result
    bounded instead of returning every read op)."""
    assert _is_enrichment_op("get_ip_reputation", "", None)   # has 'reputation'
    assert not _is_enrichment_op("search_ip", "", None)       # type-only match


# --- B2: connector preference ranking ---------------------------------------

def test_preferred_connectors_rank_above_alienvault():
    for c in ("virustotal", "fortiguard", "shodan", "ipqualityscore"):
        assert _enrich_connector_rank(c) < _enrich_connector_rank("alienvault-otx")


def test_unknown_connector_lands_mid_band():
    r = _enrich_connector_rank("some-unknown-connector")
    assert _enrich_connector_rank("virustotal") < r < _enrich_connector_rank("alienvault-otx")


@requires_db
def test_classifier_matches_db_shape():
    """Smoke test against the real catalog: VT's classified-safe lookups all
    pass, its re-analyze/upload ops all fail — no allow-list involved."""
    con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
    try:
        ops = {op: title for op, title in con.execute(
            "SELECT op_name, title FROM operations WHERE connector_name='virustotal'")}
    finally:
        con.close()
    if "query_ip" in ops:
        assert _is_enrichment_op("query_ip", (ops["query_ip"] or "").lower(), "ip")
    if "ip_re_analyze" in ops:
        assert not _is_enrichment_op(
            "ip_re_analyze", (ops["ip_re_analyze"] or "").lower(), "ip")
