"""The committed reference DBs must carry no internal infra strings.

`fsr_playbooks/_data/fsr_reference.db` is packaged into the wheel, so anything
in it is published to PyPI; `tooling/tests/fixtures/tooling_reference.db` is
tracked on the public GitHub mirror. Both are assembled from a dev cache synced
off a live lab appliance, so live URLs ride along unless something stops them.

Both had already leaked when this test was written: 7,000+ `https://10.99.x.x`
values in the fixture's `playbook_steps.source_path`, plus the lab admin
account, and a lab IP inside a `step_examples` code sample in the shipped DB.
The pre-commit guard skipped them, because it read only text files and git
renders a sqlite blob as "Binary files differ" -- no added lines, nothing to
scan, silent pass.

This runs the guard's own binary scanner in the test suite so CI enforces it on
every push, rather than trusting that each contributor has the hook installed.
Scanning raw bytes (not cell values) is deliberate: sqlite leaves deleted rows
in free pages, so a DB can have clean live cells and dirty bytes.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

import fsr_playbooks

_REPO_ROOT = Path(fsr_playbooks.__file__).resolve().parent.parent
_GUARD = _REPO_ROOT / "scripts" / "check_infra_leaks.py"

TRACKED_DBS = [
    _REPO_ROOT / "fsr_playbooks" / "_data" / "fsr_reference.db",
    _REPO_ROOT / "tooling" / "tests" / "fixtures" / "tooling_reference.db",
]


def _load_guard():
    """Import the guard by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("_infra_guard", _GUARD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_infra_guard"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("db", TRACKED_DBS, ids=lambda p: p.name)
def test_committed_reference_db_has_no_infra_strings(db: Path):
    if not _GUARD.exists():          # installed wheel, not a source checkout
        pytest.skip("scripts/check_infra_leaks.py not present (not a checkout)")
    if not db.exists():
        pytest.skip(f"{db.name} not present in this checkout")

    leaks = _load_guard().scan_blob(db.read_bytes())
    assert not leaks, (
        f"{db.relative_to(_REPO_ROOT)} contains internal infra strings: "
        f"{', '.join(leaks)}.\n"
        f"Run: python scripts/scrub_infra_from_db.py {db.relative_to(_REPO_ROOT)}"
    )
