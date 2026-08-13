"""Simulated FSR client -- offline / demo data source.

When the connector's ``simulation_mode`` config is enabled, the
``probes._env`` bridge binds :func:`get_client` here instead of the live
crudhub client (:mod:`fsr_playbooks.mcp_server._live_crudhub`). The agent loop,
the reference DB, and every *pure-local* tool (compile / validate / resolve /
render / find_connector / find_operation / get_op_schema …) run completely
unchanged -- only the three *live-touching* FortiSOAR integration endpoints
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

The surface mirrors the slice of ``pyfsr.FortiSOAR`` the tools touch -- the
same contract :class:`_live_crudhub.CrudhubLiveClient` implements -- so the
swap is invisible to the ~50 tool call-sites.
"""
from __future__ import annotations

from typing import Any

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


#: The bound record table, if any. ``None`` -- the default -- keeps the record
#: surface exactly as it was: empty-but-ok. See :func:`bind_box`.
_BOX: Any = None


def bind_box(box: Any) -> Any:
    """Serve the record surface (``/api/3/…``, ``/api/query/…``) from ``box``.

    ``box`` is a :class:`._fixture_box.FixtureBox` -- a real record table with
    the filter/sort/limit semantics the query path uses. Without one, every
    record read here answers ``{"data": []}``, which is why an offline
    investigation could run a dozen reads and learn nothing: the agent behaved
    correctly against a box that held nothing, and the *harness* scored it.

    Opt-in on purpose. Unbound, nothing about this module's behavior changes.
    Returns the previously bound box so a caller can restore it.
    """
    global _BOX
    prev, _BOX = _BOX, box
    return prev


def unbind_box() -> None:
    global _BOX
    _BOX = None


def active_box() -> Any:
    return _BOX


def _route_status(method: str, url: str, body: Any) -> tuple[int, Any]:
    """Map a (method, path, body) onto a canned ``(status, body)``.

    ``url`` is the API path (query string included); call-sites pass
    ``client.base_url + path`` and ``base_url`` is ``""``.
    """
    path = url or ""
    if "connector_details" in path:
        return 200, {"data": _sim_fixtures.connector_rows()}
    if "healthcheck" in path:
        # path: /api/integration/connectors/healthcheck/<connector>/<version>/
        name = _sim_fixtures.connector_from_healthcheck_path(path)
        return 200, _sim_fixtures.healthcheck(name)
    if "integration/execute" in path:
        b = body or {}
        return 200, {"data": _sim_fixtures.execute(
            b.get("connector"), b.get("operation"), b.get("params") or {})}
    # The record surface, when a bundle is bound. The box owns its own status
    # codes -- a 404 for a module it does not hold, a 599 for a POST that is a
    # write -- because an unanswered read has to be VISIBLE. Falling back to
    # the empty-but-ok envelope here would restore the exact failure the box
    # exists to remove.
    if _BOX is not None and ("/api/3/" in path or "/api/query/" in path):
        if method == "POST":
            return _BOX.post(url, body)
        return _BOX.get(url)
    # Anything else (icons, picklists, tags, run-history …): empty-but-ok.
    return 200, {"data": []}


def _route(method: str, url: str, body: Any) -> Any:
    """``_route_status`` without the status -- the body-only call path.

    ``SimulatedFSRClient.get/post`` mirror pyfsr's typed helpers, which hand
    back parsed JSON and have nowhere to put a status. A bound box's 404/599
    therefore reaches those callers as an error BODY (`{"message": ...}`)
    rather than a status. That is still loud -- the caller gets a shape it did
    not ask for -- but the record tools all go through ``client.session``,
    which keeps the status.
    """
    return _route_status(method, url, body)[1]


class _SimSession:
    """Mimics ``requests.Session`` used as ``client.session``."""

    def get(self, url: str, **_kw: Any) -> _Response:
        status, data = _route_status("GET", url, None)
        return _Response(data, status)

    def post(self, url: str, json: Any = None, **_kw: Any) -> _Response:
        status, data = _route_status("POST", url, json)
        return _Response(data, status)


class _SimConnector:
    """One row of ``client.connectors.list_configured()``, attribute-shaped.

    `list_configured_connectors` reads `.name/.status/.version/.label/
    .configurations` off pyfsr's typed objects, not a dict.
    """

    def __init__(self, row: dict) -> None:
        self.name = row.get("name")
        self.status = row.get("status") or "Completed"
        self.version = row.get("version")
        self.label = row.get("label") or row.get("name")
        self.configurations = list(row.get("configs") or [])


class _SimConnectorsAPI:
    """The slice of pyfsr's typed ``client.connectors`` that discovery uses.

    Without it, `list_configured_connectors` raises `AttributeError` and every
    caller downstream reports `no_fsr_configured` -- which offline meant
    `find_enrichment_actions` and `find_containment_actions` failed on 9 of 9
    calls in a five-fixture investigation run. That is not a small gap: those
    two tools ARE the shortcut past connector discovery, so the agent asked the
    right question first, got a hard error, and fell back to walking
    `find_connector` -> `find_operation` -> `get_op_schema` by hand. Half of
    every investigation's tool budget went there, and it read as the agent
    overspending.

    Built from the SAME `connector_rows()` the `/api/integration/
    connector_details/` route serves, so there is one definition of what is
    configured offline. Two would drift, and a drifted fixture reads as a
    model result.
    """

    def list_configured(self) -> list:
        return [_SimConnector(r) for r in _sim_fixtures.connector_rows()]


class SimulatedFSRClient:
    """``pyfsr.FortiSOAR``-shaped client backed by static fixtures."""

    base_url = ""
    verify_ssl = False

    def __init__(self) -> None:
        self.session = _SimSession()
        self.connectors = _SimConnectorsAPI()

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


def get_client() -> SimulatedFSRClient | None:
    return SimulatedFSRClient()


def get_config() -> SimConfig:
    return SimConfig()
