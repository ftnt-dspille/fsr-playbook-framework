"""Environment preflight -- catch a broken setup before it looks like a bug.

Every entry here exists because a silent environment fault once cost real
debugging time by presenting as a product defect:

  * an `fsr_playbooks.__version__` that resolved from a stale
    `fsr_playbooks.egg-info` in the repo root, making the version A FUNCTION OF
    THE WORKING DIRECTORY -- and tripping the connector's exact-version guard
    across ~68 otherwise-unrelated tests;
  * a `pyfsr` pinned in the lockfile far below the floor the connector
    requires, whose own `__version__` disagreed with its own metadata (0.1.0 vs
    0.2.2) -- an install that is wrong in two directions at once;
  * an empty reference DB, which makes broken YAML validate clean.

Each check answers "is this environment able to give correct answers", not "is
the code correct". Run it before a suite, not inside one.

    python -m fsr_playbooks.doctor
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

# The floor the connector declares (connector requirements.txt: pyfsr>=0.7.9).
# Kept here so a dev venv resolving an ancient PyPI build is caught locally
# rather than on a box.
_PYFSR_MIN = (0, 7, 9)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str

    def render(self) -> str:
        return f"{'PASS' if self.ok else 'FAIL'}  {self.name}\n      {self.detail}"


def _parse_version(v: str) -> tuple:
    """Leading numeric components only ('0.18.4.post1.dev2+g...' -> (0,18,4))."""
    parts: list[int] = []
    for chunk in str(v).split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def check_fsr_playbooks_version() -> Check:
    import fsr_playbooks
    v = fsr_playbooks.__version__
    if not fsr_playbooks.version_is_known():
        return Check(
            "fsr_playbooks version resolves", False,
            "__version__ is the 'unknown' sentinel -- no installed "
            "distribution metadata was found for fsr-playbooks / fsr_playbooks "
            "/ fsrpb. Anything comparing this version will misfire. "
            "Fix: `uv pip install -e .` in the framework repo.",
        )
    return Check("fsr_playbooks version resolves", True, f"__version__ = {v}")


def check_no_stale_egg_info() -> Check:
    """A stale egg-info makes the version depend on the working directory.

    importlib.metadata scans sys.path, and '' (cwd) is on sys.path, so a
    leftover `<name>.egg-info` in a repo root answers version queries for any
    process launched from there -- and nothing at all from elsewhere.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    stale = sorted(p.name for p in root.glob("*.egg-info")
                   if p.name != "fsrpb.egg-info")
    if stale:
        return Check(
            "no version-shadowing egg-info", False,
            f"stale build metadata in {root}: {', '.join(stale)}. "
            f"These answer importlib.metadata queries only when a process is "
            f"launched from this directory, so versions differ by cwd. "
            f"Fix: delete them.",
        )
    return Check("no version-shadowing egg-info", True, f"none in {root}")


def check_pyfsr() -> Check:
    try:
        import pyfsr
    except ImportError as e:
        return Check("pyfsr importable + recent enough", False, f"import failed: {e}")
    import importlib.metadata as md
    try:
        meta = md.version("pyfsr")
    except Exception as e:  # noqa: BLE001
        return Check("pyfsr importable + recent enough", False,
                     f"no distribution metadata: {e}")
    attr = getattr(pyfsr, "__version__", None)
    # A wheel whose __init__ disagrees with its own metadata is a broken build;
    # trust neither and say so.
    if attr and _parse_version(attr) != _parse_version(meta):
        return Check(
            "pyfsr importable + recent enough", False,
            f"inconsistent install: pyfsr.__version__={attr!r} but distribution "
            f"metadata says {meta!r}. Reinstall: `uv pip install -e ../pyfsr`.",
        )
    if _parse_version(meta) < _PYFSR_MIN:
        floor = ".".join(map(str, _PYFSR_MIN))
        return Check(
            "pyfsr importable + recent enough", False,
            f"pyfsr {meta} is below the required floor {floor} (the connector "
            f"declares pyfsr>={floor}). A resolver that picked an old PyPI "
            f"build will fail at import of newer modules such as pyfsr.config. "
            f"Fix: `uv pip install -e ../pyfsr`.",
        )
    return Check("pyfsr importable + recent enough", True, f"pyfsr {meta}")


def check_reference_db() -> Check:
    from fsr_playbooks.reference_db import health
    try:
        from fsr_playbooks.llm.tools import _DB_PATH
    except Exception as e:  # noqa: BLE001
        return Check("reference DB populated", False,
                     f"could not locate the reference DB: {e}")
    h = health(_DB_PATH)
    if not h.populated:
        return Check(
            "reference DB populated", False,
            f"{h.summary}. Every connector/operation lookup will miss, so "
            f"broken YAML can validate clean. Fix: point FSR_REFERENCE_DB at a "
            f"populated store, or re-vendor the full one.",
        )
    if not h.intact:
        return Check(
            "reference DB populated", False,
            f"{h.summary} Fix: rebuild the damaged table (dump its rows, "
            f"recreate, reinsert) or restore a known-good copy, then re-run "
            f"`make doctor`. Do NOT read an eval or tool-gate run taken "
            f"against a corrupt store -- the agent's misses are the store's.",
        )
    return Check("reference DB populated", True, h.summary)


CHECKS = (
    check_fsr_playbooks_version,
    check_no_stale_egg_info,
    check_pyfsr,
    check_reference_db,
)


def run() -> list[Check]:
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as e:  # noqa: BLE001 - a check must never mask itself
            results.append(Check(fn.__name__, False, f"check raised: {e!r}"))
    return results


def main() -> int:
    results = run()
    print("fsr_playbooks environment doctor")
    print("=" * 60)
    for c in results:
        print(c.render())
    bad = [c for c in results if not c.ok]
    print("=" * 60)
    print(f"{len(results) - len(bad)}/{len(results)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
