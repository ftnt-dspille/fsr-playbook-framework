"""Adapter wrapping `backend.history` so fsr_core.llm.run_agent_turn
can persist chat rows without importing from the web backend.

The HistorySink protocol (fsr_core.protocols.HistorySink) has the same
three method names as the equivalent functions in `backend.history`;
this adapter just forwards.
"""
from __future__ import annotations

from backend import history as _history


class BackendHistorySink:
    """HistorySink impl backed by web/backend/history.py."""

    def write_active_session(self, session_id):
        _history.write_active_session(session_id)

    def record_chat_turn(self, record):
        _history.record_chat_turn(record)

    def record_chat_message(self, session_id, turn, seq, kind, content, name=None):
        _history.record_chat_message(
            session_id, turn, seq, kind=kind, content=content, name=name,
        )
