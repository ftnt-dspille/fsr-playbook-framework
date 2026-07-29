"""The AUTHORING.md step reference was removed in favor of a clean
hand-authored guide that doesn't expose wire-internal shapes. The
generated block tests are retired -- the doc is now the sole source of
truth and is hand-maintained.

The alias-coverage test still runs: every short type alias must appear
somewhere in AUTHORING.md so agents discover all step types.
"""
from __future__ import annotations

from pathlib import Path

from fsr_playbooks.tests.step_reference_gen import _AUTHORING


def test_every_short_type_alias_documented():
    """Every short type that maps to an oracle-covered canonical name must
    appear in AUTHORING.md so agents discover all step types."""
    from fsr_playbooks.compiler.resolver._constants import SHORT_TYPE_TO_FSR
    from fsr_playbooks.tests.wire_shape_oracle import load_oracle

    text = Path(_AUTHORING).read_text()
    oracle = load_oracle()
    for short, canonical in SHORT_TYPE_TO_FSR.items():
        if canonical in oracle:
            assert f"`{short}`" in text, (
                f"{short} missing from AUTHORING.md -- add it to the step type table"
            )
