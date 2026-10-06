"""A shortened document must not verify (tracker #131).

Live on 8.0 the model passed verify_enhancement an elided stub -- a literal
`... (truncated) ...` inside a step argument -- as BOTH before_yaml and
after_yaml. It parsed, compiled, diffed clean against itself and came back
ready, and the salvaged patch would have put the stub behind an Apply button.
Two fixes: verify_playbook refuses elision markers (`elided_document`), and
while a playbook is open verify_enhancement diffs against FortiSOAR's copy,
never the one the model typed.
"""
from __future__ import annotations

import textwrap

import pytest

from fsr_playbooks.mcp_server import verify_playbook
from fsr_playbooks.mcp_server._shared import reset_grounded_yaml, set_grounded_yaml
from fsr_playbooks.mcp_server.tools_enhancement import verify_enhancement


def _yaml(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


def _playbook(two_body: str = 'two: "2"', extra: str = "") -> str:
    return _yaml(f"""
        collection: C
        playbooks:
          - name: P
            steps:
              - name: Start
                type: start
                next: One
              - name: One
                type: set_variable
                vars: {{one: "1"}}
                next: Two
              - name: Two
                type: set_variable
                vars: {{{two_body}}}
                next: Three
              - name: Three
                type: set_variable
                vars: {{three: "3"}}
        {extra}""")


def _elided(res: dict) -> list[dict]:
    return [f for f in res["required_fixes"] if f.get("code") == "elided_document"]


def test_clean_playbook_has_no_elision():
    res = verify_playbook(yaml_text=_playbook())
    assert _elided(res) == []
    assert res["ready_to_push"] is True


@pytest.mark.parametrize("marker", [
    'two: "... (truncated) ..."',
    'two: "[snip]"',
    'two: "x"  # ... rest unchanged',
    'two: "x"  # rest of the playbook as before',
    'two: "… remaining steps"',
])
def test_marker_blocks_ready_to_push(marker):
    res = verify_playbook(yaml_text=_playbook(two_body=marker.split("  #")[0])
                          if "#" not in marker else
                          _playbook().replace('vars: {two: "2"}',
                                              'vars: {two: "x"}' + marker.split('"x"')[1]))
    fixes = _elided(res)
    assert fixes, res["required_fixes"]
    assert res["ready_to_push"] is False
    assert res["next_actions"][0].startswith("elided_document")
    assert "line " in fixes[0]["path"]


def test_indented_ellipsis_line_blocks_but_document_end_does_not():
    indented = _playbook().replace("      - name: Three",
                                   "      ...\n      - name: Three")
    assert _elided(verify_playbook(yaml_text=indented))
    doc_end = _playbook() + "...\n"
    assert _elided(verify_playbook(yaml_text=doc_end)) == []


def test_ordinary_prose_with_the_words_is_not_a_marker():
    prose = _playbook(two_body='two: "the rest is handled by the SOC"')
    assert _elided(verify_playbook(yaml_text=prose)) == []


def test_enhancement_ignores_typed_before_when_a_playbook_is_open():
    """The #131 shape: stub passed as before AND after while a real playbook
    is open. The open copy is the baseline, so the missing steps are drops and
    the marker is an error -- not a clean self-diff."""
    open_pb = _playbook()
    stub = _yaml("""
        collection: C
        playbooks:
          - name: P
            steps:
              - name: Start
                type: start
                next: Three
              - name: Three
                type: set_variable
                vars: {three: "... (truncated) ..."}
    """)
    token = set_grounded_yaml(open_pb)
    try:
        res = verify_enhancement(before_yaml=stub, after_yaml=stub)
    finally:
        reset_grounded_yaml(token)
    assert res["ready_to_push"] is False
    assert "before_yaml_ignored" in res["evidence"]
    assert {r["step"] for r in res["regressions"]
            if r["kind"] == "step_dropped"} >= {"One", "Two"}
    assert _elided(res)


def test_marker_already_in_the_open_playbook_is_grandfathered():
    """A playbook that already carries the text is the analyst's, not the
    edit's: a one-step edit to it must still be offerable."""
    before = _playbook(two_body='two: "[snip]"')
    after = before.replace('vars: {one: "1"}', 'vars: {one: "11"}')
    token = set_grounded_yaml(before)
    try:
        res = verify_enhancement(after_yaml=after)
    finally:
        reset_grounded_yaml(token)
    assert _elided(res) == []
    assert res["ready_to_push"] is True, res["required_fixes"]
