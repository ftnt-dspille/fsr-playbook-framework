"""Phase 0.3 CI test for VISUAL_EDITOR_PLAN.

Every authored YAML fixture under `examples/` MUST round-trip through
`to_visual` → `from_visual` byte-identical when no edits are made.
This is the contract that lets the visual/yaml toggle stay safe: if
this test breaks, the toggle is no longer trustworthy.

Two additional behaviors pinned here:
- adding a position re-emits a `# fsrpb:layout` block at the head;
- the second round-trip after an edit is itself byte-stable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from compiler.visual_model import to_visual, from_visual

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
FIXTURES = sorted(p for p in EXAMPLES.glob("*.yaml") if not p.name.endswith(".test.yaml"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_identity_roundtrip(path: Path) -> None:
    text = path.read_text()
    graph = to_visual(text)
    assert graph["playbooks"], f"{path.name}: no playbooks parsed"
    out = from_visual(graph, text)
    assert out == text, (
        f"{path.name}: identity round-trip drift "
        f"(diff len={len(out) - len(text)})"
    )


def test_layout_block_persists_and_is_stable() -> None:
    text = (EXAMPLES / "decision_branch.yaml").read_text()
    g = to_visual(text)
    g["playbooks"][0]["nodes"][0]["position"] = {"x": 12, "y": 34}
    out = from_visual(g, text)
    # Layout block now lives at the bottom of the file so the YAML body
    # opens with the playbook itself — readable diffs, no header noise.
    assert "# fsrpb:layout\n" in out, "layout marker missing"
    assert out.rstrip().endswith("# fsrpb:layout-end"), "layout block should be at footer"

    g2 = to_visual(out)
    pos = g2["playbooks"][0]["nodes"][0]["position"]
    assert pos == {"x": 12, "y": 34}
    assert from_visual(g2, out) == out, "second round-trip drifted"


def test_decision_branches_become_edges() -> None:
    text = (EXAMPLES / "decision_branch.yaml").read_text()
    g = to_visual(text)
    pb = g["playbooks"][0]
    branch_edges = [e for e in pb["edges"] if e["branch_kind"] == "branch"]
    assert len(branch_edges) == 2, branch_edges
    labels = {e["label"] for e in branch_edges}
    assert "high" in labels
    # Default branch synthesizes an "Else" label (parser preserves
    # `option: Else` from the YAML).
    assert any(l in labels for l in ("Else", "default"))


def test_arg_edit_round_trips() -> None:
    """Phase 3 — argument-level edits write back through ruamel."""
    text = (EXAMPLES / "decision_branch.yaml").read_text()
    g = to_visual(text)
    # Find the set_variable that defines `severity` and rename the var.
    sv = next(n for n in g["playbooks"][0]["nodes"] if n["id"] == "read_severity")
    sv["arguments"] = {
        "arg_list": [{"name": "severity",
                       "value": "{{ vars.input.records[0].severity | upper }}"}]
    }
    out = from_visual(g, text)
    assert "| upper" in out, "edit didn't reach the YAML body"
    # Re-parse the edited YAML — should still be valid + reflect the change.
    g2 = to_visual(out)
    assert g2["errors"] == []
    sv2 = next(n for n in g2["playbooks"][0]["nodes"] if n["id"] == "read_severity")
    assert "| upper" in str(sv2["arguments"])


def test_decision_branch_retarget_round_trips() -> None:
    """Phase 3.5/3.6 — flip a decision's branch targets; YAML reflects it."""
    text = (EXAMPLES / "decision_branch.yaml").read_text()
    g = to_visual(text)
    edges = g["playbooks"][0]["edges"]
    branch_idxs = [i for i, e in enumerate(edges) if e["branch_kind"] == "branch"]
    assert len(branch_idxs) >= 2
    i, j = branch_idxs[0], branch_idxs[1]
    edges[i]["target"], edges[j]["target"] = edges[j]["target"], edges[i]["target"]
    out = from_visual(g, text)
    g2 = to_visual(out)
    assert g2["errors"] == [], g2["errors"]
    new_branches = [e for e in g2["playbooks"][0]["edges"] if e["branch_kind"] == "branch"]
    # The 'high' label should now point at log_low_severity (the swap).
    high = next(e for e in new_branches if e["label"] == "high")
    assert high["target"] == "log_low_severity"


def test_edge_source_move_round_trips() -> None:
    """Move an edge's SOURCE from one step to another (UI: drag the
    edge handle off step A and drop it on step B). The YAML side must
    reflect the new wiring after `from_visual` -> `to_visual`."""
    text = (EXAMPLES / "decision_branch.yaml").read_text()
    g = to_visual(text)
    edges = g["playbooks"][0]["edges"]
    # Target an existing linear `next` edge and re-source it.
    e = next(e for e in edges if e["source"] == "read_severity"
             and e["branch_kind"] == "next")
    old_source = e["source"]
    new_source = "start"
    # Drop the old `start -> read_severity` edge first to avoid a
    # collision when the moved edge takes its place.
    edges[:] = [x for x in edges if not (x["source"] == "start"
                                          and x["target"] == "read_severity")]
    e["source"] = new_source
    out = from_visual(g, text)
    g2 = to_visual(out)
    assert g2["errors"] == [], g2["errors"]
    # The moved edge's old source no longer points to its old target.
    assert not any(x["source"] == old_source and x["target"] == e["target"]
                    for x in g2["playbooks"][0]["edges"])
    # The new source carries the rewired edge.
    assert any(x["source"] == new_source and x["target"] == e["target"]
                for x in g2["playbooks"][0]["edges"])


def test_arg_edit_keeps_nested_keys_under_arguments() -> None:
    """Regression: editing a connector step's args (e.g. adding
    `mock_result`) must NOT promote nested `connector` / `operation` /
    `params` to the step level. Doing so left both forms in the YAML
    and broke validation. The fix preserves the original nested style
    via the existing arguments-block lookup."""
    import textwrap
    text = textwrap.dedent(
        """\
        playbooks:
          - name: Demo
            steps:
              - type: start
                name: Start
                next: Block IP
              - type: connector
                name: Block IP
                arguments:
                  connector: fortigate-firewall
                  operation: block_ip_new
                  params:
                    method: Quarantine Based
                next: End
              - type: end
                name: End
        """
    )
    g = to_visual(text)
    block = next(n for n in g["playbooks"][0]["nodes"] if n["id"] == "block_ip")
    # Emulate `saveAsMock` adding a `mock_result` key alongside the
    # existing nested args.
    block["arguments"] = {**block["arguments"], "mock_result": {"already_blocked": ["1.1.1.1"]}}
    out = from_visual(g, text)
    # connector / operation / params must remain under `arguments:`,
    # not at the step level (which is what triggered the duplicate-keys
    # bug). Re-parse and check structural location rather than matching
    # whitespace fragility.
    import yaml as _yaml
    doc = _yaml.safe_load(out)
    step = next(s for s in doc["playbooks"][0]["steps"] if s.get("name") == "Block IP")
    assert "connector" not in step, step    # not hoisted to step level
    assert "operation" not in step, step
    assert "params" not in step, step
    assert step["arguments"]["connector"] == "fortigate-firewall"
    assert step["arguments"]["operation"] == "block_ip_new"
    assert step["arguments"]["params"]["method"] == "Quarantine Based"
    assert step["arguments"]["mock_result"]["already_blocked"] == ["1.1.1.1"]


def test_linear_next_retarget_round_trips() -> None:
    """Change a step's `next:` to point at a different existing step."""
    text = (EXAMPLES / "decision_branch.yaml").read_text()
    g = to_visual(text)
    edges = g["playbooks"][0]["edges"]
    # `start -> read_severity` becomes `start -> branch_on_severity`
    se = next(e for e in edges if e["source"] == "start")
    se["target"] = "branch_on_severity"
    out = from_visual(g, text)
    g2 = to_visual(out)
    assert g2["errors"] == [], g2["errors"]
    se2 = next(e for e in g2["playbooks"][0]["edges"] if e["source"] == "start"
                and e["branch_kind"] == "next")
    assert se2["target"] == "branch_on_severity"
