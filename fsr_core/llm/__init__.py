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

__all__ = [
    "TurnResult",
    "run_agent_turn",
    "resume_agent_turn",
    "KIND_USER", "KIND_ASSISTANT_TEXT", "KIND_TOOL_USE", "KIND_TOOL_RESULT",
]
