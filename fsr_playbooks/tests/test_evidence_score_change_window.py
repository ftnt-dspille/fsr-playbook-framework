"""Phase 2 step 2h (shadow): a change record explains a rating, or contradicts a
conviction, only if its window covers the alert time. A window that ended before
the alert (or has not begun, or has lapsed) neither explains nor contradicts.
"""
from __future__ import annotations

from test_evidence_score_premise import (
    CDN,
    HOST,
    HOST_IP,
    IP,
    REAL_LOW,
    RECORD,
    alert_read,
    benign_card,
    card,
    change_read,
    entry,
    score,
    vt,
)

from fsr_playbooks.mcp_server._evidence_score import (
    premise_check,
    premise_facts,
    window_covers,
)

ALERT_T = "2026-09-29 13:47:00"  # an alert on this day


def alert_at(t=ALERT_T, host=HOST, dst=IP):
    return entry("get_record", {"iri": f"/api/3/alerts/{RECORD}"},
                 {"uuid": RECORD, "computerName": host, "sourceIp": HOST_IP,
                  "destinationIp": dst, "createDate": t,
                  "description": f"beaconing from {host} to {dst}"})


def chg(start, end, state="Closed", ip=IP, host=HOST):
    return {"result": [{"number": "CHG-7004", "state": state, "approval": "approved",
                        "description": f"Approved: {host} may reach {ip} for the test.",
                        "start_date": start, "end_date": end}]}


OLD = chg("2026-08-18 02:00:00", "2026-08-18 06:00:00")
LIVE = chg("2026-09-29 12:00:00", "2026-09-29 18:00:00", state="Implement")
NOT_YET = chg("2026-10-30 02:00:00", "2026-10-30 06:00:00", state="Scheduled")


def check(c, reg, **kw):
    return premise_check(c, reg, record_subject=RECORD, **kw)


def test_a_window_that_ended_before_the_alert_does_not_contradict_a_conviction():
    reg = {"v": vt(), "alert": alert_at(), "chg": change_read(OLD)}
    p = check(card(), reg)
    assert p["status"] == "read" and p["contradicted_by"] == []


def test_a_window_that_covers_the_alert_still_contradicts_a_conviction():
    p = check(card(), {"v": vt(), "alert": alert_at(), "chg": change_read(LIVE)})
    assert p["status"] == "contradicted"


def test_a_window_that_has_not_begun_does_not_contradict():
    p = check(card(), {"v": vt(), "alert": alert_at(), "chg": change_read(NOT_YET)})
    assert p["status"] == "read"


def test_a_cancelled_or_expired_change_covers_nothing_whatever_its_dates():
    for state in ("Cancelled", "Expired", "Rejected"):
        p = check(card(), {"v": vt(), "alert": alert_at(),
                           "chg": change_read(chg("2026-09-29 12:00:00", "2026-09-29 18:00:00",
                                                  state=state))})
        assert p["status"] == "read", state


def test_an_alert_time_the_turn_does_not_know_is_not_used_against_the_record():
    # no create date on the alert: nothing shows the window missed it
    p = check(card(), {"v": vt(), "alert": alert_read(), "chg": change_read(OLD)})
    assert p["status"] == "contradicted"


def test_a_change_with_no_stated_window_is_unchanged():
    p = check(card(), {"v": vt(), "alert": alert_at(), "chg": change_read()})
    assert p["status"] == "contradicted"


def test_the_alert_time_can_come_from_the_context_the_host_bound():
    reg = {"v": vt(), "chg": change_read(OLD)}
    p = check(card(), reg, known_names=[HOST, HOST_IP],
              known_time=premise_facts({"createDate": ALERT_T})["t"])
    assert p["status"] == "read"


def test_the_alert_time_is_read_through_a_data_wrapper():
    assert premise_facts({"data": {"createDate": ALERT_T}}).get("t") is not None


def test_premise_facts_carry_the_window_and_lapse():
    row = premise_facts(OLD)["rows"][0]
    assert row["window"][0] < row["window"][1]
    assert premise_facts(chg(None, None, state="Cancelled"))["rows"][0]["lapsed"] is True


def test_window_covers_edges():
    t = premise_facts({"createDate": ALERT_T})["t"]
    assert window_covers({"window": [t - 10, t + 10]}, [t])
    assert not window_covers({"window": [t - 20, t - 10]}, [t])
    assert not window_covers({"window": [t + 10, None]}, [t])
    assert window_covers({"window": [None, t + 1]}, [t])
    assert window_covers({}, [t]) and window_covers({"window": [t - 20, t - 10]}, [])


# ---- the explained-rating rule --------------------------------------------------------

def cdn_alert(t=ALERT_T):
    return entry("get_record", {"iri": f"/api/3/alerts/{RECORD}"},
                 {"uuid": RECORD, "computerName": "mkt-ws-31", "destinationIp": CDN,
                  "createDate": t})


def cdn_chg(start, end):
    return entry("run_op", {"connector": "servicenow", "op": "get_all_change_requests"},
                 {"result": [{"number": "CHG-5120", "approval": "approved",
                              "description": f"Approved: mkt-ws-31 pulls from {CDN}.",
                              "start_date": start, "end_date": end}]})


def test_a_change_window_that_covers_the_alert_explains_a_rating():
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(),
           "r": cdn_chg("2026-09-01 00:00:00", "2026-12-31 00:00:00")}
    assert "contradiction" not in score(benign_card(), reg)["capped_by"]


def test_a_change_window_that_ended_before_the_alert_explains_nothing():
    reg = {"v": vt(REAL_LOW, CDN), "alert": cdn_alert(),
           "r": cdn_chg("2026-08-18 02:00:00", "2026-08-18 06:00:00")}
    assert "contradiction" in score(benign_card(), reg)["capped_by"]


def test_a_window_is_ignored_when_the_alert_time_is_unknown():
    reg = {"v": vt(REAL_LOW, CDN),
           "alert": entry("get_record", {"iri": f"/api/3/alerts/{RECORD}"},
                          {"uuid": RECORD, "computerName": "mkt-ws-31", "destinationIp": CDN}),
           "r": cdn_chg("2026-08-18 02:00:00", "2026-08-18 06:00:00")}
    assert "contradiction" not in score(benign_card(), reg)["capped_by"]


# ---- wired through the emit path ----------------------------------------------------

def test_the_emitted_card_ignores_a_change_whose_window_ended_before_the_alert():
    from fsr_playbooks.mcp_server import _citation_validator as cv
    from fsr_playbooks.mcp_server.tools_emit import emit_card
    cv.clear_tool_registry()
    cv.set_result_reader(lambda c, o, p, r: None)
    cv.set_turn_known_context({"computerName": HOST, "sourceIp": HOST_IP,
                               "destinationIp": IP, "createDate": ALERT_T})
    try:
        cv.register_tool_result("call_chg", "run_op",
                                True, {"connector": "servicenow",
                                       "op": "get_all_change_requests"}, OLD)
        r = emit_card(card_type="verdict", payload={
            "disposition": "true_positive", "severity": "high", "confidence": 0.9,
            "summary": f"{HOST} ({HOST_IP}) beacons to {IP}", "unknowns": [],
            "findings": [{"claim": f"{HOST} contacted {IP}", "evidence": ["call_chg"]}]})
        assert r["card"]["premise"]["status"] == "read"
        assert r["card"]["premise"]["contradicted_by"] == []
    finally:
        cv.set_turn_known_context(None)
        cv.set_result_reader(None)
        cv.clear_tool_registry()
