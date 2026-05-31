"""In-platform live FSR client backed by ``integrations.crudhub``.

The live-touching MCP tools (`run_op`, `list_configured_connectors`,
`list_tags`, the run-history/investigation tools, picklist/icon fetches)
were written against the dev/CLI path: a ``pyfsr.FortiSOAR`` client built
from ``.env`` (``FSR_BASE_URL`` / ``FSR_API_KEY``) via ``probes._env``.

Inside the FortiSOAR connector there is no ``.env`` and no ``probes``
package — the correct, always-available transport is
``integrations.crudhub.make_request`` (a service-token loopback against
``https://localhost``, no re-auth). This module provides a drop-in client
whose surface matches the bits of ``pyfsr.FortiSOAR`` the tools actually
touch, so the connector can bridge ``probes._env`` onto crudhub without
editing any of the ~50 tool call-sites:

- ``client.post(path, body)``                      -> make_request(path, "POST", body=body)
- ``client.get(path)``                             -> make_request(path, "GET")
- ``client.session.get(base_url + url, ...)``      -> make_request(url, "GET")
- ``client.session.post(base_url + url, json=...)``-> make_request(url, "POST", body=json)
- ``client.base_url`` is ``""`` so ``base_url + path == path``
- ``client.verify_ssl`` is present but unused (the loopback handles TLS)

``make_request`` already returns parsed JSON (a dict, or None); the
``session`` shim wraps that in a minimal response object exposing
``status_code`` and ``json()`` so ``r.status_code == 200`` / ``r.json()``
call-sites keep working.
"""
from __future__ import annotations

from typing import Any, Optional


def _make_request():
    """The crudhub loopback callable, or None when not on-platform."""
    try:
        from integrations.crudhub import make_request  # type: ignore
        return make_request
    except Exception:  # noqa: BLE001
        try:
            from connectors.core.connector import make_request  # type: ignore
            return make_request
        except Exception:  # noqa: BLE001
            return None


class _Response:
    """Minimal stand-in for a ``requests.Response`` over a crudhub result."""

    def __init__(self, data: Any, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> Any:
        return self._data

    @property
    def text(self) -> str:
        return "" if self._data is None else str(self._data)


class _CrudhubSession:
    """Mimics the ``requests.Session`` used as ``client.session``. Call-sites
    pass ``client.base_url + url``; since ``base_url`` is ``""`` the argument
    IS the API path (query string included)."""

    def __init__(self, mr) -> None:
        self._mr = mr

    def get(self, url: str, **_kw: Any) -> _Response:
        try:
            return _Response(self._mr(url, "GET"))
        except Exception as e:  # noqa: BLE001
            return _Response({"error": str(e)}, status_code=599)

    def post(self, url: str, json: Any = None, **_kw: Any) -> _Response:
        try:
            return _Response(self._mr(url, "POST", body=json or {}))
        except Exception as e:  # noqa: BLE001
            return _Response({"error": str(e)}, status_code=599)

    def put(self, url: str, json: Any = None, **_kw: Any) -> _Response:
        try:
            return _Response(self._mr(url, "PUT", body=json or {}))
        except Exception as e:  # noqa: BLE001
            return _Response({"error": str(e)}, status_code=599)

    def delete(self, url: str, json: Any = None, **_kw: Any) -> _Response:
        # Single-row `/api/3/{entity}/{uuid}?$hardDelete=true` deletes carry NO
        # body. Crucially, do NOT coerce a missing body to `{}` — passing an
        # empty JSON body on a single-row DELETE makes make_request issue a
        # no-op that leaves the row in place (the scratch-collection leak fixed
        # in 0.3.64). Only forward a body when the caller actually supplies one.
        try:
            if json is None:
                return _Response(self._mr(url, "DELETE"))
            return _Response(self._mr(url, "DELETE", body=json))
        except Exception as e:  # noqa: BLE001
            return _Response({"error": str(e)}, status_code=599)


class CrudhubLiveClient:
    """``pyfsr.FortiSOAR``-shaped client backed by crudhub make_request."""

    base_url = ""
    verify_ssl = False

    def __init__(self, mr) -> None:
        self._mr = mr
        self.session = _CrudhubSession(mr)

    def post(self, path: str, data: Any = None, **_kw: Any) -> Any:
        return self._mr(path, "POST", body=data or {})

    def put(self, path: str, data: Any = None, **_kw: Any) -> Any:
        # Parity with pyfsr's client.put — needed by e2e.runner._push's
        # idempotent PUT-then-POST, which otherwise AttributeErrors here and
        # makes push_playbook/dry_run_playbook fail on the agent box.
        return self._mr(path, "PUT", body=data or {})

    def get(self, path: str, **_kw: Any) -> Any:
        return self._mr(path, "GET")

    def delete(self, path: str, data: Any = None, **_kw: Any) -> Any:
        # See _CrudhubSession.delete: never send an empty body on a single-row
        # DELETE — it no-ops. Forward a body only when one is actually given.
        if data is None:
            return self._mr(path, "DELETE")
        return self._mr(path, "DELETE", body=data)


class CrudhubConfig:
    """Stands in for ``probes._env.EnvConfig``. On-platform we are always
    'live' — crudhub is the authoritative loopback."""

    base_url = ""
    verify_ssl = False
    api_key = ""

    def is_live(self) -> bool:
        return _make_request() is not None

    def auth(self):  # parity with EnvConfig.auth()
        return None


def available() -> bool:
    """True when the crudhub loopback is importable (i.e. on-platform)."""
    return _make_request() is not None


def get_client() -> Optional[CrudhubLiveClient]:
    mr = _make_request()
    return CrudhubLiveClient(mr) if mr is not None else None


def get_config() -> CrudhubConfig:
    return CrudhubConfig()
