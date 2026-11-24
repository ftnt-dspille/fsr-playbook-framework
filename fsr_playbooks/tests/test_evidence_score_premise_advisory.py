"""Phase 2 step 3a (advisory only): the premise carries ``advisory``, one entry per
record kind the analyst should hear about: ``unread`` (a record of that kind
exists and the turn did not read it) or ``conflict`` (a record it read conflicts
with the verdict). The card words it; nothing reads it for a decision.
"""
from __future__ import annotations

import copy

import pytest
from test_evidence_score_premise import (
    CHANGE,
    PLAIN_ASSET,
    SANDBOX_ASSET,
    asset_read,
    card,
)
from test_evidence_score_premise_exists import Reader, check
from test_evidence_score_premise_kinds import reg
from test_evidence_score_shadow import BLOCK, POLICY
from test_evidence_score_shadow import vt as shadow_vt

from fsr_playbooks.llm.autonomy import evaluate, parse_policy
from fsr_playbooks.mcp_server._evidence_score import premise_advisory, record_premise


def test_an_unread_record_that_exists_is_advised_by_kind():
    p = check(reader=Reader(asset=[], change=CHANGE["result"]))
    assert p["status"] == "unread_exists"
    assert p["advisory"] == [{"kind": "change", "state": "unread"}]


def test_both_kinds_unread_are_both_advised():
    p = check(reader=Reader(asset=PLAIN_ASSET["data"], change=CHANGE["result"]))
    assert p["advisory"] == [{"kind": "asset", "state": "unread"},
                             {"kind": "change", "state": "unread"}]


def test_a_read_asset_with_an_unread_change_is_advised():
    rd = Reader(asset=PLAIN_ASSET["data"], change=CHANGE["result"])
    p = check(reg=reg(asset_read(PLAIN_ASSET)), reader=rd)
    assert p["status"] == "read"
    assert p["advisory"] == [{"kind": "change", "state": "unread"}]


def test_a_contradicting_record_is_a_conflict_of_its_kind():
    p = check(card(), reg=reg(asset_read(SANDBOX_ASSET)), reader=Reader())
    assert p["status"] == "contradicted"
    assert p["advisory"] == [{"kind": "asset", "state": "conflict"}]


@pytest.mark.parametrize("rd", [Reader(asset=[], change=[]), None])
def test_nothing_unread_and_nothing_conflicting_means_no_advisory(rd):
    assert "advisory" not in check(reader=rd)


def test_a_clean_read_has_no_advisory():
    rd = Reader(asset=PLAIN_ASSET["data"], change=[])
    p = check(reg=reg(asset_read(PLAIN_ASSET)), reader=rd)
    assert p["status"] == "read" and "advisory" not in p


def test_an_unknown_kind_is_never_advised():
    assert premise_advisory({"status": "read", "unread_kinds_exist": ["ticket"]}) == []
    assert premise_advisory({"status": "unread_exists", "exists": {"ticket": True}}) == []


def test_the_advisory_names_no_field_or_id():
    p = check(reader=Reader(asset=PLAIN_ASSET["data"], change=CHANGE["result"]))
    assert all(set(a) == {"kind", "state"} for a in p["advisory"])


def test_recording_puts_the_advisory_on_the_card():
    c = card()
    record_premise(c, check(reader=Reader(asset=[], change=CHANGE["result"])))
    assert c["premise"]["advisory"] == [{"kind": "change", "state": "unread"}]


# ---- decisions are identical with and without the advisory -----------------------

def _decide(conf, premise):
    p, err = parse_policy(copy.deepcopy(POLICY))
    assert err is None
    v = {"id": "v1", "disposition": "true_positive", "confidence": conf,
         "findings": [{"claim": "x", "evidence": ["tu1"]}]}
    if premise is not None:
        v["premise"] = premise
    return evaluate(p, BLOCK, verdicts=[v], registry={"tu1": shadow_vt()}, counter=lambda r, t: (0, 0))


@pytest.mark.parametrize("conf, expect", [(0.95, "would_act"), (0.85, "would_not_act")])
def test_the_advisory_never_changes_an_autonomy_decision(conf, expect):
    base = _decide(conf, None)
    assert base["outcome"] == expect
    for premise in ({"status": "unread_exists", "exists": {"change": True},
                     "advisory": [{"kind": "change", "state": "unread"}]},
                    {"status": "contradicted",
                     "advisory": [{"kind": "asset", "state": "conflict"}]}):
        d = _decide(conf, premise)
        assert (d["outcome"], d["failed"]) == (base["outcome"], base["failed"])
