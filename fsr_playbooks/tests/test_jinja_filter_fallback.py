"""find_jinja_filter must never return a bare [] (AGENT_HARDENING_PLAN §H).

On a corpus miss it falls back to the authoritative name catalog — the same
jinja2∪FSR∪Ansible set ``validate_yaml`` checks against (§G) — so discovery
and validation can no longer disagree about whether a filter exists.
"""
from fsr_playbooks.mcp_server.tools_jinja import _catalog_fallback


def test_exact_name_found_in_catalog():
    rows = _catalog_fallback("json_query", limit=5)
    assert any(r["name"] == "json_query" for r in rows)
    assert all(r["source"] == "catalog" for r in rows)


def test_substring_match():
    rows = _catalog_fallback("nice_json", limit=10)
    assert any(r["name"] == "to_nice_json" for r in rows)


def test_typo_gets_near_match_not_empty():
    rows = _catalog_fallback("ternery", limit=5)
    assert rows, "fallback must not return []"
    assert any(r["name"] == "ternary" for r in rows)


def test_limit_respected():
    assert len(_catalog_fallback("to", limit=3)) <= 3
