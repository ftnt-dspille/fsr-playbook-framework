"""The ONE resolver for the connector checkout, for everything in tooling/.

Order (first existing wins; an explicit variable is never second-guessed):

  1. `FSR_CONNECTOR_REPO`   the repo root or the connector package dir
  2. `FSR_CONNECTOR_DIR`    legacy alias (the deploy MCP used to read this one)
  3. `<repo>/../connector`  monorepo layout (framework/ beside connector/)

The old sibling layout (`../ConnectorsV2/conn_main`) is NOT auto-discovered here:
the Makefile exports `FSR_CONNECTOR_REPO` for it, and a test that expects "no
connector found" must stay able to say so.

`fsr_playbooks/mcp_server/_fixture_box.py` ships in the wheel and so cannot
import tooling/; it reads `FSR_CONNECTOR_REPO` itself (the same first variable).
"""
from __future__ import annotations

import os
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]


def connector_candidates() -> list[Path]:
    out: list[Path] = []
    for var in ("FSR_CONNECTOR_REPO", "FSR_CONNECTOR_DIR"):
        val = os.environ.get(var, "").strip()
        if val:
            out.append(Path(val))
    out.append(FRAMEWORK_ROOT.parent / "connector")
    return out


def connector_repo() -> Path | None:
    """The first candidate that exists, or None."""
    for c in connector_candidates():
        if c.is_dir():
            return c
    return None
