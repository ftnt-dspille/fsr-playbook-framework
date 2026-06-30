"""Guard: the published-wheel force-include manifest covers the whole package.

The published ``fsr_playbooks`` dist is built from packaging/fsr_playbooks/, whose
source tree lives two levels up at the repo root (../../fsr_playbooks). Hatchling
forbids ``..`` in ``packages``/``only-include``, so the surface is grafted in via
an explicit ``[tool.hatch.build.targets.wheel.force-include]`` manifest that lists
each top-level module and subpackage by hand (force-include cannot honour
``exclude``, which is how ``tests/`` is kept out).

Hand-maintained manifests rot: add a new module or subpackage under
fsr_playbooks/ and forget to list it, and it silently won't ship — a broken
release that nothing else catches. This test makes that failure loud and local:
it asserts every importable top-level module and every non-test subdirectory is
present in the manifest.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG_DIR = _REPO_ROOT / "fsr_playbooks"
_PYPROJECT = _REPO_ROOT / "packaging" / "fsr_playbooks" / "pyproject.toml"

# Dirs under fsr_playbooks/ that are intentionally NOT shipped in the wheel.
_NOT_SHIPPED = {"tests", "__pycache__"}


def _manifest_shipped_names() -> set[str]:
    """Top-level names the force-include manifest grafts into the wheel.

    Parsed by regex rather than a TOML lib so this runs on the 3.10 floor
    without tomli. Matches the source side of e.g.
    ``"../../fsr_playbooks/compiler" = "fsr_playbooks/compiler"`` and captures
    the first path component under fsr_playbooks/ (``compiler``, ``__init__.py``).
    """
    text = _PYPROJECT.read_text()
    # Only look inside the force-include table to avoid matching prose/comments.
    start = text.index("[tool.hatch.build.targets.wheel.force-include]")
    table = text[start:]
    names: set[str] = set()
    for m in re.finditer(r'"\.\./\.\./fsr_playbooks/([^/"]+)', table):
        names.add(m.group(1))
    return names


def _required_shipped_names() -> set[str]:
    """Top-level modules + subpackage dirs that MUST ship (everything but tests)."""
    required: set[str] = set()
    for child in _PKG_DIR.iterdir():
        if child.name in _NOT_SHIPPED:
            continue
        if child.is_dir():
            required.add(child.name)
        elif child.suffix == ".py":
            required.add(child.name)
    return required


@pytest.mark.skipif(not _PYPROJECT.exists(), reason="packaging dist not present")
def test_force_include_manifest_covers_package() -> None:
    required = _required_shipped_names()
    shipped = _manifest_shipped_names()
    missing = required - shipped
    assert not missing, (
        "These top-level fsr_playbooks entries are NOT in the wheel force-include "
        f"manifest and would silently be dropped from the published package: "
        f"{sorted(missing)}. Add them to "
        "packaging/fsr_playbooks/pyproject.toml [tool.hatch.build.targets.wheel.force-include]."
    )
