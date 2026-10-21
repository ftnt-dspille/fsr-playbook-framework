"""The record and hunt tools, as the library itself now serves them.

They moved here from the SOC assistant connector. Three things only worked, or
only looked right, while the connector supplied them:

  * the MCP server listed `_relationship_fields` and `_mounted_siem_context` as
    tools and left `search_module_records` off -- two `@mcp.tool()` decorators
    sat one function too early, hidden because the agent registry registered by
    name;
  * `assert_playbook_outcome` imported a `tools_triage` the library did not
    have, so every call answered `no_investigation_tools`;
  * `render_jinja(from_pb_execution=...)` imported `get_run_env` from that
    same missing module (it lives in tools_connector_discovery), so it always
    refused.
"""
from __future__ import annotations

import sys
import types

from fsr_playbooks.llm.hunt_tools import HUNT_RETIRED_TO_UNION, HUNT_TOOLS
from fsr_playbooks.mcp_server import _shared


def _mcp_tool_names() -> set[str]:
    tm = getattr(_shared.mcp, "_tool_manager", None)
    return set(getattr(tm, "_tools", {}) or {})


def test_the_mcp_server_lists_every_hunt_tool_and_no_private_helper():
    names = _mcp_tool_names()
    assert set(HUNT_TOOLS) <= names, sorted(set(HUNT_TOOLS) - names)
    assert not [n for n in names if n.startswith("_")], sorted(
        n for n in names if n.startswith("_"))
    # Retired helpers stay callable (saved playbooks) but are not offered to an
    # outside agent as tools.
    assert not set(HUNT_RETIRED_TO_UNION) & names


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_assert_playbook_outcome_runs_its_assertions(monkeypatch):
    from fsr_playbooks.mcp_server import tools_recipe

    client = types.SimpleNamespace(base_url="https://fortisoar.example.com")
    monkeypatch.setattr(_shared, "_live_client", lambda: client)
    monkeypatch.setattr(_shared, "live_post_with_reauth",
                        lambda c, url, **kw: _Resp({"hydra:totalItems": 2,
                                                    "hydra:member": [{}, {}]}))
    from fsr_playbooks.mcp_server import tools_triage
    monkeypatch.setattr(tools_triage, "_post_with_reauth", _shared.live_post_with_reauth)

    out = tools_recipe.assert_playbook_outcome(
        [{"kind": "record_exists", "module": "alerts", "filters": {"name": "x"}}])
    assert out.get("code") != "no_investigation_tools", out
    assert out["ok"] is True and out["passed"] == 1, out
    assert out["results"][0]["observed_count"] == 2


def test_render_jinja_from_a_run_reads_that_runs_context(monkeypatch):
    from fsr_playbooks.mcp_server import tools_connector_discovery, tools_jinja

    posted = {}

    class _Client:
        def post(self, endpoint, data):
            posted.update(data)
            return {"result": "ok"}

    env = types.ModuleType("probes._env")
    env.get_client = lambda: _Client()
    monkeypatch.setitem(sys.modules, "probes", types.ModuleType("probes"))
    monkeypatch.setitem(sys.modules, "probes._env", env)
    monkeypatch.setattr(tools_connector_discovery, "get_run_env",
                        lambda pk: {"vars": {"input": {"ip": "203.0.113.9"}}})

    out = tools_jinja.render_jinja("{{ vars.input.ip }}", from_pb_execution="676747")
    assert "error" not in out, out
    assert posted["values"] == {"vars": {"input": {"ip": "203.0.113.9"}}}
