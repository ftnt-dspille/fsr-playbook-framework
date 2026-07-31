#!/usr/bin/env python3
"""Pre-commit guard: block internal infra strings from entering the public mirror.

Scans the *staged additions* (added lines only) of each changed text file and
fails the commit if any internal host string slips in. This is the source-level
replacement for the old publish-time scrub: the tracked tree must stay clean so
the repo can be pushed to the public GitHub mirror with ordinary `git push`.

Binary files are scanned too, in full rather than by diff. They used to be
skipped outright, and that is how `tooling/tests/fixtures/tooling_reference.db`
reached the public mirror carrying 7,000+ live appliance URLs and the lab admin
account: a sqlite fixture stores its strings as plain text, but `git diff`
renders it as "Binary files differ", so the staged-diff scan saw no added lines
and passed it. There is no cheap way to diff a binary's *added* strings, so any
match anywhere in the blob is reported -- a whole-file scan on a file format
that has no line structure to begin with.

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
    # Internal lab admin account -- never ship as an example credential.
    re.compile(r"\bcsadmin\b", re.IGNORECASE),
]
# Known-public strings that match a DENY pattern but are intentionally shipped.
ALLOW = [
    re.compile(r"repo\.fortisoar\.fortinet\.com", re.IGNORECASE),
]

# Binaries get a NARROWER deny set than source text, and the difference is
# deliberate. The broad `*.fortinet.com` rule above is right for files we
# author -- we never have a reason to type an internal hostname. But the
# reference DBs are vendored: they hold stock connector definitions whose
# metadata legitimately references public Fortinet product hosts
# (docs./support./fortiguard.fortinet.com, the FortiCloud SaaS endpoints).
# Applying the broad rule there reports ~30 such hosts per DB, and a guard that
# cries wolf on vendor content is a guard people learn to skip.
#
# So binaries are scanned only for markers that are unambiguously OURS and
# could not have arrived from Fortinet: the lab subnet, the lab-internal
# domains, and the lab admin account.
BINARY_DENY = [
    re.compile(rb"\b10\.99\.\d{1,3}\.\d{1,3}\b"),
    re.compile(rb"\b[a-z0-9][a-z0-9.-]*\.fortilab\.fortinet\.(?:com|net)\b", re.I),
    re.compile(rb"\bsvl-devops[a-z0-9.-]*\b", re.I),
    re.compile(rb"\bcsadmin\b", re.I),
]
# Files that legitimately *define* the deny patterns (this guard + the hook that
# runs it). Scanning them would self-match; skip them in both modes.
SKIP = {
    "scripts/check_infra_leaks.py",
    ".pre-commit-config.yaml",
}



def is_binary(blob: bytes) -> bool:
    """A NUL byte in the first 8 KiB -- the same heuristic git itself uses."""
    return b"\x00" in blob[:8192]


def scan_blob(blob: bytes) -> list[str]:
    """Every distinct BINARY_DENY hit in a blob, in first-seen order.

    Matched against the raw bytes rather than extracted printable runs: sqlite
    stores its text unterminated and packed against adjacent cell data, so a
    `strings(1)`-style pass can fuse a host into a neighbouring value and hide
    it from an anchored pattern. The deny patterns are self-delimiting, so
    scanning the whole blob loses nothing and cannot be fooled by framing.
    """
    seen: dict[str, None] = {}
    for rx in BINARY_DENY:
        for m in rx.finditer(blob):
            hit = m.group(0).decode("ascii", "replace")
            if not any(a.search(hit) for a in ALLOW):
                seen.setdefault(hit, None)
    return list(seen)


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
                blob = open(path, "rb").read()
            except OSError:
                continue
            if is_binary(blob):
                hits += [f"{path}: {leak}  (embedded in binary)"
                         for leak in scan_blob(blob)]
                continue
            try:
                for i, line in enumerate(blob.decode("utf-8").splitlines(), 1):
                    leak = _is_leak(line)
                    if leak:
                        hits.append(f"{path}:{i}: {leak}")
            except UnicodeDecodeError:
                continue
    else:
        for path in _staged_files():
            if path in SKIP:
                continue
            # A staged binary has no usable line diff -- git renders it as
            # "Binary files differ" and _added_lines() returns nothing, which is
            # exactly how the leaked fixture got through. Scan the staged blob
            # itself instead of the diff.
            try:
                blob = subprocess.run(
                    ["git", "show", f":{path}"], capture_output=True, check=True,
                ).stdout
            except subprocess.CalledProcessError:
                blob = b""
            if is_binary(blob):
                hits += [f"{path}: {leak}  (embedded in binary)"
                         for leak in scan_blob(blob)]
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
