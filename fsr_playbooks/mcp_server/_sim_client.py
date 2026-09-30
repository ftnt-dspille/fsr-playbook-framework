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

from contextlib import contextmanager
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


# ---------------------------------------------------------------------------
# The `probes._env` seam
# ---------------------------------------------------------------------------
# Every live-touching tool resolves its client through `probes._env`, so
# pointing that one module at a fake box is the whole of "offline mode". This
# is the ONE place the swap is built. It used to be hand-rolled in four files,
# and only one of them restored what it displaced: a copy that forgot left the
# fake box installed for the rest of the process, and an unrelated test then
# saw a box with only the sim connectors configured -- red or green depending
# on test order.

def bridge_modules(client_factory: Any = None,
                   config_factory: Any = None) -> dict[str, Any]:
    """Build the stand-in `probes` / `probes._env` modules, keyed for sys.modules.

    Defaults to this module's simulated client. The real `probes._env`'s other
    attributes (`EnvConfig`, `_load_dotenv`, ...) are carried across when it is
    importable: offline should remove the box, not the module.
    """
    import types

    env_mod = types.ModuleType("probes._env")
    try:
        import probes._env as real  # tooling/ may not be on sys.path
        for attr in dir(real):
            if not attr.startswith("__"):
                setattr(env_mod, attr, getattr(real, attr))
    except Exception:  # noqa: BLE001
        pass
    env_mod.get_client = client_factory or get_client  # type: ignore[attr-defined]
    env_mod.get_config = config_factory or get_config  # type: ignore[attr-defined]
    probes_mod = types.ModuleType("probes")
    probes_mod._env = env_mod  # type: ignore[attr-defined]
    return {"probes": probes_mod, "probes._env": env_mod}


def _reset_client_caches() -> None:
    """Drop every cache that would let one box's answers outlive the swap."""
    from . import _shared
    from . import tools_execution as te

    _shared._LIVE_CLIENT_CACHE.pop("client", None)
    te._CONFIGURED_CACHE["rows"] = None
    te._CONFIGURED_CACHE["ts"] = 0.0



@contextmanager
def probes_bridge(client_factory: Any = None, config_factory: Any = None):
    """Serve `probes._env` from a fake box for the duration of the block.

    Restores the displaced modules and clears the client caches on exit, so
    nothing about the fake box survives the caller.
    """
    import sys

    mods = bridge_modules(client_factory, config_factory)
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    _reset_client_caches()
    try:
        yield
    finally:
        for key, mod in saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod
        _reset_client_caches()
