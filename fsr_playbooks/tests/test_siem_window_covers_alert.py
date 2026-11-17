"""The SIEM time window reaches the alert, a poll timeout is never a zero, and
an empty answer is typed.

A lookback shorter than the alert's age cannot show the events that drove the
alert (67% of stored SIEM/FAZ/EDR calls with a known record age did that, and
148 of 150 of them came back empty or errored). These tests drive the pub/v2
query engine with a fake FortiSIEM that serves events only inside the submitted
timeRange, the way a real pub/v2 engine does.
"""
from __future__ import annotations

import time as _real_time

import pytest

from fsr_playbooks.mcp_server import tools_triage as TT

NOW = int(_real_time.time())
HOUR = 3600


class FakeFortiSIEM:
    """run_op stand-in: submit records the timeRange; results return only the
    events whose phRecvTime falls inside it. ``progress_at`` is the poll number
    at which progress reaches 100 (None: never finishes)."""

    def __init__(self, events, progress_at=1):
        self.events = events
        self.progress_at = progress_at
        self.range = None
        self.polls = 0
        self.submits = 0

    def __call__(self, connector, op, params, **kw):
        assert op == "execute_api_request", op
        ep = params["endpoint"]
        if ep.endswith("/eventQuery"):
            self.submits += 1
            self.range = (params["payload"]["timeRange"]["from"],
                          params["payload"]["timeRange"]["to"])
            return {"ok": True, "data": {"queryId": "q-1"}}
        if ep.endswith("/progress"):
            self.polls += 1
            done = self.progress_at is not None and self.polls >= self.progress_at
            return {"ok": True, "data": {"progress": 100 if done else 40}}
        if ep.endswith("/events/results"):
            lo, hi = self.range
            rows = [e for e in self.events if lo <= e["epoch"] <= hi]
            return {"ok": True, "data": [
                {"phRecvTime": e["phRecvTime"], "srcIpAddr": "10.20.1.15",
                 "destIpAddr": "198.51.100.77", "destIpPort": 443,
                 "sentBytes64": 612, "hostName": "fin-ws-07",
                 "eventType": "Permitted traffic flow"} for e in rows]}
        raise AssertionError(ep)


def _events(*ages_hours):
    import datetime as dt
    out = []
    for h in ages_hours:
        t = NOW - int(h * HOUR)
        out.append({"epoch": t, "phRecvTime": dt.datetime.fromtimestamp(
            t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


@pytest.fixture
def siem(monkeypatch):
    import fsr_playbooks.execution_api as ea
    monkeypatch.setattr(TT, "_siem_connector", lambda: "fortinet-fortisiemv2")
    monkeypatch.setattr(TT, "_record_hunt_step", lambda *a, **k: None)
    monkeypatch.setattr(_real_time, "sleep", lambda s: None)
    monkeypatch.setattr(TT, "_mounted_alert_epoch", lambda: None, raising=False)

    def install(fake, alert_age_hours=None):
        monkeypatch.setattr(ea, "run_op", fake)
        if alert_age_hours is not None:
            monkeypatch.setattr(TT, "_mounted_alert_epoch",
                                lambda: NOW - alert_age_hours * HOUR, raising=False)
        return fake
    return install


def test_blank_window_reaches_a_26h_old_alert(siem):
    fake = siem(FakeFortiSIEM(_events(25, 26, 30)), alert_age_hours=26)
    out = TT.siem_search_ip("10.20.1.15")
    assert out["ok"] is True
    assert out["covers_alert_time"] is True
    assert out["count"] == 2, "the 25h and 26h events are inside the window"
    assert fake.range[0] <= NOW - 26 * HOUR
    unit = {"m": 60, "h": 3600, "d": 86400}[out["window"][-1]]
    assert int(out["window"][:-1]) * unit >= 27 * HOUR, out["window"]


def test_explicit_short_window_is_widened_to_the_alert(siem):
    fake = siem(FakeFortiSIEM(_events(26)), alert_age_hours=26)
    out = TT.siem_search(by="ip", value="10.20.1.15", window="2h")
    assert out["count"] == 1 and out["covers_alert_time"] is True
    assert fake.range[0] <= NOW - 26 * HOUR


def test_no_alert_time_keeps_the_requested_window_and_says_unknown(siem):
    fake = siem(FakeFortiSIEM(_events(26)))
    out = TT.siem_search_ip("10.20.1.15", window="2h")
    assert out["covers_alert_time"] is None
    assert out["count"] == 0
    assert fake.range[1] - fake.range[0] == 2 * HOUR


def test_empty_answer_is_typed_and_names_next_steps(siem):
    siem(FakeFortiSIEM([]), alert_age_hours=26)
    out = TT.siem_search_ip("10.20.1.99")
    assert out["ok"] is True and out["count"] == 0
    assert out["empty"] is True and out["code"] == "no_events"
    assert out["next"] and all(isinstance(x, str) and x for x in out["next"])


def test_empty_answer_without_alert_time_asks_for_a_wider_window(siem):
    siem(FakeFortiSIEM(_events(26)))
    out = TT.siem_search_ip("10.20.1.15")
    assert out["code"] == "no_events"
    assert any("window" in x for x in out["next"])


def test_poll_timeout_is_not_a_zero(siem):
    siem(FakeFortiSIEM(_events(1), progress_at=None), alert_age_hours=1)
    out = TT.siem_search_ip("10.20.1.15")
    assert out["ok"] is False, "a query still running is not an answer"
    assert out["partial"] is True
    assert out["code"] == "query_timeout"
    assert "count" not in out or out.get("count") != 0
    assert out["unknowns"] and out["next"]
    assert out["delivered"] == {"query_id": "q-1"}


def test_slow_query_that_finishes_inside_the_budget_is_read(siem):
    siem(FakeFortiSIEM(_events(1), progress_at=3), alert_age_hours=1)
    out = TT.siem_search_ip("10.20.1.15")
    assert out["ok"] is True and out["count"] == 1


# --- FortiAnalyzer and FortiEDR share the rule (I1) --------------------------

def test_edr_event_lookback_reaches_an_old_alert(monkeypatch):
    """The EDR default is 90 days; an alert older than that must widen the
    lookback to reach it, and say so. Past the one-year cap it says it does not."""
    from fsr_playbooks.mcp_server import tools_edr as E
    monkeypatch.setattr(TT, "_mounted_alert_epoch", lambda: NOW - 200 * 86400,
                        raising=False)
    days, covers = E._covering_days("90d")
    assert covers is True and days >= 201
    monkeypatch.setattr(TT, "_mounted_alert_epoch", lambda: NOW - 400 * 86400,
                        raising=False)
    assert E._covering_days("90d")[1] is False
    monkeypatch.setattr(TT, "_mounted_alert_epoch", lambda: None, raising=False)
    assert E._covering_days("90d") == (90, None)


def test_faz_window_covers_the_alert_and_flags_it(monkeypatch):
    import fsr_playbooks.execution_api as ea
    monkeypatch.setattr(TT, "_mounted_alert_epoch", lambda: NOW - 26 * HOUR,
                        raising=False)
    seen = {}

    def run_op(connector, op, params, **kw):
        seen.update(params)
        return {"ok": True, "data": {"result": [{"data": []}]}}
    monkeypatch.setattr(ea, "run_op", run_op)
    out = TT.faz_search_ip("10.20.1.15", window="2h")
    assert out["ok"] is True and out["covers_alert_time"] is True
    assert out["code"] == "no_events"
    start = _real_time.strptime(seen["start"][:19], "%Y-%m-%dT%H:%M:%S")
    assert _real_time.mktime(start) - _real_time.timezone <= NOW - 26 * HOUR + 60
