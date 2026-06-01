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

from fsr_core.llm.tools import _DB_PATH, _op_presence, _tier_for_run_op
from fsr_core.mcp_server.tools_triage import _is_enrichment_op, _TARGET_KEYWORDS


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


# --- Fix #2: enrichment-op classifier ---------------------------------------

IP_KW = _TARGET_KEYWORDS["ip"]


@pytest.mark.parametrize("op", [
    "query_ip", "get_ip_reputation", "search_ip", "ioc_search",
    "file_reputation",
])
def test_keeps_real_intel_lookups(op):
    assert _is_enrichment_op(op, "", IP_KW)


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
    assert not _is_enrichment_op(op, "", IP_KW)


def test_no_target_requires_intel_token():
    """With no target_type, only clearly-intel ops qualify (keeps the result
    bounded instead of returning every read op)."""
    assert _is_enrichment_op("get_ip_reputation", "", None)   # has 'reputation'
    assert not _is_enrichment_op("search_ip", "", None)       # type-only match


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
        assert _is_enrichment_op("query_ip", (ops["query_ip"] or "").lower(), IP_KW)
    if "ip_re_analyze" in ops:
        assert not _is_enrichment_op(
            "ip_re_analyze", (ops["ip_re_analyze"] or "").lower(), IP_KW)
