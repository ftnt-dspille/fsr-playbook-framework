"""Ratchet on the build system prompt: size and prohibition count only go down.

Sprint 4 W3 (prompt diet). The build prompt was 559 lines / 36.9 KB with 33
"never" and 35 "do not" restating guards and tool checks the dispatch layer
already enforces. A prompt that long is paid on every turn and buried the few
rules that matter. The ceilings sit just above the post-diet measurement. To
add a rule, first remove one; if a ceiling must rise, say why in the commit.
Detail that only matters for part of the tool surface belongs behind a
`<!--if tool-->` gate so the other slices do not pay for it.
"""
from __future__ import annotations

import re
from pathlib import Path

from fsr_playbooks.llm.intents import render_prompt_for_slice

_RAW = (Path(__file__).resolve().parents[1] / "agent"
        / "system_prompt_build.md").read_text(encoding="utf-8")

MAX_RAW_BYTES = 19_500
MAX_RENDERED_BYTES = 18_000      # full surface, every conditional taken
MAX_NEVER = 23
MAX_DO_NOT = 15
MAX_ALLCAPS_DIRECTIVES = 50


def _counts(text: str) -> dict[str, int]:
    return {
        "never": len(re.findall(r"\bnever\b", text, re.I)),
        "do_not": len(re.findall(r"\bdo not\b|\bdon't\b", text, re.I)),
        "caps": len(re.findall(r"\b[A-Z]{3,}\b", text)),
    }


def test_build_prompt_size_ceiling():
    assert len(_RAW.encode()) <= MAX_RAW_BYTES, len(_RAW.encode())
    assert len(render_prompt_for_slice(_RAW).encode()) <= MAX_RENDERED_BYTES


def test_build_prompt_prohibition_count_ceiling():
    c = _counts(_RAW)
    assert c["never"] <= MAX_NEVER, c
    assert c["do_not"] <= MAX_DO_NOT, c
    assert c["caps"] <= MAX_ALLCAPS_DIRECTIVES, c


def test_a_guided_slice_does_not_pay_for_freeform_authoring_detail():
    """Slice-gated detail: the hand-authored YAML section (skeleton, friendly
    keys) renders only when `validate_yaml` is in the slice, so a guided create
    (compose_playbook only) is smaller than the full surface."""
    from fsr_playbooks.llm.intents import FREEFORM_AUTHORING_TOOLS, tools_for_intent
    names = {t["name"] for t in tools_for_intent("build")} - FREEFORM_AUTHORING_TOOLS
    guided = render_prompt_for_slice(_RAW, names)
    full = render_prompt_for_slice(_RAW)
    assert "Hand-authored YAML" not in guided and "Hand-authored YAML" in full
    assert len(guided) < len(full)
