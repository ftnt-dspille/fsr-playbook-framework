"""LLM provider settings — split-store: non-secret JSON + secrets in keyring.

Layout:
  web/data/settings.json:
    {
      "active_provider": "lmstudio",
      "providers": {
        "lmstudio":  {"base_url": "http://localhost:1234/v1", "model": "qwen2.5-coder-32b-instruct"},
        "anthropic": {"model": "claude-sonnet-4-5-20250929"}
      }
    }
  keyring (service=fsr-studio):
    "lmstudio_api_key" → ...
    "anthropic_api_key" → ...

Why split: keys belong in OS-managed secret storage; URL/model are not
secret and benefit from being in a human-editable JSON. The two halves
join back together via `load_provider(name)` which returns a fully
populated config the providers can construct from.

Migration: on first start, if `ANTHROPIC_API_KEY` is in env and keyring
has nothing, copy across. Old workflows still work because we never
delete the env var.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from .secrets_store import get_secrets


# web/data/ — sibling of backend/, gitignored.
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"


# Provider name → list of fields the secret store holds for it. Keep
# narrow: today every provider has exactly one secret, the api_key.
_SECRET_FIELDS: dict[str, list[str]] = {
    "lmstudio": ["api_key"],
    "anthropic": ["api_key"],
}


# Provider name → (default model, default base_url-or-None). Used when
# the on-disk file has no entry for a provider yet, so reads return a
# sensible blank rather than KeyError.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "lmstudio":  {"base_url": "http://localhost:1234/v1", "model": ""},
    "anthropic": {"base_url": None, "model": "claude-sonnet-4-5-20250929"},
}


@dataclass
class ProviderConfig:
    name: str
    base_url: str | None = None
    model: str = ""
    api_key: str | None = None  # populated from keyring on read; never persisted in JSON

    def is_configured(self) -> bool:
        """A provider is 'configured' when we have what it minimally needs
        to make a chat call. Provider-specific."""
        if self.name == "lmstudio":
            # LM Studio tolerates a placeholder key but the URL is required.
            return bool(self.base_url) and bool(self.model)
        if self.name == "anthropic":
            return bool(self.api_key) and bool(self.model)
        return bool(self.model)


_lock = Lock()


def _read_raw() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        # Corrupt file shouldn't bring down the backend. Return empty;
        # the next save will overwrite cleanly.
        return {}


def _write_raw(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, SETTINGS_PATH)
    try:
        os.chmod(SETTINGS_PATH, 0o600)
    except OSError:
        pass  # Windows ignores chmod modes; that's fine.


def _provider_block(raw: dict[str, Any], name: str) -> dict[str, Any]:
    return {**_DEFAULTS.get(name, {}), **(raw.get("providers", {}).get(name) or {})}


def load_provider(name: str) -> ProviderConfig:
    """Hydrate a provider config from JSON + keyring. Always returns a
    ProviderConfig (with blanks if nothing is saved yet)."""
    with _lock:
        raw = _read_raw()
    block = _provider_block(raw, name)
    secrets = get_secrets()
    api_key = secrets.get(f"{name}_api_key")
    # Migration: if anthropic and env has a key but keyring is empty,
    # write the env key across so the user doesn't have to re-paste.
    if name == "anthropic" and not api_key:
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            try:
                secrets.set(f"{name}_api_key", env_key)
                api_key = env_key
            except Exception:
                api_key = env_key  # still usable, just not persisted
    return ProviderConfig(
        name=name,
        base_url=block.get("base_url"),
        model=block.get("model") or "",
        api_key=api_key,
    )


def save_provider(name: str, *,
                  base_url: str | None | type(...) = ...,
                  model: str | None | type(...) = ...,
                  api_key: str | None | type(...) = ...) -> None:
    """Patch the on-disk record for `name`. Sentinel `...` means leave
    unchanged. `None` for `api_key` deletes the secret; an empty-string
    api_key is rejected (use None to clear).
    """
    with _lock:
        raw = _read_raw()
        providers = raw.setdefault("providers", {})
        block = providers.setdefault(name, {})
        if base_url is not ...:
            if base_url:
                block["base_url"] = base_url.rstrip("/")
            else:
                block.pop("base_url", None)
        if model is not ...:
            if model:
                block["model"] = model
            else:
                block.pop("model", None)
        _write_raw(raw)

    if api_key is not ...:
        secrets = get_secrets()
        if api_key is None:
            secrets.delete(f"{name}_api_key")
        elif api_key == "":
            raise ValueError("empty api_key is not allowed; pass None to clear")
        else:
            secrets.set(f"{name}_api_key", api_key)


def set_active_provider(name: str, model: str | None = None) -> None:
    """Mark `name` as the chat default. Optionally update its model in
    the same call (handy when the UI's flow is test → pick model → activate)."""
    with _lock:
        raw = _read_raw()
        raw["active_provider"] = name
        if model:
            providers = raw.setdefault("providers", {})
            providers.setdefault(name, {})["model"] = model
        _write_raw(raw)


def get_active_provider_name() -> str:
    """Active provider per settings, falling back to env var, then anthropic."""
    with _lock:
        raw = _read_raw()
    return raw.get("active_provider") or os.environ.get("STUDIO_LLM_PROVIDER") or "anthropic"


def list_provider_names() -> list[str]:
    return sorted(_DEFAULTS.keys())


def redacted_view() -> dict[str, Any]:
    """Browser-safe snapshot. Real api_key never crosses this boundary."""
    out: dict[str, Any] = {
        "active_provider": get_active_provider_name(),
        "providers": {},
    }
    for name in list_provider_names():
        cfg = load_provider(name)
        out["providers"][name] = {
            "name": name,
            "base_url": cfg.base_url,
            "model": cfg.model,
            "api_key_set": bool(cfg.api_key),
            "configured": cfg.is_configured(),
        }
    return out


def secrets_health() -> dict[str, Any]:
    ok, backend = get_secrets().available()
    return {"ok": ok, "backend": backend}


__all__ = [
    "ProviderConfig",
    "load_provider", "save_provider",
    "set_active_provider", "get_active_provider_name",
    "list_provider_names", "redacted_view", "secrets_health",
]
