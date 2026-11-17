"""The hook-liveness meta-gate (PLAN_testing_that_can_fail 0.2).

`scripts/check_hook_liveness.py` fails when a pre-commit hook's `files:` pattern
selects zero tracked files -- the shape of the REORG bug where two hooks stayed
scoped to the deleted `python/` directory and quietly stopped running while
still reporting a clean pass.

This file is the gate's own gate. It runs the check against the real config
(so a dead pattern reds `make verify`, not just a commit), and -- per the plan's
cross-cutting rule -- carries the MUTATION PROOF: the historical bug is
reintroduced into a copy of the config and the check must go red on it. A gate
nobody has watched fail is a gate nobody should trust.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_hook_liveness.py"


def _run(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)],
                          cwd=str(cwd), capture_output=True, text=True)


def test_every_hook_pattern_selects_something():
    """The live config: no hook in this repo is silently doing nothing."""
    r = _run(REPO)
    assert r.returncode == 0, (
        "a pre-commit hook selects zero files, so it passes without running:\n"
        + r.stdout + r.stderr)


def test_mutation_proof_a_dead_pattern_goes_red(tmp_path, monkeypatch):
    """Reintroduce the REORG bug and the gate must fail.

    `^fsr_playbooks/compiler/` -> `^python/compiler/` is the exact edit that
    happened for real: a directory rename that left the hook pointing at a path
    no longer in the tree.
    """
    cfg = REPO / ".pre-commit-config.yaml"
    mutated = cfg.read_text().replace("^fsr_playbooks/compiler/",
                                      "^python/compiler/")
    assert mutated != cfg.read_text(), (
        "the mutation was a no-op -- the pattern it targets is gone, so this "
        "proof is no longer proving anything; retarget it at a live pattern")

    # Run against a copy of the repo's config, resolved through a stub REPO by
    # invoking the script with the mutated file swapped in via a temp checkout
    # of just the two things it reads: the config and `git ls-files`.
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    (work / ".pre-commit-config.yaml").write_text(mutated)
    (work / "fsr_playbooks").mkdir()
    (work / "fsr_playbooks" / "compiler_placeholder.py").write_text("")
    (work / "tooling").mkdir()
    (work / "tooling" / "x.py").write_text("")
    (work / "data").mkdir()
    (work / "examples").mkdir()
    (work / "examples" / "x.yaml").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=work, check=True)

    script_copy = work / "scripts"
    script_copy.mkdir()
    (script_copy / "check_hook_liveness.py").write_text(SCRIPT.read_text())
    subprocess.run(["git", "add", "-A"], cwd=work, check=True)

    r = subprocess.run([sys.executable, str(script_copy / "check_hook_liveness.py")],
                       cwd=str(work), capture_output=True, text=True)
    assert r.returncode == 1, (
        "the liveness gate stayed GREEN with a hook scoped to a directory that "
        "does not exist -- it cannot detect the bug it exists for:\n"
        + r.stdout + r.stderr)
    assert "python/compiler" in (r.stdout + r.stderr)


def test_the_checker_cannot_pass_vacuously(tmp_path):
    """An empty/unparseable config must fail, not report success.

    Same class one level down: if the config reader silently found zero hooks,
    the check would print a cheerful pass over nothing at all.
    """
    work = tmp_path / "empty"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    (work / ".pre-commit-config.yaml").write_text("repos: []\n")
    (work / "f.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=work, check=True)
    scripts = work / "scripts"
    scripts.mkdir()
    (scripts / "check_hook_liveness.py").write_text(SCRIPT.read_text())

    r = subprocess.run([sys.executable, str(scripts / "check_hook_liveness.py")],
                       cwd=str(work), capture_output=True, text=True)
    assert r.returncode == 1
    assert "0 narrowing hooks" in (r.stdout + r.stderr)


@pytest.mark.parametrize("missing", [".pre-commit-config.yaml"])
def test_missing_config_is_an_error_not_a_pass(tmp_path, missing):
    work = tmp_path / "nocfg"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    scripts = work / "scripts"
    scripts.mkdir()
    (scripts / "check_hook_liveness.py").write_text(SCRIPT.read_text())
    r = subprocess.run([sys.executable, str(scripts / "check_hook_liveness.py")],
                       cwd=str(work), capture_output=True, text=True)
    assert r.returncode == 1
