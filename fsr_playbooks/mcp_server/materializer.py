"""Dynamic tool surface -- materialize FortiSOAR 8.0 native-MCP-gateway tools as
first-class ``ToolSpec``\\ s in the LLM :data:`~fsr_playbooks.llm.tools.REGISTRY`.

The widget-drawer triage agent's tool surface was static and hand-curated (one
Python wrapper per op in ``tools_noc.py`` / ``tools_triage.py``). This module
replaces that model: at session start it asks the platform's **native MCP
gateway** (``client.mcp`` -- ``/mcp/*``, shipped FortiSOAR 8.0.0+) which tools
exist on the servers the operator allow-listed, and materializes each as a
``ToolSpec`` whose ``fn`` routes back through ``client.mcp.call_tool``. The
agent's tool surface *is* the configured-capability surface -- an unconfigured
connector's tool simply isn't registered, so the agent can't call it (the
``unknown_connector`` thrash the 0.4.37 prompt rules policed becomes
structurally impossible, and those rules become transitional).

``server`` is one of the 4 built-ins (``"modules"``, ``"playbooks"``,
``"soc"``, ``"utility"``) or ``"connector:<name>"`` for an installed
connector's auto-generated MCP server -- so registered-MCP-server tools (Power
1) *and* configured-connector-op tools (Power 2) flow through one substrate.

Discovery + execution both live on the live pyfsr ``FortiSOAR`` client
(``client.mcp.list_tools`` / ``client.mcp.call_tool``); this consumer adds no
new transport. The on-box worker reaches ``/mcp/*`` via the env-creds client
(``EnvConfig.from_env().client()``), not the crudhub loopback (crudhub speaks
Hydra REST, not MCP streamable-HTTP). ``make mcp-bridge-check`` proves
reachability.

Safety model (mirrors the platform's ``memory.yaml`` allow-list -- no
auto-discovery): the connector calls :func:`configure` with an explicit
per-server allow-list at session setup; default empty → nothing materialized →
no behavior change on upgrade. Each allow-list entry declares the server
read-only (→ tier 1, auto-run) or mutating (→ tier 3, approval card).

Phase-0 probe (``make mcp-bridge-check``) confirmed the substrate live on 8.0:
``list_tools`` returns ``[{"name", "description", "input_schema"}, ...]`` with
full JSON schemas -- passed straight into ``ToolSpec``.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

log = logging.getLogger(__name__)

# OAuth2 client_credentials token cache for external MCP servers whose auth rule
# carries an ``oauth2`` block. Keyed by (token_url, client_id) → (token, expiry).
# The materializer captures headers at build time AND recomputes them per call
# (see _make_fn), so a cached-then-refreshed token flows to both list + call.
_OAUTH_CACHE: dict[tuple[str, str], tuple[str, float]] = {}
_OAUTH_SKEW_S = 60.0  # refresh this many seconds BEFORE the token actually expires
_OAUTH_ATTEMPTS = 4   # mint tries before giving up (see _oauth2_bearer)
# Full-jitter base: sleep U(0, base * 2**(n-1)). Measured against FortiSIEM's
# token endpoint, which tolerates roughly ONE grant per 3-4s per client: mints
# 1-2s apart return 400, ~4s apart return 200. A sub-second backoff just
# re-collides, so the base is seconds, not milliseconds.
_OAUTH_BACKOFF_S = 2.0

# Cross-process token cache. THE fix for the herd (tracker #66): the workers all
# restart together on a ship and each minted its own token, so 7 grants hit the
# endpoint in the same instant and 6 got 400/429. Measured live: one token
# serves 7 concurrent MCP sessions perfectly (17 tools each) -- it is only the
# token endpoint that throttles. So mint once per box and share it, and the
# burst stops existing. With FortiSIEM's expires_in of 86400 that is one grant a
# day instead of one per worker per ship.
_OAUTH_CACHE_DIR_ENV = "FSRPB_OAUTH_CACHE_DIR"

# Servers whose materialization FAILED, → the earliest time to try them again.
# Without this a transient failure was permanent: `ensure_initialized` latches
# `_initialized` before materializing, so a worker that lost a token-endpoint
# race stayed without that server until the process was recycled. The latch is
# right for "already materialized"; it is wrong for "this server errored".
_FAILED_SERVERS: dict[str, float] = {}
_RETRY_COOLDOWN_S = 60.0  # don't re-hit a failing server on every single turn

# Cap so a misconfigured allow-list can't flood the LLM tool list (the platform
# model gates per-server; this is a backstop). Logged when hit -- no silent drop.
_MAX_TOOLS = 80

# materialized tool name → (server, tool_name). Used by the trace→playbook
# compiler (later phase) + attribution. Populated at materialize time.
SERVER_MAP: dict[str, tuple[str, str]] = {}

# module-level state (configure → ensure_initialized → initialize)
_allowlist: dict[str, dict[str, Any]] = {}
_client_factory: Callable[[], Any] | None = None
_initialized: bool = False
_materialized_names: set[str] = set()


def configure(
    *,
    mcp_allowlist: dict[str, dict[str, Any]] | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> None:
    """Set the per-session allow-list (and optional client factory).

    Called by the connector at session setup, from its config record. Safe to
    call repeatedly: each kwarg that is passed is applied, and one that is
    omitted is preserved (merge, not replace) -- so the connector's two-phase
    wiring works: ``register_mcp_materializer()`` sets ``client_factory`` at
    import time, then ``_apply_mcp_allowlist(config)`` sets ``mcp_allowlist``
    per turn without clobbering the factory. :func:`reset` clears everything
    for tests.

    ``mcp_allowlist`` maps a server (built-in name or ``"connector:<name>"``)
    to ``{"tools": ["t1", "t2"] | "*", "tier": "read_only" | "mutating"}``.
    Default (``{}`` / not called) → no MCP tools materialized; the curated
    ``SAFE_TOOLS`` remain. ``client_factory`` is injectable for tests; in
    production it's left None and :func:`initialize` builds the live pyfsr
    client from env.

    An entry may also point at an **external** MCP server (not the on-appliance
    gateway) by adding a ``url`` and optional ``auth`` -- e.g.
    ``{"my_tools": {"url": "https://host/mcp/", "auth": {"bearer": "<tok>"},
    "tools": "*", "tier": "read_only"}}``. External entries route through
    pyfsr's ``list_tools_at`` / ``call_tool_at`` with the rule's own headers
    (see :func:`_auth_headers`); the key becomes the tool-name prefix
    (``mcp_my_tools__<tool>``).
    """
    global _allowlist, _client_factory, _initialized
    if mcp_allowlist is not None:
        _allowlist = dict(mcp_allowlist)
    if client_factory is not None:
        _client_factory = client_factory
    _initialized = False  # re-configure ⟹ re-initialize on next ensure


def reset() -> None:
    """Clear all materializer state + remove materialized tools from REGISTRY /
    TOOL_TIERS. For tests so each case runs from a clean baseline."""
    global _allowlist, _client_factory, _initialized
    from ..llm import tools as llm_tools
    for name in list(_materialized_names):
        llm_tools.REGISTRY.pop(name, None)
        llm_tools.TOOL_TIERS.pop(name, None)
    _materialized_names.clear()
    SERVER_MAP.clear()
    _FAILED_SERVERS.clear()
    _DROPPED_MUTATING.clear()
    _allowlist = {}
    _client_factory = None
    _initialized = False


def ensure_initialized() -> None:
    """Lazy, idempotent materialization. Called from ``anthropic_tools`` /
    ``openai_tools`` so materialized tools appear in the LLM's tool list on the
    first turn. No-op if already initialized; never raises (a failure logs and
    leaves REGISTRY unchanged -- the curated SAFE_TOOLS keep working)."""
    global _initialized
    if _initialized:
        # Already materialized once -- but retry any server that FAILED, once
        # its cooldown is up. A server can fail for reasons that have nothing to
        # do with its configuration (a token endpoint rate-limiting the burst of
        # workers a ship restarts together), and latching that forever left the
        # agent silently short a whole toolset until the worker recycled.
        due = [s for s, at in _FAILED_SERVERS.items() if time.time() >= at]
        if not due:
            return
        try:
            _initialize_impl(only=due)
        except Exception as exc:  # noqa: BLE001 - never red a session
            log.warning("MCP materializer retry failed (curated tools remain): %s", exc)
        return
    _initialized = True  # set first so a failure doesn't retry every turn
    if not _allowlist:
        _load_allowlist_from_env()  # FSRPB_MCP_ALLOWLIST fallback
    if not _allowlist:
        return  # nothing configured → nothing to do (default path)
    try:
        _initialize_impl()
    except Exception as exc:  # noqa: BLE001 - never red a session
        log.warning("MCP materializer failed (curated tools remain): %s", exc)


def _load_allowlist_from_env() -> None:
    """Fallback: read the allowlist from ``FSRPB_MCP_ALLOWLIST`` (JSON) so the
    materializer can be activated without a code-level ``configure()`` call --
    the operator sets it in the worker env. Dormant when unset (default)."""
    global _allowlist
    import json
    import os
    raw = os.environ.get("FSRPB_MCP_ALLOWLIST", "").strip()
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("MCP materializer: FSRPB_MCP_ALLOWLIST is not valid JSON (%s); ignoring", exc)
        return
    if isinstance(parsed, dict):
        _allowlist = parsed
    else:
        log.warning("MCP materializer: FSRPB_MCP_ALLOWLIST must be a JSON object; ignoring")


def _build_client() -> Any:
    """Construct the live pyfsr FortiSOAR client. Priority: injected factory
    (tests) → EnvConfig.from_env().client() (production, the path the
    mcp-bridge-check probe proved). Returns None if unavailable (offline /
    no creds)."""
    if _client_factory is not None:
        return _client_factory()
    try:
        from pyfsr.config import EnvConfig
        return EnvConfig.from_env().client()
    except Exception as exc:  # noqa: BLE001
        log.debug("MCP materializer: no live client (%s)", exc)
        return None


def _initialize_impl(only: list[str] | None = None) -> None:
    """Materialize the allowlist. ``only`` restricts the pass to named servers --
    the retry path for ones that failed earlier (see :func:`ensure_initialized`)."""
    client = _build_client()
    if client is None:
        return
    mcp = getattr(client, "mcp", None)
    if mcp is None:
        log.debug("MCP materializer: client has no .mcp (not a pyfsr FortiSOAR client)")
        return
    supports = getattr(client, "supports_native_mcp", lambda: None)
    try:
        ok = supports()
    except Exception as exc:  # noqa: BLE001
        log.debug("MCP materializer: supports_native_mcp() raised: %s", exc)
        return
    if ok is False:
        log.info("MCP materializer: native MCP gateway not supported on this appliance")
        return

    from ..llm import tools as llm_tools
    from ..llm.tools import ToolSpec

    specs: dict[str, ToolSpec] = {}
    tiers: dict[str, int] = {}
    for server, raw_rule in _allowlist.items():
        if only is not None and server not in only:
            continue
        rule = _normalize_rule(raw_rule)
        if rule is None:
            continue  # server explicitly disabled (False / None / empty)
        tier_label = rule.get("tier", "read_only")
        tier = 3 if tier_label == "mutating" else 1
        allowed_tools = rule.get("tools", "*")
        # External server: an allowlist rule may carry a ``url`` pointing at an
        # MCP server that is NOT the on-appliance gateway (a partner tool, an
        # internal service). When present we route enumeration + execution
        # through pyfsr's lower-level ``*_at`` methods with the rule's own auth
        # headers, instead of the credentialed on-box ``/mcp/<server>/`` path.
        # ``server`` stays the operator's chosen name (→ ``mcp_<name>__<tool>``).
        ext_url = rule.get("url")
        ext_headers = _auth_headers(rule) if ext_url else None
        # A rule that DECLARES oauth2 but produced no Authorization header means
        # the mint failed. Listing anyway sends an unauthenticated request, which
        # is what turned a plain 429 into `unhandled errors in a TaskGroup (1
        # sub-exception)` in the log -- the real cause a frame away and invisible.
        # Fail closed and mark the server for retry instead.
        if ext_url and _rule_wants_oauth2(rule) and not (ext_headers or {}).get("Authorization"):
            _FAILED_SERVERS[server] = time.time() + _RETRY_COOLDOWN_S
            log.warning("MCP materializer: %r skipped -- oauth2 token unavailable "
                        "(will retry in %ds)", server, int(_RETRY_COOLDOWN_S))
            continue
        ext_verify = rule.get("verify", True) if ext_url else None
        try:
            if ext_url:
                tools = mcp.list_tools_at(ext_url, ext_headers or {}, verify=ext_verify)
            else:
                tools = mcp.list_tools(server)
        except Exception as exc:  # noqa: BLE001 - one bad server shouldn't abort the rest
            _FAILED_SERVERS[server] = time.time() + _RETRY_COOLDOWN_S
            log.warning("MCP materializer: list_tools(%r) failed (will retry in %ds): %s",
                        server, int(_RETRY_COOLDOWN_S), exc)
            continue
        if not isinstance(tools, list):
            _FAILED_SERVERS[server] = time.time() + _RETRY_COOLDOWN_S
            continue
        _FAILED_SERVERS.pop(server, None)
        # Sort by name before registering. The gateway's list_tools() ordering is
        # not contractual, and REGISTRY insertion order IS the order the tool
        # array goes on the wire -- which is part of the provider prompt-cache
        # prefix. An ordering wobble between two turns rewrites those bytes and
        # busts the cache (OpenAI matches the prefix exactly; reads are 90% off,
        # so a silent miss is a ~10x input-cost regression that raises no error).
        tools = sorted(tools, key=lambda t: _tool_field(t, "name") or "")
        for tool in tools:
            # pyfsr's native client returns MCPTool pydantic models (dict-style
            # access via _Lenient), while the built-in servers / tests hand back
            # plain dicts. Accept either -- a strict ``isinstance(tool, dict)``
            # gate silently skipped every live tool (bridge never materialized).
            tname = _tool_field(tool, "name")
            if not tname:
                continue
            if isinstance(allowed_tools, list) and tname not in allowed_tools:
                continue
            full = _make_name(server, tname)
            if full in llm_tools.REGISTRY and full not in _materialized_names:
                # don't clobber a curated SAFE_TOOLS entry; skip + log
                log.warning("MCP materializer: name collision, skipping %r", full)
                continue
            if len(specs) >= _MAX_TOOLS:
                log.warning("MCP materializer: hit %d-tool cap; further tools on %r dropped",
                            _MAX_TOOLS, server)
                break
            specs[full] = ToolSpec(
                name=full,
                description=_tool_field(tool, "description") or f"{tname} on {server}",
                input_schema=(_tool_field(tool, "input_schema")
                              or _tool_field(tool, "inputSchema")
                              or {"type": "object", "properties": {}}),
                fn=_make_fn(client, server, tname,
                            url=ext_url, headers=ext_headers, verify=ext_verify,
                            rule=rule if ext_url else None),
                tier=tier,
                confirm_mode="auto" if tier <= 1 else ("approve" if tier <= 3 else "step_up"),
            )
            tiers[full] = tier
            SERVER_MAP[full] = (server, tname)

    if specs:
        llm_tools.TOOL_TIERS.update(tiers)  # _resolve_tier reads TOOL_TIERS, not spec.tier
        llm_tools.REGISTRY.update(specs)
        _materialized_names.update(specs)
        log.info("MCP materializer: registered %d tool(s) across %d server(s)",
                 len(specs), len({s for s, _ in SERVER_MAP.values()}))


def _tool_field(tool: Any, key: str) -> Any:
    """Read ``key`` from an advertised tool that may be a plain dict OR a
    pydantic model (pyfsr's ``MCPTool``). Both support ``.get``; models also
    expose attributes, so fall back to ``getattr`` for property-only fields
    (e.g. ``input_schema`` derived from ``inputSchema``)."""
    getter = getattr(tool, "get", None)
    if callable(getter):
        val = getter(key)
        if val is not None:
            return val
    return getattr(tool, key, None)


def _normalize_rule(rule: Any) -> dict[str, Any] | None:
    """Coerce a per-server allowlist value into the canonical
    ``{"tools": ..., "tier": ...}`` dict the loop expects.

    Admins write the allowlist by hand in the connector config, so accept the
    natural shorthands instead of failing (a raw ``True`` used to raise
    ``'bool' object has no attribute 'get'`` and silently disable *all*
    materialization):

    - ``True`` / ``"*"`` / ``"read_only"`` / ``"all"`` → ``{}`` (all tools, read-only)
    - ``"mutating"`` → ``{"tier": "mutating"}``
    - ``["t1", "t2"]`` → ``{"tools": ["t1", "t2"]}`` (subset, read-only)
    - a dict → returned as-is
    - ``False`` / ``None`` / ``""`` → ``None`` (server disabled, skipped)
    """
    if rule is None or rule is False or rule == "":
        return None
    if rule is True:
        return {}
    if isinstance(rule, str):
        val = rule.strip().lower()
        if val in ("*", "read_only", "all"):
            return {}
        if val == "mutating":
            return {"tier": "mutating"}
        # a bare tool name → single-tool allowlist
        return {"tools": [rule]}
    if isinstance(rule, list):
        return {"tools": rule}
    if isinstance(rule, dict):
        return rule
    # unknown scalar → treat as "enabled, defaults" rather than aborting
    return {}


def _oauth_cache_path(key: tuple[str, str]) -> "Any":
    """Where the shared token for ``(token_url, client_id)`` lives.

    Filename is a hash: the client id is a credential and must not be readable
    from a directory listing. Dir 0700, file 0600 -- the token is a bearer at
    rest, no wider than the client_secret already sitting in the connector
    config it was minted from.
    """
    import hashlib
    import os
    import tempfile
    from pathlib import Path

    base = os.environ.get(_OAUTH_CACHE_DIR_ENV) or os.path.join(
        tempfile.gettempdir(), "fsrpb-oauth")
    d = Path(base)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha256("\x00".join(key).encode()).hexdigest()[:32]
    return d / f"{digest}.json"


def _oauth_cache_read(key: tuple[str, str]) -> str | None:
    """A still-valid shared token, or None. Never raises -- a corrupt or
    unreadable cache just means "mint one"."""
    import json

    try:
        path = _oauth_cache_path(key)
        if not path.exists():
            return None
        rec = json.loads(path.read_text())
        token, exp = rec.get("token"), float(rec.get("exp", 0))
        if token and time.time() < exp - _OAUTH_SKEW_S:
            return str(token)
    except Exception as exc:  # noqa: BLE001 - cache is an optimization, never a dependency
        log.debug("MCP oauth2: shared cache unreadable (%s)", exc)
    return None


def _oauth_cache_write(key: tuple[str, str], token: str, exp: float) -> None:
    """Publish a freshly minted token for the other workers. Atomic (write +
    replace) so a reader never sees a half-written file."""
    import json
    import os

    try:
        path = _oauth_cache_path(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"token": token, "exp": exp}))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        log.debug("MCP oauth2: could not publish shared token (%s)", exc)


def _oauth2_bearer(cfg: dict[str, Any]) -> str | None:
    """Return a valid access token for an OAuth2 client_credentials rule,
    minting a fresh one (and caching it to expiry) when none is cached or the
    cached one is within ``_OAUTH_SKEW_S`` of expiring.

    Rule shape (all under ``auth.oauth2``)::

        {"token_url": "https://host/.../oauth/token",
         "client_id": "...", "client_secret": "...",
         "scope": "optional", "verify": false,
         "grant_type": "client_credentials"}   # default

    Fail-soft: any error returns ``None`` (the server then simply fails to
    list/call and is logged upstream -- never aborts the other servers)."""
    token_url = cfg.get("token_url") or cfg.get("url")
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")
    if not (token_url and client_id and client_secret):
        log.warning("MCP oauth2: rule missing token_url/client_id/client_secret")
        return None

    key = (str(token_url), str(client_id))
    cached = _OAUTH_CACHE.get(key)
    if cached and time.time() < cached[1] - _OAUTH_SKEW_S:
        return cached[0]

    # Another worker on this box may already hold a valid token.
    shared = _oauth_cache_read(key)
    if shared:
        _OAUTH_CACHE[key] = (shared, time.time() + _OAUTH_SKEW_S * 2)
        return shared

    # Serialize the mint across processes so the ship-time herd becomes one
    # grant, not seven. Whoever loses the lock re-reads the cache the winner
    # just published instead of hitting the endpoint at all. Best-effort: if
    # locking is unavailable, fall through and mint (the retry loop covers it).
    lock = _oauth_lock(key)
    try:
        with lock:
            shared = _oauth_cache_read(key)
            if shared:
                _OAUTH_CACHE[key] = (shared, time.time() + _OAUTH_SKEW_S * 2)
                return shared
            return _mint_with_retry(cfg, key, token_url, client_id, client_secret)
    except Exception as exc:  # noqa: BLE001 - never fail a turn over locking
        log.debug("MCP oauth2: lock unavailable (%s); minting unserialized", exc)
    return _mint_with_retry(cfg, key, token_url, client_id, client_secret)


def _oauth_lock(key: tuple[str, str]) -> "Any":
    """A cross-process lock for minting ``key``'s token. Returns a context
    manager; a no-op one where ``fcntl`` is unavailable (non-POSIX)."""
    import contextlib

    try:
        import fcntl
    except Exception:  # noqa: BLE001 - not POSIX
        return contextlib.nullcontext()

    path = _oauth_cache_path(key).with_suffix(".lock")

    @contextlib.contextmanager
    def _locked():
        fh = open(path, "a+")  # noqa: SIM115 - closed in finally
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            finally:
                fh.close()

    return _locked()


def _mint_with_retry(cfg: dict[str, Any], key: tuple[str, str],
                     token_url: Any, client_id: Any,
                     client_secret: Any) -> str | None:
    """Mint a token, retrying a throttled endpoint. Called under the mint lock.

    Publishes every successful token to the shared cross-process cache so the
    other workers never issue their own grant.
    """
    # Retry with jittered backoff. The workers all restart together on a ship
    # and each materializes independently, so every mint for a given server is
    # issued in the same instant -- a thundering herd we create ourselves.
    # FortiSIEM's token endpoint answers that burst with 429 (and, in the
    # majority of cases observed, a bare 400): live, a sequential mint+list is
    # 10/10 while seven concurrent ones are 0-1/7. One mint failing used to cost
    # the whole server on that worker for the life of the process.
    import random

    last = ""
    for attempt in range(_OAUTH_ATTEMPTS):
        if attempt:
            # Full jitter -- a fixed backoff would just re-synchronize the herd.
            time.sleep(random.uniform(0, _OAUTH_BACKOFF_S * (2 ** (attempt - 1))))
        try:
            import httpx
            data = {"grant_type": cfg.get("grant_type", "client_credentials"),
                    "client_id": client_id, "client_secret": client_secret}
            if cfg.get("scope"):
                data["scope"] = cfg["scope"]
            r = httpx.post(str(token_url), data=data,
                           verify=bool(cfg.get("verify", False)), timeout=20)
            r.raise_for_status()
            body = r.json()
            token = body.get("access_token")
            if not token:
                log.warning("MCP oauth2: token response had no access_token")
                return None  # a well-formed refusal, not congestion -- don't retry
            # expires_in is seconds; default to a conservative 5 min if absent.
            ttl = float(body.get("expires_in", 300))
            exp = time.time() + ttl
            _OAUTH_CACHE[key] = (token, exp)
            _oauth_cache_write(key, token, exp)
            if attempt:
                log.info("MCP oauth2: token minted for %s on attempt %d",
                         token_url, attempt + 1)
            return token
        except Exception as exc:  # noqa: BLE001 - fail-soft, logged, never abort
            last = str(exc)
            log.debug("MCP oauth2: mint attempt %d/%d failed for %s: %s",
                      attempt + 1, _OAUTH_ATTEMPTS, token_url, exc)
    log.warning("MCP oauth2: token mint failed for %s after %d attempts: %s",
                token_url, _OAUTH_ATTEMPTS, last)
    return None


def _rule_wants_oauth2(rule: dict[str, Any]) -> bool:
    """True when the rule declares an oauth2 / client_credentials auth block --
    i.e. an empty header set means "the mint failed", not "public server"."""
    auth = rule.get("auth")
    if not isinstance(auth, dict):
        return False
    return isinstance(auth.get("oauth2") or auth.get("client_credentials"), dict)


def _auth_headers(rule: dict[str, Any]) -> dict[str, str]:
    """Build the HTTP headers for an EXTERNAL MCP server from its allowlist rule.

    Accepts the natural shorthands an operator would hand-write:

    - ``"auth": {"headers": {"X-Api-Key": "…"}}`` → sent verbatim
    - ``"auth": {"bearer": "<token>"}``          → ``Authorization: Bearer <token>``
    - ``"auth": {"api_key": "<key>"}``           → ``Authorization: API-KEY <key>``
      (FortiSOAR convention; override the scheme with ``"header"`` if the server
      wants a different one, e.g. ``{"api_key": "k", "header": "X-Api-Key"}``)
    - no ``auth`` / empty → ``{}`` (a public / unauthenticated server)

    Kept permissive on purpose: a malformed auth block yields ``{}`` and the
    server simply fails to list (logged upstream), never aborts the rest.
    """
    auth = rule.get("auth")
    if not isinstance(auth, dict):
        return {}
    headers = auth.get("headers")
    if isinstance(headers, dict):
        return {str(k): str(v) for k, v in headers.items()}
    # OAuth2 client_credentials: mint + cache + auto-refresh a bearer so a
    # short-lived token (e.g. FortiSIEM's) never goes stale mid-session. Placed
    # before the static ``bearer`` branch so an oauth2 rule wins.
    oauth2 = auth.get("oauth2") or auth.get("client_credentials")
    if isinstance(oauth2, dict):
        tok = _oauth2_bearer(oauth2)
        return {"Authorization": f"Bearer {tok}"} if tok else {}
    bearer = auth.get("bearer")
    if bearer:
        return {"Authorization": f"Bearer {bearer}"}
    api_key = auth.get("api_key")
    if api_key:
        header_name = auth.get("header")
        if header_name:
            return {str(header_name): str(api_key)}
        return {"Authorization": f"API-KEY {api_key}"}
    return {}


_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


def _make_name(server: str, tool_name: str) -> str:
    """Materialized tool name: ``mcp_<server_slug>__<tool_name>``. Server slug
    keeps it identifier-safe + unique across servers (two servers can share a
    tool_name; the prefix disambiguates)."""
    slug = _SLUG_RE.sub("_", server).strip("_").lower() or "srv"
    return f"mcp_{slug}__{tool_name}"


_CONNECTOR_PREFIX = "connector:"

# The connector whose `call_mcp_tool` op replays a materialized MCP tool from a
# playbook step. A built-in server's tool compiles to a step against this.
SOC_ASSISTANT_CONNECTOR = "connector-fsr-soc-assistant"

# Materialized built-in tools dropped from the trace because they're mutating and
# `call_mcp_tool` can't invoke them. Surfaced on the compile result so the omission
# is visible rather than silent.
_DROPPED_MUTATING: list[str] = []


def _titleize(tool_name: str) -> str:
    """`get_alert` -> `Get Alert`. Gives the compiled step a readable name instead
    of the wire name, matching what `record_run_op` does for a connector op."""
    return " ".join(p.capitalize() for p in re.split(r"[^a-zA-Z0-9]+", tool_name) if p)


def _is_mutating(materialized_name: str) -> bool:
    """True when the materialized tool is tier-3 (approval-gated)."""
    try:
        from ..llm.tools import TOOL_TIERS
        return int(TOOL_TIERS.get(materialized_name, 1) or 1) >= 3
    except Exception:  # noqa: BLE001
        return False


def _note_dropped_mutating(name: str) -> None:
    if name not in _DROPPED_MUTATING:
        _DROPPED_MUTATING.append(name)


def dropped_mutating_mcp() -> list[str]:
    """Mutating built-in MCP tools this session called that could NOT be compiled
    into a playbook step. The caller surfaces these as a gap."""
    return list(_DROPPED_MUTATING)


def connector_of(server: str) -> str | None:
    """The installed-connector name behind a Power-2 server (``"connector:<name>"``
    → ``"<name>"``), else None for a built-in server (``"soc"``, ``"utility"``, …).

    A Power-2 MCP tool IS a connector action: the server carries the connector and
    the tool name is the operation. That 1:1 is what lets a native-MCP call compile
    to a DIRECT connector step rather than a generic run-a-tool step."""
    if not isinstance(server, str) or not server.startswith(_CONNECTOR_PREFIX):
        return None
    return server[len(_CONNECTOR_PREFIX):].strip() or None


def _record_connector_trace(server: str, tool_name: str,
                            args: dict[str, Any], env: Any) -> None:
    """Record a Power-2 MCP call on the active skill trace as a
    ``run_connector_action`` -- the same SkillCall shape ``run_op`` records -- so
    a native-MCP investigation compiles to the same direct connector steps as a
    ``run_op`` one. Before this, every MCP call was invisible to the trace and a
    trace-built playbook silently omitted exactly those steps.

    Mirrors ``run_op``'s recording contract: unwrap a ``data`` envelope and set
    ``ref_prefix`` accordingly, so value-match wiring sees the shape a runtime
    ``vars.steps.<name>.*`` reference will actually resolve against.

    Best-effort and no-op'd unless a session wrapper installed an active trace --
    a recorder must never break a live tool call.

    The native gateway resolves the connector configuration server-side and never
    tells the caller which one ran, so we record ``config=""`` -- unlike ``run_op``,
    which pins the id it resolved. That is fine for ``config``: the compiler fills
    a config-less connector step with the connector's default from the warmed
    catalog (``resolver/connector_args.py`` ``_resolve_connector_args``), offline.

    KNOWN GAP -- the ``agent`` binding has no such fallback. ``run_op`` records the
    agent id when it routes through one; an MCP call cannot know it, and nothing
    downstream supplies a default. So an AGENT-BOUND connector reached over native
    MCP compiles to a step with no agent binding, which the workflow engine can't
    route. Unverified against a box: it may be that the catalog's default config
    for an agent-bound connector is already the agent config, making this moot.

    A BUILT-IN server's tool (``soc``, ``utility``, …) has no connector of its own,
    but it is still replayable from a playbook: the SOC-assistant connector's
    ``call_mcp_tool`` op invokes any materialized tool by name. So those record as a
    connector step against that op rather than being dropped -- one uniform compile
    target for every MCP call, and no new skill or step type.

    A MUTATING (tier-3) built-in tool is NOT recorded: ``call_mcp_tool`` bypasses the
    approval-card machinery and the connector deliberately refuses to expose tier-3
    tools to it, so such a step would fail at runtime with ``unknown_tool``. It is
    dropped rather than compiled broken -- see ``dropped_mutating_mcp`` on the
    compile result, which surfaces it instead of losing it silently."""
    try:
        from fsr_playbooks.agent.skill_trace import record_run_op as _record
        data = env.get("data", env) if isinstance(env, dict) else env
        prefix = "data" if (isinstance(env, dict) and "data" in env) else ""

        name = connector_of(server)
        if name:
            # Power-2: the server IS the connector -> a DIRECT connector step.
            _record(name, tool_name, args, data, ref_prefix=prefix)
            return

        # Built-in: replay through the SOC-assistant connector's call_mcp_tool.
        materialized = _make_name(server, tool_name)
        if _is_mutating(materialized):
            _note_dropped_mutating(materialized)
            return
        _record(
            SOC_ASSISTANT_CONNECTOR, "call_mcp_tool",
            {"tool": materialized, "args": dict(args or {})},
            data, step_name=_titleize(tool_name), ref_prefix=prefix,
        )
    except Exception:
        pass


def _make_fn(
    client: Any,
    server: str,
    tool_name: str,
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    verify: Any = None,
    rule: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """Closure the LLM dispatches against. ``dispatch`` calls ``fn(**raw_args)``
    with the LLM's tool-use args; we forward them as the MCP ``arguments``
    dict. Each call opens a fresh MCP session (connect, initialize, call,
    disconnect) -- simple + safe; the client re-auths once on a 401/403.

    When ``url`` is set the tool lives on an EXTERNAL server: route through
    ``call_tool_at`` with the rule's own headers (the external server owns its
    credential). Headers are recomputed from ``rule`` at CALL time (falling back
    to the build-time ``headers``) so an auto-refreshing oauth2 bearer is never
    stale for a long-lived worker -- the cache in ``_oauth2_bearer`` makes the
    common (unexpired) case a dict rebuild, not a network round-trip."""
    def fn(**kwargs: Any) -> Any:
        if url:
            call_headers = _auth_headers(rule) if rule is not None else (headers or {})
            raw = client.mcp.call_tool_at(
                url, call_headers, tool_name,
                arguments=kwargs or None, verify=verify)
            return _envelope(raw)
        raw = client.mcp.call_tool(server, tool_name, arguments=kwargs or None)
        env = _envelope(raw)
        # On-box Power-2 calls only: an EXTERNAL server is not an installed
        # connector, so it has no direct connector step to compile to even if an
        # operator named its rule "connector:…".
        _record_connector_trace(server, tool_name, kwargs, env)
        return env
    fn.__name__ = _make_name(server, tool_name)
    return fn


def _envelope(raw: Any) -> Any:
    """Normalize an MCP tool result to the dispatch tool-output contract (a dict
    envelope, or a list of dict envelopes). FortiSOAR's native servers return
    parsed JSON dicts, but an arbitrary EXTERNAL MCP tool may return a bare
    string/number/None (its content block was plain text) -- which trips the
    fail-open "must be a dict envelope" warning. Wrap those in ``{"result": …}``
    so the LLM sees a clean, consistent shape. Dicts and lists-of-dicts pass
    through untouched."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        return raw
    return {"result": raw}
