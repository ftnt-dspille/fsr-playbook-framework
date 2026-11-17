"""What the model is actually told about each tool.

`build_registry` used to send only the first docstring paragraph
(`doc.split("\\n\\n", 1)[0]`). Every "call me when", every "NOT for", and
every safety contract below a blank line was written, maintained, and never
delivered -- `run_op` shipped 89 chars and withheld its whole destructive-op
`confirm=True` contract. The bug was invisible because a docstring that looks
right in the source reads nothing like what the model receives.

These tests pin the delivered text, not the source text.
"""
from __future__ import annotations

import inspect

from fsr_playbooks.llm.tools import REGISTRY, tool_description


def test_guidance_below_the_blank_line_is_delivered():
    """The regression itself: a second paragraph must survive."""
    doc = "One-line purpose.\n\nNOT for the sibling case; use the other tool."
    assert "NOT for the sibling case" in tool_description(doc)


def test_args_block_is_dropped():
    """Parameter docs are already in `input_schema` -- don't pay twice."""
    doc = "Purpose.\n\nWhen to call it.\n\nArgs:\n  x: the x value.\n  y: the y."
    out = tool_description(doc)
    assert "When to call it." in out
    assert "the x value" not in out


def test_cap_truncates_on_a_paragraph_boundary():
    doc = "\n\n".join(["A" * 300, "B" * 300, "C" * 300, "D" * 300, "E" * 300])
    out = tool_description(doc, cap=700)
    assert len(out) <= 700
    # whole paragraphs only -- never a sentence cut mid-word
    assert all(len(set(p)) == 1 for p in out.split("\n\n"))


def test_one_oversized_paragraph_is_truncated_not_dropped():
    out = tool_description("Z" * 5000, cap=100)
    assert out and len(out) <= 100


def test_run_op_delivers_its_destructive_op_contract():
    """The safety case. If this ever fails, the agent is executing
    containment ops without ever having been told the confirm rules."""
    desc = REGISTRY["run_op"].description
    assert "confirm=True" in desc
    assert "destructive" in desc.lower()
    assert "requires_confirmation" in desc


def test_no_tool_describes_itself_in_under_80_characters():
    """20 of 39 tools once did. A description that short cannot state a
    precondition, so the model is guessing between siblings."""
    thin = {n: s.description for n, s in REGISTRY.items() if len(s.description) < 80}
    assert not thin, f"too thin to choose on: {sorted(thin)}"


def test_delivered_description_is_a_prefix_of_the_docstring():
    """No paraphrasing layer: what ships is what an author reads in the
    source, so editing the docstring is enough to change the model's view."""
    for name, spec in REGISTRY.items():
        doc = (inspect.getdoc(spec.fn) or "").strip()
        if not doc:
            continue
        first = spec.description.split("\n\n", 1)[0]
        assert doc.startswith(first[:200]), name
