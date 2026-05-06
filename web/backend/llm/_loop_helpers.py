"""Pieces shared between the Anthropic and LM Studio agent loops.

Kept here (not in `provider.py`) because they're implementation details
of the loop, not part of the protocol contract a future provider has to
honor. A new provider can opt in to self-repair by importing these.
"""
from __future__ import annotations

import re
from pathlib import Path


MAX_TOOL_TURNS = 8
# Cap on extra "fix the YAML" turns auto-issued when the assistant's
# final message contains a yaml block that fails to compile. Each repair
# turn is roughly one extra LLM round-trip; 2 keeps cost bounded.
MAX_SELF_REPAIR_TURNS = 2


def extract_yaml_block(text: str) -> str | None:
    """Return the contents of the LAST fenced ```yaml block, or None.
    Mirrors the frontend's extractYamlBlock so the in-chat YAML the user
    sees and the YAML we self-repair against are exactly the same string.
    """
    matches = list(re.finditer(r"```ya?ml\n([\s\S]*?)```", text, flags=re.IGNORECASE))
    return matches[-1].group(1) if matches else None


def compile_errors(yaml_text: str) -> str | None:
    """Run the same compiler the editor uses; return a bullet list of
    blocking errors or None if clean. Imported lazily so a missing
    compiler doesn't break test collection."""
    try:
        from compiler import compile_yaml as _cy  # type: ignore
    except Exception as e:
        return f"compiler import failed: {e}"

    db = Path(__file__).resolve().parents[3] / "store" / "fsr_reference.db"
    res = _cy(yaml_text, db)
    if res.ok:
        return None
    blocking = [e for e in res.errors if e.severity != "warning"]
    if not blocking:
        return None
    lines: list[str] = []
    for e in blocking:
        line = f"- [{e.code.value}] {e.message}"
        if e.path:
            line += f"  (path: {e.path})"
        if e.suggestion:
            line += f"  → {e.suggestion}"
        lines.append(line)
    return "\n".join(lines)
