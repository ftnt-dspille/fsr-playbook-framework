"""`edit_playbook`: edits as operations on the open playbook, never a re-type.

Live: an agent re-typed a verified playbook to deliver an edit, dropped two
`next:` links, and the saved playbook ran only its first search. Here the model
names only the change and the tool applies it to the open playbook, so a step or
link it did not name cannot go missing.

The open playbook is built the way the designer mount builds it: compile, then
decompile back to YAML (slug routes, uuids, layout keys and all).
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp", reason="mcp package not installed")

from ruamel.yaml import YAML  # noqa: E402

from fsr_playbooks.compiler import compile_yaml  # noqa: E402
from fsr_playbooks.compiler.decompiler import decompile_to_yaml  # noqa: E402
from fsr_playbooks.llm._loop_helpers import EnhanceDeliveryGuard  # noqa: E402
from fsr_playbooks.mcp_server import _verified_yaml  # noqa: E402
from fsr_playbooks.mcp_server._shared import (  # noqa: E402
    DB_PATH,
    reset_grounded_yaml,
    set_grounded_yaml,
)
from fsr_playbooks.mcp_server.tools_emit import emit_card  # noqa: E402
from fsr_playbooks.mcp_server.tools_enhancement import (  # noqa: E402
    edit_playbook,
    verify_enhancement,
)

AUTHORED = """collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, module: alerts, next: Check}
      - name: Check
        type: decision
        conditions:
          - {display: big, when: "{{ vars.input.records[0].severity == 'High' }}", next: Note A}
          - {display: Else, default: true, next: Note B}
      - {name: Note A, type: set_variable, vars: {a: "1"}, next: Note C}
      - {name: Note C, type: set_variable, vars: {c: "1"}, next: Note B}
      - {name: Note B, type: set_variable, vars: {b: "1"}}
"""


@pytest.fixture(scope="module")
def open_yaml() -> str:
    res = compile_yaml(AUTHORED, DB_PATH)
    assert res.ok, [e.to_dict() for e in res.errors]
    return decompile_to_yaml(res.fsr_json, DB_PATH)


@pytest.fixture(autouse=True)
def grounded(open_yaml):
    _verified_yaml.clear()
    tok = set_grounded_yaml(open_yaml)
    yield
    reset_grounded_yaml(tok)
    _verified_yaml.clear()


def _steps(yaml_text: str) -> dict:
    doc = YAML(typ="safe").load(yaml_text)
    return {s["name"]: s for s in doc["playbooks"][0]["steps"]}


def _dump_step(step: dict) -> str:
    import io
    buf = io.StringIO()
    YAML(typ="safe").dump(step, buf)
    return buf.getvalue()


def _route_names(yaml_text: str) -> set[tuple[str, str]]:
    """(from, to-ref) for every route in the document."""
    out = set()
    for name, s in _steps(yaml_text).items():
        if s.get("next"):
            out.add((name, s["next"]))
        for c in s.get("conditions") or []:
            if c.get("next"):
                out.add((name, c["next"]))
    return out


def test_add_step_splices_into_the_chain_and_touches_nothing_else(open_yaml):
    res = edit_playbook([{"op": "add_step", "after": "Note A",
                          "step": {"name": "Note D", "type": "set_variable",
                                   "vars": {"d": "1"}}}])
    assert res["ready_to_push"], res.get("required_fixes")
    assert res["verified_id"]
    before, after = _steps(open_yaml), _steps(res["after_yaml"])
    assert after["Note A"]["next"] == "Note D"
    assert after["Note D"]["next"] == before["Note A"]["next"]
    # Every step the op did not name is identical, uuid and layout included --
    # except that steps after the splice move down a row to make room.
    for name in ("Start", "Check"):
        assert _dump_step(after[name]) == _dump_step(before[name]), name
    for name in ("Note C", "Note B"):
        moved = {k: v for k, v in after[name].items() if k != "top"}
        was = {k: v for k, v in before[name].items() if k != "top"}
        assert _dump_step(moved) == _dump_step(was), name
    assert res["diff_summary"]["steps_added"] == ["Note D"]


def test_the_incident_cannot_happen_a_param_edit_keeps_every_link(open_yaml):
    """The live bug, as an invariant: changing one step leaves all routes."""
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"vars": {"c": "2"}}}])
    assert res["ready_to_push"], res.get("required_fixes")
    assert _route_names(res["after_yaml"]) == _route_names(open_yaml)
    assert _steps(res["after_yaml"])["Note C"]["vars"] == {"c": "2"}


def test_remove_step_reconnects_its_predecessors():
    res = edit_playbook([{"op": "remove_step", "name": "Note C"}],
                        user_message="remove the step Note C")
    assert res["ready_to_push"], (res.get("required_fixes"), res.get("regressions"))
    after = _steps(res["after_yaml"])
    assert "Note C" not in after
    assert after["Note A"]["next"] in ("note_b", "Note B")


def test_set_route_on_a_decision_branch():
    res = edit_playbook([{"op": "set_route", "from": "Check", "option": "Else",
                          "to": "Note C"}])
    assert res["ready_to_push"], res.get("required_fixes")
    cond = _steps(res["after_yaml"])["Check"]["conditions"][1]
    assert cond["next"] == "Note C"


def test_rerouting_away_from_a_step_orphans_it_and_verify_refuses():
    # `big` was the only way into Note A: the gate catches what the op did.
    res = edit_playbook([{"op": "set_route", "from": "Check", "option": "big",
                          "to": "Note C"}])
    assert res["ready_to_push"] is False
    assert any("Note A" in f["message"] for f in res["required_fixes"])


def test_rename_step_moves_the_routes_with_it():
    res = edit_playbook([{"op": "rename_step", "name": "Note B", "to": "Close Out"}],
                        user_message="rename Note B to Close Out")
    after = _steps(res["after_yaml"])
    assert "Close Out" in after and "Note B" not in after
    assert after["Note C"]["next"] == "Close Out"
    assert after["Check"]["conditions"][1]["next"] == "Close Out"


def test_removing_a_route_orphans_a_step_and_verify_refuses():
    res = edit_playbook([{"op": "remove_route", "from": "Note A"}])
    assert res["ready_to_push"] is False
    assert res["verified_id"] is None
    assert any(f["code"] == "unreachable_step" for f in res["required_fixes"])


def test_a_bad_operation_applies_nothing():
    res = edit_playbook([
        {"op": "update_step", "name": "Note C", "set": {"vars": {"c": "2"}}},
        {"op": "update_step", "name": "No Such Step", "set": {"x": 1}},
    ])
    assert res["ok"] is False
    assert res["code"] == "bad_operation"
    assert res["operation_index"] == 1
    assert "Note C" in res["message"] or "steps are" in res["message"]


@pytest.mark.parametrize("op", [
    {"op": "update_step", "name": "Note C", "set": {"name": "X"}},
    {"op": "add_step", "after": "Note A", "step": {"name": "Note B", "type": "set_variable"}},
    {"op": "set_route", "from": "Check", "to": "Note C"},
    {"op": "frobnicate"},
])
def test_invalid_operations_are_refused(op):
    assert edit_playbook([op])["code"] == "bad_operation"


def test_no_open_playbook_is_a_typed_refusal():
    tok = set_grounded_yaml(None)
    try:
        assert edit_playbook([{"op": "remove_step", "name": "x"}])["code"] == \
            "no_open_playbook"
        assert verify_enhancement(after_yaml=AUTHORED)["code"] == "no_open_playbook"
    finally:
        reset_grounded_yaml(tok)


def test_verify_enhancement_defaults_before_to_the_open_playbook(open_yaml):
    edited = open_yaml.replace("c: '1'", "c: '2'")
    assert edited != open_yaml
    res = verify_enhancement(after_yaml=edited)
    assert res["ready_to_push"], res.get("required_fixes")
    assert res["diff_summary"]["steps_modified"] == ["Note C"]


def test_the_handle_delivers_exactly_the_edited_bytes():
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"vars": {"c": "2"}}}])
    out = emit_card("enhancement_offer", {"id": "e1", "summary": "c to 2",
                                          "verified_id": res["verified_id"]})
    assert out["ok"], out
    assert out["card"]["final_yaml"] == res["after_yaml"]


def test_enhance_delivery_guard_counts_an_edit_playbook_pass():
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"vars": {"c": "2"}}}])
    g = EnhanceDeliveryGuard()
    g.note_result("edit_playbook", {"operations": []}, res)
    assert g.outstanding({"emit_card"}) == res["verified_id"]


def test_edit_playbook_is_registered_like_verify_enhancement():
    from fsr_playbooks.llm import intents, tools, turn_plan
    assert "edit_playbook" in tools.REGISTRY
    assert tools.TOOL_TIERS["edit_playbook"] == tools.TOOL_TIERS["verify_enhancement"]
    for group in (intents.BUILD_ONLY_TOOLS, intents.ENHANCE_ONLY_TOOLS,
                  turn_plan._OPEN_PLAYBOOK_TOOLS, tools.WRITE_FRONTIER_TOOLS):
        assert ("edit_playbook" in group) == ("verify_enhancement" in group)


def test_op_name_as_key_with_inline_step_is_accepted():
    """Live shape (gpt, designer create turn): `{add_step: {name, type, ...,
    after}}`. Unambiguous, so it applies instead of `unknown op None`."""
    res = edit_playbook([
        {"add_step": {"name": "Note D", "type": "set_variable",
                      "vars": {"d": "1"}, "after": "Note A"}},
        {"update_step": {"name": "Note C", "set": {"vars": {"c": "2"}}}},
    ])
    assert res["ready_to_push"], (res.get("code"), res.get("message"),
                                  res.get("required_fixes"))
    after = _steps(res["after_yaml"])
    assert after["Note A"]["next"] == "Note D"
    assert "after" not in after["Note D"]
    assert after["Note C"]["vars"] == {"c": "2"}


def test_add_step_with_inline_fields_beside_op_is_accepted():
    res = edit_playbook([{"op": "add_step", "after": "Note A", "name": "Note D",
                          "type": "set_variable", "vars": {"d": "1"}}])
    assert res["ready_to_push"], res.get("message")
    assert _steps(res["after_yaml"])["Note A"]["next"] == "Note D"


def test_an_unknown_keyed_op_is_still_refused_with_the_shape():
    res = edit_playbook([{"frobnicate": {"name": "Note C"}}])
    assert res["code"] == "bad_operation"
    assert "{op: <kind>" in res["message"]


def test_a_spliced_step_sits_under_its_predecessor_and_pushes_the_rest_down(open_yaml):
    """Live: added steps had no position, fell to the emitter's auto-layout
    grid, and collided with saved positions (End above the steps routed in)."""
    before = _steps(open_yaml)
    res = edit_playbook([{"op": "add_step", "after": "Note A",
                          "step": {"name": "Note D", "type": "set_variable",
                                   "vars": {"d": "1"}}}])
    after = _steps(res["after_yaml"])
    pos = {n: (int(s["top"]), int(s["left"])) for n, s in after.items()}
    was = {n: (int(s["top"]), int(s["left"])) for n, s in before.items()}
    assert pos["Note D"] == (was["Note A"][0] + 130, was["Note A"][1])
    # Downstream of the splice moves down a row; upstream stays put.
    for n in ("Note C", "Note B"):
        assert pos[n] == (was[n][0] + 130, was[n][1]), n
    for n in ("Start", "Check", "Note A"):
        assert pos[n] == was[n], n
    # Route order reads top to bottom along the new chain.
    assert pos["Note A"][0] < pos["Note D"][0] < pos["Note C"][0]


def test_an_unrouted_step_goes_below_everything(open_yaml):
    res = edit_playbook([{"op": "add_step", "step": {"name": "Loose",
                                                     "type": "set_variable",
                                                     "vars": {"x": "1"}}},
                         {"op": "set_route", "from": "Note B", "to": "Loose"}])
    after = _steps(res["after_yaml"])
    lowest = max(int(s["top"]) for n, s in _steps(open_yaml).items())
    assert int(after["Loose"]["top"]) == lowest + 130


def test_a_position_the_model_gave_is_kept():
    res = edit_playbook([{"op": "add_step", "after": "Note A",
                          "step": {"name": "Note D", "type": "set_variable",
                                   "vars": {"d": "1"}, "top": "900", "left": "900"}}])
    d = _steps(res["after_yaml"])["Note D"]
    assert (str(d["top"]), str(d["left"])) == ("900", "900")
