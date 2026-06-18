"""Frozen public-surface contract (REORG_PLAN Phase 0).

The FortiSOAR SOC connector (`connector-fsr-soc-assistant`) imports ~50 deep
paths into this library. REORG_PLAN names these "surface A" — the authoring /
runtime code that STAYS in `fsr_playbooks` and must remain importable at stable
paths through every later refactor phase.

This test is the safety net that makes those later internal file moves
non-breaking: if a move (Phase 2+) or a careless edit drops one of these paths
or symbols, this test goes red *in the library suite* before the connector ever
sees the break.

It intentionally does NOT assert the surface-B triage/execution modules
(`llm.triage_*`, `mcp_server.tools_{execution,agent,triage,noc}`,
`_live_crudhub`) — those carve out to the connector in Phase 1, so pinning them
here would fight that move. See REORG_PLAN section 0 for the A/B split.
"""
from __future__ import annotations

import importlib

import pytest

# Surface-A module paths the connector imports. Each must stay importable.
SURFACE_A_MODULES = [
    "fsr_playbooks",
    # compiler — the authoring core (no LLM, no transport)
    "fsr_playbooks.compiler",
    "fsr_playbooks.compiler.typed_walker",
    "fsr_playbooks.compiler.parser",
    "fsr_playbooks.compiler.validator",
    "fsr_playbooks.compiler.resolver",
    "fsr_playbooks.compiler.ir",
    "fsr_playbooks.compiler.render_paths",
    "fsr_playbooks.compiler.render_analyzer",
    "fsr_playbooks.compiler.mi_output_catalog",
    "fsr_playbooks.compiler.samples",
    "fsr_playbooks.compiler.errors",
    "fsr_playbooks.compiler.decompiler",
    "fsr_playbooks.compiler.skill_compiler",
    "fsr_playbooks.compiler.skill_verify",
    # llm — generic runtime + build-agent assist (NOT triage_*)
    "fsr_playbooks.llm",
    "fsr_playbooks.llm.provider",
    "fsr_playbooks.llm.run_turn",
    "fsr_playbooks.llm.intents",
    "fsr_playbooks.llm.approvals",
    "fsr_playbooks.llm.anthropic_provider",
    "fsr_playbooks.llm.tools",
    "fsr_playbooks.llm.usage_log",
    "fsr_playbooks.llm.fake_provider",
    "fsr_playbooks.llm._loop_helpers",
    # agent + protocols
    "fsr_playbooks.agent",
    "fsr_playbooks.agent.skill_trace",
    "fsr_playbooks.protocols",
    # mcp_server — authoring delivery only
    "fsr_playbooks.mcp_server",
    "fsr_playbooks.mcp_server.tools_compile",
    "fsr_playbooks.mcp_server._shared",
    "fsr_playbooks.mcp_server._sim_fixtures",
    "fsr_playbooks.mcp_server._sim_client",
    "fsr_playbooks.mcp_server.tools_discovery",
    # execution facade — the stable run/healthcheck surface the carved-out
    # triage cluster imports (RECONCILIATION_PLAN Phase 1, D4=(a))
    "fsr_playbooks.execution_api",
]

# Surface-A symbols that must resolve at their named path (module, attr).
SURFACE_A_SYMBOLS = [
    ("fsr_playbooks.compiler", "compile_yaml"),
    ("fsr_playbooks.compiler", "parse_yaml"),
    ("fsr_playbooks.compiler", "validate"),
    ("fsr_playbooks.compiler", "Resolver"),
    ("fsr_playbooks.compiler", "Collection"),
    ("fsr_playbooks.compiler", "Playbook"),
    ("fsr_playbooks.compiler", "Step"),
    ("fsr_playbooks.compiler.parser", "_slugify"),
    ("fsr_playbooks.llm.provider", "Message"),
    ("fsr_playbooks.llm.provider", "UsageEvent"),
    ("fsr_playbooks.llm.run_turn", "run_agent_turn"),
    ("fsr_playbooks.llm.tools", "anthropic_tools"),
    ("fsr_playbooks.mcp_server.tools_compile", "build_playbook_from_trace"),
    # execution_api facade names (the frozen run/exec contract for triage)
    ("fsr_playbooks.execution_api", "VERIF_RANK"),
    ("fsr_playbooks.execution_api", "capability_gap_suggestion"),
    ("fsr_playbooks.execution_api", "open_reference_db"),
    ("fsr_playbooks.execution_api", "live_client"),
    ("fsr_playbooks.execution_api", "query_rows"),
    ("fsr_playbooks.execution_api", "agent_configured_rows"),
    ("fsr_playbooks.execution_api", "cached_health"),
    ("fsr_playbooks.execution_api", "fetch_runs"),
    ("fsr_playbooks.execution_api", "live_healthcheck"),
    ("fsr_playbooks.execution_api", "shape_run"),
    ("fsr_playbooks.execution_api", "store_health"),
    ("fsr_playbooks.execution_api", "run_op"),
    ("fsr_playbooks.execution_api", "tier_for_run_op"),
    ("fsr_playbooks.execution_api", "mute_recording"),
]


@pytest.mark.parametrize("modpath", SURFACE_A_MODULES)
def test_surface_a_module_importable(modpath):
    importlib.import_module(modpath)


@pytest.mark.parametrize("modpath,attr", SURFACE_A_SYMBOLS)
def test_surface_a_symbol_present(modpath, attr):
    mod = importlib.import_module(modpath)
    assert hasattr(mod, attr), f"{modpath}.{attr} missing from frozen surface A"


def test_openai_provider_path_resolves_when_dep_present():
    """`openai_provider` is surface A but kept lazy (optional `openai` dep).

    When `openai` is installed the module must import; when it isn't, the path
    is allowed to raise ImportError on the dep only — never vanish structurally.
    """
    pytest.importorskip("openai")
    importlib.import_module("fsr_playbooks.llm.openai_provider")
