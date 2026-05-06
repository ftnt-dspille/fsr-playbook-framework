"""Agent-facing assets: the externalized system prompt + helpers.

Kept inside the `python/` tree (not `web/`) so non-web frontends —
CLI agents, the eval harness, the MCP-driven Claude Code session —
can load the SAME prompt without depending on the web backend.
"""
from __future__ import annotations

from pathlib import Path

_PROMPT_PATH = Path(__file__).with_name("system_prompt.md")


def load_system_prompt() -> str:
    """Return the externalized FSR-authoring system prompt as text.

    The prompt lives in `system_prompt.md` so it can be diffed,
    reviewed, and swapped without code changes. Any caller that
    streams LLM messages should pull the text through this helper
    rather than inlining a Python string literal.
    """
    return _PROMPT_PATH.read_text(encoding="utf-8")


__all__ = ["load_system_prompt"]
