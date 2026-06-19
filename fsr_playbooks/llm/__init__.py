"""LLM provider + agent loop layer.

Public surface for consumers (web backend, FortiSOAR connector):
- `run_agent_turn` / `resume_agent_turn`: drive one user / resume turn
  end-to-end against any LLMProvider, with optional history persistence
  via a HistorySink and optional per-event callback for SSE streaming.
- `factory.get_provider` / `factory.set_config_provider`: wire up which
  provider answers at runtime.
- `provider`: the Event / Message / LLMProvider Protocol definitions.

The agent tool-use loop itself lives inside each provider's `stream()`
implementation; `run_agent_turn` is the *consumer* of that stream.
"""
from __future__ import annotations

from .run_turn import (
    TurnResult,
    run_agent_turn,
    resume_agent_turn,
    KIND_USER, KIND_ASSISTANT_TEXT, KIND_TOOL_USE, KIND_TOOL_RESULT,
)

# --- Frozen public surface (REORG_PLAN Phase 0) ---------------------------
# Generic LLM runtime consumed by the connector at stable paths. NOTE:
# triage_* modules are deliberately NOT part of this surface — they carve out
# to the connector in REORG_PLAN Phase 1 (surface B). Keep this block
# authoring/runtime-only.
#
# Only `provider` is re-exported eagerly: it is dependency-light and free of
# import-time side effects. `intents`, `approvals`, `anthropic_provider`, and
# `openai_provider` stay lazy submodule paths — `anthropic_provider` builds the
# tool REGISTRY at import time, which must run AFTER the mcp_server discovery
# tools register, and `openai_provider` carries the optional `openai` dep. The
# connector imports all of them as `fsr_playbooks.llm.<name>` submodule paths
# (still guaranteed by test_public_surface_contract), so eager binding here is
# unnecessary and only invites import-order breakage.
from . import provider
from .provider import Message, UsageEvent

__all__ = [
    "TurnResult",
    "run_agent_turn",
    "resume_agent_turn",
    "KIND_USER", "KIND_ASSISTANT_TEXT", "KIND_TOOL_USE", "KIND_TOOL_RESULT",
    "provider", "Message", "UsageEvent",
]
