"""Dynamic tool surface — materialize FortiSOAR 8.0 native-MCP-gateway tools as
first-class ``ToolSpec``\\ s in the LLM :data:`~fsr_playbooks.llm.tools.REGISTRY`.

The widget-drawer triage agent's tool surface was static and hand-curated (one
Python wrapper per op in ``tools_noc.py`` / ``tools_triage.py``). This module
replaces that model: at session start it asks the platform's **native MCP
gateway** (``client.mcp`` — ``/mcp/*``, shipped FortiSOAR 8.0.0+) which tools
exist on the servers the operator allow-listed, and materializes each as a
``ToolSpec`` whose ``fn`` routes back through ``client.mcp.call_tool``. The
agent's tool surface *is* the configured-capability surface — an unconfigured
connector's tool simply isn't registered, so the agent can't call it (the
``unknown_connector`` thrash the 0.4.37 prompt rules policed becomes
structurally impossible, and those rules become transitional).

``server`` is one of the 4 built-ins (``"modules"``, ``"playbooks"``,
``"soc"``, ``"utility"``) or ``"connector:<name>"`` for an installed
connector's auto-generated MCP server — so registered-MCP-server tools (Power
1) *and* configured-connector-op tools (Power 2) flow through one substrate.

Discovery + execution both live on the live pyfsr ``FortiSOAR`` client
(``client.mcp.list_tools`` / ``client.mcp.call_tool``); this consumer adds no
new transport. The on-box worker reaches ``/mcp/*`` via the env-creds client
(``EnvConfig.from_env().client()``), not the crudhub loopback (crudhub speaks
Hydra REST, not MCP streamable-HTTP). ``make mcp-bridge-check`` proves
reachability.

Safety model (mirrors the platform's ``memory.yaml`` allow-list — no
auto-discovery): the connector calls :func:`configure` with an explicit
per-server allow-list at session setup; default empty → nothing materialized →
no behavior change on upgrade. Each allow-list entry declares the server
read-only (→ tier 1, auto-run) or mutating (→ tier 3, approval card).

Phase-0 probe (``make mcp-bridge-check``) confirmed the substrate live on 8.0:
``list_tools`` returns ``[{"name", "description", "input_schema"}, ...]`` with
full JSON schemas — passed straight into ``ToolSpec``.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

log = logging.getLogger(__name__)

# Cap so a misconfigured allow-list can't flood the LLM tool list (the platform
# model gates per-server; this is a backstop). Logged when hit — no silent drop.
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
    omitted is preserved (merge, not replace) — so the connector's two-phase
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
    _allowlist = {}
    _client_factory = None
    _initialized = False


def ensure_initialized() -> None:
    """Lazy, idempotent materialization. Called from ``anthropic_tools`` /
    ``openai_tools`` so materialized tools appear in the LLM's tool list on the
    first turn. No-op if already initialized; never raises (a failure logs and
    leaves REGISTRY unchanged — the curated SAFE_TOOLS keep working)."""
    global _initialized
    if _initialized:
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
    materializer can be activated without a code-level ``configure()`` call —
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


def _initialize_impl() -> None:
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
        rule = _normalize_rule(raw_rule)
        if rule is None:
            continue  # server explicitly disabled (False / None / empty)
        tier_label = rule.get("tier", "read_only")
        tier = 3 if tier_label == "mutating" else 1
        allowed_tools = rule.get("tools", "*")
        try:
            tools = mcp.list_tools(server)
        except Exception as exc:  # noqa: BLE001 - one bad server shouldn't abort the rest
            log.warning("MCP materializer: list_tools(%r) failed: %s", server, exc)
            continue
        if not isinstance(tools, list):
            continue
        for tool in tools:
            # pyfsr's native client returns MCPTool pydantic models (dict-style
            # access via _Lenient), while the built-in servers / tests hand back
            # plain dicts. Accept either — a strict ``isinstance(tool, dict)``
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
                fn=_make_fn(client, server, tname),
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


_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


def _make_name(server: str, tool_name: str) -> str:
    """Materialized tool name: ``mcp_<server_slug>__<tool_name>``. Server slug
    keeps it identifier-safe + unique across servers (two servers can share a
    tool_name; the prefix disambiguates)."""
    slug = _SLUG_RE.sub("_", server).strip("_").lower() or "srv"
    return f"mcp_{slug}__{tool_name}"


def _make_fn(client: Any, server: str, tool_name: str) -> Callable[..., Any]:
    """Closure the LLM dispatches against. ``dispatch`` calls ``fn(**raw_args)``
    with the LLM's tool-use args; we forward them as the MCP ``arguments``
    dict. Each call opens a fresh MCP session (connect, initialize, call,
    disconnect) — simple + safe; the client re-auths once on a 401/403."""
    def fn(**kwargs: Any) -> Any:
        return client.mcp.call_tool(server, tool_name, arguments=kwargs or None)
    fn.__name__ = _make_name(server, tool_name)
    return fn
