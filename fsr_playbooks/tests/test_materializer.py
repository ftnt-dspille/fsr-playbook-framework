"""Dynamic tool-surface materializer — turns FortiSOAR 8.0 native-MCP-gateway
tools (``client.mcp.list_tools``) into first-class ``ToolSpec``\\ s in the LLM
REGISTRY. Regression for the design: an unconfigured connector's tool is NOT
registered (structural-impossibility — the ``unknown_connector`` thrash the
prompt rules policed can't happen), tier is wired into ``TOOL_TIERS`` (which
``_resolve_tier`` reads, not ``spec.tier``), and every failure path leaves
REGISTRY unchanged.
"""
import pytest

from fsr_playbooks.mcp_server import materializer as M
from fsr_playbooks.llm import tools as T


def _stub_client(tools_by_server, *, supports=True):
    """Build a stub pyfsr-like client whose ``.mcp.list_tools(server)`` returns
    ``tools_by_server[server]`` and ``.mcp.call_tool`` echoes the call."""
    class _MCP:
        def list_tools(self, server):
            return tools_by_server.get(server, [])
        def call_tool(self, server, name, arguments=None):
            return {"called": name, "server": server, "args": arguments}
    class _Client:
        def supports_native_mcp(self):
            return supports
        mcp = _MCP()
    return _Client()


SOC_TOOLS = [
    {"name": "get_alert", "description": "get an alert",
     "input_schema": {"type": "object", "properties": {"uuid": {"type": "array", "items": {"type": "string"}}}, "required": ["uuid"]}},
    {"name": "enrich_indicator", "description": "enrich an IOC",
     "input_schema": {"type": "object", "properties": {"indicator": {"type": "string"}}}},
]


@pytest.fixture(autouse=True)
def _clean():
    M.reset()
    yield
    M.reset()


def test_empty_allowlist_is_noop():
    """Default (nothing configured) → REGISTRY unchanged — safe upgrade."""
    before = set(T.REGISTRY)
    M.ensure_initialized()
    assert set(T.REGISTRY) == before
    assert not M.SERVER_MAP


def test_materializes_tools_and_schemas_passthrough():
    M.configure(mcp_allowlist={"soc": {"tools": "*", "tier": "read_only"}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    assert "mcp_soc__enrich_indicator" in T.REGISTRY
    spec = T.REGISTRY["mcp_soc__get_alert"]
    assert spec.input_schema["required"] == ["uuid"]   # schema passes straight through
    assert spec.description == "get an alert"


def test_tier_wired_into_tool_tiers_not_just_spec():
    """dispatch() uses _resolve_tier which reads TOOL_TIERS, not spec.tier —
    so the materializer MUST register the name in TOOL_TIERS for gating."""
    M.configure(mcp_allowlist={"soc": {"tools": "*", "tier": "read_only"}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert T.TOOL_TIERS["mcp_soc__get_alert"] == 1   # read-only → auto-run
    assert T.REGISTRY["mcp_soc__get_alert"].confirm_mode == "auto"


def test_mutating_tier_is_3_approval_card():
    M.configure(mcp_allowlist={"soc": {"tools": "*", "tier": "mutating"}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert T.TOOL_TIERS["mcp_soc__get_alert"] == 3   # mutating → approval card
    assert T.REGISTRY["mcp_soc__get_alert"].confirm_mode == "approve"


def test_fn_closure_routes_to_call_tool():
    M.configure(mcp_allowlist={"soc": {"tools": "*"}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    res = T.REGISTRY["mcp_soc__get_alert"].fn(uuid=["abc"])
    assert res == {"called": "get_alert", "server": "soc", "args": {"uuid": ["abc"]}}


def test_tool_filter_within_server():
    M.configure(mcp_allowlist={"soc": {"tools": ["get_alert"]}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    assert "mcp_soc__enrich_indicator" not in T.REGISTRY   # filtered out


def test_connector_server_slug_naming():
    """Power-2 path: configured connector ops live on 'connector:<name>'."""
    tools = [{"name": "lookup_ioc", "description": "ioc lookup",
              "input_schema": {"type": "object", "properties": {"ioc": {"type": "string"}}}}]
    M.configure(mcp_allowlist={"connector:fortinet-fortiguard-ioc": {"tools": "*"}},
                client_factory=lambda: _stub_client({"connector:fortinet-fortiguard-ioc": tools}))
    M.ensure_initialized()
    assert "mcp_connector_fortinet_fortiguard_ioc__lookup_ioc" in T.REGISTRY
    assert M.SERVER_MAP["mcp_connector_fortinet_fortiguard_ioc__lookup_ioc"] == \
        ("connector:fortinet-fortiguard-ioc", "lookup_ioc")


def test_fallback_supports_native_mcp_false():
    client = _stub_client({"soc": SOC_TOOLS}, supports=False)
    M.configure(mcp_allowlist={"soc": {"tools": "*"}}, client_factory=lambda: client)
    before = set(T.REGISTRY)
    M.ensure_initialized()
    assert set(T.REGISTRY) == before   # nothing materialized


def test_fallback_no_client():
    M.configure(mcp_allowlist={"soc": {"tools": "*"}}, client_factory=lambda: None)
    before = set(T.REGISTRY)
    M.ensure_initialized()
    assert set(T.REGISTRY) == before


def test_fallback_list_tools_raises():
    class _Boom:
        def list_tools(self, server): raise RuntimeError("network down")
        def call_tool(self, s, n, a=None): return {}
    class _C:
        def supports_native_mcp(self): return True
        mcp = _Boom()
    M.configure(mcp_allowlist={"soc": {"tools": "*"}}, client_factory=lambda: _C())
    before = set(T.REGISTRY)
    M.ensure_initialized()   # must not raise
    assert set(T.REGISTRY) == before


def test_anthropic_tools_lazy_init_hook():
    """anthropic_tools() must trigger materialization so tools appear on turn 1."""
    T.anthropic_tools()   # empty allowlist → no-op
    assert "mcp_soc__get_alert" not in T.REGISTRY
    M.configure(mcp_allowlist={"soc": {"tools": "*"}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    T.anthropic_tools()   # now materializes
    assert "mcp_soc__get_alert" in T.REGISTRY


def test_dispatch_unknown_materialized_tool_errors():
    r = T.dispatch("mcp_soc__nonexistent", {})
    assert "unknown tool" in r.get("error", "")


def test_reset_removes_materialized_tools():
    M.configure(mcp_allowlist={"soc": {"tools": "*"}},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    M.reset()
    assert "mcp_soc__get_alert" not in T.REGISTRY
    assert "mcp_soc__get_alert" not in T.TOOL_TIERS
    assert not M.SERVER_MAP


def test_rematerialize_is_idempotent_no_duplicates():
    """Re-configure + re-init (e.g. config reload) must not error or double up."""
    client = _stub_client({"soc": SOC_TOOLS})
    M.configure(mcp_allowlist={"soc": {"tools": "*"}}, client_factory=lambda: client)
    M.ensure_initialized()
    n1 = len(T.REGISTRY)
    assert "mcp_soc__get_alert" in T.REGISTRY
    # second configure (resets _initialized) + re-init
    M.configure(mcp_allowlist={"soc": {"tools": "*"}}, client_factory=lambda: client)
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    assert len(T.REGISTRY) == n1   # no duplication
    # fn still routes correctly after re-materialize
    assert T.REGISTRY["mcp_soc__get_alert"].fn(uuid=["x"]) == \
        {"called": "get_alert", "server": "soc", "args": {"uuid": ["x"]}}


def test_env_var_allowlist_fallback(monkeypatch):
    """FSRPB_MCP_ALLOWLIST (JSON) activates the materializer without a code-level
    configure() call — the operator sets it in the worker env."""
    import json
    monkeypatch.setenv("FSRPB_MCP_ALLOWLIST",
                       json.dumps({"soc": {"tools": "*", "tier": "read_only"}}))
    M.ensure_initialized()  # no configure() call — env var drives it
    # client_factory unset → _build_client() returns None (no EnvConfig) → dormant
    assert "mcp_soc__get_alert" not in T.REGISTRY
    # but the allowlist WAS loaded (proved by configuring a factory + re-running)
    M.reset()
    monkeypatch.setenv("FSRPB_MCP_ALLOWLIST",
                       json.dumps({"soc": {"tools": "*"}}))
    M.configure(client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY


def test_env_var_invalid_json_ignored(monkeypatch):
    monkeypatch.setenv("FSRPB_MCP_ALLOWLIST", "{not json")
    M.ensure_initialized()  # must not raise
    assert not M.SERVER_MAP


def test_two_phase_configure_preserves_client_factory():
    """The connector wires in two phases: ``register_mcp_materializer()``
    sets ``client_factory`` at import time, then ``_apply_mcp_allowlist(config)``
    sets ``mcp_allowlist`` per turn. The second ``configure()`` call MUST NOT
    clobber the factory set by the first — otherwise ensure_initialized builds
    the client from env (None on-box) and the materializer stays dormant even
    with the allowlist set. Regression for the config-field path going live."""
    M.configure(client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.configure(mcp_allowlist={"soc": {"tools": "*", "tier": "read_only"}})
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    assert "mcp_soc__enrich_indicator" in T.REGISTRY


# --- live-shape regressions (found box-proving against 8.0 box 159) ----------

class _MCPToolModel:
    """Mimics pyfsr's ``MCPTool`` pydantic model: attribute access + dict-style
    ``.get``/``in``/``[]`` (via ``_Lenient``), and ``input_schema`` exposed as a
    read-only property derived from the wire's ``inputSchema``. The materializer
    used to gate on ``isinstance(tool, dict)`` and silently skip every one of
    these — so the live gateway materialized zero tools."""
    def __init__(self, name, description=None, input_schema=None):
        self.name = name
        self.description = description
        self._schema = input_schema
    @property
    def input_schema(self):
        return self._schema
    def get(self, key, default=None):
        # _Lenient.get exposes model fields but NOT the input_schema property
        return {"name": self.name, "description": self.description}.get(key, default)
    def __contains__(self, key):
        return key in ("name", "description")
    def __getitem__(self, key):
        return {"name": self.name, "description": self.description}[key]


def test_materializes_pydantic_model_tools():
    """pyfsr's native client returns MCPTool models, not dicts — the materializer
    must read name/description/input_schema off the model. Regression: the live
    bridge registered 0 tools until this was fixed."""
    models = [
        _MCPToolModel("get_alert", "get an alert",
                      {"type": "object", "properties": {"uuid": {"type": "string"}}, "required": ["uuid"]}),
        _MCPToolModel("enrich_indicator", "enrich an IOC",
                      {"type": "object", "properties": {"indicator": {"type": "string"}}}),
    ]
    M.configure(mcp_allowlist={"soc": {"tools": "*", "tier": "read_only"}},
                client_factory=lambda: _stub_client({"soc": models}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    spec = T.REGISTRY["mcp_soc__get_alert"]
    assert spec.description == "get an alert"
    assert spec.input_schema["required"] == ["uuid"]   # read off the property, not .get


@pytest.mark.parametrize("rule, should_register", [
    (True, True),            # {"soc": true} → all tools, read-only
    ("*", True),             # {"soc": "*"}
    ("read_only", True),     # {"soc": "read_only"}
    ("all", True),           # {"soc": "all"}
    (False, False),          # explicitly disabled
    (None, False),           # explicitly disabled
    ("", False),             # empty
])
def test_shorthand_allowlist_rules(rule, should_register):
    """Admins write the allowlist by hand — a bare ``true``/``"*"`` used to raise
    ``'bool' object has no attribute 'get'`` and silently disable ALL
    materialization. Each shorthand now normalizes; falsey values skip the server."""
    M.configure(mcp_allowlist={"soc": rule},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert ("mcp_soc__get_alert" in T.REGISTRY) is should_register


def test_shorthand_mutating_rule_is_tier_3():
    M.configure(mcp_allowlist={"soc": "mutating"},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert T.TOOL_TIERS["mcp_soc__get_alert"] == 3


def test_shorthand_list_rule_filters_tools():
    """A bare list value → tool-name allowlist (read-only)."""
    M.configure(mcp_allowlist={"soc": ["get_alert"]},
                client_factory=lambda: _stub_client({"soc": SOC_TOOLS}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    assert "mcp_soc__enrich_indicator" not in T.REGISTRY


def test_bad_rule_does_not_abort_other_servers():
    """One malformed rule must not take down materialization for other servers."""
    M.configure(mcp_allowlist={"soc": True, "utility": {"tools": "*"}},
                client_factory=lambda: _stub_client(
                    {"soc": SOC_TOOLS, "utility": [{"name": "now", "description": "clock"}]}))
    M.ensure_initialized()
    assert "mcp_soc__get_alert" in T.REGISTRY
    assert "mcp_utility__now" in T.REGISTRY
