"""scripts/hook_pass_cache.sh: a slow gate runs once per content, not per stage.

Drives the real script in a throwaway git repo. The gated "command" appends to a
counter file, so each test can see whether the gate actually ran.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hook_pass_cache.sh"


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.py").write_text("x = 1\n")
    _git(r, "add", "a.py")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _gate(repo: Path, *, to_ref: str | None = None, ok: bool = True, **env) -> int:
    """Run the wrapper around a command that counts its runs; returns exit code."""
    counter = repo.parent / "runs"
    cmd = f'echo run >> "{counter}"; exit {0 if ok else 1}'
    e = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", **env}
    e.pop("PRE_COMMIT_TO_REF", None)
    if to_ref:
        e["PRE_COMMIT_TO_REF"] = to_ref
    return subprocess.run(["bash", str(SCRIPT), "gate", "--", "bash", "-c", cmd],
                          cwd=repo, env=e, capture_output=True, text=True).returncode


def _runs(repo: Path) -> int:
    f = repo.parent / "runs"
    return len(f.read_text().splitlines()) if f.exists() else 0


def test_a_tree_that_passed_at_commit_is_not_re_run_at_push(repo):
    assert _gate(repo) == 0                 # commit stage: runs, records the index tree
    assert _runs(repo) == 1
    head = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, to_ref=head) == 0    # push stage, same tree
    assert _runs(repo) == 1                 # skipped


def test_a_different_pushed_tree_runs_the_gate(repo):
    assert _gate(repo) == 0
    (repo / "a.py").write_text("x = 2\n")
    _git(repo, "commit", "-q", "-am", "change")       # committed without the gate
    assert _gate(repo, to_ref=_git(repo, "rev-parse", "HEAD")) == 0
    assert _runs(repo) == 2


def test_a_failed_gate_is_not_recorded_and_push_runs_it_again(repo):
    assert _gate(repo, ok=False) == 1
    assert _gate(repo, to_ref=_git(repo, "rev-parse", "HEAD"), ok=False) == 1
    assert _runs(repo) == 2


def test_a_cache_miss_at_push_still_fails_on_a_failing_gate(repo):
    assert _gate(repo, to_ref=_git(repo, "rev-parse", "HEAD"), ok=False) == 1


def test_an_untracked_file_means_the_pass_is_not_recorded(repo):
    (repo / "new_test.py").write_text("assert True\n")   # could change what a run sees
    assert _gate(repo) == 0
    (repo / "new_test.py").unlink()
    assert _gate(repo, to_ref=_git(repo, "rev-parse", "HEAD")) == 0
    assert _runs(repo) == 2


def test_unstaged_edits_mean_the_pass_is_not_recorded(repo):
    (repo / "a.py").write_text("x = 99\n")              # tracked, not staged
    assert _gate(repo) == 0
    _git(repo, "checkout", "--", "a.py")
    assert _gate(repo, to_ref=_git(repo, "rev-parse", "HEAD")) == 0
    assert _runs(repo) == 2


def test_the_cache_can_be_turned_off(repo):
    assert _gate(repo) == 0
    assert _gate(repo, to_ref=_git(repo, "rev-parse", "HEAD"), HOOK_PASS_CACHE="0") == 0
    assert _runs(repo) == 2


def test_gates_are_cached_separately(repo):
    assert _gate(repo) == 0
    counter = repo.parent / "runs"
    e = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
         "PRE_COMMIT_TO_REF": _git(repo, "rev-parse", "HEAD")}
    subprocess.run(["bash", str(SCRIPT), "other", "--", "bash", "-c", f'echo run >> "{counter}"'],
                   cwd=repo, env=e, check=True, capture_output=True)
    assert _runs(repo) == 2                 # "other" never passed this tree


def test_the_config_routes_the_slow_gates_through_the_cache():
    cfg = (SCRIPT.parents[1] / ".pre-commit-config.yaml").read_text()
    assert "hook_pass_cache.sh pytest-fast --" in cfg
    assert "hook_pass_cache.sh mypy --" in cfg
