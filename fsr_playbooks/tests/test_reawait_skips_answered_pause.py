"""After a submit, the wait for the run's next pause must not stop on the pause
just answered.

The resume is asynchronous: the first reads still show the run `awaiting` on the
answered input (or `awaiting` with nothing pending once it is consumed). Live,
that stale read ended the wait on its first poll, so the metadata-source run's
next pause, "Data Collected" about 12 seconds later, never surfaced and the chat
said "the run is still active".
"""
from __future__ import annotations

from fsr_playbooks.mcp_server import tools_playbook_run as tp


class _Playbooks:
    def __init__(self, statuses):
        self.statuses = list(statuses)

    def get_execution(self, run_pk):
        s = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"status": s}


def _run(monkeypatch, statuses, pending, answered):
    pending = list(pending)
    monkeypatch.setattr(tp, "_pending_input",
                        lambda c, p, r: pending.pop(0) if len(pending) > 1 else pending[0])
    monkeypatch.setattr(tp.time, "sleep", lambda s: None)
    return tp._reawait_after_resume(None, _Playbooks(statuses), "80936", 45, answered=answered)


NEXT = {"manual_input_id": 654, "title": "Data Collected", "fields": [],
        "options": [{"option": "Ok"}, {"option": "Save Example"}]}


def test_the_answered_pause_and_an_empty_read_are_waited_out(monkeypatch):
    old = {"manual_input_id": 653, "title": "Choose a Manager and a Device"}
    form, status = _run(monkeypatch, ["awaiting", "awaiting", "active", "awaiting"],
                        [old, None, NEXT], answered=653)
    assert status == "awaiting" and form["manual_input_id"] == 654


def test_without_an_answered_id_an_awaiting_read_settles_at_once(monkeypatch):
    form, status = _run(monkeypatch, ["awaiting"], [NEXT], answered=None)
    assert form["manual_input_id"] == 654


def test_active_is_still_running(monkeypatch):
    """FortiSOAR 8.0 reports a resumed, running workflow as `active`."""
    form, status = _run(monkeypatch, ["active", "active", "awaiting"], [NEXT], answered=None)
    assert form["manual_input_id"] == 654


def test_a_run_that_ends_still_ends(monkeypatch):
    form, status = _run(monkeypatch, ["awaiting", "finished"], [None], answered=653)
    assert form is None and status == "finished"
