"""SessionState.created_records: the host's live list of records this
conversation created (tracker #179). A source, not a snapshot."""
from __future__ import annotations

from fsr_playbooks.llm import session_state


def test_unbound_by_default():
    assert session_state.current().created_records is None


def test_a_bound_source_is_read_live():
    made: list[str] = []
    token = session_state.update(created_records=lambda: list(made))
    try:
        source = session_state.current().created_records
        assert source() == []
        made.append("/api/3/alerts/a1")
        assert source() == ["/api/3/alerts/a1"]
    finally:
        session_state.reset(token)
    assert session_state.current().created_records is None
