"""Phase 5 — the AUTHORING.md per-step reference is generated from the oracle.

Guards against hand-drift: the GENERATED block in `docs/AUTHORING.md` must
match `render_step_reference()` byte-for-byte. If this fails, regenerate with
`python -m fsr_playbooks.tests.step_reference_gen --write` and commit.
"""
from __future__ import annotations

from pathlib import Path

from fsr_playbooks.tests.step_reference_gen import (
    _AUTHORING,
    _BEGIN,
    _END,
    render_step_reference,
)


def test_authoring_has_generated_block():
    text = Path(_AUTHORING).read_text()
    assert _BEGIN in text and _END in text, (
        "AUTHORING.md is missing the generated step-reference markers; run "
        "`python -m fsr_playbooks.tests.step_reference_gen --write`"
    )


def test_generated_block_is_in_sync():
    text = Path(_AUTHORING).read_text()
    committed = text[text.index(_BEGIN): text.index(_END) + len(_END)]
    assert committed == render_step_reference(), (
        "docs/AUTHORING.md step reference is stale — regenerate with "
        "`python -m fsr_playbooks.tests.step_reference_gen --write` and commit."
    )


def test_every_short_type_alias_documented():
    """Every short type that maps to an oracle-covered canonical name must
    appear as an alias in the rendered reference."""
    from fsr_playbooks.compiler.resolver._constants import SHORT_TYPE_TO_FSR
    from fsr_playbooks.tests.wire_shape_oracle import load_oracle

    block = render_step_reference()
    oracle = load_oracle()
    for short, canonical in SHORT_TYPE_TO_FSR.items():
        if canonical in oracle:
            assert f"`{short}`" in block, f"{short} missing from step reference"
