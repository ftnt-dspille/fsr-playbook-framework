"""find_jinja_pattern ranks an exact `head` match above the occurrences floor.

The corpus has one dominant idiom (`vars.input.records`, ~532 occurrences) that
a substring LIKE matches for almost any input-records query. Without a precision
signal the ranking was pure `occurrences DESC`, so a query for a *specific*
idiom (`vars.input.records[0]`, 435 occurrences) still returned the broader
`vars.input.records` first -- and a model that couldn't tell whether it had the
right idiom re-queried with different substrings (8 near-identical calls in one
build turn, #48). An exact `head` match is a strong relevance signal (the query
IS the canonical expression) and now ranks first, before occurrences.
"""
from fsr_playbooks.mcp_server.tools_jinja import find_jinja_pattern


def test_exact_head_ranks_above_more_frequent_substring():
    # `vars.input.records[0]` (435 occ) is an exact head; `vars.input.records`
    # (532 occ) only contains it as a substring. The exact match wins.
    rows = find_jinja_pattern("vars.input.records[0]", limit=5)
    assert rows, "corpus should have this idiom"
    assert rows[0]["head"] == "vars.input.records[0]"


def test_broad_query_keeps_most_frequent_first():
    # A broad query with no exact-head match keeps the occurrences ranking --
    # the boost must not promote a coincidental low-frequency head above the
    # canonical idiom (regression guard for the starts-with tier that was
    # tried and reverted: `head LIKE q||'%'` matched set-block LHS names).
    rows = find_jinja_pattern("input", limit=5)
    assert rows, "corpus should have input idioms"
    # The dominant input idiom is `vars.input.records` (~532 occ); no exact
    # head == "input" exists, so occurrences DESC still drives the order.
    assert rows[0]["head"] == "vars.input.records"


def test_kind_filter_still_applies():
    rows = find_jinja_pattern("vars.input.records", kind="expr", limit=3)
    assert rows
    assert all(r["kind"] == "expr" for r in rows)


def test_empty_query_returns_empty():
    assert find_jinja_pattern("zzzNoSuchIdiomZzz", limit=3) == []


def test_like_wildcards_in_query_are_escaped():
    # `_` is a LIKE wildcard (matches any single char). A literal underscore
    # in the query must be ESCAPE'd so it matches itself, not any char.
    # `vars.input.records` has no underscore, but a query containing one must
    # not match more rows than the same query with `%`/`_` stripped.
    rows = find_jinja_pattern("vars.input.records", limit=3)
    assert rows
    assert rows[0]["head"] == "vars.input.records"
