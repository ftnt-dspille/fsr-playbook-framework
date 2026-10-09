"""`edit_playbook`: edits as operations on the open playbook, never a re-type.

Live: an agent re-typed a verified playbook to deliver an edit, dropped two
`next:` links, and the saved playbook ran only its first search. Here the model
names only the change and the tool applies it to the open playbook, so a step or
link it did not name cannot go missing.

The open playbook is built the way the designer mount builds it: compile, then
decompile back to YAML (slug routes, uuids, layout keys and all).
"""
from __future__ import annotations

import re

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


# ── Live friction (sess on an EMPTY playbook: 5 of 7 calls refused) ─────────

_EMPTY = "collection: C\nplaybooks:\n  - name: P\n    steps: []\n"


def _grounded_as(yaml_text):
    tok = set_grounded_yaml(yaml_text)
    return tok


def test_an_empty_playbook_says_how_to_start():
    tok = _grounded_as(_EMPTY)
    try:
        res = edit_playbook([{"op": "add_step", "after": "Start",
                              "step": {"name": "Ask", "type": "set_variable", "vars": {"a": "1"}}}])
        assert res["code"] == "bad_operation"
        assert "no steps yet" in res["message"] and "start" in res["message"]
    finally:
        reset_grounded_yaml(tok)


def test_an_empty_playbook_builds_from_a_start_step():
    tok = _grounded_as(_EMPTY)
    try:
        res = edit_playbook([
            {"op": "add_step", "step": {"name": "Start", "type": "start", "module": "alerts"}},
            {"op": "add_step", "after": "Start",
             "step": {"name": "Note", "type": "set_variable", "vars": {"a": "1"}}},
        ], user_message="build it")
        assert res["ready_to_push"], (res.get("code"), res.get("message"), res.get("required_fixes"))
        assert _steps(res["after_yaml"])["Start"]["next"] == "Note"
    finally:
        reset_grounded_yaml(tok)


_GATED = """collection: C
playbooks:
  - name: P
    steps:
      - {name: Start, type: start, module: alerts, next: Ask}
      - name: Ask
        type: manual_input
        title: Enter IP
        inputs: [{name: ip, kind: ipv4, label: IP, required: true}]
        options:
          - {display: Continue, primary: true, next: Done}
      - {name: Done, type: set_variable, vars: {d: "1"}}
"""


def test_add_after_a_single_branch_step_splices_into_that_branch():
    """Live: `after` a manual_input with one Continue button was refused."""
    tok = _grounded_as(compile_and_decompile(_GATED))
    try:
        res = edit_playbook([{"op": "add_step", "after": "Ask",
                              "step": {"name": "Note", "type": "set_variable", "vars": {"n": "1"}}}])
        assert res["ready_to_push"], (res.get("message"), res.get("required_fixes"))
        after = _steps(res["after_yaml"])
        assert after["Ask"]["options"][0]["next"] == "Note"
        assert after["Note"]["next"] in ("done", "Done")
    finally:
        reset_grounded_yaml(tok)


def test_add_after_a_multi_branch_step_needs_the_option(open_yaml):
    res = edit_playbook([{"op": "add_step", "after": "Check",
                          "step": {"name": "X", "type": "set_variable", "vars": {"x": "1"}}}])
    assert res["code"] == "bad_operation" and "option=" in res["message"]
    res = edit_playbook([{"op": "add_step", "after": "Check", "option": "Else",
                          "step": {"name": "X", "type": "set_variable", "vars": {"x": "1"}}}])
    assert res["ready_to_push"], (res.get("message"), res.get("required_fixes"))
    assert _steps(res["after_yaml"])["Check"]["conditions"][1]["next"] == "X"


def test_a_route_to_a_step_added_later_in_the_list_applies():
    """Live: set_route to "Create ServiceNow incident" came before the add_step
    that creates it, and the whole list was refused."""
    tok = _grounded_as(compile_and_decompile(_GATED))
    try:
        res = edit_playbook([
            {"op": "set_route", "from": "Ask", "option": "Continue", "to": "Ticket"},
            {"op": "add_step", "step": {"name": "Ticket", "type": "set_variable",
                                        "vars": {"t": "1"}, "next": "Done"}},
        ])
        assert res["ready_to_push"], (res.get("message"), res.get("required_fixes"))
        assert _steps(res["after_yaml"])["Ask"]["options"][0]["next"] == "Ticket"
    finally:
        reset_grounded_yaml(tok)


def test_a_reference_to_a_step_nobody_adds_is_still_refused(open_yaml):
    res = edit_playbook([{"op": "set_route", "from": "Note A", "to": "Ghost"}])
    assert res["code"] == "bad_operation" and res["operation_index"] == 0


def compile_and_decompile(authored: str) -> str:
    res = compile_yaml(authored, DB_PATH)
    assert res.ok, [e.to_dict() for e in res.errors]
    return decompile_to_yaml(res.fsr_json, DB_PATH)


def test_rename_accepts_from_to():
    """Live: `{op: rename_step, from, to}` was refused 3 times in one run and
    stuck twice -- the refusal never said the op wants `name`."""
    from fsr_playbooks.mcp_server.tools_enhancement import _normalize_op
    assert _normalize_op({"op": "rename_step", "from": "A", "to": "B"}) == \
        {"op": "rename_step", "name": "A", "to": "B"}


def test_a_refusal_quotes_the_ops_expected_shape():
    from fsr_playbooks.mcp_server import tools_enhancement as TE
    assert "rename_step" in TE._OP_SHAPES
    assert set(TE._OP_SHAPES) == set(TE._EDIT_OPS)


def test_a_rename_without_its_step_quotes_the_shape():
    out = edit_playbook(operations=[{"op": "rename_step", "to": "B"}])
    assert out["code"] == "bad_operation"
    assert "expected {op: rename_step, name: <current name>, to: <new name>}" in out["message"]
    assert "got keys ['to']" in out["message"]


def test_every_instruction_for_the_offer_names_its_required_fields():
    """Models copy our example payload verbatim. It said
    `payload={verified_id: ...}` in 8 places, and emit_card refused exactly that
    payload for a missing `summary` -- 4 of 10 refusals in one live run."""
    import inspect
    import re
    from pathlib import Path

    import fsr_playbooks.mcp_server.tools_emit as TEm
    import fsr_playbooks.mcp_server.tools_enhancement as TEn
    texts = {
        "system_prompt_build.md": (Path(TEn.__file__).parents[1] / "agent"
                                   / "system_prompt_build.md").read_text(),
        "tools_emit.py": inspect.getsource(TEm),
        "tools_enhancement.py": inspect.getsource(TEn),
    }
    bad = [(f, m.group(0)) for f, t in texts.items()
           for m in re.finditer(r"enhancement_offer', payload=\{[^)]*\)", t)
           if "summary" not in m.group(0)]
    assert bad == []


# --- dotted keys ---------------------------------------------------------------
# Live (effect probe A5): `set: {"params.ip_addresses": X}` was written as a
# literal sibling key, verify passed it, and the offer would have "applied"
# with the old IP still in `params`. A dotted key sets one leaf.

def test_a_dotted_key_sets_one_leaf_and_keeps_its_siblings():
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"vars.c": "2", "vars.d": "3"}}])
    assert res["ready_to_push"], res.get("required_fixes")
    step = _steps(res["after_yaml"])["Note C"]
    assert step["vars"] == {"c": "2", "d": "3"}
    assert not any("." in str(k) for k in step), sorted(step)


def test_a_dotted_unset_removes_one_leaf():
    res = edit_playbook([
        {"op": "update_step", "name": "Note C", "set": {"vars.d": "3"}},
        {"op": "update_step", "name": "Note C", "unset": ["vars.d"]},
    ])
    assert res["ready_to_push"], res.get("required_fixes")
    assert _steps(res["after_yaml"])["Note C"]["vars"] == {"c": "1"}


def test_a_dotted_key_through_a_scalar_is_refused():
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"next.x": "1"}}])
    assert res["ok"] is False and res["code"] == "bad_operation"
    assert "not a mapping" in res["message"]


def test_a_dotted_key_cannot_reach_a_forbidden_key():
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"name.x": "1"}}])
    assert res["ok"] is False and "rename_step" in res["message"]


def test_step_names_the_step_like_name_does():
    # Live (A5 run 1): `step: "Block IP"` was refused as not a step reference.
    res = edit_playbook([{"op": "update_step", "step": "Note C",
                          "set": {"vars.c": "2"}}])
    assert res["ready_to_push"], res
    assert _steps(res["after_yaml"])["Note C"]["vars"] == {"c": "2"}


def test_action_names_the_op_like_op_does():
    # Live (A5): `action: update_step` was refused as "unknown op None".
    res = edit_playbook([{"action": "update_step", "name": "Note C",
                          "set": {"vars.c": "2"}}])
    assert res["ready_to_push"], res
    assert _steps(res["after_yaml"])["Note C"]["vars"] == {"c": "2"}


def test_replacing_a_mapping_says_what_it_dropped():
    # Live (A5): set={params: {...}} dropped `method`; the turn was never told.
    res = edit_playbook([
        {"op": "update_step", "name": "Note C", "set": {"vars.d": "3"}},
        {"op": "update_step", "name": "Note C", "set": {"vars": {"d": "4"}}},
    ])
    line = res["applied"][1]
    assert "REPLACED" in line and "vars.c" in line, line
    assert 'set: {"vars.<key>": value}' in line, line


# --- the advertised item shape (A4) -------------------------------------------
# Live (A5/A6): with `operations: list[object]` the model spelled the op key
# `action` and `type`. The item shape is now advertised; keep it in step with
# what `_apply_op` accepts.

def test_the_advertised_op_enum_is_the_tool_s_op_list():
    from fsr_playbooks.llm.tools import TOOL_SCHEMA_OVERRIDES
    from fsr_playbooks.mcp_server.tools_enhancement import _EDIT_OPS, _OP_SHAPES
    item = TOOL_SCHEMA_OVERRIDES["edit_playbook"]["properties"]["operations"]["items"]
    assert set(item["properties"]["op"]["enum"]) == set(_EDIT_OPS) == set(_OP_SHAPES)
    shape_keys = {k.strip() for shape in _OP_SHAPES.values()
                  for k in re.findall(r"[{,]\s*([a-z_]+):", shape)}
    assert shape_keys <= set(item["properties"]), shape_keys - set(item["properties"])


def test_a_misnamed_op_key_is_refused_at_the_gate_by_name():
    from fsr_playbooks.llm.tools import dispatch
    res = dispatch("edit_playbook", {"operations": [
        {"type": "update_step", "name": "Note C", "set": {"vars.c": "2"}}]})
    assert res["ok"] is False and res["code"] == "invalid_tool_args"
    assert "operations[0]: 'op' is a required property" in res["error"]


def test_a_step_added_after_one_that_already_routes_to_it_does_not_loop():
    """Live: a build-from-empty batch had each step name its successor
    (`next: End`) and then added End `after` its predecessor. The splice gave
    End the predecessor's old `next` -- itself -- and the batch was refused as
    `cycle end -> end`, though the model wrote no cycle; it never recovered."""
    tok = _grounded_as(_EMPTY)
    try:
        res = edit_playbook([
            {"op": "add_step", "step": {"name": "Start", "type": "start",
                                        "module": "alerts", "next": "Check"}},
            {"op": "add_step", "after": "Start",
             "step": {"name": "Check", "type": "decision", "conditions": [
                 {"display": "Go", "when": "{{ true }}", "next": "Note"},
                 {"display": "Else", "default": True, "next": "End"}]}},
            # no option: Check's "Go" branch already routes to Note (live)
            {"op": "add_step", "after": "Check",
             "step": {"name": "Note", "type": "set_variable", "vars": {"n": "1"},
                      "next": "End"}},
            {"op": "add_step", "after": "Note", "step": {"name": "End", "type": "end"}},
        ], user_message="build it")
        assert res["ready_to_push"], (res.get("code"), res.get("message"), res.get("required_fixes"))
        after = _steps(res["after_yaml"])
        assert not after["End"].get("next")
        assert after["Note"]["next"] == "End"
        assert after["Check"]["conditions"][1]["next"] == "End"
    finally:
        reset_grounded_yaml(tok)


def test_a_step_added_into_a_branch_that_already_routes_to_it_does_not_loop():
    tok = _grounded_as(compile_and_decompile(_GATED))
    try:
        res = edit_playbook([
            {"op": "set_route", "from": "Ask", "option": "Continue", "to": "Note"},
            {"op": "add_step", "after": "Ask",
             "step": {"name": "Note", "type": "set_variable", "vars": {"n": "1"}}},
        ])
        assert res.get("ready_to_push"), (res.get("code"), res.get("message"),
                                          res.get("required_fixes"))
        after = _steps(res["after_yaml"])
        assert after["Ask"]["options"][0]["next"] == "Note"
        assert after["Note"].get("next") not in ("Note", "note")
    finally:
        reset_grounded_yaml(tok)


def test_a_rename_that_also_edits_the_step_is_still_a_rename():
    """Live (analyst sim): "rename the manual task to 'Approve IPv4 Block'" --
    the model sent rename_step plus an update_step retitling the same step.
    The changed contents broke the projection pairing, so the verifier called
    the step dropped and refused the analyst's own rename three times. The
    step kept its uuid; that, and the rename_step op, are what decide it."""
    res = edit_playbook([
        {"op": "rename_step", "name": "Note B", "to": "Close Out"},
        {"op": "update_step", "name": "Close Out", "set": {"vars.b": "2"}},
    ], user_message="tidy up the last step")
    kinds = {r["kind"]: r for r in res["regressions"]}
    assert "step_dropped" not in kinds
    assert kinds["step_renamed_as_requested"]["severity"] == "warning"
    assert res["ready_to_push"], res.get("required_fixes")
    renamed = [c for c in res["diff_summary"]["changes"] if c["kind"] == "renamed"]
    assert renamed and "arguments" in renamed[0]["changed_fields"]
    assert "Close Out" in res["diff_summary"]["steps_modified"]


def test_a_rename_outside_edit_playbook_is_not_requested_by_default(open_yaml):
    """The rename_step exemption comes from the op, not from the model's say-so:
    the same rename re-typed through verify_enhancement, with no rename asked
    for, still blocks."""
    after = open_yaml.replace("name: Note B", "name: Close Out")
    res = verify_enhancement(after_yaml=after, user_message="tidy up")
    kinds = {r["kind"] for r in res["regressions"]}
    assert "step_renamed_silently" in kinds
    assert not res["ready_to_push"]


def test_add_parameter_declares_what_a_step_reads():
    """Live: a step read `vars.input.params.servicenow_caller_id`, the gate
    said to declare it, and edit_playbook had no op that could -- the model
    fell back to re-typing the whole playbook. Declaring it is one op."""
    edit = {"op": "update_step", "name": "Note B",
            "set": {"vars.b": "{{ vars.input.params.caller_id }}"}}
    refused = edit_playbook([edit], user_message="set Note B from the caller id")
    assert "add_parameter" in str(refused.get("required_fixes"))
    res = edit_playbook([edit, {"op": "add_parameter", "name": "caller_id"}],
                        user_message="set Note B from the caller id")
    assert res["ready_to_push"], res.get("required_fixes")
    doc = YAML(typ="safe").load(res["after_yaml"])
    assert "caller_id" in doc["playbooks"][0]["parameters"]
    again = edit_playbook([edit, {"op": "add_parameter", "name": "caller_id"},
                           {"op": "add_parameter", "name": "caller_id"}])
    assert again["applied"][-1] == "parameter 'caller_id' already declared"


def test_add_parameter_refuses_a_non_identifier():
    out = edit_playbook([{"op": "add_parameter", "name": "caller id"}])
    assert out["code"] == "bad_operation"


def test_the_enhancement_card_states_the_trigger():
    """The analyst approves what starts the playbook, not only its steps."""
    res = edit_playbook([{"op": "update_step", "name": "Note C",
                          "set": {"vars": {"c": "2"}}}])
    card = emit_card("enhancement_offer", {"id": "e2", "summary": "c to 2",
                                           "verified_id": res["verified_id"]})["card"]
    assert card["trigger"]["label"].startswith("Runs when an analyst")
    assert card["trigger"]["modules"] == ["alerts"]
