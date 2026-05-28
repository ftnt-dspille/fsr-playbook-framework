"""Protocols consumers must supply to fsr_core.

`fsr_core` ships agent-loop + compiler + tool plumbing. Anything that
depends on where config / secrets / reference data actually live is
deferred to the consumer (web/backend, FortiSOAR connector, CLI). The
consumer hands fsr_core an object satisfying these protocols at startup.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class ProviderConfig:
    """Resolved per-provider config (URL/key/model). Mirrors the shape
    that `backend.settings.load_provider` returns; redefined here so
    fsr_core has no inbound dep on the web backend."""
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
