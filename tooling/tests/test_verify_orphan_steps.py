"""A step no route reaches must block `verify_playbook`.

Live failure: an agent re-typed a verified three-search playbook, dropped two
`next:` links, and verify still answered `ready_to_push=True` -- the compiler's
reachability check was a `bad_value` WARNING. The saved playbook ran only its
first search. The compiler still only warns (an appliance playbook may park a
step and must round-trip); the authoring gate is what blocks.

Also pins the parser fix found on the way: `unlabeled_next` (fan-out) was
silently dropped at parse, so a fan-out playbook compiled clean and emitted
with no routes out of the fan-out step.
"""
from __future__ import annotations

import textwrap

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.mcp_server import verify_playbook
from fsr_playbooks.mcp_server._shared import DB_PATH
from fsr_playbooks.mcp_server.tools_enhancement import verify_enhancement


def _yaml(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


def _three_searches(link_a: bool = True, link_b: bool = True) -> str:
    return _yaml(f"""
        collection: C
        playbooks:
          - name: P
            steps:
              - name: Start
                type: start
                next: Search One
              - name: Search One
                type: set_variable
                vars: {{one: "1"}}
                {"next: Search Two" if link_a else ""}
              - name: Search Two
                type: set_variable
                vars: {{two: "2"}}
                {"next: Search Three" if link_b else ""}
              - name: Search Three
                type: set_variable
                vars: {{three: "3"}}
    """)


def _orphan_codes(res: dict) -> list[dict]:
    return [f for f in res["required_fixes"] if f.get("code") == "unreachable_step"]


def test_fully_linked_playbook_has_no_orphans():
    res = verify_playbook(yaml_text=_three_searches())
    assert _orphan_codes(res) == []
    assert not [w for w in res["warnings"] if w.get("code") == "unreachable_step"]


def test_dropped_links_block_ready_to_push():
    res = verify_playbook(yaml_text=_three_searches(link_a=False, link_b=False))
    assert res["ready_to_push"] is False
    assert res["ok"] is False
    orphans = _orphan_codes(res)
    msgs = " ".join(f["message"] for f in orphans)
    assert "search_two" in msgs and "search_three" in msgs, orphans
    assert all(f["severity"] == "error" for f in orphans)
    assert any(a.startswith("unreachable_step:") for a in res["next_actions"])


def test_one_dropped_link_orphans_the_tail():
    # Search Two -> Search Three still linked, but nothing reaches Search Two.
    res = verify_playbook(yaml_text=_three_searches(link_a=False))
    assert res["ready_to_push"] is False
    assert len(_orphan_codes(res)) == 2


def test_compiler_still_only_warns():
    # An appliance playbook with a parked step must keep compiling/round-tripping.
    cres = compile_yaml(_three_searches(link_a=False, link_b=False), DB_PATH)
    assert cres.ok
    orphans = [e for e in cres.errors if e.code.value == "unreachable_step"]
    assert len(orphans) == 2 and all(e.severity == "warning" for e in orphans)


def test_graph_toggle_suppresses_visibly():
    res = verify_playbook(yaml_text=_three_searches(link_a=False),
                          disable_checks=["graph"])
    assert _orphan_codes(res) == []
    assert res["suppressed_count"] >= 2


def test_unlabeled_next_fan_out_is_parsed_and_emitted():
    y = _yaml("""
        collection: C
        playbooks:
          - name: P
            steps:
              - name: Start
                type: start
                unlabeled_next: [Search One, Search Two]
              - name: Search One
                type: set_variable
                vars: {one: "1"}
              - name: Search Two
                type: set_variable
                vars: {two: "2"}
    """)
    cres = compile_yaml(y, DB_PATH)
    assert cres.ok, [e.to_dict() for e in cres.errors]
    routes = cres.fsr_json["data"][0]["workflows"][0]["routes"]
    assert sorted(r["name"] for r in routes) == [
        "Start -> Search One", "Start -> Search Two"]
    assert _orphan_codes(verify_playbook(yaml_text=y)) == []


def test_unlabeled_next_unknown_target_is_an_error():
    y = _yaml("""
        collection: C
        playbooks:
          - name: P
            steps:
              - name: Start
                type: start
                unlabeled_next: [Nowhere]
              - name: Search One
                type: set_variable
                vars: {one: "1"}
    """)
    cres = compile_yaml(y, DB_PATH)
    assert not cres.ok
    assert any(e.code.value == "unknown_next_step" for e in cres.errors)


def test_enhancement_keeps_pre_existing_orphan_as_warning():
    before = _three_searches(link_b=False)          # Search Three already parked
    after = before.replace('{two: "2"}', '{two: "22"}')
    res = verify_enhancement(before_yaml=before, after_yaml=after,
                             user_message="change two to 22")
    assert _orphan_codes(res) == []
    parked = [w for w in res["warnings"] if w.get("code") == "unreachable_step"]
    assert parked and parked[0]["pre_existing"] is True
    assert res["ready_to_push"] is True


def test_enhancement_blocks_an_orphan_the_edit_introduced():
    before = _three_searches()
    after = _three_searches(link_a=False)
    res = verify_enhancement(before_yaml=before, after_yaml=after,
                             user_message="change search one")
    assert res["ready_to_push"] is False
    assert len(_orphan_codes(res)) == 2
    assert res["verified_id"] is None
