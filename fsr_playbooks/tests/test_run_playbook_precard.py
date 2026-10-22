"""`run_playbook`'s pre-card validator: an un-runnable name must never be carded.

Live, a ztpf session asked to "run these steps" and the agent called
``run_playbook("Create Next SingleLo Interface")`` -- an automation-step *label*,
not a playbook. Because tier-3 suspends into an approval card WITHOUT running the
tool body, the invented name was never resolved: the analyst got a card that
looked legitimate and could only have failed after approval. The session ended
there, thumbs-down.

The validator resolves the name at gate time and bounces `unknown_playbook` (with
the real candidate list) instead. It must be strictly fail-open: it refuses ONLY
on a lookup that succeeded and matched nothing.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server import tools_playbook_run as tp


class _Playbooks:
    def __init__(self, definition=None, raises=None):
        self.definition = definition
        self.raises = raises

    def get_definition(self, uuid, *, relationships=True):
        if self.raises is not None:
            raise self.raises
        return self.definition or {}

    def find(self, **_kw):
        return []


class _Client:
    """A stub whose ``get`` answers the workflows-by-name lookup."""

    def __init__(self, members, *, raises=None, playbooks=None):
        self.members = members
        self.raises = raises
        self.playbooks = playbooks or _Playbooks()
        self.paths: list[str] = []

    def get(self, path, params=None, **_kw):
        self.paths.append(path)
        if self.raises is not None:
            raise self.raises
        if "/workflows" in path:
            return {"hydra:member": list(self.members)}
        return {}


@pytest.fixture
def bind(monkeypatch):
    """Bind a stub live client; also neutralize the candidate-list lookup so a
    test asserts on the refusal itself, not on discovery."""
    def _bind(client):
        monkeypatch.setattr(_shared, "_live_client", lambda: client)
        monkeypatch.setattr(tp, "_runnable_candidates",
                            lambda limit=12: ["Create Run Group and Execute Steps"])
        return client
    return _bind


# --------------------------------------------------------------------------- #
# the refusals
# --------------------------------------------------------------------------- #
def test_invented_name_is_refused_with_candidates(bind):
    """The exact live defect: a step label passed as a playbook name."""
    bind(_Client(members=[]))
    out = tp.precard_validate({"playbook": "Create Next SingleLo Interface"})
    assert out is not None, "an invented name must NOT reach an approval card"
    assert out["ok"] is False
    assert out["code"] == "unknown_playbook"
    assert out["candidates"] == ["Create Run Group and Execute Steps"]
    # The message has to steer away from the retry-a-variation loop.
    assert "list_module_playbooks" in out["message"]


def test_real_name_falls_through_to_the_card(bind):
    bind(_Client(members=[{"name": "Create Run Group and Execute Steps",
                           "uuid": "u-1", "isActive": True}]))
    assert tp.precard_validate(
        {"playbook": "Create Run Group and Execute Steps"}) is None


def test_deactivated_playbook_is_refused(bind):
    """A disabled playbook resolves but is absent from the Execute menu -- a
    trigger on it cannot succeed, so carding it is asking for a doomed approval."""
    bind(_Client(members=[{"name": "Queue Device Actions - deprecated",
                           "uuid": "u-2", "isActive": False}]))
    out = tp.precard_validate({"playbook": "Queue Device Actions - deprecated"})
    assert out is not None and out["code"] == "playbook_inactive"


def test_name_match_is_exact_not_first_row(bind):
    """FSR's ?name= lookup can return near matches; picking row 0 would let a
    typo resolve to a real-but-different playbook and run the WRONG automation."""
    bind(_Client(members=[
        {"name": "Create Run Group and Execute Steps v2", "uuid": "u-3", "isActive": True},
        {"name": "Create Run Group and Execute Steps", "uuid": "u-4", "isActive": True},
    ]))
    assert tp.precard_validate(
        {"playbook": "Create Run Group and Execute Steps"}) is None
    wf = tp._workflow_by_name(
        _Client(members=[
            {"name": "Create Run Group and Execute Steps v2", "uuid": "u-3"},
            {"name": "Create Run Group and Execute Steps", "uuid": "u-4"},
        ]), "Create Run Group and Execute Steps")
    assert wf["uuid"] == "u-4", "the EXACT name must win over row order"


# --------------------------------------------------------------------------- #
# fail-open -- refusing a legitimate run is worse than carding a doomed one
# --------------------------------------------------------------------------- #
def test_no_client_is_fail_open(monkeypatch):
    monkeypatch.setattr(_shared, "_live_client", lambda: None)
    assert tp.precard_validate({"playbook": "Anything"}) is None


def test_transport_error_is_fail_open(bind):
    bind(_Client(members=[], raises=RuntimeError("box unreachable")))
    assert tp.precard_validate({"playbook": "Create Run Group and Execute Steps"}) is None, (
        "an unreachable box must not turn into 'this playbook does not exist'")


def test_empty_playbook_arg_is_left_to_the_arg_gate(bind):
    bind(_Client(members=[]))
    assert tp.precard_validate({"playbook": ""}) is None
    assert tp.precard_validate({}) is None


def test_uuid_arg_is_only_checked_for_liveness(bind):
    uuid = "0afe7bb1-e842-43d4-975e-b9f60d9d01ce"
    c = bind(_Client(members=[], playbooks=_Playbooks(definition={"isActive": True})))
    assert tp.precard_validate({"playbook": uuid}) is None
    assert not any("/workflows?" in p for p in c.paths), (
        "a uuid is already resolved identity -- no name lookup needed")


def test_uuid_of_a_deactivated_playbook_is_refused(bind):
    uuid = "0afe7bb1-e842-43d4-975e-b9f60d9d01ce"
    bind(_Client(members=[], playbooks=_Playbooks(
        definition={"name": "Old One", "isActive": False})))
    out = tp.precard_validate({"playbook": uuid})
    assert out is not None and out["code"] == "playbook_inactive"


class _TypedWorkflow:
    """What pyfsr ACTUALLY returns from ``playbooks.get_definition``: a typed
    ``Workflow`` model, not a dict. The first cut of the validator tested
    ``isinstance(defn, dict)``, so a deactivated playbook referenced by UUID
    sailed straight through to an approval card -- invisible offline (the stub
    returned dicts everywhere) and caught only by probing a live box."""

    def __init__(self, name, is_active):
        self.name = name
        self.isActive = is_active


def test_uuid_of_a_deactivated_playbook_is_refused_when_typed(bind):
    uuid = "006e0eee-862f-4316-bcd9-554632dee049"
    bind(_Client(members=[], playbooks=_Playbooks(
        definition=_TypedWorkflow("Get IP Reputation", False))))
    out = tp.precard_validate({"playbook": uuid})
    assert out is not None and out["code"] == "playbook_inactive"
    assert out["playbook"] == "Get IP Reputation", \
        "the refusal must name the playbook, read off the typed model"


def test_typed_active_workflow_falls_through(bind):
    uuid = "006e0eee-862f-4316-bcd9-554632dee049"
    bind(_Client(members=[], playbooks=_Playbooks(
        definition=_TypedWorkflow("Live One", True))))
    assert tp.precard_validate({"playbook": uuid}) is None


def test_name_lookup_reads_typed_members_too(bind):
    """The ?name= path can hand back typed rows as well -- the same blind spot."""
    bind(_Client(members=[_TypedWorkflow("Deactivated PB", False)]))
    out = tp.precard_validate({"playbook": "Deactivated PB"})
    assert out is not None and out["code"] == "playbook_inactive"


@pytest.mark.parametrize("obj,expected", [
    ({"isActive": False}, False),
    (_TypedWorkflow("x", False), False),
    ({}, None),
    (_TypedWorkflow("x", None), None),
])
def test_field_of_reads_dicts_and_models_alike(obj, expected):
    assert tp._field_of(obj, "isActive") is expected


def test_uuid_lookup_failure_is_fail_open(bind):
    uuid = "0afe7bb1-e842-43d4-975e-b9f60d9d01ce"
    bind(_Client(members=[], playbooks=_Playbooks(raises=RuntimeError("nope"))))
    assert tp.precard_validate({"playbook": uuid}) is None


def test_candidate_lookup_failure_still_refuses(monkeypatch):
    """Discovery is a bonus ON the refusal -- a broken discovery must not restore
    the card for a name we already KNOW does not exist."""
    monkeypatch.setattr(_shared, "_live_client", lambda: _Client(members=[]))
    monkeypatch.setattr(tp, "list_module_playbooks",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    out = tp.precard_validate({"playbook": "Ghost"})
    assert out is not None and out["code"] == "unknown_playbook"
    assert out["candidates"] == []


def test_runnable_candidates_swallows_discovery_errors(monkeypatch):
    monkeypatch.setattr(tp, "list_module_playbooks",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert tp._runnable_candidates() == []


def test_runnable_candidates_ignores_a_failed_listing(monkeypatch):
    monkeypatch.setattr(tp, "list_module_playbooks",
                        lambda *a, **k: {"ok": False, "code": "no_fsr_configured"})
    assert tp._runnable_candidates() == []


def test_runnable_candidates_returns_names(monkeypatch):
    monkeypatch.setattr(tp, "list_module_playbooks", lambda *a, **k: {
        "ok": True, "playbooks": [{"name": "A"}, {"name": "B"}, {"nope": 1}]})
    assert tp._runnable_candidates() == ["A", "B"]
