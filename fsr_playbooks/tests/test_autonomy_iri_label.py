"""A close written as a picklist IRI is judged by the label the IRI names,
even when the field-to-picklist map is missing (unwarmed catalog)."""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks import picklists as pl
from fsr_playbooks.llm import autonomy

CLOSED = "/api/3/picklists/" + "c" * 32
OPEN = "/api/3/picklists/" + "0" * 32
LABELS = {CLOSED: "Closed", OPEN: "Open"}


@pytest.fixture()
def empty_field_map(monkeypatch):
    monkeypatch.setattr(autonomy, "_picklist_iri", lambda m, f, label: None)
    monkeypatch.setattr(autonomy, "_picklist_label", lambda iri: LABELS.get(iri))


def test_iri_whose_label_is_allowed_passes_with_empty_field_map(empty_field_map):
    assert autonomy._value_allowed("alerts", "status", CLOSED, ["Closed"])
    assert autonomy._value_allowed("alerts", "status", {"@id": CLOSED}, ["Closed"])


def test_iri_naming_another_label_is_refused(empty_field_map):
    assert not autonomy._value_allowed("alerts", "status", OPEN, ["Closed"])


def test_unresolvable_iri_fails_closed(empty_field_map):
    assert not autonomy._value_allowed("alerts", "status",
                                       "/api/3/picklists/" + "f" * 32, ["Closed"])


def _conn(rows):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE picklists (list_name TEXT, item_value TEXT, item_iri TEXT)")
    c.executemany("INSERT INTO picklists VALUES (?,?,?)", rows)
    return c


class _Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class _Client:
    base_url, verify_ssl = "https://x", False

    def __init__(self, resp):
        self.session = self
        self._resp, self.urls = resp, []

    def get(self, url, **kw):
        self.urls.append(url)
        return self._resp


def test_label_for_iri_reads_the_store():
    c = _conn([("AlertStatus", "Closed", CLOSED)])
    assert pl.label_for_iri(c, CLOSED) == "Closed"
    assert pl.label_for_iri(c, OPEN) is None


def test_label_for_iri_falls_back_to_a_live_get():
    cl = _Client(_Resp(200, {"itemValue": "Closed"}))
    assert pl.label_for_iri(_conn([]), CLOSED, cl) == "Closed"
    assert cl.urls == ["https://x" + CLOSED]
    assert pl.label_for_iri(_conn([]), CLOSED, _Client(_Resp(404, {}))) is None


def test_label_for_iri_rejects_non_picklist_iris():
    assert pl.label_for_iri(_conn([]), "/api/3/alerts/" + "a" * 32) is None
