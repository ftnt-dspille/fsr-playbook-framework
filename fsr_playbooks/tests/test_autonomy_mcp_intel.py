"""A declared MCP intel lookup can be the autonomy policy's evidence (S12).

`_intel_lookup` accepted only run_op, so an MCP lookup that rated a C2 address
malicious could never satisfy a rule's evidence check. The host now declares
which MCP tools are intel lookups for the turn; nothing is guessed by name.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm import autonomy
from fsr_playbooks.llm.tools import TOOL_TIERS
from fsr_playbooks.mcp_server import _citation_validator as cv
from fsr_playbooks.mcp_server import materializer

REP = "mcp_fortisiem__get_reputation_by_entity"


@pytest.fixture
def declared():
    TOOL_TIERS[REP] = 1
    tok = materializer.set_turn_intel_mcp_tools({REP: "fortisiem"})
    yield
    materializer._TURN_INTEL_MCP_TOOLS.reset(tok)
    TOOL_TIERS.pop(REP, None)


def test_a_declared_mcp_lookup_is_intel(declared):
    assert autonomy._intel_lookup({"name": REP, "args": {}})


def test_an_undeclared_mcp_lookup_is_not():
    TOOL_TIERS[REP] = 1
    try:
        assert not autonomy._intel_lookup({"name": REP, "args": {}})
    finally:
        TOOL_TIERS.pop(REP, None)


def test_a_declared_mcp_write_is_not_intel(declared):
    TOOL_TIERS[REP] = 3  # gated: not a read
    assert not autonomy._intel_lookup({"name": REP, "args": {}})


def test_read_finding_hands_a_declared_mcp_result_to_the_reader(declared, monkeypatch):
    seen = {}

    def reader(connector, op, params, result):
        seen.update(connector=connector, op=op, params=params, result=result)
        return {"source": "FortiSIEM", "severity": "error", "verdict": "malicious"}

    monkeypatch.setattr(cv, "_RESULT_READER", reader)
    args = {"params": {"ip": ["198.51.100.77"]}}
    got = cv.read_finding(REP, args, [{"ip": "198.51.100.77"}])
    assert got == {"source": "FortiSIEM", "severity": "error", "verdict": "malicious"}
    assert seen == {"connector": "mcp:fortisiem", "op": "get_reputation_by_entity",
                    "params": args, "result": {"ok": True, "data": [{"ip": "198.51.100.77"}]}}
    assert cv.read_finding("mcp_fortisiem__get_incidents_by_entity", args, []) is None
