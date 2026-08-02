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
import pytest

from fsr_playbooks.mcp_server.tools_jinja import find_jinja_pattern

# Every ranking assertion below names a real idiom, so it needs the mined
# corpus -- which the slim DB shipped to CI does not carry. Probe once for ANY
# expression rather than for the specific idiom: keyed to the specific one, a
# genuine ranking regression would present as "corpus absent" and skip itself
# green. Empty corpus -> skip; present corpus -> every assertion must hold.
def _corpus_present() -> bool:
    """True only when the probe returned a REAL row.

    `bool(rows)` was enough until `find_jinja_pattern` started answering a miss
    with a one-element `no_match` sentinel instead of `[]` (so a model gets told
    what was searched rather than a bare empty list). That sentinel is truthy,
    so on CI -- whose slim DB carries no corpus -- the guard read "corpus
    present", every assertion ran, and all six died on `KeyError: 'head'`. The
    guard has to key on the sentinel, not on emptiness.
    """
    rows = find_jinja_pattern("vars", limit=1)
    return bool(rows) and not rows[0].get("no_match")


_HAS_CORPUS = _corpus_present()
needs_corpus = pytest.mark.skipif(
    not _HAS_CORPUS, reason="jinja corpus absent from the slim reference DB")


@needs_corpus
def test_exact_head_ranks_above_more_frequent_substring():
    # `vars.input.records[0]` (435 occ) is an exact head; `vars.input.records`
    # (532 occ) only contains it as a substring. The exact match wins.
    rows = find_jinja_pattern("vars.input.records[0]", limit=5)
    assert rows, "corpus should have this idiom"
    assert rows[0]["head"] == "vars.input.records[0]"


@needs_corpus
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


@needs_corpus
def test_kind_filter_still_applies():
    rows = find_jinja_pattern("vars.input.records", kind="expr", limit=3)
    assert rows
    assert all(r["kind"] == "expr" for r in rows)


def test_a_query_that_matches_nothing_says_so_instead_of_returning_bare_empty():
    """A bare `[]` reads as "there is no such idiom", so the model rephrases
    and asks again -- the #48 loop. Say what was searched instead."""
    rows = find_jinja_pattern("zzzNoSuchIdiomZzz", limit=3)
    assert len(rows) == 1 and rows[0]["no_match"] is True
    assert "zzzNoSuchIdiomZzz" in rows[0]["note"]
    assert "find_jinja_filter" in rows[0]["note"], (
        "must name the one thing a BLOCK search structurally cannot find")


@needs_corpus
def test_a_prose_query_falls_back_to_token_matching():
    """The #48 diagnosis: whole-string LIKE can only match a query that is
    already Jinja text, so a question asked in words matched nothing 7 times
    out of 11 and the model just rephrased it."""
    rows = find_jinja_pattern("for record in vars.steps.find", limit=3)
    assert rows and not rows[0].get("no_match")
    assert any("for record in" in r["raw"] for r in rows)


def test_one_accidental_token_hit_is_not_an_answer():
    """`here` is inside `where`. A 3+-word query needs two tokens, or the
    model chases a coincidence."""
    rows = find_jinja_pattern("zzzz nothing here", limit=3)
    assert len(rows) == 1 and rows[0]["no_match"] is True


@needs_corpus
def test_like_wildcards_in_query_are_escaped():
    # `_` is a LIKE wildcard (matches any single char). A literal underscore
    # in the query must be ESCAPE'd so it matches itself, not any char.
    # `vars.input.records` has no underscore, but a query containing one must
    # not match more rows than the same query with `%`/`_` stripped.
    rows = find_jinja_pattern("vars.input.records", limit=3)
    assert rows
    assert rows[0]["head"] == "vars.input.records"


@needs_corpus
def test_exact_head_boost_fires_for_underscore_query():
    # `head = ?` is an equality, not LIKE -- so it must bind the RAW query,
    # not the LIKE-escaped form. A query containing `_` (a LIKE wildcard)
    # like `vars.indicator_value` must still rank its exact head first:
    # binding the escaped `vars.indicator\_value` would match no head (the
    # backslash is literal in `=`), and a boost that silently never fires
    # for every `_`/`%` query looks exactly like "no exact hit".
    q = "vars.indicator_value"
    rows = find_jinja_pattern(q, limit=5)
    assert rows, "corpus should have this idiom"
    assert rows[0]["head"] == q, "exact head match must rank first"
