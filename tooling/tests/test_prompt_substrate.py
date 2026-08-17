"""The investigation eval must never score a prompt nobody ships.

Regression pin for a defect that was invisible for as long as it existed:
`calibrate_investigation` called `load_intent_prompt("triage")`, which resolves
`fsr_playbooks/agent/system_prompt_triage.md` -- a file this repo does not have
-- and silently returned a 583-char fallback stub. Every investigation number,
including A/B comparisons of triage-prompt edits, was measured against that
stub. Both arms of an A/B got the same text, so prompt changes were structurally
unmeasurable while the runs looked entirely healthy.

These tests are offline and connector-optional: they assert the SHAPE of the
resolution (refuse, don't fall back), not any particular prompt content.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from evals.prompt_source import (
    MIN_CREDIBLE_PROMPT_CHARS,
    PromptUnresolvable,
    resolve_triage_prompt,
)

CALIBRATE = (Path(__file__).resolve().parents[1]
             / "evals" / "calibrate_investigation.py")


def test_calibrate_does_not_use_the_fallback_loader() -> None:
    """`load_intent_prompt` is the exact call that introduced the stub.

    Grepping the source (rather than running the agent) is deliberate: the
    defect was that the wrong prompt loaded *successfully*, so nothing at
    runtime raised. Only the call site itself distinguishes the two.
    """
    src = CALIBRATE.read_text(encoding="utf-8")
    calls = re.findall(r"^\s*system\s*=\s*load_intent_prompt\(", src, re.M)
    assert not calls, (
        "calibrate_investigation assigns its system prompt from "
        "load_intent_prompt(), which falls back to a 583-char stub in this "
        "repo. Use evals.prompt_source.resolve_triage_prompt(), which raises "
        "instead of quietly measuring the wrong agent."
    )
    assert "resolve_triage_prompt" in src


def test_unresolvable_prompt_raises_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no connector reachable, the resolver must REFUSE.

    A fallback here is worse than a crash: it produces numbers that look like
    measurements of the shipped prompt.
    """
    monkeypatch.delenv("FSR_CONNECTOR_REPO", raising=False)
    monkeypatch.setattr(
        "evals.prompt_source._connector_on_path", lambda: None)

    import sys
    # Hide any already-imported connector so this test is order-independent.
    monkeypatch.setitem(sys.modules, "fsr_soc_triage.prompt_assembly", None)

    with pytest.raises(PromptUnresolvable) as exc:
        resolve_triage_prompt()
    assert "FSR_CONNECTOR_REPO" in str(exc.value), (
        "the error must say how to fix it, not just that it failed")


def test_stub_is_opt_in_and_labels_itself() -> None:
    """`allow_stub=True` is legal, but the origin must admit what it is."""
    src = resolve_triage_prompt(allow_stub=True)
    if "FALLBACK STUB" in src.origin:
        assert len(src.text) < MIN_CREDIBLE_PROMPT_CHARS, (
            "a prompt long enough to be real should not be labelled a stub")
    else:
        # A real prompt was reachable -- then it must clear the floor.
        assert len(src.text) >= MIN_CREDIBLE_PROMPT_CHARS


def test_fingerprint_distinguishes_two_prompts() -> None:
    """Two runs with the same fingerprint cannot show a prompt effect.

    This is the property that would have caught the void A/B immediately:
    identical fingerprints across 'treatment' and 'control' means nothing was
    manipulated, however different the scores looked.
    """
    a = resolve_triage_prompt(allow_stub=True)
    b = resolve_triage_prompt(allow_stub=True)
    assert a.fingerprint == b.fingerprint, "resolution must be deterministic"
    assert len(a.fingerprint) == 12
    assert str(len(a.text)) in a.summary and a.fingerprint in a.summary
