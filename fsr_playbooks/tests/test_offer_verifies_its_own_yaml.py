"""A direct-build `playbook_offer` verifies the YAML it carries.

Live: the model verified a three-search playbook, re-typed it into the offer
with two `next:` links missing, listed the warnings in prose, and offered it
anyway. The card trusted the model to have verified; the saved playbook ran
only its first search. The offer now runs `verify_playbook` on its own bytes.
"""
from __future__ import annotations

from fsr_playbooks.mcp_server.tools_emit import _offer_from_yaml

LINKED = """
collection: C
playbooks:
  - name: Three Searches
    steps:
      - name: Start
        type: start
        next: Search One
      - name: Search One
        type: set_variable
        vars: {one: "1"}
        next: Search Two
      - name: Search Two
        type: set_variable
        vars: {two: "2"}
        next: Search Three
      - name: Search Three
        type: set_variable
        vars: {three: "3"}
"""

RETYPED = LINKED.replace("        next: Search Two\n", "") \
                .replace("        next: Search Three\n", "")


def _offer(yaml_text: str) -> dict:
    return _offer_from_yaml("c1", "save it", yaml_text,
                            title_suggestion=None, editable_title=True)


def test_verified_yaml_is_offered():
    res = _offer(LINKED)
    assert res["ok"] is True, res
    assert res["card"]["final_yaml"] == LINKED


def test_retyped_yaml_with_dropped_links_is_refused():
    assert RETYPED != LINKED
    res = _offer(RETYPED)
    assert res["ok"] is False
    assert res["code"] == "offer_not_verified"
    codes = {f["code"] for f in res["required_fixes"]}
    assert codes == {"unreachable_step"}
    assert res["suggestions"], "the refusal must say what to fix"


def test_warnings_ride_on_the_card():
    # An unknown Jinja filter is a non-blocking warning: offered, but the
    # analyst sees it on the card rather than only in the model's prose.
    warned = LINKED.replace('{three: "3"}',
                            '{three: "{{ vars.steps.Search_One.one | nosuchfilter }}"}')
    res = _offer(warned)
    assert res["ok"] is True, res
    assert any(w["code"] == "unknown_jinja_filter"
               for w in res["card"].get("warnings", [])), res["card"]
