"""Phase 2 step 4 (shadow): change rows from a second ticketing connector (Jira
REST v3 shape: a search body with ``issues``, each issue's fields under
``fields``, status as an object, the description as an Atlassian Document Format
tree) are read by the extractors, and a stale or windowless approval that names
the destination is characterised as the relevance rule treats it today.
"""
from __future__ import annotations

from test_evidence_score_preread import ALERT_T, HOST, IP, pre

from fsr_playbooks.mcp_server._evidence_score import (
    _row_facts,
    preread_review,
    preread_rows,
    record_line,
    row_relevant,
    supports_innocent,
    unwrap_fields,
)

DEST = [IP]


def adf(text):
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def issue(status="Implementing", text=None, due=None, summary="Vendor proof of concept"):
    return {"expand": "operations", "id": "10042", "key": "CHG-42",
            "self": "https://jira.example.com/rest/api/3/issue/10042",
            "fields": {"summary": summary,
                       "issuetype": {"id": "10005", "name": "Change"},
                       "status": {"id": "3", "name": status,
                                  "statusCategory": {"key": "indeterminate"}},
                       "created": "2026-09-20T09:12:44.000+0000", "duedate": due,
                       "labels": [],
                       "description": adf(text or f"Approved: {HOST} runs a proof of "
                                                  f"concept against {IP}.")}}


def body(*issues):
    return {"issues": list(issues), "isLast": True}


def test_a_jira_search_body_yields_one_parsed_row_per_issue():
    rows, unparsed = preread_rows(pre(change=[body(issue(), issue())]), "change")
    assert len(rows) == 2 and unparsed is False


def test_a_jira_issue_reads_as_a_flat_record():
    flat = unwrap_fields(issue(due="2026-09-30"))
    assert flat["key"] == "CHG-42" and flat["status"] == "Implementing"
    assert flat["issuetype"] == "Change"
    assert flat["description"].startswith("Approved:") and IP in flat["description"]


def test_a_jira_row_carries_the_roles_names_and_a_covering_due_date():
    rows, _ = preread_rows(pre(change=[body(issue(due="2026-09-30"))]), "change")
    f = _row_facts(rows[0])
    assert {"approved", "change"} <= f["roles"] and IP in f["names"]
    assert f["window"][0] is None and f["window"][1] > ALERT_T
    assert supports_innocent(rows[0], [ALERT_T], DEST)


def test_a_cancelled_or_declined_jira_change_does_not_excuse():
    for status in ("Cancelled", "Declined"):
        rows, _ = preread_rows(pre(change=[body(issue(status=status))]), "change")
        assert _row_facts(rows[0])["lapsed"] is True
        assert not supports_innocent(rows[0], [ALERT_T], DEST)


def test_a_due_date_before_the_alert_is_a_lapsed_window():
    rows, _ = preread_rows(pre(change=[body(issue(due="2026-08-18"))]), "change")
    assert not supports_innocent(rows[0], [ALERT_T], DEST)


def test_a_date_only_due_date_on_the_alert_day_still_covers_it():
    rows, _ = preread_rows(pre(change=[body(issue(due="2026-09-29"))]), "change")
    assert supports_innocent(rows[0], [ALERT_T], DEST)


def test_the_note_line_names_the_jira_change_without_field_names():
    rows, _ = preread_rows(pre(change=[body(issue(due="2026-09-30"))]), "change")
    line = record_line("change", rows[0])
    assert line.startswith("Change record CHG-42 (state Implementing")
    assert "Approved:" in line
    for banned in ("fields", "issuetype", "statusCategory", "rest/api"):
        assert banned not in line


def test_a_jira_row_is_not_flagged_unparsed_and_a_convict_on_it_holds_only_if_it_excuses():
    review = preread_review({"disposition": "true_positive"},
                            pre(change=[body(issue(due="2026-09-30"))]), [ALERT_T], DEST)
    assert "unparsed_record" not in review and review["relevant"] == ["change"]
    review = preread_review({"disposition": "true_positive"},
                            pre(change=[body(issue(status="Cancelled"))]), [ALERT_T], DEST)
    assert "unparsed_record" not in review and review["relevant"] == []


def test_an_empty_jira_issue_list_is_no_row_and_not_unparsed():
    assert preread_rows(pre(change=[body()]), "change") == ([], False)


# ---- keyword agrees, truth differs: an approval that names the destination with no window ----

NO_WINDOW = {"number": "CHG-7201", "state": "Implemented", "approval": "approved",
             "short_description": "Quarterly reconciliation file transfer",
             "description": f"Approved: {HOST} may send the quarterly reconciliation file to {IP}."}


def test_a_windowless_approval_that_names_the_destination_looks_excusing_to_relA():
    """Characterisation of today's rule (no stated window covers): the record
    counts as able to excuse, so a conviction is held and a benign close is
    admitted as backed. Recorded so the owner's decision (a missing window is an
    affirmative undermining signal for a benign close) has a test to change."""
    assert supports_innocent(NO_WINDOW, [ALERT_T], DEST)
    assert row_relevant(NO_WINDOW, "true_positive", [ALERT_T], DEST) is True
    assert row_relevant(NO_WINDOW, "benign", [ALERT_T], DEST) is False
    assert _row_facts(NO_WINDOW)["window"] is None


def test_a_lapsed_window_on_the_same_record_does_not_excuse():
    old = dict(NO_WINDOW, start_date="2026-08-18 02:00:00", end_date="2026-08-18 06:00:00")
    assert not supports_innocent(old, [ALERT_T], DEST)
    assert row_relevant(old, "true_positive", [ALERT_T], DEST) is False
    assert row_relevant(old, "benign", [ALERT_T], DEST) is True
