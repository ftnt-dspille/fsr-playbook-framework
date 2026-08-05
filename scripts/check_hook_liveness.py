#!/usr/bin/env python3
"""Fail when a pre-commit hook's `files:` pattern selects nothing.

PLAN_testing_that_can_fail 0.2: *a gate that runs over an empty set is
indistinguishable from a gate that passes*. Two hooks in this repo were scoped
to `^python/` after the REORG renamed that directory to `tooling/`. They matched
zero files, so ruff and pytest silently stopped running at commit time -- and the
hook output looked exactly the same as a clean pass. Nothing could have told you
apart from reading the config.

This is the meta-gate: for every hook that narrows itself with `files:` (or
`exclude:`), assert the pattern still selects at least one tracked path. It is
deliberately a *liveness* check, not a correctness one -- it cannot tell you the
pattern selects the RIGHT files, only that it has not gone dead.

Stdlib only (`ast`-free, yaml via pre-commit's own dependency is not assumed):
the config is parsed with a tiny hand-rolled reader so this runs under a bare
`python3` like the repo's other hook entries.

Usage:
    python3 scripts/check_hook_liveness.py            # check, exit 1 on a dead pattern
    python3 scripts/check_hook_liveness.py --list     # show every pattern + its match count
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / ".pre-commit-config.yaml"


def _tracked_paths() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                         capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def _hooks(text: str) -> list[dict]:
    """Every hook block, as {id, files, exclude, line}.

    A minimal line reader rather than a YAML parse so this stays dependency-free
    (pre-commit hooks run before any venv is guaranteed). It only needs three
    keys, all of which are written as plain `key: value` at a fixed indent in
    this config.
    """
    hooks: list[dict] = []
    cur: dict | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = re.match(r"^-?\s*id:\s*(\S+)", line)
        if m and (raw.lstrip().startswith("- id:") or raw.lstrip().startswith("id:")):
            # `- repo:` blocks also carry an `id:` for their hooks; both are hooks
            # for our purposes, and a repo line never has `files:`.
            cur = {"id": m.group(1), "files": None, "exclude": None, "line": lineno}
            hooks.append(cur)
            continue
        if cur is None or line.startswith("#"):
            continue
        for key in ("files", "exclude"):
            m = re.match(rf"^{key}:\s*(.+)$", line)
            if m:
                cur[key] = m.group(1).strip().strip("'\"")
    return [h for h in hooks if h["files"] or h["exclude"]]


def main(argv: list[str]) -> int:
    if not CONFIG.exists():
        print(f"✗ no {CONFIG.name} -- nothing to check", file=sys.stderr)
        return 1
    hooks = _hooks(CONFIG.read_text())
    if not hooks:
        # The check itself must not be able to pass vacuously -- the exact bug
        # class it exists for.
        print("✗ parsed 0 narrowing hooks out of .pre-commit-config.yaml; the "
              "config reader is broken or the config is empty", file=sys.stderr)
        return 1

    paths = _tracked_paths()
    if not paths:
        print("✗ `git ls-files` returned nothing", file=sys.stderr)
        return 1

    dead: list[str] = []
    listing = "--list" in argv
    for h in hooks:
        for key in ("files", "exclude"):
            pat = h[key]
            if not pat:
                continue
            try:
                rx = re.compile(pat)
            except re.error as e:
                dead.append(f"{h['id']}: {key}: {pat!r} is not a valid regex ({e})")
                continue
            n = sum(1 for p in paths if rx.search(p))
            if listing:
                print(f"{n:>6}  {h['id']}.{key}  {pat}")
            if n == 0:
                dead.append(
                    f"{h['id']} (line {h['line']}): {key}: {pat!r} matches 0 "
                    "tracked files -- this hook is silently doing nothing")

    if dead:
        print("✗ dead pre-commit hook pattern(s):", file=sys.stderr)
        for d in dead:
            print(f"  - {d}", file=sys.stderr)
        print("\nA hook that selects nothing looks exactly like a hook that "
              "passes. Fix the pattern or delete the hook.", file=sys.stderr)
        return 1
    if not listing:
        print(f"✓ {len(hooks)} narrowing hook(s): every pattern still selects "
              "tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
