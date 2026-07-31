"""`__version__` must not depend on the working directory.

It used to. `fsr_playbooks/__init__.py` asked importlib.metadata for a
distribution named `fsr_playbooks`, which does not exist -- the package ships
as `fsr-playbooks` on PyPI and as `fsrpb` in a dev checkout. The only thing
that ever answered was a stale `fsr_playbooks.egg-info` in the repo root, and
importlib.metadata finds that only when cwd is on sys.path. So the version read
0.4.10 from this repo and "0.0.0+unknown" from anywhere else, which tripped the
connector's exact-version guard across ~68 unrelated tests.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fsr_playbooks

_REPO_ROOT = Path(fsr_playbooks.__file__).resolve().parent.parent


def _version_from(cwd: Path) -> str:
    out = subprocess.run(
        [sys.executable, "-c",
         "import fsr_playbooks; print(fsr_playbooks.__version__)"],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_version_is_the_same_from_any_working_directory(tmp_path):
    assert _version_from(_REPO_ROOT) == _version_from(tmp_path)


def test_version_is_known_in_a_normal_install():
    assert fsr_playbooks.version_is_known()
    assert fsr_playbooks.__version__ != "0.0.0+unknown"


def test_version_is_known_reports_the_sentinel_honestly(monkeypatch):
    """Callers gate on version_is_known(), not on a string comparison."""
    monkeypatch.setattr(fsr_playbooks, "__version__", "0.0.0+unknown")
    assert not fsr_playbooks.version_is_known()


def test_no_version_shadowing_egg_info_in_the_repo_root():
    """A leftover egg-info reintroduces the cwd-dependent version."""
    stale = sorted(p.name for p in _REPO_ROOT.glob("*.egg-info")
                   if p.name != "fsrpb.egg-info")
    assert not stale, (
        f"stale build metadata in {_REPO_ROOT}: {stale}. These answer "
        f"importlib.metadata only for processes launched from this directory, "
        f"making __version__ depend on cwd. Delete them."
    )
