"""find_connector must search EVERY word of a multi-word query, not just the first.

Live-caught by the S3 build-persona eval (0/5). The ask named the connector the
way a human would — "FortiSOAR Utilities" — but the right answer is
`cyops_utilities`, whose label is exactly "Utilities".

The old implementation:

    rows = <whole-phrase LIKE>
    if not rows:
        w = q.split()[0]          # ← only the FIRST word ever searched
        rows = <LIKE on w>

"FortiSOAR Utilities" got zero whole-phrase hits, broadened on "FortiSOAR"
alone, and returned `fortisoar-ml-engine` — a confident WRONG match, with the
one word that would have found the right connector never searched. The build
model then correctly reported "only FortiSOAR ML Engine is found similarly
named" and declined to author: a right answer to a wrong tool result.

Two defects, both covered here:
  1. only `words[0]` was searched;
  2. broadening ran only `if not rows`, so a single spurious whole-phrase hit
     suppressed it — one bad hit was worse than no hits.
"""
import pytest

from fsr_playbooks.mcp_server.tools_discovery import find_connector


def _names(q, **kw):
    return [m["name"] for m in (find_connector(q, **kw).get("matches") or [])]


def test_multiword_query_finds_connector_matched_by_a_later_word():
    """THE regression. Goes red on the words[0]-only implementation."""
    names = _names("FortiSOAR Utilities")
    assert "cyops_utilities" in names, (
        "'Utilities' is the SECOND word and the only one that matches "
        f"cyops_utilities (label 'Utilities'); got {names}"
    )


def test_later_word_match_survives_a_spurious_earlier_hit():
    """Defect 2: broadening must not be suppressed by an unrelated first hit.

    Catalog-independent on purpose: the full catalog and the slim test catalog
    hold different connectors, so this asserts the *relationship* (an
    earlier-word hit does not suppress a later-word hit) rather than naming the
    earlier-word connector.
    """
    first_word_hits = _names("FortiSOAR")
    if not first_word_hits:
        pytest.skip("this catalog has no 'FortiSOAR' match — nothing to suppress")
    names = _names("FortiSOAR Utilities")
    assert "cyops_utilities" in names, (
        f"a first-word hit ({first_word_hits}) must not suppress later words; got {names}"
    )


def test_single_word_and_exact_queries_are_unregressed():
    assert "cyops_utilities" in _names("cyops_utilities")
    assert "cyops_utilities" in _names("Utilities")


def test_short_words_do_not_drag_in_the_whole_catalog():
    """Noise words ('to', 'of') are skipped — otherwise a natural-language ask
    would substring-match nearly everything and bury the real answer.

    Asserted structurally: every result must be attributable to one of the
    query's >2-char words. If 'to' were searched, connectors matching only 'to'
    (which is a substring of a great many names) would appear.
    """
    phrase = set(_names("Convert String Time to Minutes", limit=50))
    attributable = set()
    for w in ("Convert", "String", "Time", "Minutes"):
        attributable |= set(_names(w, limit=50))
    assert phrase <= attributable, (
        "results not attributable to any >2-char query word — a short word "
        f"leaked into the search: {phrase - attributable}"
    )


def test_limit_is_respected_across_the_word_union():
    for lim in (1, 3, 5):
        assert len(_names("FortiSOAR Utilities", limit=lim)) <= lim


def test_true_miss_still_returns_a_suggestion():
    # Every token must be absent from the catalog. NB: ordinary-looking words
    # like "connector" ARE catalog tokens (connector-fsr-soc-assistant), and
    # now that every word is searched they legitimately match — so a "miss"
    # query has to avoid them.
    r = find_connector("zzqqx wibblefrotz plughxyzzy")
    assert not (r.get("matches") or [])
    assert r.get("suggestion"), "a genuine zero-hit must still guide the agent"


def test_whole_phrase_matches_outrank_single_word_matches():
    """Union order matters: broadening appends, so the stronger whole-phrase
    signal stays at the top and word-level noise cannot bury it."""
    names = _names("cyops_utilities Utilities")
    assert names[0] == "cyops_utilities", (
        f"the whole-phrase/exact match must lead, got {names}"
    )
