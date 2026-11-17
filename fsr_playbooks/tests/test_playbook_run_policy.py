"""run_playbook / resume_playbook: the host's run gate, its annotations, and
the plain-identifier rule for anything that reaches a request URL.

No box -- a stub live client whose ``playbooks`` records every trigger. The
invariants:
  - No host gate => a run proceeds (standalone has always been able to run a
    playbook; on the LLM path tier 3 still cards it).
  - A host gate that refuses => nothing is triggered, its envelope is returned;
    it is told whether a human approved the call, and which action it is.
  - A gate that raises => refused (an unreadable policy is not consent).
  - Host annotations land on the run result.
  - A ``record`` that is not a plain ``/api/3/<module>/<uuid>`` IRI, or a
    ``module`` that is not a plain name, is refused before any lookup.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_playbook_run as tp


class _Playbooks:
    def __init__(self):
        self.triggered = []
        self.finds = []

    def _resolve_uuid(self, playbook):
        return "pb-uuid"

    def get_definition(self, uuid, *, relationships=True):
        raise AttributeError("no definition")  # a manual playbook

    def trigger(self, playbook, *, records=None, inputs=None, follow=False,
                timeout=300):
        self.triggered.append({"playbook": playbook, "records": records})
        return {"status": "finished", "ok": True}

    def find(self, **kw):
        self.finds.append(kw)
        return []

    def approval(self, run_pk, *, decision="approve", **_kw):
        return {"task_id": "t"}

    def get_execution(self, run_pk, **_kw):
        return {"status": "finished"}


class _Client:
    base_url = ""

    def __init__(self):
        self.playbooks = _Playbooks()
        self.paths = []

    def get(self, path, params=None, **_kw):
        self.paths.append(path)
        return {}


@pytest.fixture
def box(monkeypatch):
    client = _Client()
    monkeypatch.setattr(_shared, "_live_client", lambda: client)
    monkeypatch.setattr(_shared, "active_record_iri", lambda: None)
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_GATE", None)
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_ANNOTATOR", None)
    return client


def _refusing_gate(calls):
    def gate(playbook, approved, action):
        calls.append((playbook, approved, action))
        if approved:
            return None
        return {"ok": False, "code": f"{action}_not_permitted", "message": "no"}
    return gate


# --- the gate ---------------------------------------------------------------

def test_no_host_gate_permits_a_run(box):
    out = tp.run_playbook(playbook="Block IP")
    assert out["ok"] is True and out["triggered"] is True
    assert [t["playbook"] for t in box.playbooks.triggered] == ["Block IP"]


def test_a_refusing_gate_stops_the_run_before_anything_is_triggered(box, monkeypatch):
    calls = []
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_GATE", _refusing_gate(calls))
    out = tp.run_playbook(playbook="Block IP")
    assert out["code"] == "run_not_permitted"
    assert box.playbooks.triggered == []
    assert calls == [("Block IP", False, "run")]


def test_an_approved_call_is_told_to_the_gate(box, monkeypatch):
    calls = []
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_GATE", _refusing_gate(calls))
    with tp.approved_dispatch():
        out = tp.run_playbook(playbook="Block IP")
    assert out["ok"] is True
    assert calls == [("Block IP", True, "run")]


def test_a_gate_that_raises_refuses(box, monkeypatch):
    def boom(*_a):
        raise RuntimeError("policy store down")
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_GATE", boom)
    out = tp.run_playbook(playbook="Block IP")
    assert out["code"] == "run_not_permitted" and box.playbooks.triggered == []


def test_resume_asks_the_same_gate_as_a_resume(box, monkeypatch):
    calls = []
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_GATE", _refusing_gate(calls))
    out = tp.resume_playbook(run="9046")
    assert out["code"] == "resume_not_permitted"
    assert calls == [("", False, "resume")]


def test_annotations_land_on_the_result(box, monkeypatch):
    monkeypatch.setattr(_shared, "_PLAYBOOK_RUN_ANNOTATOR",
                        lambda pb: {"unlisted": True} if pb == "Block IP" else {})
    assert tp.run_playbook(playbook="Block IP")["unlisted"] is True
    assert "unlisted" not in tp.run_playbook(playbook="Other")


# --- plain identifiers ------------------------------------------------------

_BAD_RECORDS = [
    "/api/3/alerts/../people/u1",
    "/api/3/alerts/u1?$relationships=true",
    "/api/3/alerts/u1/../../x",
    "/api/3/al%2Ferts/u1",
    "/api/3//u1",
    "alerts:u1",
    "99999999-9999-9999-9999-999999999999",
]


@pytest.mark.parametrize("record", _BAD_RECORDS)
def test_a_record_that_is_not_a_plain_iri_is_refused(box, record):
    out = tp.run_playbook(playbook="Block IP", record=record)
    assert out["ok"] is False and out["code"] == "bad_record", out
    assert box.playbooks.triggered == [] and box.paths == []


@pytest.mark.parametrize("record", _BAD_RECORDS)
def test_the_precard_check_refuses_it_too(box, record, monkeypatch):
    monkeypatch.setattr(tp, "_precard_playbook", lambda args: None)
    out = tp.precard_validate({"playbook": "Block IP", "record": record})
    assert out and out["code"] == "bad_record", out
    assert box.paths == []


def test_a_plain_record_iri_passes(box):
    out = tp.run_playbook(playbook="Block IP",
                          record="/api/3/alerts/5b23794a-a657-4169-97d3-98698126d59f")
    assert out["ok"] is True
    assert box.playbooks.triggered[0]["records"].endswith("98698126d59f")


@pytest.mark.parametrize("module", ["alerts/../people", "alerts/x", "al erts"])
def test_list_module_playbooks_refuses_a_module_that_is_not_a_name(box, module):
    out = tp.list_module_playbooks(module=module)
    assert out["ok"] is False and out["code"] == "bad_module", out
    assert box.playbooks.finds == []


def test_list_module_playbooks_takes_a_plain_name(box):
    out = tp.list_module_playbooks(module="ztpf_devices")
    assert out["ok"] is True and box.playbooks.finds


def test_a_run_reference_is_reduced_to_digits():
    assert tp._run_pk_of("/wf/api/workflows/2971/") == "2971"
    assert tp._run_pk_of("2971?x=1") == ""
    assert tp._run_pk_of("../2971") == "2971"
    assert tp._run_pk_of("29/../71x") == ""
