"""`probe modules` must read the tags collection in both shapes it comes in.

On 8.0 `/api/3/tags` is a list of bare strings. The probe only read objects,
so it deleted the table and inserted nothing, and the compiler's check for a
misspelled `set_variable.message.tags` entry went quiet without saying so.
"""
from __future__ import annotations

from probes.probe_modules import TAGS_URL, _tag_rows


def test_bare_string_tags_become_rows():
    assert _tag_rows(["Phishing", "", "Agentic AI"]) == [
        ("Phishing", "/api/3/tags/Phishing"),
        ("Agentic AI", "/api/3/tags/Agentic AI"),
    ]


def test_object_tags_still_read():
    assert _tag_rows([{"name": "c2", "@id": "/api/3/tags/c2"},
                      {"name": "no-iri"}]) == [("c2", "/api/3/tags/c2")]


def test_tags_are_not_ordered_by_a_column_8_0_lacks():
    # `$orderby=name` is a server-side QueryException (HTTP 400) on 8.0.
    assert "orderby" not in TAGS_URL
