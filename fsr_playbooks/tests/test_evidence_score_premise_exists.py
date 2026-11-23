"""Phase 2 step 2f (shadow): the premise status ``unread`` splits into "a record
existed and the turn did not read it" (``unread_exists``) and "the host looked and
none exists" (``none_exists``). The host answers through a bounded reader bound
for the turn; with none bound (or a lookup that fails) the status stays ``unread``.
"""
from __future__ import annotations

import pytest
from test_evidence_score_premise import (
    CHANGE,
    HOST,
    HOST_IP,
    IP,
    MAL,
    OTHER_ASSET,
    PLAIN_ASSET,
    RECORD,
    SANDBOX_ASSET,
    alert_read,
    asset_read,
    card,
    vt,
)

from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._evidence_score import (
    premise_check,
    subject_records_exist,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card

UNREAD = {"v": vt(), "alert": alert_read()}


class Reader:
    def __init__(self, asset=None, change=None, raises=False):
        self.answer = {"asset": asset, "change": change}
        self.calls: list[list[str]] = []
        self.raises = raises

    def __call__(self, names):
        self.calls.append(list(names))
        if self.raises:
            raise RuntimeError("box down")
        return self.answer


def check(c=None, reg=None, reader=None):
    return premise_check(c or card(), reg or UNREAD, record_subject=RECORD,
                         subject_reader=reader)


def test_a_record_that_exists_and_was_not_read_is_unread_exists():
    r = Reader(asset=PLAIN_ASSET["data"], change=[])
    p = check(reader=r)
    assert p["status"] == "unread_exists"
    assert p["exists"] == {"asset": True, "change": False}
    assert r.calls and HOST in r.calls[0]


def test_a_change_record_that_names_the_subject_counts():
    p = check(reader=Reader(asset=[], change=CHANGE["result"]))
    assert p["status"] == "unread_exists" and p["exists"] == {"asset": False, "change": True}


def test_no_record_for_the_subject_is_none_exists():
    p = check(reader=Reader(asset=[], change=[]))
    assert p["status"] == "none_exists"
    assert p["exists"] == {"asset": False, "change": False}


def test_a_neighbours_record_is_not_the_subjects():
    p = check(reader=Reader(asset=OTHER_ASSET["data"], change=[]))
    assert p["status"] == "none_exists"


def test_a_lookup_that_could_not_look_stays_unread():
    assert check(reader=Reader(asset=None, change=None))["status"] == "unread"
    assert check(reader=Reader(asset=[], change=None))["status"] == "unread"
    assert check(reader=Reader(raises=True))["status"] == "unread"
    assert check(reader=None)["status"] == "unread"
    # one kind found is enough even when the other could not be looked up
    assert check(reader=Reader(asset=PLAIN_ASSET["data"], change=None))["status"] == "unread_exists"


def test_the_reader_is_asked_when_a_kind_of_record_is_unread_and_never_on_a_contradiction():
    r = Reader(asset=PLAIN_ASSET["data"], change=[])
    p = check(reg={**UNREAD, "asset": asset_read(PLAIN_ASSET)}, reader=r)
    # 2h: an asset read leaves the change kind unread, so the host is asked; the
    # status stays ``read`` and nothing is flagged because no change record exists
    assert p["status"] == "read" and len(r.calls) == 1 and "unread_kinds_exist" not in p
    r.calls.clear()
    p = check(reg={**UNREAD, "asset": asset_read(SANDBOX_ASSET)}, reader=r)
    assert p["status"] == "contradicted" and r.calls == []


def test_a_row_or_a_wrapped_result_both_work():
    wrapped = {"hydra:member": PLAIN_ASSET["data"], "hydra:totalItems": 1}
    assert check(reader=Reader(asset=wrapped, change=[]))["status"] == "unread_exists"
    assert subject_records_exist(Reader(asset=[], change=[]), set()) == {}


@pytest.fixture
def turn():
    cv.clear_tool_registry()
    cv.set_result_reader(lambda c, o, p, r: MAL if c == "virustotal" else None)
    cv.register_tool_result("call_vt", "run_op", True,
                            {"connector": "virustotal", "op": "query_ip",
                             "params": {"ip": IP}}, {"ok": True, "data": {"malicious": 40}})
    yield
    cv.set_turn_subject_records(None)
    cv.set_result_reader(None)
    cv.clear_tool_registry()


def _emit():
    return emit_card(card_type="verdict", payload={
        "disposition": "true_positive", "severity": "high", "confidence": 0.9,
        "summary": f"{HOST} ({HOST_IP}) beacons to {IP}", "unknowns": [],
        "findings": [{"claim": f"{HOST} contacted {IP}", "evidence": ["call_vt"]}]})["card"]


def test_the_bound_reader_reaches_the_card(turn):
    cv.set_turn_subject_records(Reader(asset=SANDBOX_ASSET["data"], change=[]))
    c = _emit()
    assert c["premise"]["status"] == "unread_exists"
    assert cv.get_turn_evidence().verdicts()[-1]["premise"]["status"] == "unread_exists"
    assert c["confidence"] == 0.9


def test_no_reader_bound_leaves_the_card_as_before(turn):
    assert _emit()["premise"]["status"] == "unread"


def test_the_lookup_cost_is_recorded_with_the_hosts_request_counts():
    r = Reader(asset=[], change=[])
    r.answer["stats"] = {"asset_requests": 2, "change_ops": 0, "junk": "x"}
    lk = check(reader=r)["lookup"]
    assert isinstance(lk["ms"], int) and lk["ms"] >= 0
    assert lk["asset_requests"] == 2 and lk["change_ops"] == 0 and "junk" not in lk


def test_no_lookup_cost_when_no_reader_was_asked():
    assert "lookup" not in check()
    read = {"v": vt(), "alert": alert_read(), "asset": asset_read(PLAIN_ASSET)}
    assert "lookup" not in check(reg=read)
    assert "lookup" in check(reg=read, reader=Reader(asset=[], change=[]))
