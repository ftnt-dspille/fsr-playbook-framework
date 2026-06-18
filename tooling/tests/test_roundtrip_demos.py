"""YAML→compile→decompile→emit roundtrip on the demo fixtures.

Catches regressions where a friendly-form authoring change diverges from
the canonical wire form on the second emission. The compiled FSR JSON is
the round-trip surface — same property the published `roundtrip` tool
checks.
"""
from pathlib import Path

import pytest

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.roundtrip import roundtrip

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _yaml_fixtures() -> list[Path]:
    out = []
    for p in sorted(EXAMPLES.glob("demo_*.yaml")):
        if p.name.endswith(".test.yaml"):
            continue
        out.append(p)
    return out


def _sidecarless_fixtures() -> list[Path]:
    """Examples without a .test.yaml partner — the smoke set from TODO #5."""
    out = []
    for p in sorted(EXAMPLES.glob("*.yaml")):
        if p.name.startswith("demo_"):
            continue
        if p.name.endswith(".test.yaml") or p.suffix.endswith(".bak"):
            continue
        # `recipe_*` fixtures depend on connectors being installed on a
        # live FSR (precheck phase); skip in offline smoke.
        if p.name.startswith("recipe_"):
            continue
        out.append(p)
    return out


@pytest.mark.parametrize("fixture", _yaml_fixtures(), ids=lambda p: p.stem)
def test_demo_yaml_semantic_roundtrip(fixture: Path, db_path):
    text = fixture.read_text()
    res = compile_yaml(text, db_path)
    assert res.ok, [e.to_dict() for e in res.errors]
    ok, diffs = roundtrip(res.fsr_json, db_path)
    assert ok, f"{fixture.name} diffs:\n  " + "\n  ".join(diffs[:20])


@pytest.mark.parametrize(
    "fixture", _sidecarless_fixtures(), ids=lambda p: p.stem,
)
def test_sidecarless_example_compiles_and_roundtrips(fixture: Path, db_path):
    """TODO #5 smoke: examples without a .test.yaml sidecar still need a
    safety net. Compile + semantic roundtrip catches the bulk of regressions
    that would otherwise sneak in (the live push+200 leg is e2e-only)."""
    text = fixture.read_text()
    res = compile_yaml(text, db_path)
    assert res.ok, [e.to_dict() for e in res.errors]
    ok, diffs = roundtrip(res.fsr_json, db_path)
    assert ok, f"{fixture.name} diffs:\n  " + "\n  ".join(diffs[:20])
