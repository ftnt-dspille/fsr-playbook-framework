"""Gate test for the step-type coverage matrix -- the north-star instrument.

Enforces three invariants so the matrix cannot silently drift from reality:

  1. COMPLETENESS -- every friendly step type in ``SHORT_TYPE_TO_FSR`` has an
     explicit COVERAGE row. Adding a step type without a coverage decision
     fails the gate. No accidental gaps.
  2. NO FALSE CLAIMS -- the ``typed``/``schema`` flags match the live
     registries (``STEP_ARG_MODELS`` / ``emit_step_arg_schema``). A row
     claiming a type is typed/schema'd when it isn't (or vice versa) fails.
  3. PALETTE GAPS -- the editor palette is fully mapped, and
     ``palette_gaps()`` returns exactly the known set. Closing a gap
     (adding a friendly surface for Utilities/Evaluate/etc.) requires
     updating this assertion -- the gate makes the win visible instead of
     letting it slip by unnoticed.

Plus a read-classification sanity check: every type marked ``minimified``
must have an explicit per-type branch in the decompiler source.

This gate is the enforcement arm of ``docs/plans/STEP_TYPE_COVERAGE_PLAN.md``
(in the pyfsr repo). When it fails, the fix is almost always to update the
COVERAGE matrix to match the new reality -- and then act on the change.
"""
from __future__ import annotations

from pathlib import Path

from fsr_playbooks.compiler.resolver import SHORT_TYPE_TO_FSR
from fsr_playbooks.compiler.typed_args.schema import emit_step_arg_schema
from fsr_playbooks.compiler.typed_args.steps import STEP_ARG_MODELS

import tooling.step_type_coverage as cov

_REPO = Path(__file__).resolve().parents[2]
_DECOMPILER = (_REPO / "fsr_playbooks" / "compiler" / "decompiler.py").read_text()

# Editor palette types that currently have NO friendly YAML surface.
# Closing any of these is a north-star win -- update this set when one lands.
# (Evaluate and Add Reference Block are NOT step types -- no `script` handler --
# so they are in NON_STEP_TYPES, not here.)
#
# EMPTY as of P4 (2026-07-01): both palette gaps are closed.
#   - Utilities (CyopsUtilices) -> `utilities` connector-family alias (reuses
#     the P3 ConnectorArgs envelope model; defaults connector:cyops_utilities).
#   - Trigger Tenant Playbook (RemotePlaybookReference) -> `trigger_tenant_playbook`
#     (own script handler; TriggerTenantPlaybookArgs validation-only envelope).
# All 17 authorable editor-palette step types now have a friendly YAML surface.
_EXPECTED_PALETTE_GAPS: set[str] = set()

# Palette entries that are not step types at all (no script handler). If one
# ever becomes a real step type, move it to EDITOR_PALETTE + add coverage.
_EXPECTED_NON_STEP_TYPES = {
    "Evaluate": "RunScript",
    "Add Reference Block": "ReferenceBlock",
}

# The connector family: first-class UI options that all route through the
# connector dispatcher. Grounded in the step_types `script` column.
_EXPECTED_CONNECTOR_FAMILY = {
    "Connectors", "CodeSnippet", "CyopsUtilites", "SendMail",
}


def test_coverage_matrix_literals_valid():
    for name, c in cov.COVERAGE.items():
        c.validate_literal()  # raises on bad read/priority enum


def test_every_friendly_type_has_a_coverage_row():
    friendly = set(SHORT_TYPE_TO_FSR)
    covered = set(cov.COVERAGE)
    assert friendly == covered, (
        f"friendly types without a coverage decision (add a COVERAGE row): "
        f"{sorted(friendly - covered)}; "
        f"coverage rows for non-friendly types (remove): {sorted(covered - friendly)}"
    )


def test_typed_flag_matches_live_registry():
    for name, c in cov.COVERAGE.items():
        live = name in STEP_ARG_MODELS
        assert c.typed is live, (
            f"{name}: COVERAGE.typed={c.typed} but STEP_ARG_MODELS has it={live}"
        )


def test_schema_flag_matches_live_emitter():
    for name, c in cov.COVERAGE.items():
        live = emit_step_arg_schema(name) is not None
        assert c.schema is live, (
            f"{name}: COVERAGE.schema={c.schema} but emit_step_arg_schema "
            f"returns {'a schema' if live else 'None'}"
        )


def test_minimified_types_have_decompiler_branch():
    for name, c in cov.COVERAGE.items():
        if c.read != cov.READ_MINIMIFIED:
            continue
        needle = f's.type == "{name}"'
        assert needle in _DECOMPILER, (
            f"{name}: COVERAGE.read=minimified but the decompiler has no "
            f"explicit `{needle}` branch (reclassify as pass-through, or add "
            f"the minimification branch)"
        )


def test_editor_palette_is_fully_mapped():
    # Every editor label maps to a known canonical, and the canonical set
    # is non-empty (guards against a typo silently dropping the palette).
    # NOTE: Evaluate + Add Reference Block are NOT step types (no script) and
    # live in NON_STEP_TYPES, so the palette is 17, not 19.
    assert len(cov.EDITOR_PALETTE) == 17, cov.EDITOR_PALETTE
    for label, canonical in cov.EDITOR_PALETTE.items():
        assert isinstance(canonical, str) and canonical, label


def test_non_step_types_documented():
    # The two palette entries that aren't step types must be explicitly tracked
    # so their exclusion is a decision, not an omission.
    assert cov.NON_STEP_TYPES == _EXPECTED_NON_STEP_TYPES, cov.NON_STEP_TYPES


def test_connector_family_documented():
    assert set(cov.CONNECTOR_FAMILY) == _EXPECTED_CONNECTOR_FAMILY, cov.CONNECTOR_FAMILY


def test_palette_gaps_match_expected():
    actual = {label for label, _canon in cov.palette_gaps()}
    assert actual == _EXPECTED_PALETTE_GAPS, (
        f"editor palette gaps changed -- if a gap was closed, congratulations, "
        f"drop it from _EXPECTED_PALETTE_GAPS: {sorted(actual ^ _EXPECTED_PALETTE_GAPS)}; "
        f"now: {sorted(actual)}"
    )


def test_matrix_snapshot_is_truthful():
    # A readable failure if someone prints the dashboard but the gate is red.
    out = cov.render_matrix()
    assert "step_type" in out and "typed" in out
