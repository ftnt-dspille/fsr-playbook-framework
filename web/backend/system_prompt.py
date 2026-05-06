"""System prompt loader.

The prompt body lives in `python/agent/system_prompt.md` so that the
web backend, the MCP-driven CLI agent, and the eval harness all read
the SAME prompt without duplication. Keeping the import surface here
(`from backend.system_prompt import SYSTEM_PROMPT`) means existing
callers don't change.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PYTHON = _REPO / "python"
if str(_PYTHON) not in sys.path:
    sys.path.insert(0, str(_PYTHON))

from agent import load_system_prompt  # noqa: E402

SYSTEM_PROMPT = load_system_prompt()
