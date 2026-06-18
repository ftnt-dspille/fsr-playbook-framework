"""Agent skill-trace + system prompts for fsr_playbooks."""
from __future__ import annotations

# --- Frozen public surface (REORG_PLAN Phase 0) ---------------------------
# The connector imports `fsr_playbooks.agent.skill_trace`. Re-export it so the
# stable path is guaranteed by the package, not just by file location.
from . import skill_trace

__all__ = ["skill_trace"]
