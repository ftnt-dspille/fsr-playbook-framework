"""Simulated FSR client — offline / demo data source.

When the connector's ``simulation_mode`` config is enabled, the
``probes._env`` bridge binds :func:`get_client` here instead of the live
crudhub client (:mod:`fsr_playbooks.mcp_server._live_crudhub`). The agent loop,
the reference DB, and every *pure-local* tool (compile / validate / resolve /
render / find_connector / find_operation / get_op_schema …) run completely
unchanged — only the three *live-touching* FortiSOAR integration endpoints
are served from canned fixtures instead of hitting the platform:

    POST /api/integration/connector_details/        -> a roster of healthy,
         "Completed" connectors, so ``list_configured_connectors`` and
         ``run_op``'s preflight see a fully-wired, reachable instance.
    GET  /api/integration/connectors/healthcheck/<c>/<v>/
                                                     -> {"status": "available"}
    POST /api/integration/execute/                  -> a realistic per-
         (connector, operation) result: SIEM context / events, threat-intel
         enrichment, firewall containment, etc. Unknown (connector, op)
         pairs get a generic ok envelope so a hunt never dead-ends.

Why this exists: on the dev box the SIEM + several TI connectors are
frequently *Disconnected*, which (correctly) short-circuits the preflight
gate and starves a hunt/timeline/blast-radius demo of data. Simulation mode
gives the real agent rich, deterministic data to reason over without any
live dependency, and doubles as the substrate for the offline test harness.

The surface mirrors the slice of ``pyfsr.FortiSOAR`` the tools touch — the
same contract :class:`_live_crudhub.CrudhubLiveClient` implements — so the
swap is invisible to the ~50 tool call-sites.
"""
from __future__ import annotations

from typing import Any, Optional

from . import _sim_fixtures


class _Response:
    """Minimal ``requests.Response`` stand-in over a simulated result."""

    def __init__(self, data: Any, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> Any:
        return self._data

    @property
    def text(self) -> str:
        return "" if self._data is None else str(self._data)


def _route(method: str, url: str, body: Any) -> Any:
    """Map a (method, path, body) onto a canned response.

    ``url`` is the API path (query string included); call-sites pass
    ``client.base_url + path`` and ``base_url`` is ``""``.
    """
    path = url or ""
    if "connector_details" in path:
        return {"data": _sim_fixtures.connector_rows()}
    if "healthcheck" in path:
        # path: /api/integration/connectors/healthcheck/<connector>/<version>/
        name = _sim_fixtures.connector_from_healthcheck_path(path)
        return _sim_fixtures.healthcheck(name)
    if "integration/execute" in path:
        b = body or {}
        return {"data": _sim_fixtures.execute(
            b.get("connector"), b.get("operation"), b.get("params") or {})}
    # Anything else (icons, picklists, tags, run-history …): empty-but-ok.
    return {"data": []}


class _SimSession:
    """Mimics ``requests.Session`` used as ``client.session``."""

    def get(self, url: str, **_kw: Any) -> _Response:
        return _Response(_route("GET", url, None))

    def post(self, url: str, json: Any = None, **_kw: Any) -> _Response:
        return _Response(_route("POST", url, json))


class SimulatedFSRClient:
    """``pyfsr.FortiSOAR``-shaped client backed by static fixtures."""

    base_url = ""
    verify_ssl = False

    def __init__(self) -> None:
        self.session = _SimSession()

    def post(self, path: str, data: Any = None, **_kw: Any) -> Any:
        return _route("POST", path, data)

    def get(self, path: str, **_kw: Any) -> Any:
        return _route("GET", path, None)


class SimConfig:
    """Stands in for ``probes._env.EnvConfig`` / ``CrudhubConfig``. In
    simulation mode we are always 'live' against the fixtures."""

    base_url = ""
    verify_ssl = False
    api_key = ""

    def is_live(self) -> bool:
        return True

    def auth(self):  # parity with EnvConfig.auth()
        return None


def available() -> bool:
    return True


def get_client() -> Optional[SimulatedFSRClient]:
    return SimulatedFSRClient()


def get_config() -> SimConfig:
    return SimConfig()
