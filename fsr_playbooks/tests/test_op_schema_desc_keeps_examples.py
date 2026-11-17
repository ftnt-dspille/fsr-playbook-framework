"""get_op_schema's one-line descriptions must not cut at an abbreviation.

The first-sentence clip split on ". ", so "(E.g. /api/3/events)" became
"(E.g" -- 138 catalog params lost the example that answers the question.
Live consequence: a fix-the-failed-run turn could not tell whether
make_cyops_request's `iri` takes a full path or a bare uuid, guessed the
uuid, and shipped a fix that would 404.
"""
from fsr_playbooks.mcp_server.tools_discovery import _first_sentence, _short_desc


def test_example_after_eg_survives():
    p = {"description": "An IRI that points to the location of the FortiSOAR "
                        "collection (E.g. /api/3/events)"}
    assert _short_desc(p).endswith("(E.g. /api/3/events)")


def test_ie_and_etc_do_not_end_the_sentence():
    assert _first_sentence("Specify the offset, i.e. rows to skip. More.") == \
        "Specify the offset, i.e. rows to skip"
    assert _first_sentence("Tags, labels, etc. are kept. Extra.") == \
        "Tags, labels, etc. are kept"


def test_a_real_sentence_end_still_cuts():
    assert _first_sentence("First sentence. Second sentence.") == "First sentence"
    assert _first_sentence("No period at all") == "No period at all"
