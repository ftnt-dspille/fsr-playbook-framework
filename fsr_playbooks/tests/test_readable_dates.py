"""The model never converts an epoch itself.

Live on Frank, over a tasks/assets persona surface, the model rendered a task
due 2026-10-03 (dueBy=1791046800) as "Jun 2026", and one due 2027-02-01 as
"Feb 1, 2025" -- on both builds of an A/B, so it is the model, not a change.
It was also never told today's date, so "overdue" was a guess.
"""
from __future__ import annotations

import json

from fsr_playbooks.llm import anthropic_provider, openai_provider
from fsr_playbooks.llm._loop_helpers import today_line, with_readable_dates
from fsr_playbooks.llm.turn_plan import TurnBudget, _constraints


def test_epoch_date_fields_get_a_utc_rendering_beside_the_raw_value():
    out = with_readable_dates({"dueBy": 1791046800, "createDate": 1784052208.18})
    assert out["dueBy"] == 1791046800          # raw value untouched: filters use it
    assert out["_dates"] == {"dueBy": "2026-10-03 17:00 UTC",
                             "createDate": "2026-07-14 18:03 UTC"}


def test_milliseconds_and_nested_related_records():
    out = with_readable_dates({"assets": [{"name": "a", "lastSeen": 1791046800000}]})
    assert out["assets"][0]["_dates"] == {"lastSeen": "2026-10-03 17:00 UTC"}


def test_non_dates_are_left_alone():
    rec = {"responseTime": 3600, "severity": 3, "updatedAt": "2026-01-01",
           "id": 1791046800, "dateFormat": "iso", "flag": True}
    assert with_readable_dates(rec) == rec   # no `_dates` key added


def test_the_input_is_not_mutated():
    rec = {"dueBy": 1791046800}
    with_readable_dates(rec)
    assert rec == {"dueBy": 1791046800}


def test_both_providers_show_the_model_the_readable_view():
    for mod in (openai_provider, anthropic_provider):
        text = mod._stringify({"ok": True, "dueBy": 1791046800})
        assert "2026-10-03 17:00 UTC" in json.loads(text)["_dates"]["dueBy"]


def test_today_is_stated_in_every_turn_plan(monkeypatch):
    monkeypatch.setenv("FSRPB_TODAY", "2026-09-27 (Sunday)")
    assert "Today is 2026-09-27 (Sunday), UTC." in _constraints(TurnBudget())


def test_today_defaults_to_the_real_clock(monkeypatch):
    import datetime as dt
    monkeypatch.delenv("FSRPB_TODAY", raising=False)
    now = dt.datetime(2026, 9, 27, 3, tzinfo=dt.timezone.utc)
    assert today_line(now).startswith("Today is 2026-09-27 (Sunday), UTC.")
