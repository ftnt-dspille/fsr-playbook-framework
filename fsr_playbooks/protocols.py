"""Protocols consumers must supply to fsr_playbooks.

`fsr_playbooks` ships agent-loop + compiler + tool plumbing. Anything that
depends on where config / secrets / reference data actually live is
deferred to the consumer (web/backend, FortiSOAR connector, CLI). The
consumer hands fsr_playbooks an object satisfying these protocols at startup.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class ProviderConfig:
    """Resolved per-provider config (URL/key/model). Mirrors the shape
    that `backend.settings.load_provider` returns; redefined here so
    fsr_playbooks has no inbound dep on the web backend."""
    name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class ConfigProvider(Protocol):
    """Source of provider config. The FastAPI app implements this with
    `backend.settings`; the connector implements it by pulling from the
    FortiSOAR-decrypted `config` dict."""

    def get_active_provider_name(self) -> str: ...
    def load_provider(self, name: str) -> ProviderConfig: ...


class ApprovalGateway(Protocol):
    """Store for HITL-suspended agent sessions. Web backend uses the
    in-memory default; the FortiSOAR connector swaps in a sqlite-backed
    impl so paused turns survive worker restarts."""

    def stash(self, session) -> None: ...
    def peek(self, approval_id: str): ...
    def pop(self, approval_id: str): ...
    def clear(self) -> None: ...


class HistorySink(Protocol):
    """Persistent record of chat turns + per-message rows. The web
    backend uses the sqlite-backed `backend.history` module; the
    connector implements a parallel schema scoped by `session_id`."""

    def write_active_session(self, session_id: str) -> None: ...
    def record_chat_turn(self, record: dict) -> None: ...
    def record_chat_message(
        self, session_id: str, turn: int, seq: int,
        kind: str, content: str, name: str | None = None,
    ) -> None: ...
