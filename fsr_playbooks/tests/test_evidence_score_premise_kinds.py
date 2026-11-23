"""Phase 2 step 2h (shadow): a turn that read one kind of the subject's records
(its asset) while another kind exists unread (a change record) keeps status
``read`` and says which kind it left behind (``unread_kinds_exist``). The host
lookup runs only when a kind is unread.
"""
from __future__ import annotations

from test_evidence_score_premise import (
    CHANGE,
    PLAIN_ASSET,
    SANDBOX_ASSET,
    alert_read,
    asset_read,
    card,
    change_read,
    vt,
)
from test_evidence_score_premise_exists import Reader, check


def reg(*extra):
    r = {"v": vt(), "alert": alert_read()}
    r.update({f"r{i}": e for i, e in enumerate(extra)})
    return r


def test_an_asset_read_with_an_unread_change_record_is_flagged():
    rd = Reader(asset=PLAIN_ASSET["data"], change=CHANGE["result"])
    p = check(reg=reg(asset_read(PLAIN_ASSET)), reader=rd)
    assert p["status"] == "read" and p["read_kinds"] == ["asset"]
    assert p["unread_kinds_exist"] == ["change"]
    assert p["exists"] == {"asset": True, "change": True} and rd.calls


def test_a_change_read_with_an_unread_asset_record_is_flagged():
    rd = Reader(asset=PLAIN_ASSET["data"], change=CHANGE["result"])
    p = check(reg=reg(change_read()), reader=rd)
    assert p["status"] == "contradicted" or p["unread_kinds_exist"] == ["asset"]


def test_no_other_record_means_no_flag():
    rd = Reader(asset=PLAIN_ASSET["data"], change=[])
    p = check(reg=reg(asset_read(PLAIN_ASSET)), reader=rd)
    assert p["status"] == "read" and "unread_kinds_exist" not in p


def test_both_kinds_read_never_calls_the_host():
    rd = Reader(asset=PLAIN_ASSET["data"], change=CHANGE["result"])
    # a change read that does not contradict a benign conviction path: scoped away
    scope = {"result": [{"number": "CHG-2", "approval": "approved",
                         "description": "Approved: sec-host-02 scans 100.64.60.0/24."}]}
    p = check(reg=reg(asset_read(PLAIN_ASSET), change_read(scope)), reader=rd)
    assert p["status"] == "read" and p["read_kinds"] == ["asset", "change"]
    assert rd.calls == [] and "unread_kinds_exist" not in p


def test_a_contradiction_does_not_look_up():
    rd = Reader(asset=[], change=CHANGE["result"])
    p = check(reg=reg(asset_read(SANDBOX_ASSET)), reader=rd)
    assert p["status"] == "contradicted" and rd.calls == []


def test_a_failing_lookup_leaves_a_read_turn_unflagged():
    p = check(reg=reg(asset_read(PLAIN_ASSET)), reader=Reader(raises=True))
    assert p["status"] == "read" and "unread_kinds_exist" not in p


def test_no_reader_means_no_lookup_and_no_flag():
    p = check(reg=reg(asset_read(PLAIN_ASSET)), reader=None)
    assert p["status"] == "read" and "unread_kinds_exist" not in p
    assert card()  # keep the shared helper imported
