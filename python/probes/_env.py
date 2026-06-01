"""Load `.env` and build a ready-to-use pyfsr client.

Probes call `get_client()` — they don't parse env vars themselves. Returns
None when the env is incomplete (no base URL or no auth), so each probe can
fall back to local-only mode and stamp `seen` rows.
"""
from __future__ import annotations

import os
from typing import Optional

from .common import REPO_ROOT

ENV_PATH = REPO_ROOT / ".env"


def _load_dotenv() -> None:
    """Tiny .env parser. Avoids a python-dotenv dep for one file with simple syntax."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip inline comments. If the value isn't quoted, anything from the
        # first `#` onward is a comment (covers both `KEY=val # cmt` and
        # `KEY=# cmt` → empty).
        if value and value[0] not in ('"', "'"):
            hash_idx = value.find("#")
            if hash_idx >= 0:
                value = value[:hash_idx].rstrip()
        key, value = key.strip(), value.strip('"').strip("'")
        # Don't clobber values already set in the real environment.
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class EnvConfig:
    """Lazy view over the env. Probes use `is_live()` to decide live vs local."""

    def __init__(self) -> None:
        _load_dotenv()
        self.base_url: str = os.environ.get("FSR_BASE_URL", "").strip()
        self.api_key: str = os.environ.get("FSR_API_KEY", "").strip()
        self.username: str = os.environ.get("FSR_USERNAME", "").strip()
        self.password: str = os.environ.get("FSR_PASSWORD", "").strip()
        self.verify_ssl: bool = _bool("FSR_VERIFY_SSL", True)
        self.port: Optional[int] = (
            int(os.environ["FSR_PORT"]) if os.environ.get("FSR_PORT") else None
        )
        self.timeout: int = int(os.environ.get("FSR_TIMEOUT", "30"))
        self.instance_label: str = os.environ.get("FSR_INSTANCE_LABEL", "").strip()
        self.allow_e2e: bool = _bool("FSR_ALLOW_E2E", False)
        # SSH access to the appliance (for reading connector source files)
        _ssh_host_default = self.base_url.replace("https://", "").replace("http://", "").split(":")[0]
        self.ssh_host: str = os.environ.get("FSR_SSH_HOST", _ssh_host_default).strip()
        self.ssh_user: str = os.environ.get("FSR_SSH_USER", self.username or "csadmin").strip()
        self.ssh_password: str = os.environ.get("FSR_SSH_PASSWORD", self.password).strip()
        self.ssh_key_path: str = os.environ.get("FSR_SSH_KEY_PATH", "").strip()
        self.ssh_port: int = int(os.environ.get("FSR_SSH_PORT", "22"))

    def is_live(self) -> bool:
        if not self.base_url:
            return False
        return bool(self.api_key) or bool(self.username and self.password)

    def auth(self):  # tuple | str | None — matches pyfsr's FortiSOAR(auth=...) shape
        if self.api_key:
            return self.api_key
        if self.username and self.password:
            return (self.username, self.password)
        return None


_cached_cfg: EnvConfig | None = None


def get_config() -> EnvConfig:
    global _cached_cfg
    if _cached_cfg is None:
        _cached_cfg = EnvConfig()
    return _cached_cfg


def get_client():
    """Return a pyfsr `FortiSOAR` client, or None if env is incomplete."""
    cfg = get_config()
    if not cfg.is_live():
        return None
    from pyfsr import FortiSOAR  # type: ignore

    kwargs = dict(base_url=cfg.base_url, auth=cfg.auth(), verify_ssl=cfg.verify_ssl)
    if cfg.port is not None:
        kwargs["port"] = cfg.port
    client = FortiSOAR(**kwargs)
    # pyfsr unconditionally prepends https://; restore the original scheme
    # when the caller pointed at a plain-HTTP host (used by the E2E stub).
    if cfg.base_url.startswith("http://"):
        client.base_url = cfg.base_url.rstrip("/")
    return client
