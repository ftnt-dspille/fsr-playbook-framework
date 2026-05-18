"""Tests for tools_catalog (Phase 0 + 0.5 of CONNECTOR_INTEGRATION_PLAN).

These tests run against the live attached catalog when present. If
the catalog is missing they assert the graceful-degrade envelope
instead — the tools must NEVER throw.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from probes.common import CATALOG_DB_PATH  # noqa: E402
from mcp_server.tools_catalog import (  # noqa: E402
    find_api_example,
    find_api_fixture,
    find_api_product,
    propose_http_fallback,
    _METHOD_TO_HTTP_OP,
    _looks_like_api_call_op,
    _render_fallback_step,
    _split_url_template,
)


CATALOG_PRESENT = CATALOG_DB_PATH.exists()
catalog_required = pytest.mark.skipif(
    not CATALOG_PRESENT,
    reason=f"catalog.sqlite not at {CATALOG_DB_PATH}",
)


# ---------------------------------------------------------------------------
# Pure-Python helpers (run without the catalog).
# ---------------------------------------------------------------------------


def test_method_to_op_covers_all_http_verbs():
    for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        assert verb in _METHOD_TO_HTTP_OP
        assert _METHOD_TO_HTTP_OP[verb].startswith("http_")


def test_looks_like_api_call_op_matches_variants():
    for name in ("api_call", "generic_api_call", "raw_api",
                 "make_http_request", "execute_api_call_v2"):
        assert _looks_like_api_call_op(name), name
    for name in ("get_user", "block_ip", "list_records"):
        assert not _looks_like_api_call_op(name), name


def test_split_url_template_handles_absolute_and_relative():
    base, path = _split_url_template("https://api.example.com/v1/foo?x=1")
    assert base == "https://api.example.com"
    assert path == "/v1/foo?x=1"
    base, path = _split_url_template("/v1/foo")
    assert base == ""
    assert path == "/v1/foo"


def test_render_fallback_step_post_with_bearer_emits_warnings():
    fixture = {
        "method": "POST",
        "url_template": "https://api.akamai.example/v1/networklists",
        "auth_method": "bearer",
        "confidence": "high",
        "request_body": {"name": "block_list", "list": ["{ip}"]},
        "query_params": None,
    }
    step, warnings = _render_fallback_step(fixture, step_name="Block Url")
    assert step["type"] == "connector"
    assert step["connector"] == "http"
    assert step["op"] == "http_post"
    params = step["arguments"]["params"]
    assert "rest_api" in params
    assert "header" in params
    assert "Authorization" in params["header"]
    assert "Bearer" in params["header"]["Authorization"]
    assert "data" in params  # POST got the body
    # warnings should mention base URL + bearer
    joined = " ".join(warnings).lower()
    assert "base url" in joined or "vendor_base_url" in joined
    assert "bearer" in joined or "token" in joined


def test_render_fallback_step_get_no_body():
    fixture = {
        "method": "GET",
        "url_template": "/v1/users",
        "auth_method": "apikey",
        "confidence": "high",
    }
    step, warnings = _render_fallback_step(fixture, step_name="Get Users")
    assert step["op"] == "http_get"
    params = step["arguments"]["params"]
    assert "data" not in params  # no body on GET
    assert "X-Api-Key" in params["header"]


# ---------------------------------------------------------------------------
# Catalog-backed lookups (skip when catalog absent).
# ---------------------------------------------------------------------------


@catalog_required
def test_find_api_product_returns_hits_for_known_vendor():
    out = find_api_product("servicenow", limit=3)
    assert "matches" in out
    assert any("servicenow" in m["normalized"].lower()
               for m in out["matches"]), out


@catalog_required
def test_find_api_product_fuzzy_suggestion_on_typo():
    out = find_api_product("servicenoww", limit=3)
    # Either matches via LIKE substring or returns a near-list.
    assert out.get("matches") or out.get("near"), out


@catalog_required
def test_find_api_example_returns_entries():
    out = find_api_example("jira", q="get issue", limit=3)
    assert "matches" in out
    # Slim mode: no description in slim rows
    if out["matches"]:
        assert "description" not in out["matches"][0]


@catalog_required
def test_find_api_example_verbose_includes_description():
    out = find_api_example("jira", q="get issue", limit=1, verbose=True)
    if out.get("matches"):
        keys = out["matches"][0].keys()
        # description is one of the verbose-only columns; it should be
        # present even if NULL.
        assert "description" in keys


@catalog_required
def test_find_api_fixture_high_confidence_first():
    out = find_api_fixture("jira", method="GET", limit=3)
    assert "matches" in out
    if len(out["matches"]) >= 2:
        # Confidence ordering: high < medium < low (we sort ascending).
        order_map = {"high": 0, "medium": 1, "low": 2}
        scores = [order_map.get(m.get("confidence"), 3)
                  for m in out["matches"]]
        assert scores == sorted(scores), scores


# ---------------------------------------------------------------------------
# propose_http_fallback decision tree
# ---------------------------------------------------------------------------


def test_propose_http_fallback_missing_args():
    out = propose_http_fallback("", "block url")
    assert out.get("ok") is False
    assert out["code"] == "missing_args"


@catalog_required
def test_propose_http_fallback_picks_native_when_available():
    # virustotal has a get_ip_reputation op (or similar) in the FSR
    # reference store — the native branch should win.
    out = propose_http_fallback("virustotal", "ip reputation")
    if out.get("ok") is True and out["decision"] == "native_op":
        assert out["step"]["connector"] == "virustotal"
        assert out["step"]["op"]
    # If virustotal isn't in this tenant's store, we still must not throw.
    else:
        assert out["decision"] in ("api_call", "http_fixture",
                                   "no_grounded_shape")


@catalog_required
def test_propose_http_fallback_returns_http_step_when_no_native():
    # Made-up intent for a real catalog vendor — should land on
    # http_fixture or no_grounded_shape, not throw.
    out = propose_http_fallback("akamai", "block url")
    assert out.get("ok") is True or out.get("code") == "no_grounded_shape"
    if out.get("ok"):
        assert out["decision"] in ("native_op", "api_call",
                                   "http_fixture")
        if out["decision"] == "http_fixture":
            assert out["step"]["connector"] == "http"
            assert out["step"]["op"].startswith("http_")
            assert out.get("fixture")
            assert isinstance(out.get("warnings"), list)
            # auth must be flagged somehow
            assert out["warnings"], "fallback must emit at least one warning"
