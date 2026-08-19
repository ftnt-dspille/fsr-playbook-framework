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


# A sweep against the screening gateway costs 35 minutes and N model calls.
# Run 20260817T020056Z spent all of it and lost 4 repeats because the gateway
# dropped -- a single request beforehand would have caught the front half of
# that. Reachability only: it cannot catch a MID-sweep drop (that is the
# calibrate retry's job), and it deliberately spends no completion tokens.
_GATEWAY_TIMEOUT_S = 8.0


def probe_llm_gateway(base_url: str, api_key: str, model: str | None,
                      timeout_s: float = _GATEWAY_TIMEOUT_S) -> tuple[bool, str]:
    """(reachable, detail) for an OpenAI-compatible endpoint.

    Asks `GET /models` -- free, and it answers the two questions a sweep needs:
    is the host up, and does it serve the model we are about to name. A
    listing the endpoint declines to serve is NOT a failure: some gateways
    gate /models but complete fine, so we report reachable-but-unverified
    rather than inventing an outage.
    """
    import httpx

    url = base_url.rstrip("/") + "/models"
    try:
        r = httpx.get(url, timeout=timeout_s,
                      headers={"Authorization": f"Bearer {api_key}"})
    except Exception as e:  # noqa: BLE001 -- the outage IS the answer
        return False, f"{url} unreachable: {e.__class__.__name__}: {e}"
    if r.status_code in (401, 403):
        return False, f"{url} -> {r.status_code}: the key is rejected"
    if r.status_code >= 400:
        # Up enough to answer. Not proof it completes, but not an outage.
        return True, (f"{url} -> {r.status_code} (endpoint up; it does not "
                      f"serve a model listing, so `{model}` is unverified)")
    try:
        served = [m.get("id") for m in (r.json().get("data") or [])]
    except Exception:  # noqa: BLE001
        return True, f"{url} -> 200 (unparseable listing; `{model}` unverified)"
    if model and served and model not in served:
        return False, (f"{url} is up but does NOT serve `{model}`. It serves: "
                       f"{', '.join(sorted(filter(None, served))[:8])}. A run "
                       f"against an unnamed default measures a model nobody chose.")
    return True, f"{url} up, serving `{model}`" if model else f"{url} up"


def _gateway_env() -> dict:
    """FRANK_* from the process env, falling back to a `.env` in the cwd.

    The eval entrypoints load `.env` themselves before they build a provider,
    so they see these either way. `make doctor` does not -- and a preflight
    that reports "not configured" on the one machine that IS configured would
    be worse than no preflight at all.
    """
    import os
    keys = ("FRANK_BASE_URL", "FRANK_API_KEY", "FRANK_MODEL")
    env = {k: os.environ.get(k) for k in keys}
    if all(env.get(k) for k in keys):
        return env
    # Fill each key INDEPENDENTLY. Returning early once the URL and key were
    # present left FRANK_MODEL unresolved on a shell that exports only those
    # two -- so the probe reported the endpoint "up" and never checked that it
    # serves the model the sweep was about to name.
    try:
        from pathlib import Path

        from dotenv import dotenv_values
        dotted = dotenv_values(Path.cwd() / ".env")
    except Exception:  # noqa: BLE001 -- no dotenv / no file: nothing to add
        return env
    for k in keys:
        if not env.get(k):
            env[k] = dotted.get(k)
    return env


def check_llm_gateway() -> Check:
    """Reachability of the screening gateway, when one is configured.

    Unconfigured is not a fault -- most work in this repo never touches it --
    so it passes with a note. Configured-and-down is exactly the failure this
    exists to catch before a long sweep commits to it.
    """
    env = _gateway_env()
    base_url = env.get("FRANK_BASE_URL")
    key = env.get("FRANK_API_KEY")
    model = env.get("FRANK_MODEL")
    if not base_url or not key:
        return Check("LLM gateway reachable", True,
                     "FRANK_BASE_URL/FRANK_API_KEY not set -- no gateway to "
                     "preflight (set them in .env before an eval sweep).")
    ok, detail = probe_llm_gateway(base_url, key, model)
    if not ok:
        detail += ("\n      Fix the gateway (or point FRANK_BASE_URL "
                   "elsewhere) BEFORE starting a sweep -- a dropped gateway "
                   "scores as an agent that reached nothing.")
    return Check("LLM gateway reachable", ok, detail)


CHECKS = (
    check_fsr_playbooks_version,
    check_no_stale_egg_info,
    check_pyfsr,
    check_reference_db,
    check_llm_gateway,
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
