"""find_jinja_pattern's token fallback stays inside a payload budget.

The exact-match path is self-limiting: a query that matches verbatim matches
few things. The fallback is the opposite -- it deliberately widens, so it
returns `limit` rows every time, and it fires on exactly the prose queries the
model asks in bulk (7-10 calls in one build turn, #48). Measured at ~9 KB for
a four-token query, which is a fifth of a turn's context spent on a guess.

The cap is three cuts: the note goes on row 0 only, an outsized `raw` block is
truncated with its real length stated, and rows past the budget are dropped
with a count -- never silently, because a truncated list that looks complete
is a worse answer than a short one that says it was cut.
"""
import json

import pytest

from fsr_playbooks.mcp_server import tools_jinja
from fsr_playbooks.mcp_server.tools_jinja import find_jinja_pattern

_find = find_jinja_pattern.fn if hasattr(find_jinja_pattern, "fn") \
    else find_jinja_pattern

_HAS_CORPUS = bool(_find("vars", limit=1))
needs_corpus = pytest.mark.skipif(
    not _HAS_CORPUS, reason="jinja corpus absent from the slim reference DB")

# Prose queries that miss verbatim and therefore exercise the fallback.
_PROSE = ["join loop list string", "for record in loop",
          "current date time now", "set variable from step output"]


@needs_corpus
@pytest.mark.parametrize("q", _PROSE)
def test_fallback_payload_stays_within_budget(q):
    rows = _find(q, limit=12)
    if rows[0].get("no_match"):
        pytest.skip("query found nothing at all; not the fallback path")
    size = len(json.dumps(rows, default=str))
    # The budget bounds the row set; row 0 also carries the note and any
    # truncation notice, so allow one row's slack over the raw budget.
    assert size <= tools_jinja._FALLBACK_CHAR_BUDGET + 1200, \
        f"{q!r} returned {size} chars"


@needs_corpus
def test_the_note_is_not_repeated_on_every_row():
    rows = _find("join loop list string", limit=12)
    assert sum(1 for r in rows if "note" in r) == 1


@needs_corpus
def test_truncation_is_announced_not_silent():
    rows = _find("join loop list string", limit=12)
    if len(rows) < 12:
        assert "omitted" in rows[0]["truncated"]


def test_an_oversized_block_is_truncated_with_its_length():
    """Directly, so the assertion holds without the mined corpus."""
    huge = "{% set x = " + "a" * 5000 + " %}"
    out = tools_jinja._cap([{"raw": huge, "occurrences": 1}], "note")
    assert out[0]["raw"].endswith("chars, truncated>")
    assert str(len(huge)) in out[0]["raw"]


def test_rows_past_the_budget_are_dropped_with_a_count():
    rows = [{"raw": "x" * 300, "vars_csv": "y" * 300, "occurrences": i}
            for i in range(40)]
    out = tools_jinja._cap(rows, "note")
    assert len(out) < 40
    assert f"{40 - len(out)} more matches omitted" in out[0]["truncated"]


def test_the_budget_never_cuts_below_a_ranked_list(monkeypatch):
    """Below a few rows the answer stops being a ranking, so the floor wins
    over the budget. `raw` truncation keeps normal rows small enough that
    this only bites on rows fat in the uncapped columns."""
    monkeypatch.setattr(tools_jinja, "_FALLBACK_CHAR_BUDGET", 10)
    rows = [{"raw": "x" * 300, "occurrences": i} for i in range(10)]
    out = tools_jinja._cap(rows, "note")
    assert len(out) == tools_jinja._FALLBACK_MIN_ROWS
    assert "omitted" in out[0]["truncated"]
