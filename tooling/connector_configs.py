"""Connector configuration resolution.

Connector steps (incl. code_snippet, http, etc.) require a `config` UUID
that points to a per-instance connector-configuration record. Configs
are not part of compiled playbook JSON in any portable way — they're
created out-of-band on each FSR box. This module:

  - Lists configurations for a connector (live, via /api/integration/connectors/).
  - Resolves friendly config name → config_id (UUID).
  - Caches the resolution to `store/connector_config_map.json` so repeat
    compiles don't need a live API.

Used by:
  - compiler.resolver (code_snippet normalization)
  - mcp_server.list_configured_connectors (already exists; pre-dates this module)
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data" / "connector_config_map.json"

# In-process cache: "connector:config_name" → config_id (UUID).
_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    if CACHE_PATH.exists():
        try:
            _cache = json.loads(CACHE_PATH.read_text())
        except Exception:  # noqa: BLE001
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save() -> None:
    if _cache is None:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, indent=2, sort_keys=True))


def _live_client():
    try:
        from probes._env import get_client, get_config
    except Exception:  # noqa: BLE001
        return None
    if not get_config().is_live():
        return None
    return get_client()


def list_configurations(connector: str) -> list[dict]:
    """Live-fetch [{config_id, name, default}] for a connector. Empty
    list if the env isn't configured or the connector isn't installed."""
    client = _live_client()
    if client is None:
        return []
    # The integration API is Django-REST: it paginates on `page_size`/`page`
    # (default 30) — the crudhub's `$limit` is silently ignored here, which used
    # to cap this at the first 30 connectors. Filter by name server-side and
    # raise the page size so a connector past the default page is still found.
    r = client.session.get(
        client.base_url + "/api/integration/connectors/",
        params={"name": connector, "page_size": 1000},
        verify=client.verify_ssl,
    )
    if r.status_code != 200:
        return []
    for m in r.json().get("data") or []:
        if m.get("name") == connector:
            return [
                {"config_id": c.get("config_id"),
                 "name": c.get("name"),
                 "default": bool(c.get("default"))}
                for c in (m.get("configuration") or [])
            ]
    return []


def resolve_config_id(connector: str, config_name: str | None = None
                      ) -> str | None:
    """Return the config UUID for `connector` and optional `config_name`.
    If `config_name` is None, returns the default config (or the first
    config if none is flagged default). Caches result."""
    cache = _load()
    key = f"{connector}:{config_name or '__default__'}"
    if key in cache:
        return cache[key] or None
    configs = list_configurations(connector)
    if not configs:
        return None
    chosen = None
    if config_name:
        chosen = next((c for c in configs if c.get("name") == config_name), None)
    if chosen is None:
        chosen = next((c for c in configs if c.get("default")), None) \
                 or configs[0]
    cid = chosen.get("config_id") if chosen else None
    cache[key] = cid or ""
    _save()
    return cid
