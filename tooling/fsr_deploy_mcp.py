#!/usr/bin/env python3
"""Connector build + deploy MCP server (`fsr-deploy`).

Exposes the `fsr-playbook-builder` connector's package + deploy pipeline to
SOAR as MCP tools, so the whole loop — build the tarball, push it onto the
live FortiSOAR box, confirm the rollout — is drivable from an agent.

These are **write/heavy** operations (they mutate the live platform and bump
versions), deliberately kept OUT of the read-only `fsr-read` server. `deploy`
self-gates: it refuses to install without `confirm=True`.

Connector location: `$FSR_CONNECTOR_DIR`, else the usual sibling layout
(`../ConnectorsV2/fsr-playbook-builder` relative to this framework repo).
Creds for the live check / install come from the framework `.env` (the
connector's deploy.sh sources it itself).

Run:    python python/fsr_deploy_mcp.py        (stdio)
Config: register in .mcp.json / .claude/settings.json as `fsr-deploy`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tooling"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

deploy_mcp = FastMCP("fsr-deploy")


# --------------------------------------------------------------------------
# Locate the connector repo
# --------------------------------------------------------------------------

def _connector_dir() -> Path | None:
    """Find the fsr-playbook-builder connector package dir (the one holding
    scripts/ + info.json). Honors $FSR_CONNECTOR_DIR, else tries the standard
    sibling layout."""
    env = os.environ.get("FSR_CONNECTOR_DIR")
    candidates = [Path(env)] if env else []
    candidates += [
        REPO_ROOT.parent / "ConnectorsV2" / "fsr-playbook-builder",
        REPO_ROOT.parent / "fsr-playbook-builder",
    ]
    for c in candidates:
        if (c / "scripts" / "deploy.sh").exists():
            return c
    return None


def _run(cmd: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    """Run a subprocess, capture combined output, return a structured result
    with a trimmed log tail (full output is large + noisy)."""
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        tail = (e.output or "")[-3000:] if isinstance(e.output, str) else ""
        return {"ok": False, "timed_out": True, "timeout_s": timeout,
                "cmd": " ".join(cmd), "log_tail": tail}
    out = (p.stdout or "") + (p.stderr or "")
    return {"ok": p.returncode == 0, "returncode": p.returncode,
            "cmd": " ".join(cmd), "log_tail": out[-4000:]}


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@deploy_mcp.tool()
def connector_status() -> dict[str, Any]:
    """Live status of the deployed connector: version it reports + health.

    Hits the box via the framework `.env` creds (read-only). Use it before a
    deploy to see the current live version, and after to confirm the rollout.
    """
    cdir = _connector_dir()
    if cdir is None:
        return {"ok": False, "error": "connector dir not found; set FSR_CONNECTOR_DIR"}
    try:
        sys.path.insert(0, str(cdir / "scripts"))
        from probes._env import get_config  # loads framework .env  # noqa: PLC0415
        get_config()  # side effect: populate os.environ from .env
        from fsr_live import LiveFSR  # noqa: PLC0415
        fsr = LiveFSR.from_env()
        res = fsr.execute("health_check", {}, timeout=60)
        d = res.data if isinstance(res.data, dict) else {}
        return {"ok": bool(res.ok), "status": res.status,
                "fsr_playbooks_version": d.get("fsr_playbooks_version"),
                "worker_identity": {k: v for k, v in d.items()
                                    if "version" in k.lower() or "worker" in k.lower()},
                "connector_dir": str(cdir)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@deploy_mcp.tool()
def connector_build(slim: bool = True, timeout_s: int = 300) -> dict[str, Any]:
    """Build the connector tarball (vendor fsr_playbooks + reference DB → .tgz).

    Read-only w.r.t. the live box — it does NOT install. `slim=True` ships the
    truncated reference DB (warmup repopulates on the box). Returns the built
    tarball path + a log tail.
    """
    cdir = _connector_dir()
    if cdir is None:
        return {"ok": False, "error": "connector dir not found; set FSR_CONNECTOR_DIR"}
    cmd = ["bash", "scripts/build.sh"] + (["--slim"] if slim else [])
    res = _run(cmd, cdir, timeout_s)
    # surface the produced tarball
    dist = cdir / "dist"
    if dist.exists():
        tgz = sorted(dist.glob("*.tgz"), key=lambda p: p.stat().st_mtime)
        if tgz:
            res["tarball"] = str(tgz[-1])
    return res


@deploy_mcp.tool()
def connector_deploy(
    confirm: bool = False,
    bump: str = "patch",
    warmup: bool = True,
    verify: bool = True,
    timeout_s: int = 600,
) -> dict[str, Any]:
    """Build + install the connector onto the live SOAR box (bump → vendor →
    build → install → warmup → verify), via scripts/deploy.sh.

    **Mutates the live platform** — requires `confirm=True`. Without it, returns
    a dry-run summary of what would happen (no changes made).

    Args:
        confirm: must be True to actually deploy.
        bump: 'patch' | 'minor' | 'major' | 'none' (version bump policy).
        warmup: run the post-install op-catalog warmup (recommended).
        verify: confirm every worker recycled onto the new version.
        timeout_s: hard cap; deploy typically takes 1-4 min.
    """
    cdir = _connector_dir()
    if cdir is None:
        return {"ok": False, "error": "connector dir not found; set FSR_CONNECTOR_DIR"}
    if bump not in {"patch", "minor", "major", "none"}:
        return {"ok": False, "error": f"bad bump {bump!r}; want patch|minor|major|none"}

    args = ["--bump", bump]
    if not warmup:
        args.append("--no-warmup")
    if not verify:
        args.append("--no-verify")

    if not confirm:
        return {
            "ok": False, "requires_confirmation": True,
            "would_run": f"bash scripts/deploy.sh {' '.join(args)}",
            "connector_dir": str(cdir),
            "note": ("This installs onto the LIVE FortiSOAR box and bumps the "
                     "connector version. Re-call with confirm=True to proceed. "
                     "For a no-install build use connector_build()."),
        }

    res = _run(["bash", "scripts/deploy.sh", *args], cdir, timeout_s)
    # best-effort: pull the resulting version out of the log
    import re
    m = re.search(r"bump version \S+ . (\S+)", res.get("log_tail", "")) \
        or re.search(r"version unchanged: (\S+)", res.get("log_tail", ""))
    if m:
        res["version"] = m.group(1)
    return res


if __name__ == "__main__":
    deploy_mcp.run(transport="stdio")
