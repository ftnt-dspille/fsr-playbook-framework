"""The release script's refusals, exercised against real git repos.

`scripts/release.sh` is a shell script full of guards, and a guard that stops
matching is indistinguishable from a guard that passes. These build throwaway
repos and check the refusal actually fires.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_SH = ROOT / "scripts" / "release.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-qm", "init")
    return repo


def _copy_script(repo: Path) -> None:
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "release.sh").write_bytes(RELEASE_SH.read_bytes())
    _git(repo, "add", "scripts/release.sh")
    _git(repo, "commit", "-qm", "vendor release.sh")


def test_release_refuses_when_head_is_already_tagged(tmp_path: Path):
    """#158: a release needs a commit of its own.

    Run the real script against a repo whose HEAD already carries a version
    tag. It must refuse BEFORE doing anything permanent -- and, because the
    failure it prevents is silent, the message has to name the consequence
    rather than just say no.
    """
    repo = _repo(tmp_path)
    # release.sh resolves its own repo root from BASH_SOURCE and cd's there,
    # so it has to be run from a COPY inside the fixture repo -- pointing it
    # at the script in this checkout would test this checkout. Commit the
    # copy before tagging: the script also demands a clean tree, and an
    # untracked file would trip that guard instead of the one under test.
    _copy_script(repo)
    _git(repo, "tag", "v0.6.40")

    proc = subprocess.run(
        ["bash", "scripts/release.sh", "0.6.41"],
        cwd=repo, capture_output=True, text=True, timeout=120,
    )
    err = proc.stderr
    assert proc.returncode != 0, f"release.sh did not refuse:\n{proc.stdout}"
    assert "HEAD already carries a version tag" in err, err
    assert "v0.6.40" in err, "the refusal must name the tag in the way"
    assert "LOWER" in err, "the refusal must say what goes wrong, not just no"
    # Nothing permanent may have happened on the way to the refusal.
    tags = subprocess.run(["git", "-C", str(repo), "tag"],
                          capture_output=True, text=True).stdout.split()
    assert tags == ["v0.6.40"], f"release.sh created a tag anyway: {tags}"


def test_the_head_tag_guard_runs_before_any_network_call(tmp_path: Path):
    """It must refuse offline.

    The guard is the cheapest check in the script and it protects the most
    expensive mistake, so it belongs ahead of the PyPI reads -- otherwise a
    box with no network fails at a curl and never reaches it. Ordering is
    the whole point, so pin it: this repo has no remote and no network is
    needed to reach the refusal.
    """
    repo = _repo(tmp_path)
    _copy_script(repo)
    src = (repo / "scripts" / "release.sh").read_text()
    guard_at = src.index("HEAD already carries a version tag")
    assert guard_at < src.index("pypi.org"), (
        "the HEAD-tag guard moved behind a PyPI read"
    )
