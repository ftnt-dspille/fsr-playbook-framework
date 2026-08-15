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
# The refusal must say WHICH KIND it is, and offer a remedy that exists.
#
# Both classes carry `ok: False`, but only one is acknowledgeable. They were
# once reported under a single code, distinguishable only by `dropped` being
# empty -- so a caller doing the documented thing (re-send the dropped paths)
# retried an unreadable-live refusal with an empty acknowledgement, forever.
# --------------------------------------------------------------------------- #

def _unexpanded(name: str = "linear_baseline") -> dict:
    """A live pull that came back without `?$relationships=true`."""
    live = _load(name)
    live["data"][0].pop("workflows", None)
    return live


def test_field_loss_and_unreadable_live_are_different_codes():
    """The two refusals must not be conflated -- their remedies differ."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    _workflows(outgoing)[0]["steps"].pop()

    loss = check_prewrite(live, outgoing)
    unreadable = check_prewrite(_unexpanded(), _load("linear_baseline"))

    assert loss.code == "would_drop_fields"
    assert unreadable.code == "live_unreadable"
    assert loss.code != unreadable.code, (
        "one code for both refusals leaves `dropped == []` as the only "
        "discriminator, which reads as 'nothing was dropped'"
    )


def test_unreadable_live_is_not_acknowledgeable():
    """No acknowledgement may satisfy a refusal we cannot even diff."""
    for ack in ([], ["anything"], None,
                ["collection.workflows[Simple Note].steps[Set B]"]):
        verdict = check_prewrite(_unexpanded(), _load("linear_baseline"), ack)
        assert not verdict.ok, f"acknowledgement {ack!r} cleared an unreadable live pull"
        assert verdict.code == "live_unreadable"
        assert verdict.dropped == []


def test_unexpanded_live_refuses_a_total_wipe():
    """The 8dbf8b9 case: unexpanded live must not read as 'nothing there'."""
    wipe = _load("linear_baseline")
    wipe["data"][0]["workflows"] = []
    verdict = check_prewrite(_unexpanded(), wipe)
    assert not verdict.ok, "an unexpanded pull approved wiping every workflow"
    assert verdict.code == "live_unreadable"


def test_field_loss_message_names_the_real_parameter():
    """The remedy must name the parameter the caller actually passes.

    `check_prewrite`'s kwarg is `acknowledged`, but the surface a user meets is
    `push_playbook(acknowledged_drops=...)`. The copy shipped naming the former,
    so following it verbatim raised an unknown-argument error.
    """
    import inspect

    from fsr_playbooks.mcp_server.tools_execution import push_playbook

    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    _workflows(outgoing)[0]["steps"].pop()
    message = check_prewrite(live, outgoing).message

    param = "acknowledged_drops"
    assert param in inspect.signature(push_playbook).parameters
    assert f"`{param}`" in message, (
        f"refusal copy must name `{param}`, the parameter the caller passes"
    )


def test_the_documented_remedy_actually_clears_the_refusal():
    """End-to-end on the advice as written: re-send `dropped`, get a pass."""
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    _workflows(outgoing)[0]["steps"].pop()

    refused = check_prewrite(live, outgoing)
    assert refused.code == "would_drop_fields"
    assert refused.dropped, "a field-loss refusal must name what it would drop"

    retried = check_prewrite(live, outgoing, refused.dropped)
    assert retried.ok, retried.message


def test_code_is_empty_when_the_write_is_allowed():
    """`code` is a refusal class; a pass must not carry one."""
    live = _load("linear_baseline")
    assert check_prewrite(live, copy.deepcopy(live)).code == ""
    assert check_prewrite(None, live).code == ""


def test_code_crosses_the_wire():
    """Callers branch on `code`, so `as_dict` must carry it."""
    payload = check_prewrite(_unexpanded(), _load("linear_baseline")).as_dict()
    assert json.loads(json.dumps(payload))["code"] == "live_unreadable"


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


# --------------------------------------------------------------------------- #
# #136 -- the guard over-corrected: it refused deletions it had itself asked
# the caller to make.
#
# Live probe A3 ("delete the Dead End step") was refused with FOUR paths, only
# one of which the caller had any way to reason about:
#
#     - routes[Block IP->Dead End]        entailed by the deletion
#     - routes[Dead End->End]             entailed by the deletion
#     - steps[Block IP].arguments.config  re-derived, environment-dependent
#     - steps[Dead End]                   the actual deletion
#
# A guard whose escape hatch requires the caller to enumerate the guard's own
# internal path grammar -- including consequences it did not author and a field
# the compiler re-derives -- is not an escape hatch. These tests fix the shape
# of the remedy, not just its existence.
# --------------------------------------------------------------------------- #

def _delete_middle_step(live: dict, victim: str = "Set A") -> dict:
    """Remove one step AND the routes that touched it, as a real edit would.

    A caller cannot keep a route whose endpoint no longer exists -- FSR would
    reject the document. So the routes going missing is not an independent
    decision the caller made; it is arithmetic.
    """
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    gone = [s for s in wf["steps"] if s["name"] == victim]
    assert gone, f"fixture has no step {victim!r} -- test is vacuous"
    dead_iris = {s["@id"] for s in gone} | {
        f"/api/3/workflow_steps/{s['uuid']}" for s in gone}
    wf["steps"] = [s for s in wf["steps"] if s["name"] != victim]
    wf["routes"] = [r for r in wf["routes"]
                    if r.get("sourceStep") not in dead_iris
                    and r.get("targetStep") not in dead_iris]
    return outgoing


def test_deleting_a_step_reports_it_but_not_its_routes():
    """The refusal must name the DECISION, not its arithmetic consequences.

    Routes incident to a deleted step cannot survive it. Listing them as
    separate losses tripled the size of the ack list and made the remedy read
    as though three unrelated things were being destroyed.
    """
    live = _load("linear_baseline")
    outgoing = _delete_middle_step(live)

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok, "deleting a step must still be refused by default"
    assert any(p.endswith("steps[Set A]") for p in verdict.dropped), verdict.dropped
    assert not [p for p in verdict.dropped if ".routes[" in p], (
        "routes incident to a deleted step were reported as independent "
        f"losses the caller has to acknowledge separately: {verdict.dropped}"
    )


def test_acknowledging_the_step_permits_its_entailed_routes():
    """A3 itself: name the step you are deleting, and the save goes through."""
    live = _load("linear_baseline")
    outgoing = _delete_middle_step(live)

    verdict = check_prewrite(live, outgoing, acknowledged=["Set A"])
    assert verdict.ok, (
        "acknowledging the deleted step did not clear the routes its own "
        f"deletion removed: {verdict.message}"
    )


def test_acknowledgement_accepts_a_bare_step_name():
    """The ack list must be expressible in the caller's vocabulary.

    `acknowledged_drops` previously required the guard's full internal path
    (`collection.workflows[X].steps[Y]`), which the model can only produce by
    copying the refusal back verbatim -- and it demonstrably did not.
    """
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    victim = _workflows(outgoing)[0]["steps"].pop()["name"]

    assert check_prewrite(live, outgoing, acknowledged=[victim]).ok


def test_full_path_acknowledgement_still_works():
    """The documented remedy (echo `dropped` back) must not regress."""
    live = _load("linear_baseline")
    outgoing = _delete_middle_step(live)
    refused = check_prewrite(live, outgoing)
    assert check_prewrite(live, outgoing, refused.dropped).ok


def test_a_route_deleted_on_its_own_is_still_refused():
    """Entailment is scoped to deleted steps -- it must not blanket-forgive.

    Dropping an edge between two steps that both survive silently reshapes
    execution, and is exactly what the route check exists to catch.
    """
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    wf["routes"].pop()

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok
    assert any(".routes[" in p for p in verdict.dropped), verdict.dropped


def test_acknowledging_one_deletion_does_not_forgive_another_steps_routes():
    """Entailment must attribute each route to the step that actually removed
    it, not to whichever deletion happened to be acknowledged."""
    live = _load("linear_baseline")
    # Give the fixture an edge whose endpoints BOTH survive the deletion --
    # every route it ships with touches Set A, so without this the premise is
    # vacuous and the test passes for the wrong reason.
    lwf = _workflows(live)[0]
    by_name = {s["name"]: s for s in lwf["steps"]}
    lwf["routes"].append({
        "@id": "/api/3/workflow_routes/bypass",
        "@type": "WorkflowRoute",
        "name": "Start -> Set B",
        "label": None,
        "isExecuted": False,
        "uuid": "11111111-1111-1111-1111-111111111111",
        "sourceStep": f"/api/3/workflow_steps/{by_name['Start']['uuid']}",
        "targetStep": f"/api/3/workflow_steps/{by_name['Set B']['uuid']}",
    })

    outgoing = _delete_middle_step(live, "Set A")
    # ...and additionally sever the bypass, which the deletion did not require.
    wf = _workflows(outgoing)[0]
    wf["routes"] = [r for r in wf["routes"] if r.get("name") != "Start -> Set B"]

    verdict = check_prewrite(live, outgoing, acknowledged=["Set A"])
    assert not verdict.ok, (
        "acking the Set A deletion also waved through an unrelated route drop"
    )


def test_a_re_derived_connector_config_is_not_customer_data():
    """`arguments.config` is resolved from a per-appliance catalog.

    `connector_args.py` fills it from the local `connector_configs` table and
    falls back to `""` ("use the connector's default") when that table has no
    row -- so the SAME yaml compiles with a uuid on one host and `""` on
    another. The decompiler already treats it as re-derived. The guard did
    not, so every save made from a host with a different catalog was refused
    for a field neither the author nor the model ever touched.
    """
    live = _load("linear_baseline")
    for wf in _workflows(live):
        for step in wf["steps"]:
            step.setdefault("arguments", {})["config"] = (
                "4744035b-7f44-4272-afe2-0dfd7f7f2c4a")

    outgoing = copy.deepcopy(live)
    for wf in _workflows(outgoing):
        for step in wf["steps"]:
            step["arguments"]["config"] = ""

    verdict = check_prewrite(live, outgoing)
    assert verdict.ok, (
        f"a re-derived default config counted as data loss: {verdict.dropped}"
    )


def test_a_real_argument_still_counts_even_next_to_config():
    """The config exemption is one key, not a hole in the arguments check."""
    live = _load("linear_baseline")
    for wf in _workflows(live):
        for step in wf["steps"]:
            step.setdefault("arguments", {})["config"] = "some-uuid"

    outgoing = copy.deepcopy(live)
    for wf in _workflows(outgoing):
        for step in wf["steps"]:
            step["arguments"]["config"] = ""
            step["arguments"].pop("a", None)

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok, "a real argument vanished alongside config"
    assert not any(p.endswith(".config") for p in verdict.dropped), verdict.dropped


# --------------------------------------------------------------------------- #
# #137 / probe A2 -- the insertion mirror of the A3 case.
#
# "Add a set-variable step named 'Stamp Verdict' right after 'Enrich IP'"
# replaces the direct edge Enrich IP->Block IP with a path through the new
# step. The guard read the vanished direct edge as data loss and refused, so
# the most common enhancement there is -- add a step in the middle -- could not
# be saved at all. The refusal reached the analyst as a bare "apply_failed"
# (connector-side envelope bug), which is why this cost a live run to find.
# --------------------------------------------------------------------------- #

def _insert_step_between(live: dict, src: str, tgt: str,
                         new_name: str = "Stamp Verdict") -> dict:
    """Splice a new step into an existing edge, rewiring as FSR requires."""
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    by_name = {s["name"]: s for s in wf["steps"]}
    assert src in by_name and tgt in by_name, "fixture lacks the edge endpoints"

    new_uuid = "abcdabcd-0000-0000-0000-00000000abcd"
    new_step = copy.deepcopy(by_name[src])
    new_step.update({"name": new_name, "uuid": new_uuid,
                     "@id": f"/api/3/workflow_steps/{new_uuid}"})
    wf["steps"].append(new_step)

    src_iri = f"/api/3/workflow_steps/{by_name[src]['uuid']}"
    tgt_iri = f"/api/3/workflow_steps/{by_name[tgt]['uuid']}"
    new_iri = f"/api/3/workflow_steps/{new_uuid}"
    # The direct edge is REPLACED, exactly as the designer would do it.
    wf["routes"] = [r for r in wf["routes"]
                    if not (r.get("sourceStep") == src_iri
                            and r.get("targetStep") == tgt_iri)]
    for i, (s, t) in enumerate(((src_iri, new_iri), (new_iri, tgt_iri))):
        wf["routes"].append({
            "@id": f"/api/3/workflow_routes/spliced-{i}",
            "@type": "WorkflowRoute", "name": f"spliced {i}", "label": None,
            "isExecuted": False,
            "uuid": f"22222222-2222-2222-2222-00000000000{i}",
            "sourceStep": s, "targetStep": t})
    return outgoing


def test_inserting_a_step_mid_flow_is_not_a_loss():
    """THE A2 defect. The replaced direct edge is arithmetic on the insertion."""
    live = _load("linear_baseline")
    outgoing = _insert_step_between(live, "Start", "Set A")

    verdict = check_prewrite(live, outgoing)
    assert verdict.ok, (
        "adding a step in the middle of a flow was refused as data loss: "
        f"{verdict.dropped}"
    )


def test_an_insertion_rewire_needs_no_acknowledgement():
    """The cause is an ADDITION, and additions are never refused -- so there is
    no refusal for the caller to acknowledge. Demanding one would ask them to
    sign off on a deletion they did not make."""
    live = _load("linear_baseline")
    outgoing = _insert_step_between(live, "Start", "Set A")

    assert check_prewrite(live, outgoing, acknowledged=[]).ok
    assert check_prewrite(live, outgoing, acknowledged=None).ok


def test_severing_an_edge_while_adding_an_unrelated_step_is_still_a_loss():
    """The rule is narrow on purpose: rerouted, not merely 'a step was added'.

    Without this the insertion exemption would degrade into 'any addition
    forgives any route drop', which is the guard's whole reason to exist.
    """
    live = _load("linear_baseline")
    outgoing = copy.deepcopy(live)
    wf = _workflows(outgoing)[0]
    added = copy.deepcopy(wf["steps"][-1])
    added.update({"name": "Unrelated", "uuid": "deaddead-0000-0000-0000-00000000dead"})
    wf["steps"].append(added)          # an addition, connected to nothing
    wf["routes"].pop()                 # ...and an edge severed, not rerouted

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok, "an unrelated addition forgave a severed edge"
    assert any(".routes[" in p for p in verdict.dropped), verdict.dropped


def test_the_rewire_must_actually_reconnect_the_same_endpoints():
    """A new step that takes the source's edge but never reaches the original
    target has changed where execution goes. That is a reshape, not a reroute."""
    live = _load("linear_baseline")
    outgoing = _insert_step_between(live, "Start", "Set A")
    wf = _workflows(outgoing)[0]
    # Drop the second leg, so Start -> Stamp Verdict -> (nothing).
    wf["routes"] = [r for r in wf["routes"] if r.get("name") != "spliced 1"]

    verdict = check_prewrite(live, outgoing)
    assert not verdict.ok, (
        "a half-spliced insertion that never rejoins the flow was allowed"
    )
