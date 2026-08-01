"""The infra-leak guard's deny sets, pinned against synthetic hosts.

This repo pushes to a public GitHub mirror, so the tracked tree must never
carry lab infrastructure. The guard already had a hard lesson behind it: a
sqlite fixture reached the mirror carrying thousands of live appliance URLs and
the lab admin account, because `git diff` renders a binary as "Binary files
differ" and the staged-diff scan saw no added lines.

An audit of the surviving rules planted the host *shapes* actually in use and
found three that walked through: the demo-pod domain and the internal GitLab
domain passed BOTH scans, and the devops GitLab host was blocked in binaries
but waved through in source. None is a Fortinet subdomain, so the
`*.fortinet.com` rule never matched them.

**No lab hostname or domain appears in this file.** The deny fixtures are read
from the gitignored overlay, so nothing here tells a reader of the public
mirror what to look for. A public clone simply skips those cases.

The allow cases matter as much as the deny ones. A guard that cries wolf on
vendor content is a guard people learn to skip with `--no-verify`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import check_infra_leaks as guard  # noqa: E402

# Fixtures live in the gitignored overlay, NOT here. Even a fragment-assembled
# literal like "example." + "<lab-domain>" still shows a reader of the public
# mirror which domain to look for -- which is the leak this guard exists to
# prevent, committed by its own test. The overlay carries synthetic hosts that
# match its patterns and name no real machine.
#
# A public clone has no overlay, so these cases skip and only the generic
# vendor-subdomain rules are exercised. That is correct: there is nothing
# lab-specific to test there.
def _overlay_samples() -> list[str]:
    import json
    if not guard._OVERLAY_PATH.exists():
        return []
    try:
        return json.loads(guard._OVERLAY_PATH.read_text()).get("samples", [])
    except (json.JSONDecodeError, OSError):
        return []


BLOCKED_EVERYWHERE = _overlay_samples()
_needs_overlay = pytest.mark.skipif(
    not BLOCKED_EVERYWHERE,
    reason="no local infra-pattern overlay (expected in a public clone / CI)",
)


def _text_blocked(s: str) -> bool:
    return (any(p.search(s) for p in guard.DENY)
            and not any(a.search(s) for a in guard.ALLOW))


def _binary_blocked(s: str) -> bool:
    return any(p.search(s.encode()) for p in guard.BINARY_DENY)


@_needs_overlay
@pytest.mark.parametrize("s", BLOCKED_EVERYWHERE)
def test_blocked_in_source(s):
    assert _text_blocked(s), f"text scan let through: {s!r}"


@_needs_overlay
@pytest.mark.parametrize("s", BLOCKED_EVERYWHERE)
def test_blocked_in_binaries(s):
    """A reference DB is exactly where an appliance hostname hides."""
    assert _binary_blocked(s), f"binary scan let through: {s!r}"


@pytest.mark.parametrize("s", [
    "https://repo.fortisoar.fortinet.com/content-hub/content-hub.json",
    "someone@fortinet.com",
    "https://fortisoar.example.com/api/3/alerts",
    "192.168.77.49",  # synthetic attacker IP in the eval fixtures
])
def test_public_strings_are_not_blocked(s):
    assert not _text_blocked(s), f"false positive on public string: {s!r}"


def test_binary_set_stays_narrower_than_text():
    """Deliberate asymmetry -- don't "fix" it by widening the binary set.

    Vendored reference DBs carry stock connector metadata that legitimately
    names public Fortinet product hosts. The broad `*.fortinet.com` rule is
    right for files we author and wrong for vendor content, so binaries are
    scanned only for markers that are unambiguously ours.
    """
    vendor = "https://docs." + "fortinet.com/document/fortisoar"
    assert _text_blocked(vendor)
    assert not _binary_blocked(vendor)


def test_this_file_does_not_itself_leak():
    """The test for the leak guard must pass the leak guard.

    Written after the first draft of this file embedded a real appliance IP and
    two real hostnames -- the guard blocked the commit, which is the system
    working, but the file should never have contained them.

    Checked line-by-line through `_text_blocked`, which is DENY *minus* ALLOW
    -- the guard's actual decision. A raw DENY sweep flags this file's own
    public `repo.fortisoar` fixture, which is intentional.
    """
    offending = [
        (n, line.strip())
        for n, line in enumerate(Path(__file__).read_text().splitlines(), 1)
        if _text_blocked(line)
    ]
    assert not offending, f"this file would trip the guard: {offending}"


def test_the_tracked_tree_is_clean():
    import subprocess
    repo = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, "scripts/check_infra_leaks.py", "--all"],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
