"""The offer card lists changed steps in flow order, trigger first.

`_diff_collections` builds added/removed from name *sets*, so the card used to
show steps in hash order (live: "Start" rendered last, under the steps it
triggers). Every change row, and each name list, follows the playbook's flow:
trigger, then breadth-first along next / branches.
"""
import itertools

import pytest

from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.mcp_server.tools_enhancement import _diff_collections

_FLOW = ["Start", "Read Key Id", "Revoke Key", "Add Note", "Tag Alert", "Close Alert"]

_BEFORE = """
collection: Flow Order
playbooks:
  - name: Suspend
    steps:
      - name: Placeholder
        type: start
"""


def _after(declared):
    nxt = {a: b for a, b in zip(_FLOW, _FLOW[1:])}
    lines = ["collection: Flow Order", "playbooks:", "  - name: Suspend",
             "    steps:"]
    for n in declared:
        typ = "start" if n == "Start" else "set_variable"
        lines += [f"      - name: {n}", f"        type: {typ}"]
        if n in nxt:
            lines.append(f"        next: {nxt[n]}")
        if typ == "set_variable":
            lines += ["        vars:", f"          v{_FLOW.index(n)}: 1"]
    return "\n".join(lines) + "\n"


def _diff(before_text, after_text):
    before, berrs = parse_yaml(before_text)
    after, aerrs = parse_yaml(after_text)
    assert before is not None, berrs
    assert after is not None, aerrs
    return _diff_collections(before, after, None)


# Several declaration orders, so a pass can't be set-hash luck.
_ORDERS = [list(reversed(_FLOW))] + [
    list(p) for p in itertools.islice(itertools.permutations(_FLOW), 7, 400, 57)]


@pytest.mark.parametrize("declared", _ORDERS)
def test_added_steps_follow_the_flow(declared):
    _regs, summary = _diff(_BEFORE, _after(declared))
    added_rows = [c["step"] for c in summary["changes"] if c["kind"] == "added"]
    assert added_rows == _FLOW
    assert summary["steps_added"] == _FLOW


def test_removed_steps_rank_by_where_they_sat_before():
    _regs, summary = _diff(_after(list(reversed(_FLOW))), _BEFORE)
    removed = [c["step"] for c in summary["changes"] if c["kind"] == "removed"]
    assert removed == _FLOW
    assert summary["steps_removed"] == _FLOW
