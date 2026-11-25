"""Phase 2 step 4 (shadow): the host reads the subject's asset and change records
at the start of the turn. The model is shown a compact note of them, the evidence
score and the premise count them as read, relA relevance is applied to them, and a
fetched row the extractors cannot read sets ``unparsed_record`` (relevant to any
non-hedge verdict, so a conviction on it would hold). No decision reads any of it.
"""
from __future__ import annotations

import copy

import pytest
from test_evidence_score_premise import (
    HOST,
    HOST_IP,
    IP,
    PLAIN_ASSET,
    RECORD,
    SANDBOX_ASSET,
    alert_read,
    card,
    vt,
)
from test_evidence_score_premise_exists import Reader
from test_evidence_score_shadow import BLOCK, POLICY
from test_evidence_score_shadow import vt as shadow_vt

from fsr_playbooks.llm.autonomy import evaluate, parse_policy
from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server._evidence_score import (
    premise_check,
    preread_entries,
    preread_note,
    preread_review,
    row_relevant,
    score_verdict,
    subject_context,
    unwrap_fields,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card

ALERT_T = 1790690820.0  # 2026-09-29 14:07 UTC
WINDOW_OPEN = {"start_date": "2026-09-29 08:00:00", "end_date": "2026-09-30 08:00:00"}
WINDOW_OLD = {"start_date": "2026-08-18 02:00:00", "end_date": "2026-08-18 06:00:00"}


def chg(extra=None, text=None):
    row = {"number": "CHG-7101", "state": "Implement", "approval": "approved",
           "short_description": "Vendor proof of concept",
           "description": text or f"Approved: {HOST} runs a proof of concept against {IP}."}
    row.update(extra or {})
    return row


def pre(asset=None, change=None, **kw):
    out = {"asset": asset, "change": change, "names": [HOST, HOST_IP], "t": ALERT_T,
           "dst": [IP], "ms": 1234, "stats": {"asset_requests": 2, "change_ops": 2}}
    out.update(kw)
    return out


UNREAD = {"v": vt(), "alert": alert_read()}


def check(c=None, preread=None, reader=None, reg=None):
    return premise_check(c or card(), reg or UNREAD, record_subject=RECORD,
                         subject_reader=reader, preread=preread)


# ---- the note the model sees ---------------------------------------------------------

def test_the_note_gives_kind_state_window_and_scope():
    note = preread_note(pre(change={"result": [chg({**WINDOW_OPEN, "scope": "198.51.100.0/24"})]}))
    assert "Change record" in note and "Implement" in note and "approved" in note
    assert "2026-09-29 08:00 UTC to 2026-09-30 08:00 UTC" in note
    assert "scope 198.51.100.0/24" in note
    assert f"runs a proof of concept against {IP}" in note


def test_the_note_names_no_tool_field_or_id():
    row = {**chg(WINDOW_OPEN), "sys_id": "c0a1d0a10f3e4a518c01aa0000007101",
           "@id": "/api/3/change/abc"}
    note = preread_note(pre(asset=PLAIN_ASSET["data"], change={"result": [row]}))
    for banned in ("sys_id", "c0a1d0a1", "@id", "/api/", "run_op", "servicenow", "hydra",
                   "start_date", "short_description", "{"):
        assert banned not in note, banned
    assert "Asset record" in note


def test_the_note_skips_a_neighbours_records_and_is_empty_without_any():
    other = [{"name": "eng-ws-044", "ipAddress": "100.64.30.40", "description": "Engineering."}]
    assert preread_note(pre(asset=other, change=[])) == ""
    assert preread_note(None) == ""
    assert preread_note(pre(asset=None, change=None)) == ""


# ---- counted as read ------------------------------------------------------------------

def test_a_preread_record_counts_as_read_and_the_reader_is_not_asked():
    rd = Reader(asset=PLAIN_ASSET["data"], change=[])
    p = check(preread=pre(asset=PLAIN_ASSET["data"], change=[]), reader=rd)
    assert p["status"] == "read" and p["read_kinds"] == ["asset"]
    assert "preread:asset" in p["records"]
    assert rd.calls == []
    assert p["lookup"]["ms"] == 1234 and p["lookup"]["asset_requests"] == 2
    assert "unread_kinds_exist" not in p


def test_without_a_preread_the_same_turn_is_unread_exists():
    p = check(reader=Reader(asset=PLAIN_ASSET["data"], change=[]))
    assert p["status"] == "unread_exists" and "preread" not in p


def test_both_kinds_found_is_read_with_both_kinds():
    p = check(preread=pre(asset=PLAIN_ASSET["data"], change={"result": [chg(WINDOW_OLD)]}))
    assert p["status"] == "read" and p["read_kinds"] == ["asset", "change"]


def test_nothing_found_is_none_exists_and_nothing_could_not_look_stays_unread():
    assert check(preread=pre(asset=[], change=[]))["status"] == "none_exists"
    assert check(preread=pre(asset=None, change=None))["status"] == "unread"


def test_a_preread_sandbox_asset_contradicts_a_conviction():
    p = check(preread=pre(asset=SANDBOX_ASSET["data"], change=[]))
    assert p["status"] == "contradicted"
    assert p["advisory"] == [{"kind": "asset", "state": "conflict"}]
    assert p["preread"]["hold"] is True


def test_the_score_counts_a_preread_record_as_support_for_a_benign_close():
    reg = {"alert": alert_read()}
    c = card("benign")
    without = score_verdict(c, reg, record_subject=RECORD)
    merged = {**preread_entries(pre(asset=PLAIN_ASSET["data"])), **reg}
    withit = score_verdict(c, merged, record_subject=RECORD)
    assert without["components"]["support"] is False
    assert withit["components"]["support"] is True
    assert withit["score"] > without["score"]


# ---- relA on the pre-read rows ---------------------------------------------------------

def rel(row, disposition, times=(ALERT_T,), dest=(IP,)):
    return row_relevant(row, disposition, list(times), list(dest))


def test_a_conviction_is_moved_only_by_a_record_that_excuses_it():
    assert rel(chg(WINDOW_OPEN), "true_positive") is True          # approved, names dest, covers
    assert rel(chg(WINDOW_OLD), "true_positive") is False          # lapsed window
    assert rel(chg(WINDOW_OPEN, text="Approved scanning of 198.51.100.0/24."),
               "true_positive") is False                           # scope excludes the dest
    assert rel(chg({"state": "Canceled"}), "true_positive") is False
    assert rel(PLAIN_ASSET["data"][0], "true_positive") is False   # plain asset, no role
    assert rel(SANDBOX_ASSET["data"][0], "true_positive") is True  # strong role


def test_a_benign_close_is_held_only_on_an_affirmative_undermining_signal():
    assert rel(chg(WINDOW_OPEN), "benign") is False                # backs the close
    assert rel(chg(WINDOW_OLD), "benign") is True                  # lapsed window
    assert rel(chg({"state": "Canceled"}), "benign") is True       # lapsed state
    assert rel(chg(), "benign") is True                            # no window stated
    assert rel(chg(WINDOW_OPEN, text="Approved scan of 198.51.100.0/24."), "benign") is True
    assert rel(PLAIN_ASSET["data"][0], "benign") is False          # silent: admitted
    assert rel({"name": HOST, "description": "Vendor laptop, Dell."}, "benign") is False  # neutral
    assert rel(SANDBOX_ASSET["data"][0], "benign") is False        # strong role backs it
    assert rel({"name": HOST, "description": "Host is compromised and quarantined."},
               "false_positive") is True


@pytest.mark.parametrize("d", ["suspicious", "needs_more_info"])
def test_a_hedge_is_never_relevant(d):
    assert rel(chg(WINDOW_OPEN), d) is False
    assert rel(SANDBOX_ASSET["data"][0], d) is False


def test_the_review_lists_the_relevant_kinds_and_holds_on_them():
    c = card("true_positive")
    r = preread_review(c, pre(asset=PLAIN_ASSET["data"],
                              change={"result": [chg(WINDOW_OPEN)]}), [ALERT_T], [IP])
    assert r == {"kinds": ["asset", "change"], "relevant": ["change"], "hold": True,
                 "backed": True, "alarm": False}
    r = preread_review(c, pre(asset=PLAIN_ASSET["data"],
                              change={"result": [chg(WINDOW_OLD)]}), [ALERT_T], [IP])
    assert r["relevant"] == [] and r["hold"] is False


def test_the_review_carries_whole_set_facts_for_replay():
    r = preread_review(card("benign"), pre(asset=PLAIN_ASSET["data"],
                                           change={"result": [chg(WINDOW_OPEN)]}),
                       [ALERT_T], [IP])
    # the plain asset is silent (not held under rule A) and the set is backed
    assert r["relevant"] == [] and r["backed"] is True and r["alarm"] is False
    r = preread_review(card("benign"), pre(asset=[{"name": HOST, "description": "compromised"}]),
                       [ALERT_T], [IP])
    assert r["alarm"] is True and r["backed"] is False
    assert "backed" not in preread_review(card(), pre(asset=[], change=[]), [ALERT_T], [IP])


def test_the_alert_time_and_destination_come_from_the_preread_through_the_check():
    covers = check(preread=pre(change={"result": [chg(WINDOW_OPEN)]}))
    assert covers["preread"]["relevant"] == ["change"] and covers["preread"]["hold"]
    lapsed = check(preread=pre(change={"result": [chg(WINDOW_OLD)]}))
    assert lapsed["preread"]["relevant"] == [] and lapsed["preread"]["hold"] is False
    elsewhere = check(preread=pre(change={"result": [chg(WINDOW_OPEN)]}, dst=["100.64.1.1"]))
    assert elsewhere["preread"]["relevant"] == []


def test_a_row_for_a_neighbour_is_not_the_subjects():
    other = {"result": [chg(WINDOW_OPEN, text="Approved: eng-ws-044 may reach 203.0.113.9.")
                        | {"number": "CHG-1"}]}
    p = check(preread=pre(asset=[], change=other))
    assert p["status"] == "none_exists" and p["preread"]["kinds"] == []


# ---- the unparsed flag -------------------------------------------------------------------

@pytest.mark.parametrize("blob", [
    "CHG0030001 | Implement | lab-eval-12 | approved",   # an opaque string
    ["CHG0030001 lab-eval-12", "CHG0030002"],             # a list of strings
    [{"a": None, "b": [], "c": {}}],                      # a dict with no text in it
])
def test_a_fetched_row_that_cannot_be_read_sets_the_flag_and_would_hold_a_conviction(blob):
    p = check(preread=pre(asset=[], change=blob))
    assert p["unparsed_record"] is True
    assert p["preread"]["unparsed_record"] is True and p["preread"]["hold"] is True


def test_the_flag_holds_a_conviction_not_a_benign_close_and_never_a_hedge():
    blob = "CHG0030001 | Implement | lab-eval-12"
    assert check(card("benign"), preread=pre(asset=[], change=blob))["preread"]["hold"] is False
    assert check(card("true_positive"), preread=pre(asset=[], change=blob))["preread"]["hold"] is True
    h = check(card("needs_more_info"), preread=pre(asset=[], change=blob))
    assert h["unparsed_record"] is True and h["preread"]["hold"] is False


def test_readable_and_empty_results_do_not_set_the_flag():
    for c in ({"result": [chg(WINDOW_OPEN)]}, {"result": []}, [], None):
        p = check(preread=pre(asset=[], change=c))
        assert "unparsed_record" not in p and "unparsed_record" not in p["preread"]


# ---- subject context from the alert record -------------------------------------------------

def test_subject_context_takes_internal_names_time_and_destination_from_the_record():
    rec = {"uuid": RECORD, "computerName": HOST, "sourceIp": HOST_IP, "destinationIp": IP,
           "createDate": ALERT_T, "description": f"{HOST} beacons to {IP}",
           "relatedAlerts": [{"computerName": "other-host-9", "sourceIp": "100.64.9.9"}]}
    ctx = subject_context(rec)
    assert ctx["names"][0] == HOST and HOST_IP in ctx["names"] and IP not in ctx["names"]
    assert "other-host-9" not in ctx["names"] and "100.64.9.9" not in ctx["names"]
    assert ctx["t"] == ALERT_T and ctx["dst"] == [IP]
    assert subject_context(None) == {} and subject_context({}) == {}


# ---- wired through the emit path, and decisions are unchanged --------------------------------

def _emit(preread, disposition="true_positive"):
    cv.clear_tool_registry()
    cv.set_result_reader(lambda c, o, p, r: None)
    cv.set_turn_preread_records(preread)
    try:
        cv.register_tool_result("call_vt", "run_op", True,
                                {"connector": "virustotal", "op": "query_ip"}, {})
        return emit_card(card_type="verdict", payload={
            "disposition": disposition, "severity": "high", "confidence": 0.9,
            "summary": f"{HOST} ({HOST_IP}) beacons to {IP}", "unknowns": [],
            "findings": [{"claim": f"{HOST} contacted {IP}", "evidence": ["call_vt"]}]})["card"]
    finally:
        cv.set_turn_preread_records(None)
        cv.set_result_reader(None)
        cv.clear_tool_registry()


def test_the_emitted_card_carries_the_preread_premise():
    c = _emit(pre(asset=PLAIN_ASSET["data"], change={"result": [chg(WINDOW_OLD)]}), "benign")
    assert c["premise"]["status"] == "read"
    assert c["premise"]["read_kinds"] == ["asset", "change"]
    # neither a silent asset nor a lapsed change can back the close
    assert c["premise"]["preread"]["relevant"] == ["change"]
    assert c["premise"]["preread"]["hold"] is True


def test_the_emitted_card_without_a_preread_has_none():
    assert "preread" not in _emit(None)["premise"]


def _decide(conf, premise):
    p, err = parse_policy(copy.deepcopy(POLICY))
    assert err is None
    v = {"id": "v1", "disposition": "true_positive", "confidence": conf,
         "findings": [{"claim": "x", "evidence": ["tu1"]}]}
    if premise is not None:
        v["premise"] = premise
    return evaluate(p, BLOCK, verdicts=[v], registry={"tu1": shadow_vt()},
                    counter=lambda r, t: (0, 0))


@pytest.mark.parametrize("conf, expect", [(0.95, "would_act"), (0.85, "would_not_act")])
def test_a_preread_never_changes_an_autonomy_decision(conf, expect):
    base = _decide(conf, None)
    assert base["outcome"] == expect
    cases = [
        pre(asset=PLAIN_ASSET["data"], change={"result": [chg(WINDOW_OPEN)]}),   # relevant
        pre(asset=SANDBOX_ASSET["data"], change=[]),                              # contradicts
        pre(asset=[], change="CHG0030001 | Implement | lab-eval-12"),            # unparsed
    ]
    for case in cases:
        premise = check(preread=case)
        assert premise["preread"]["hold"] is True      # the shadow would hold ...
        d = _decide(conf, premise)
        assert (d["outcome"], d["failed"]) == (base["outcome"], base["failed"])  # ... and does not


# ---- ServiceNow wraps every field as {value, display_value} -------------------------------

def sn(v, d=None):
    return {"value": v, "display_value": v if d is None else d}


def sn_chg(extra=None):
    """A change row in the shape the ServiceNow connector returns: every field a
    wrapper, a reference field carrying a link, dates as UTC ``value``."""
    row = {"number": sn("CHG0030001"), "state": sn("-1", "Implement"),
           "approval": sn("approved", "Approved"),
           "short_description": sn("Vendor proof of concept"),
           "description": sn(f"Approved: {HOST} runs a proof of concept against {IP}."),
           "start_date": sn("2026-09-29 08:00:00", "2026-09-29 04:00:00"),
           "end_date": sn("2026-09-30 08:00:00", "2026-09-30 04:00:00"),
           "reason": sn(""), "parent": {"value": "", "link": ""},
           "assigned_to": {"value": "6816f79cc0a8016401c5a33be04be441",
                           "link": "https://example.service-now.com/api/now/table/sys_user/6816"},
           "sys_id": sn("c0a1d0a10f3e4a518c01aa0000007101")}
    row.update(extra or {})
    return row


def test_a_servicenow_change_row_is_parsed_not_flagged_unparsed():
    p = check(preread=pre(asset=[], change={"result": [sn_chg({"scope": sn("198.51.100.0/24")})]}))
    assert "unparsed_record" not in p and "unparsed_record" not in p["preread"]
    assert p["preread"]["kinds"] == ["change"]


def test_a_servicenow_change_row_gives_kind_state_approval_window_and_scope():
    note = preread_note(pre(change={"result": [sn_chg({"scope": sn("198.51.100.0/24")})]}))
    assert "Change record CHG0030001" in note
    assert "state Implement" in note and "approval Approved" in note
    assert "window 2026-09-29 08:00 UTC to 2026-09-30 08:00 UTC" in note  # UTC value, not the zoned display
    assert "scope 198.51.100.0/24" in note
    assert f"runs a proof of concept against {IP}" in note


def test_a_servicenow_row_relevance_follows_its_window_and_state():
    live = pre(change={"result": [sn_chg()]})
    lapsed = pre(change={"result": [sn_chg({"start_date": sn("2026-08-18 02:00:00"),
                                            "end_date": sn("2026-08-18 06:00:00")})]})
    cancelled = pre(change={"result": [sn_chg({"state": sn("4", "Canceled")})]})
    # a covering approved change can excuse a conviction; a lapsed or cancelled one cannot
    assert check(card("true_positive"), preread=live)["preread"]["relevant"] == ["change"]
    assert check(card("true_positive"), preread=lapsed)["preread"]["relevant"] == []
    assert check(card("true_positive"), preread=cancelled)["preread"]["relevant"] == []


def test_an_unreadable_servicenow_row_still_sets_the_flag():
    empty = {"number": sn(""), "state": sn(""), "parent": {"value": "", "link": ""}}
    p = check(preread=pre(asset=[], change={"result": [empty]}))
    assert p["unparsed_record"] is True and p["preread"]["hold"] is True


def test_plain_rows_are_unchanged_by_the_unwrap():
    row = chg(WINDOW_OPEN)
    assert unwrap_fields(row) == row
    assert unwrap_fields("CHG0030001 | Implement") == "CHG0030001 | Implement"
    assert preread_note(pre(change={"result": [row]})) == preread_note(
        pre(change={"result": [{k: sn(v) for k, v in row.items()}]}))


# ---- owner rule A, end to end through the review ------------------------------------------

def test_a_windowless_approval_holds_a_benign_close_and_a_neutral_record_admits_it():
    windowless = {"result": [chg()]}
    held = preread_review(card("benign"), pre(change=windowless), [ALERT_T], [IP])
    assert held["relevant"] == ["change"] and held["hold"] is True
    neutral = preread_review(card("benign"), pre(asset=PLAIN_ASSET["data"]), [ALERT_T], [IP])
    assert neutral["relevant"] == [] and neutral["hold"] is False
    covered = preread_review(card("benign"), pre(change={"result": [chg(WINDOW_OPEN)]}),
                             [ALERT_T], [IP])
    assert covered["hold"] is False


def test_the_conviction_side_is_unchanged_by_rule_a():
    # a plain asset does not excuse a conviction; a covering approval does; so does
    # a windowless one (no stated window covers on the conviction side)
    plain = preread_review(card("true_positive"), pre(asset=PLAIN_ASSET["data"]), [ALERT_T], [IP])
    assert plain["hold"] is False
    assert preread_review(card("true_positive"), pre(change={"result": [chg()]}),
                          [ALERT_T], [IP])["hold"] is True


def test_an_asset_row_that_cites_a_change_number_does_not_undermine_a_benign_close():
    """Only a real change or approval RECORD from a ticketing source can fail an
    authority. An asset row whose text cites a change number (no window, no
    approval fields) is not one; it must not hold a benign close."""
    asset = {"name": HOST, "description":
             f"Developer workstation, syncs with a vendor endpoint at {IP} (change CHG-8803)."}
    assert row_relevant(asset, "benign", [ALERT_T], [IP], "asset") is False
    r = preread_review(card("benign"), pre(asset=[asset]), [ALERT_T], [IP])
    assert r["relevant"] == [] and r["hold"] is False
    # the same wording as a change-kind record (no window) still holds
    assert row_relevant(asset, "benign", [ALERT_T], [IP], "change") is True
    # an alarm role in an asset row still holds
    bad = {"name": HOST, "description": "Host is compromised (change CHG-8803)."}
    assert row_relevant(bad, "benign", [ALERT_T], [IP], "asset") is True
    # the conviction side does not look at the kind
    assert row_relevant(asset, "true_positive", [ALERT_T], [IP], "asset") is True


# ---- a hold always names its record --------------------------------------------------

# the known-answer world where the asset leans benign and the standing change scopes
# the approval to a range that excludes the alert's destination
SCOPED_ASSET = {"name": HOST, "ipAddress": HOST_IP, "hostName": HOST,
                "description": "Vendor support jump host. Sessions to the vendor support "
                               "portal are expected. The vendor rotates portal addresses."}
SCOPED_CHANGE = {"number": "CHG-7102", "state": "Implement", "approval": "approved",
                 "short_description": "Vendor support portal egress",
                 "description": f"Approved standing change: {HOST} may reach the vendor support "
                                "portal range 198.51.100.0/24 only. Any other destination is "
                                "not covered by this change.",
                 "start_date": "2026-01-01 00:00:00", "end_date": "2026-12-31 23:59:00"}


def test_a_verdict_that_quotes_the_change_scope_is_not_contradicted_by_that_change():
    text = (f"{HOST} ({HOST_IP}) is beaconing to {IP}, outside its approved egress scope "
            "(CHG-7102 covers 198.51.100.0/24 only).")
    c = {"id": "v", "disposition": "true_positive", "confidence": 0.7, "summary": text,
         "findings": [{"claim": text, "evidence": ["a"]}]}
    p = check(c, preread=pre(asset=[SCOPED_ASSET], change={"result": [SCOPED_CHANGE]}))
    assert p["status"] == "read" and p["contradicted_by"] == []
    assert p["preread"]["relevant"] == [] and p["preread"]["hold"] is False
    # the same change does contradict a verdict that accuses an address it names
    named = {**SCOPED_CHANGE, "description": SCOPED_CHANGE["description"] + f" Also {IP}."}
    p = check(c, preread=pre(asset=[SCOPED_ASSET], change={"result": [named]}))
    assert p["status"] == "contradicted"


def test_every_hold_names_the_record_that_caused_it():
    # a conflict hold (the turn's own contradiction) says which kinds
    p = check(card(), preread=pre(change={"result": [chg(WINDOW_OPEN)]}))
    r = p["preread"]
    assert r["hold"] is True and (r["relevant"] or r.get("conflict") or r.get("unparsed_record"))
    c2 = check(card(), reg={**UNREAD, "asset": __import__("test_evidence_score_premise").asset_read(
        SANDBOX_ASSET)}, preread=pre(asset=[], change=[]))
    r2 = c2["preread"]
    assert c2["status"] == "contradicted" and r2["hold"] is True
    assert r2["conflict"] == ["asset"] and r2["relevant"] == []
