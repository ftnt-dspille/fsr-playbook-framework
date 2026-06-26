#!/usr/bin/env python3
"""Pre-commit guard: block internal infra strings from entering the public mirror.

Scans the *staged additions* (added lines only) of each changed text file and
fails the commit if any internal host string slips in. This is the source-level
replacement for the old publish-time scrub: the tracked tree must stay clean so
the repo can be pushed to the public GitHub mirror with ordinary `git push`.

What it blocks:
  - live appliance IPs in the lab range  (10.99.x.x)
  - any internal Fortinet subdomain host (*.fortinet.com / *.fortinet.net),
    which covers the internal GitLab box, fortilab, and fndn hosts
  - FortiCloud instance hosts            (*.forticloud.com)

Allowed (public, safe to ship):
  - repo.fortisoar.fortinet.com          (public connector repo)
  - sample @fortinet.com email addresses (no dot before "fortinet", so the
    host regex below never matches them)

Run automatically via .pre-commit-config.yaml; run manually with:
    python scripts/check_infra_leaks.py            # scan staged changes
    python scripts/check_infra_leaks.py --all      # scan whole tracked tree
"""
from __future__ import annotations

import re
import subprocess
import sys

DENY = [
    re.compile(r"\b10\.99\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b[a-z0-9][a-z0-9.-]*\.fortinet\.(?:com|net)\b", re.IGNORECASE),
    re.compile(r"\b[a-z0-9][a-z0-9.-]*\.forticloud\.com\b", re.IGNORECASE),
    # Internal lab admin account — never ship as an example credential.
    re.compile(r"\bcsadmin\b", re.IGNORECASE),
]
# Known-public strings that match a DENY pattern but are intentionally shipped.
ALLOW = [
    re.compile(r"repo\.fortisoar\.fortinet\.com", re.IGNORECASE),
]
# Files that legitimately *define* the deny patterns (this guard + the hook that
# runs it). Scanning them would self-match; skip them in both modes.
SKIP = {
    "scripts/check_infra_leaks.py",
    ".pre-commit-config.yaml",
}


def _is_leak(text: str) -> str | None:
    for rx in DENY:
        for m in rx.finditer(text):
            if not any(a.search(m.group(0)) for a in ALLOW):
                return m.group(0)
    return None


def _staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [f for f in out.splitlines() if f]


def _added_lines(path: str) -> list[tuple[int, str]]:
    """Return (line_no_in_new_file, text) for lines added in the staged diff."""
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color", "--", path],
        capture_output=True, text=True, check=True,
    ).stdout
    lines: list[tuple[int, str]] = []
    new_ln = 0
    for ln in diff.splitlines():
        if ln.startswith("@@"):
            m = re.search(r"\+(\d+)", ln)
            new_ln = int(m.group(1)) if m else 0
        elif ln.startswith("+") and not ln.startswith("+++"):
            lines.append((new_ln, ln[1:]))
            new_ln += 1
    return lines


def main() -> int:
    scan_all = "--all" in sys.argv
    hits: list[str] = []

    if scan_all:
        files = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        for path in files:
            if path in SKIP:
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    for i, line in enumerate(fh, 1):
                        leak = _is_leak(line)
                        if leak:
                            hits.append(f"{path}:{i}: {leak}")
            except (OSError, UnicodeDecodeError):
                continue  # binary / unreadable
    else:
        for path in _staged_files():
            if path in SKIP:
                continue
            try:
                for lineno, text in _added_lines(path):
                    leak = _is_leak(text)
                    if leak:
                        hits.append(f"{path}:{lineno}: {leak}")
            except (subprocess.CalledProcessError, UnicodeDecodeError):
                continue

    if hits:
        sys.stderr.write(
            "\n\033[31mInfra-leak guard: internal host string(s) detected\033[0m\n"
        )
        for h in hits:
            sys.stderr.write(f"  {h}\n")
        sys.stderr.write(
            "\nUse an RFC5737 doc IP (198.51.100.x) or a placeholder host instead.\n"
            "If this is a genuinely public string, add it to ALLOW in "
            "scripts/check_infra_leaks.py.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
