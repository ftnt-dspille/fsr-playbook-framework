"""A picklist IRI that doesn't resolve to the field's list is an affordance,
not a silent pass-through.

The compiler rewrites friendly picklist labels to the canonical
`/api/3/picklists/<uuid>` IRI. An IRI-shaped value used to pass through with NO
catalog check, so a stale or cross-box IRI (copied from another appliance)
compiled clean and failed at runtime with an opaque uuid the agent can't
self-correct from (#15). Now a picklist IRI is validated against the catalog:
a correct IRI passes; an IRI from the wrong list names both lists; an IRI in no
list at all names it stale and lists the valid values. The error becomes an
affordance, matching the friendly-label path.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler.resolver.picklists import PicklistMixin


# CI ships the slim reference DB. Probe once for a row this file can actually
# assert on; no such row -> skip the IRI assertions (a genuine regression would
# still run on a full DB). Mirrors the jinja-ranking test's guard.
#
# The probe must require a NON-EMPTY `item_iri`, not merely any row. The slim
# catalog ships picklist VALUES but deliberately never IRIs (a value must
# compile on any box; an IRI is per-appliance), so once values started shipping
# the any-row probe found 205 rows with `item_iri = ''`, un-skipped this file,
# and every IRI assertion failed against the empty string -- three red tests on
# CI describing nothing but the guard's own blind spot. A guard that stopped
# guarding looks exactly like a corpus that arrived.
def _probe():
    db = default_db_path()
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT list_name, item_value, item_iri FROM picklists "
            "WHERE item_iri IS NOT NULL AND item_iri != '' LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    return str(db), row


_PROBE = _probe()
_HAS_CORPUS = _PROBE is not None and _PROBE[1] is not None
needs_corpus = pytest.mark.skipif(
    not _HAS_CORPUS, reason="reference DB has no picklist rows (slim CI DB)")


class _R(PicklistMixin):
    """Minimal host giving the mixin a sqlite connection."""

    def __init__(self, conn):
        self.conn = conn


@pytest.fixture
def resolver():
    if not _HAS_CORPUS:
        pytest.skip("no picklist corpus")
    con = sqlite3.connect(f"file:{_PROBE[0]}?mode=ro", uri=True)
    yield _R(con)
    con.close()


@needs_corpus
def test_correct_iri_passes_through(resolver):
    list_name, _value, iri = _PROBE[1]
    errors = []
    out = resolver._rewrite_one_picklist_token(iri, list_name, "p", errors)
    assert out == iri
    assert errors == []


@needs_corpus
def test_iri_from_the_wrong_list_names_both(resolver):
    list_name, _value, _iri = _PROBE[1]
    wrong = resolver.conn.execute(
        "SELECT list_name, item_iri FROM picklists "
        "WHERE list_name != ? AND item_iri IS NOT NULL AND item_iri != '' "
        "LIMIT 1", (list_name,)
    ).fetchone()
    if wrong is None:
        pytest.skip("corpus has only one picklist")
    wrong_list, wrong_iri = wrong
    errors = []
    out = resolver._rewrite_one_picklist_token(wrong_iri, list_name, "p", errors)
    assert out == wrong_iri  # value is returned unchanged; the error is the signal
    assert len(errors) == 1
    msg = errors[0].message
    assert wrong_list in msg, "must name the list the IRI actually belongs to"
    assert list_name in msg, "must name the list the field expects"
    assert errors[0].check == "picklist_iri_drift"


@needs_corpus
def test_stale_iri_lists_valid_values(resolver):
    list_name, _value, _iri = _PROBE[1]
    errors = []
    stale = "/api/3/picklists/00000000-0000-0000-0000-000000000000"
    out = resolver._rewrite_one_picklist_token(stale, list_name, "p", errors)
    assert out == stale
    assert len(errors) == 1
    assert "not in the catalog" in errors[0].message
    assert list_name in errors[0].message


def test_jinja_expression_passes_through(resolver):
    errors = []
    out = resolver._rewrite_one_picklist_token(
        '{{ "A" | picklist("B", "@id") }}', "Whatever", "p", errors)
    assert "{{" in out
    assert errors == []


def test_non_picklist_api_iri_passes_through(resolver):
    # A record IRI is not a picklist IRI -- not ours to validate.
    errors = []
    out = resolver._rewrite_one_picklist_token(
        "/api/3/incidents/abc-123", "Whatever", "p", errors)
    assert out == "/api/3/incidents/abc-123"
    assert errors == []


def test_placeholder_picklist_iri_passes_through(resolver):
    # A non-uuid placeholder like `/api/3/picklists/x` (recipe templates,
    # tests) is not an opaque uuid copied from another box -- flagging it
    # would be a false positive on the authoring surface. Only uuid-shaped
    # IRIs are validated.
    errors = []
    out = resolver._rewrite_one_picklist_token(
        "/api/3/picklists/x", "Whatever", "p", errors)
    assert out == "/api/3/picklists/x"
    assert errors == []


@needs_corpus
def test_unknown_list_passes_through_no_false_positive(resolver):
    # A custom picklist the catalog has no rows for can't be validated;
    # flagging a valid IRI would be a false positive.
    list_name, _value, iri = _PROBE[1]
    errors = []
    out = resolver._rewrite_one_picklist_token(iri, "NoSuchListXYZ", "p", errors)
    assert out == iri
    assert errors == []


@needs_corpus
def test_friendly_label_still_resolves(resolver):
    list_name, value, iri = _PROBE[1]
    errors = []
    out = resolver._rewrite_one_picklist_token(value, list_name, "p", errors)
    assert out == iri
    assert errors == []
