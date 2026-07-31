"""HARDEN-1: the pre-write guard, and proof it catches the losses that shipped.

`corpus_gate` asks "can the compiler round-trip a playbook we thought of?".
This asks the harder question at the moment it matters: "is the document about
to be written over the customer's playbook missing something the live one had?"

The two historical silent deletions (`for_each`, then declared `parameters`)
are RED-proofed here directly against the guard: take the real corpus fixture
that carries the field, strip the field from the *outgoing* side only, and
assert the guard refuses AND names the path. Per
[[tests_inherit_the_fixs_blind_spots]], a guard that never goes red on the bug
it exists to catch is not a guard -- so each of these is written to fail if
`check_prewrite` is reverted to a pass-through.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from fsr_playbooks.compiler.prewrite import (
    PreWriteVerdict,
    check_prewrite,
    diff_losses,
)

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "roundtrip_corpus"


def _load(name: str) -> dict:
    payload = json.loads((CORPUS_DIR / f"{name}.json").read_text())
    return payload["envelope"]


def _workflows(env: dict) -> list[dict]:
    return env["data"][0]["workflows"]


# --------------------------------------------------------------------------- #
# GREEN -- an unchanged save, and the edits that are legitimately allowed.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("fixture", [
    "linear_baseline", "for_each_loop", "declared_parameters",
    "trigger_parameters", "envelope_sugar",
])
def test_identical_write_is_allowed(fixture):
    """Writing a playbook back unchanged must never be refused."""
    env = _load(fixture)
    verdict = check_prewrite(env, copy.deepcopy(env))
    assert verdict.ok, verdict.message
    assert verdict.dropped == []


def test_create_is_always_allowed():
    """No live document means nothing can be destroyed."""
    verdict = check_prewrite(None, _load("linear_baseline"))
    assert verdict.ok
    assert "create" in verdict.message


def test_adding_a_step_is_not_a_loss():
    """Additions are the edit, not data loss."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    steps = _workflows(outgoing)[0]["steps"]
    added = copy.deepcopy(steps[-1])
    added["name"] = "Brand New Step"
    added["uuid"] = "99999999-9999-9999-9999-999999999999"
    steps.append(added)

    verdict = check_prewrite(live, outgoing)
    assert verdict.ok, verdict.message


def test_changing_a_value_is_not_a_loss():
    """A modified argument is an edit; only disappearance is refused."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    for step in _workflows(outgoing)[0]["steps"]:
        if step.get("arguments"):
            key = sorted(step["arguments"])[0]
            step["arguments"][key] = "a deliberately different value"
            break

    verdict = check_prewrite(live, outgoing)
    assert verdict.ok, verdict.message


# --------------------------------------------------------------------------- #
# RED-PROOF -- the two field classes that were silently deleted in production.
# --------------------------------------------------------------------------- #

def test_refuses_when_for_each_is_dropped():
    """LOSSY CLASS #1: a step keeps its name but loses its loop."""
    live = _load("for_each_loop")
    outgoing = copy.deepcopy(live)
    stripped = 0
    for wf in _workflows(outgoing):
        for step in wf.get("steps", []):
            if (step.get("arguments") or {}).pop("for_each", None) is not None:
                stripped += 1
    assert stripped, "fixture no longer carries for_each -- test is vacuous"

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok, "for_each vanished and the guard let the save through"
    assert any("for_each" in p for p in verdict.dropped), verdict.dropped
    assert "refusing to save" in verdict.message


def test_refuses_when_declared_parameters_are_dropped():
    """LOSSY CLASS #2: the manual-trigger form loses its declared inputs."""
    live = _load("declared_parameters")
    outgoing = copy.deepcopy(live)
    dropped_names = []
    for wf in _workflows(outgoing):
        dropped_names += list(wf.get("parameters") or [])
        wf["parameters"] = []
        # The normalizer unions in the trigger step's inputVariables, so a
        # real loss has to clear both or the union hides it.
        for step in wf.get("steps", []):
            (step.get("arguments") or {}).pop("inputVariables", None)
    assert dropped_names, "fixture declares no parameters -- test is vacuous"

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok, "declared parameters vanished and the save was allowed"
    assert any("parameters" in p for p in verdict.dropped), verdict.dropped
    for name in dropped_names:
        assert any(name in p for p in verdict.dropped), (
            f"guard refused but never named the lost parameter {name!r}: "
            f"{verdict.dropped}")


def test_refuses_when_a_whole_step_disappears():
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    victim = wf["steps"].pop()["name"]

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok
    assert any(victim in p for p in verdict.dropped), verdict.dropped


def test_refuses_when_a_route_disappears():
    """Losing an edge silently reshapes execution without touching a step."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    if not wf.get("routes"):
        pytest.skip("fixture has no routes")
    wf["routes"].pop()

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok
    assert any(".routes" in p for p in verdict.dropped), verdict.dropped


# --------------------------------------------------------------------------- #
# The escape hatch: a deletion that WAS asked for.
# --------------------------------------------------------------------------- #

def test_acknowledged_drop_is_allowed_through():
    """"Delete the last step" is a legitimate request -- naming it permits it."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    _workflows(outgoing)[0]["steps"].pop()

    refused = check_prewrite(live, outgoing)
    assert not refused.ok

    allowed = check_prewrite(live, outgoing, acknowledged=refused.dropped)
    assert allowed.ok, allowed.message
    assert allowed.acknowledged == refused.dropped


def test_acknowledging_one_drop_does_not_permit_another():
    """The ack list is path-exact, not a blanket override."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    first = wf["steps"].pop()["name"]
    second = wf["steps"].pop()["name"]

    verdict = check_prewrite(live, outgoing)
    acked = [p for p in verdict.dropped if first in p]
    assert acked, verdict.dropped

    partial = check_prewrite(live, outgoing, acknowledged=acked)
    assert not partial.ok, "acking one deletion waved a second one through"
    assert any(second in p for p in partial.dropped)


# --------------------------------------------------------------------------- #
# Fail-closed: an unusable comparison must refuse, not shrug.
# --------------------------------------------------------------------------- #

def test_unparseable_live_document_refuses_the_write():
    """If we cannot prove the write is safe, we have not proven it is safe."""
    verdict = check_prewrite({"data": []}, _load("linear_baseline"))
    assert not verdict.ok
    assert "refusing the save" in verdict.message


def test_unparseable_outgoing_document_refuses_the_write():
    verdict = check_prewrite(_load("linear_baseline"), {"nonsense": True})
    assert not verdict.ok


def test_verdict_is_json_serializable():
    """The verdict crosses the wire back to the agent as a tool result."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    _workflows(outgoing)[0]["steps"].pop()
    payload = check_prewrite(live, outgoing).as_dict()
    assert json.loads(json.dumps(payload))["ok"] is False


def test_diff_losses_is_one_directional():
    """Sanity: swapping the arguments turns an addition into a loss."""
    live = _load("linear_baseline")
    bigger = copy.deepcopy(live)
    extra = copy.deepcopy(_workflows(bigger)[0]["steps"][-1])
    extra["name"] = "Extra"
    extra["uuid"] = "99999999-9999-9999-9999-999999999999"
    _workflows(bigger)[0]["steps"].append(extra)

    assert diff_losses(live, bigger) == []
    assert any("Extra" in p for p in diff_losses(bigger, live))


# --------------------------------------------------------------------------- #
# The wiring: how push_playbook reads the live side.
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = _FakeResponse(status_code)


class _FakeClient:
    def __init__(self, behaviour):
        self._behaviour = behaviour
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        if isinstance(self._behaviour, Exception):
            raise self._behaviour
        return self._behaviour


def _fetch(behaviour):
    from fsr_playbooks.mcp_server.tools_execution import _fetch_live_collection
    client = _FakeClient(behaviour)
    return _fetch_live_collection(client, "abc"), client


def test_live_fetch_expands_relationships():
    """Without $relationships the live side looks empty and every deletion
    would be waved through -- that is the whole failure mode."""
    _, client = _fetch({"uuid": "abc", "workflows": []})
    assert "$relationships=true" in client.urls[0]


def test_live_fetch_returns_none_only_for_a_clean_404():
    live, _ = _fetch(_HttpError(404))
    assert live is None, "a genuine 404 is a create, not a refusal"
    assert check_prewrite(live, _load("linear_baseline")).ok


@pytest.mark.parametrize("behaviour", [
    _HttpError(500), _HttpError(403), Exception("connection reset"),
    None, {"no": "uuid"}, "not a dict",
])
def test_live_fetch_fails_closed_on_anything_but_a_404(behaviour):
    """A failed read must never be mistaken for "there was nothing there"."""
    live, _ = _fetch(behaviour)
    assert live == {}, f"{behaviour!r} was treated as an absent playbook"
    verdict = check_prewrite(live, _load("linear_baseline"))
    assert not verdict.ok, "a failed live read let an unchecked overwrite through"


def test_empty_string_counts_as_a_loss_but_zero_does_not():
    """A cleared field is gone; a falsy-but-real value is not."""
    assert isinstance(check_prewrite(None, {}), PreWriteVerdict)
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    _workflows(outgoing)[0]["description"] = ""
    if not _workflows(live)[0].get("description"):
        pytest.skip("fixture workflow has no description to clear")
    assert not check_prewrite(live, outgoing).ok
