"""Every record/hunt/playbook-run tool ERROR envelope speaks `code` + `message`.

Moved here with the tools from the SOC assistant connector, whose
`tests/test_tool_envelope_vocabulary.py` asserts the same over the tools it
still owns. A source scan on purpose: these tools mostly fail against a live
appliance, so their error paths are exactly the ones a unit suite does not
reach, and a dropped key would otherwise ship unnoticed.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

MCP = Path(__file__).resolve().parent.parent / "mcp_server"
MODULES = ("tools_triage.py", "tools_noc.py", "tools_edr.py", "_record_lookup.py",
           "tools_playbook_run.py")
REQUIRED = {"code", "message"}


def _error_envelopes():
    """Every `return {"ok": False, ...}` dict literal in the moved modules."""
    found = []
    for name in MODULES:
        tree = ast.parse((MCP / name).read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)):
                continue
            pairs = list(zip(node.value.keys, node.value.values))
            if any(isinstance(k, ast.Constant) and k.value == "ok"
                   and isinstance(v, ast.Constant) and v.value is False
                   for k, v in pairs):
                keys = {k.value for k, _ in pairs
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                found.append((f"{name}:{node.lineno}", keys))
    return found


ENVELOPES = _error_envelopes()


def test_the_scan_found_envelopes():
    """A walker that silently matches nothing makes the whole file vacuous."""
    assert len(ENVELOPES) > 20, f"only found {len(ENVELOPES)}"


@pytest.mark.parametrize("where,keys", ENVELOPES, ids=[e[0] for e in ENVELOPES])
def test_error_envelope_declares_code_and_message(where, keys):
    missing = REQUIRED - keys
    assert not missing, (
        f"{where} returns an error envelope without {sorted(missing)}. The "
        f"agent branches on `code` and reads `message`; an envelope missing "
        f"either leaves it re-parsing prose. Use `llm.tool_result.tool_err()`.")
