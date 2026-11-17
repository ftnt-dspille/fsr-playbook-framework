"""``run_playbook`` failure reporting -- from stored live sessions where three
consecutive "Validate this metadata source by running the 'Get Metadata Source
Data on Device' playbook" turns all ended in an undiagnosable failure.

Two defects, both "the tool hands the model less than it needs":

  * the run was fired down the recordless ``notrigger`` route with no record
    bound, so the playbook died reading ``vars.input.records[0]``
    ("list object has no element 0", run pk 6800, ``env.input.records: []``).
    A record-action playbook without a record CANNOT succeed -- refuse up front.
  * the reported ``run`` was shaped from the run LIST, whose ``error_message``
    is always null, so the agent could only say "it failed and did not return
    data". The populated message + failing step live on the step-detail fetch.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_playbook_run as tp


class _InstantClock:
    """`time` stand-in whose `sleep` advances a virtual clock instead of
    blocking, so the run-polling deadlines cost no wall time."""

    def __init__(self):
        import time as _t
        self._t = _t
        self._offset = 0.0

    def sleep(self, seconds):
        self._offset += max(0.0, float(seconds))

    def monotonic(self):
        return self._t.monotonic() + self._offset

    def time(self):
        return self._t.time() + self._offset

    def __getattr__(self, name):
        return getattr(self._t, name)


@pytest.fixture(autouse=True)
def _instant_playbook_polling(monkeypatch):
    monkeypatch.setattr(tp, "time", _InstantClock())


PB = "Get Metadata Source Data on Device"
ACTION_DEF = {"steps": [
    {"stepType": {"name": "cybersponse.action"},
     "arguments": {"route": "route-uuid",
                   "resources": ["ztpf_metadata_sources"]}},
]}
MANUAL_DEF = {"steps": [{"stepType": {"name": "cybersponse.trigger"},
                         "arguments": {}}]}


class _Playbooks:
    def __init__(self, *, definition=None, result=None, failure=None):
        self._definition = definition
        self._result = result or {"status": "finished", "ok": True}
        self._failure = failure
        self.triggered = []
        self.failure_calls = []

    def _resolve_uuid(self, playbook):
        return "pb-uuid"

    def get_definition(self, uuid, *, relationships=True):
        if self._definition is None:
            raise AttributeError("no definition")
        return self._definition

    def trigger(self, playbook, *, records=None, inputs=None, follow=False,
                timeout=300):
        self.triggered.append({"playbook": playbook, "records": records})
        return self._result

    def trigger_action(self, route_uuid, *, module, record_uuid,
                       playbook_uuid=None, env=None):
        self.triggered.append({"route": route_uuid, "module": module,
                               "record_uuid": record_uuid})
        return {"task_ids": ["t"]}

    def wait_for_run(self, **_kw):
        return self._result

    def run_failure(self, pk):
        self.failure_calls.append(pk)
        if isinstance(self._failure, Exception):
            raise self._failure
        return self._failure


class _Client:
    def __init__(self, playbooks):
        self.playbooks = playbooks

    def get(self, path, params=None, **_kw):
        return {}


@pytest.fixture
def install(monkeypatch):
    def _install(**kw):
        pb = _Playbooks(**kw)
        monkeypatch.setattr(_shared, "_live_client", lambda: _Client(pb))
        return pb
    return _install


@pytest.fixture(autouse=True)
def _no_mounted_record(monkeypatch):
    """Default: nothing mounted. Tests that want a record set it explicitly."""
    monkeypatch.setattr(_shared, "active_record_iri", lambda: "")


# --------------------------------------------------------------------------- #
# a record-action playbook with no record is refused, not fired into failure
# --------------------------------------------------------------------------- #
def test_record_action_playbook_without_a_record_is_refused(install):
    pb = install(definition=ACTION_DEF)
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is False and out["code"] == "record_required"
    assert out["triggered"] is False, \
        "a run that cannot succeed must not be fired at all"
    assert pb.triggered == [], "nothing should reach the box"
    assert out["modules"] == ["ztpf_metadata_sources"]
    # The message has to be actionable -- name the module to search.
    assert "ztpf_metadata_sources" in out["message"]
    assert "search_module_records" in out["message"]


def test_mounted_record_is_used_and_routes_through_the_action_trigger(
        install, monkeypatch):
    monkeypatch.setattr(
        _shared, "active_record_iri",
        lambda: "/api/3/ztpf_metadata_sources/"
                "5b23794a-a657-4169-97d3-98698126d59f")
    pb = install(definition=ACTION_DEF, result={"status": "finished", "ok": True})
    monkeypatch.setattr(tp, "_wait_run_or_awaiting",
                        lambda *a, **k: ({"status": "finished", "ok": True},
                                         "terminal"))
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is True
    assert pb.triggered[0]["route"] == "route-uuid", \
        "a record-action playbook must NOT go down the recordless notrigger route"
    assert pb.triggered[0]["module"] == "ztpf_metadata_sources"


def test_a_manual_playbook_without_a_record_still_runs(install):
    """The guard is scoped to record-action playbooks -- a manual-trigger
    playbook legitimately needs no record and must not be blocked."""
    pb = install(definition=MANUAL_DEF, result={"status": "finished", "ok": True})
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is True
    assert pb.triggered[0]["records"] is None


def test_unresolvable_definition_does_not_block_the_run(install):
    """Definition lookup is best-effort; if it fails we must fall through to the
    manual path rather than refusing a playbook we simply couldn't inspect."""
    pb = install(definition=None, result={"status": "finished", "ok": True})
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is True and pb.triggered


# --------------------------------------------------------------------------- #
# a failed run explains itself
# --------------------------------------------------------------------------- #
JINJA_ERR = ("CS-WF-5: Inappropriate use of Jinja key: 'list object has no "
             "element 0' in Jinja template '{%- set in = "
             "vars.input.records[0].inputParameters -%}'")


def test_failed_run_carries_the_real_error_message(install):
    pb = install(definition=MANUAL_DEF,
                 # what the run LIST gives us: a failure with no reason
                 result={"status": "failed", "error_message": None, "pk": "6800"},
                 failure={"status": "failed", "failing_step": "Get Data",
                          "error_message": JINJA_ERR, "pk": "6800"})
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is False and out["status"] == "failed"
    assert out["failure"]["error_message"] == JINJA_ERR, \
        "the agent must be able to say WHY, not just that it failed"
    assert out["failure"]["failing_step"] == "Get Data"
    assert pb.failure_calls == ["6800"]


def test_pk_is_recovered_from_the_run_iri(install):
    pb = install(definition=MANUAL_DEF,
                 result={"status": "failed",
                         "@id": "/wf/api/historical-workflows/6800/"},
                 failure={"failing_step": "s", "error_message": "boom"})
    out = tp.run_playbook(playbook=PB)
    assert pb.failure_calls == ["6800"] and out["failure"]["error_message"] == "boom"


def test_successful_run_is_not_diagnosed(install):
    pb = install(definition=MANUAL_DEF,
                 result={"status": "finished", "ok": True, "pk": "1"},
                 failure={"failing_step": "x", "error_message": "y"})
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is True and "failure" not in out
    assert pb.failure_calls == [], "no detail fetch on a run that succeeded"


def test_diagnosis_lookup_failure_never_masks_the_run_result(install):
    """A best-effort bonus must not turn a reported failure into an exception."""
    install(definition=MANUAL_DEF,
            result={"status": "failed", "pk": "6800"},
            failure=RuntimeError("detail endpoint down"))
    out = tp.run_playbook(playbook=PB)
    assert out["ok"] is False and out["status"] == "failed"
    assert "failure" not in out


def test_empty_diagnosis_is_omitted_rather_than_reported_as_null(install):
    install(definition=MANUAL_DEF,
            result={"status": "failed", "pk": "6800"},
            failure={"failing_step": None, "error_message": None})
    out = tp.run_playbook(playbook=PB)
    assert "failure" not in out, \
        "an all-null failure block is noise -- omit it"


def test_not_followed_run_is_not_diagnosed(install):
    pb = install(definition=MANUAL_DEF, result={"status": "failed", "pk": "6800"},
                 failure={"failing_step": "s", "error_message": "boom"})
    out = tp.run_playbook(playbook=PB, follow=False)
    assert out["ok"] is True and pb.failure_calls == [], \
        "fire-and-forget has no terminal status to explain yet"
