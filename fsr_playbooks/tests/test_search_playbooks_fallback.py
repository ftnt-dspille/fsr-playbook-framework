"""search_playbooks answers a question asked in prose, and never returns [].

The old shape was a whole-string LIKE over playbook names, which only ever
matches a query that is already a playbook NAME. A model asks "phishing email
triage" or "block ip on firewall", the 1,600-playbook corpus that certainly
contains the pattern answers `[]`, and that reads as "nobody does this" -- so
the model either rephrases (the search loop) or tells the user the pattern is
unsupported. Same failure and same fix as find_jinja_pattern: match per token,
rank by how many distinct tokens a row hits, and when there is genuinely
nothing, say what the corpus holds instead of handing back an empty list
(AGENT_HARDENING_PLAN §H).
"""
import pytest

from fsr_playbooks.mcp_server.tools_corpus import search_playbooks

_search = search_playbooks.fn if hasattr(search_playbooks, "fn") \
    else search_playbooks

# The mined corpus is not in the slim DB shipped to CI. Probe for ANY row
# rather than for a specific playbook: keyed to a specific one, a real
# regression would present as "corpus absent" and skip itself green.
_HAS_CORPUS = not _search("a", limit=1)[0].get("no_match", False)
needs_corpus = pytest.mark.skipif(
    not _HAS_CORPUS, reason="playbook corpus absent from the slim reference DB")


@needs_corpus
def test_exact_substring_still_wins_unannotated():
    """The literal path is unchanged -- a name match is not a "fallback" and
    must not carry the fallback's explanatory note."""
    rows = _search("phishing", limit=5)
    assert rows and not rows[0].get("no_match")
    assert "match" not in rows[0], "a verbatim hit must not be labelled tokens"


@needs_corpus
def test_prose_query_finds_playbooks_the_literal_search_missed():
    rows = _search("phishing email triage", limit=5)
    assert rows and not rows[0].get("no_match"), \
        "a prose query must not dead-end on a corpus that has the pattern"
    assert rows[0]["match"] == "tokens"
    assert rows[0]["matched_tokens"] >= 2
    assert "Phishing" in rows[0]["workflow"]


@needs_corpus
def test_token_ranking_puts_the_best_match_first():
    rows = _search("block ip on firewall", limit=5)
    scores = [r["matched_tokens"] for r in rows]
    assert scores == sorted(scores, reverse=True)


@needs_corpus
def test_the_explanatory_note_is_not_repeated_per_row():
    """A 20-word note on every row triples a payload whose rows are two
    short strings each, and says nothing new on row 7."""
    rows = _search("block ip on firewall", limit=10)
    assert sum(1 for r in rows if "note" in r) <= 1


def test_a_genuine_miss_names_the_tool_that_can_answer():
    rows = _search("zzzq nonexistent qqzz", limit=5)
    assert len(rows) == 1 and rows[0]["no_match"] is True
    note = rows[0]["note"]
    # The corpus indexes NAMES; a "what does this playbook do" question
    # belongs to a different tool, and the miss has to say so or the model
    # just asks this one again.
    assert "find_recipe" in note
    assert rows[0]["searched_tokens"]


def test_wildcards_in_the_query_are_matched_literally():
    """An unescaped `%` makes LIKE match everything, so a junk query would
    return the whole corpus and read as a hit."""
    rows = _search("%", limit=5)
    assert rows[0].get("no_match") is True
