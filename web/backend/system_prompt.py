"""System prompt loader.

The prompt body lives in `python/agent/system_prompt.md` so that the
web backend, the MCP-driven CLI agent, and the eval harness all read
the SAME prompt without duplication. Keeping the import surface here
(`from backend.system_prompt import SYSTEM_PROMPT`) means existing
callers don't change.

`build_system_prompt(intent)` is the intent-aware builder used by
chat.py — pass `"enhance"` to append the minimal-diff addendum. The
module-level `SYSTEM_PROMPT` remains the build-mode default for
back-compat with tests and other callers.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PYTHON = _REPO / "python"
if str(_PYTHON) not in sys.path:
    sys.path.insert(0, str(_PYTHON))

from agent import Intent, load_system_prompt  # noqa: E402


def build_system_prompt(intent: Intent = "build") -> str:
    return load_system_prompt(intent)


SYSTEM_PROMPT = load_system_prompt()
